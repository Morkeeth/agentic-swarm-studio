"""Durable USD 2 account on one Cloud Storage object (compare-and-swap).
No GCP and no Token Factory: MemoryStore copies the generation and 412 rules; a fake client counts calls."""
import io
import json
import threading
import time
import urllib.error
import urllib.parse
import pytest
from sim import route_a_account as ra
from sim.first_users_route_a import RouteASummary
from sim.first_users_nebius import MODEL
from sim.adapters.openai_compat import ChatReply


class Fake:
    def __init__(self): self.calls = []
    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        return ChatReply('Fix the guide link, then check it again.', MODEL, 'RUNTIME', {'prompt_tokens': 180, 'completion_tokens': 40}, 'stop')


@pytest.fixture(autouse=True)
def forbid_external(monkeypatch):
    monkeypatch.setattr('sim.first_users_nebius.tokenfactory.load_key', lambda: pytest.fail('No real key use'))
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: pytest.fail('No external calls'))


REPORT = {'contract': {'intent': 'read', 'required_moves': ['went_somewhere']},
          'checks': [{'label': 'First link opens', 'status': 'failed'}]}


def bucket(prior=0):
    state = ra.initial_state()
    state['attempts'] = {f'prior-{i}': {'reserve': 5000, 'status': 'returned'} for i in range(prior)}
    return ra.MemoryStore(json.dumps(state))


class SlowRead(ra.MemoryStore):
    """Widens the gap between read and write, so instances really race."""
    races = 0
    def read(self):
        out = super().read(); time.sleep(0.002); return out
    def write(self, text, generation):
        try: return super().write(text, generation)
        except ra.PreconditionFailed: self.races += 1; raise


def test_two_concurrent_instances_cannot_exceed_usd_2():
    store = SlowRead(json.dumps({**ra.initial_state(), 'attempts': {f'p{i}': {'reserve': 5000, 'status': 'returned'} for i in range(396)}}))
    instances = [ra.CasAccount(store, tries=200), ra.CasAccount(store, tries=200)]  # two Cloud Run instances
    ok, refused, start = [], [], threading.Barrier(8)
    def run(n):
        start.wait()
        try: instances[n % 2].reserve(f'job-{n}'); ok.append(n)
        except ra.AccountError: refused.append(n)
    threads = [threading.Thread(target=run, args=(n,)) for n in range(8)]
    [t.start() for t in threads]; [t.join() for t in threads]
    state = json.loads(store.text)
    assert len(ok) == 4 and len(refused) == 4  # 396 + 4 = 400 x USD 0.005 = USD 2.00
    assert len(state['attempts']) == 400 and ra.CasAccount(store).spent() == ra.HARD_CAP_MICROUSD
    assert {f'job-{n}' for n in ok} <= set(state['attempts'])
    assert store.races > 0  # the instances did collide, and the precondition caught it


def test_restart_keeps_spend_and_records_actual_usage():
    store = bucket()
    first = RouteASummary('gs://unused/x', client=Fake(), account=ra.CasAccount(store))
    for n in range(3): first.explain(f'before-{n}', REPORT)
    restarted_client = Fake()
    after = RouteASummary('gs://unused/x', client=restarted_client, account=ra.CasAccount(store))  # new process, same object
    assert after.account.spent() == 15000
    after.explain('after-restart', REPORT)
    state = json.loads(store.text)
    assert after.account.spent() == 20000 and len(restarted_client.calls) == 1
    # 180 x 0.06 + 40 x 0.24 = 20.4 micro-USD, rounded up; the 5,000 reservation still counts.
    assert state['attempts']['after-restart'] == {'reserve': 5000, 'status': 'returned', 'actual_microusd': 21}


def test_cap_reached_after_restart_means_no_call():
    store, client = bucket(prior=400), Fake()
    with pytest.raises(ValueError, match='exhausted'):
        RouteASummary('gs://unused/x', client=client, account=ra.CasAccount(store)).explain('new', REPORT)
    assert client.calls == []


class AlwaysRaced(ra.MemoryStore):
    def write(self, text, generation):
        self.writes += 1; raise ra.PreconditionFailed()


class RacedOnce(ra.MemoryStore):
    def write(self, text, generation):
        if not self.writes:
            self.writes += 1; self.generation += 1  # another instance wrote first
            raise ra.PreconditionFailed()
        return super().write(text, generation)


def test_lost_race_retries_then_fails_closed():
    store, client = AlwaysRaced(json.dumps(ra.initial_state())), Fake()
    with pytest.raises(ValueError, match='busy'):
        RouteASummary('gs://unused/x', client=client, account=ra.CasAccount(store)).explain('job', REPORT)
    assert client.calls == [] and store.writes == ra.MAX_CAS_TRIES
    store, client = RacedOnce(json.dumps(ra.initial_state())), Fake()
    RouteASummary('gs://unused/x', client=client, account=ra.CasAccount(store)).explain('job', REPORT)
    assert len(client.calls) == 1 and store.writes >= 2


@pytest.mark.parametrize('damage', ['missing', 'garbage', 'wrong_cap', 'bad_attempt', 'read_error'])
def test_unreadable_account_means_no_call(damage):
    good = ra.initial_state()
    texts = {'missing': None, 'garbage': 'not json', 'wrong_cap': json.dumps({**good, 'policy': {**good['policy'], 'cap': 9_000_000}}),
             'bad_attempt': json.dumps({**good, 'attempts': {'x': {'reserve': 0, 'status': 'reserved'}}}), 'read_error': json.dumps(good)}
    store, client = ra.MemoryStore(texts[damage]), Fake()
    if damage == 'read_error':
        summary = RouteASummary('gs://unused/x', client=client, account=ra.CasAccount(store))  # boot was fine
        store.read = lambda: (_ for _ in ()).throw(OSError('network'))  # then the store fails
        with pytest.raises(ValueError, match='unreadable'): summary.explain('job', REPORT)
    else:
        with pytest.raises(ValueError): RouteASummary('gs://unused/x', client=client, account=ra.CasAccount(store))
    assert client.calls == []


class Resp(io.BytesIO):
    def __init__(self, body, headers=None): super().__init__(body); self.headers = headers or {}
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_gcs_store_sends_the_generation_precondition_and_maps_412():
    seen = []
    def opener(req, timeout):
        seen.append(req)
        if 'metadata.google.internal' in req.full_url: return Resp(b'{"access_token":"t"}')
        if req.get_method() == 'GET': return Resp(b'{}', {'x-goog-generation': '7'})
        raise urllib.error.HTTPError(req.full_url, 412, 'Precondition Failed', {}, None)
    store = ra.GcsStore('gs://hack-fleet-first-users-budget/route-a.json', opener=opener)
    assert store.read() == (7, '{}')
    with pytest.raises(ra.PreconditionFailed): store.write('{}', 7)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(seen[-1].full_url).query)
    assert query['ifGenerationMatch'] == ['7'] and query['name'] == ['route-a.json']
    assert seen[0].headers.get('Metadata-flavor') == 'Google'


def test_gcs_read_without_generation_fails_closed():
    def opener(req, timeout):
        return Resp(b'{"access_token":"t"}') if 'metadata' in req.full_url else Resp(b'{}', {})
    with pytest.raises(ValueError, match='unreadable'):
        ra.CasAccount(ra.GcsStore('gs://b/o', opener=opener)).load()
