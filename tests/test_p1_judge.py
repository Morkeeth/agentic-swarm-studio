"""P1: a Nano crowd and a Super VL judge share one spend ledger. No test here calls a provider."""
import json
from types import SimpleNamespace

import pytest

from sim import app_swarm, hosted_cost

JUDGE = hosted_cost.JUDGE_MODEL


class Reply(SimpleNamespace):
    pass


class Scripted:
    def __init__(self, texts, model=hosted_cost.MODEL, answer_as=None):
        self.texts = list(texts); self.model = model; self.answer_as = answer_as or model; self.seen = []

    def chat(self, messages, **kwargs):
        self.seen.append(messages)
        return Reply(text=self.texts.pop(0), model=self.answer_as, usage={'prompt_tokens': 1000, 'completion_tokens': 40}, finish_reason='stop')


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setenv('TOKEN_FACTORY_API_KEY', 'test-value-never-sent')
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: pytest.fail('No external calls'))


@pytest.fixture
def account(tmp_path, monkeypatch):
    prior = tmp_path / 'prior.json'; prior.write_text(json.dumps({'runs': []}))
    record = tmp_path / 'cost.json'
    monkeypatch.setattr(hosted_cost, 'PRIOR', prior); monkeypatch.setattr(hosted_cost, 'RECORD', record)
    return record


@pytest.fixture
def judge_on(monkeypatch):
    monkeypatch.setenv(hosted_cost.JUDGE_MODEL_ENV, JUDGE)


def test_without_a_judge_id_nothing_changes(monkeypatch):
    monkeypatch.delenv(hosted_cost.JUDGE_MODEL_ENV, raising=False)
    assert hosted_cost.judge_model() is None
    assert hosted_cost.worst_case(1) == hosted_cost.worst_case(1, hosted_cost.MODEL)
    with pytest.raises(ValueError, match='priced only'):
        hosted_cost.projected(1, JUDGE)


def test_the_judge_is_priced_at_super_vl_rates(judge_on):
    nano, judge = hosted_cost.worst_case(1), hosted_cost.worst_case(1, JUDGE)
    assert hosted_cost.rates(JUDGE)['input'] == hosted_cost.SUPER_VL['input'] and judge != nano
    with pytest.raises(ValueError, match='priced only'):
        hosted_cost.projected(1, 'nvidia/some-other-model')


def test_the_judge_id_is_the_verified_one_and_no_other(monkeypatch):
    assert hosted_cost.JUDGE_MODEL == 'nvidia/Nemotron-3.5-Super-VL' and hosted_cost.SUPER_VL['id_verified'] is True
    monkeypatch.setenv(hosted_cost.JUDGE_MODEL_ENV, 'nvidia/nemotron-3-super-120b-a12b')      # listed, but text only
    with pytest.raises(ValueError, match='registered'):
        hosted_cost.judge_model()


def test_five_judges_in_flight_fit_one_run_cap(judge_on):
    # Each visitor runs in its own thread, so up to five calls are reserved at once.
    assert len(app_swarm.CAST) * hosted_cost.worst_case(1, JUDGE) <= app_swarm.RUN_CAP_USD


def test_crowd_and_judge_settle_on_one_ledger_at_their_own_rates(account, judge_on):
    budget = app_swarm.Budget('run-p1', max_calls=4)
    crowd = Scripted(['{"action":"scroll"}']); judge = Scripted(['{"done":false}'], model=JUDGE)
    budget.call(crowd, [{'role': 'user', 'content': 'x'}], 'c-01', seed=0)
    budget.call(judge, [{'role': 'user', 'content': 'x'}], 'j-01', seed=0)
    rows = json.loads(account.read_text())['runs']
    assert rows['run-p1/c-01']['model'] == hosted_cost.MODEL and rows['run-p1/j-01']['model'] == JUDGE
    assert rows['run-p1/c-01']['accounted_usd'] == pytest.approx((1000 * 0.06 + 40 * 0.24) / 1e6)
    assert rows['run-p1/j-01']['accounted_usd'] == pytest.approx((1000 * 0.30 + 40 * 0.90) / 1e6)
    total, mine = budget._account()
    assert float(mine) == pytest.approx(rows['run-p1/c-01']['accounted_usd'] + rows['run-p1/j-01']['accounted_usd'])
    assert budget.summary()['models'] == sorted([hosted_cost.MODEL, JUDGE])


def test_the_shared_stop_counts_both_roles(account, judge_on, monkeypatch):
    monkeypatch.setattr(app_swarm, 'SHARED_STOP_USD', hosted_cost.worst_case(1) + hosted_cost.worst_case(1, JUDGE) - hosted_cost.money('0.000001'))
    monkeypatch.setattr(hosted_cost, 'settle', lambda key, usage, complete: {'status': 'unknown_usage_reservation_held',
                                                                           'accounted_usd': json.loads(account.read_text())['runs'][key]['accounted_usd']})
    budget = app_swarm.Budget('run-stop', max_calls=4)
    budget.call(Scripted(['{"action":"scroll"}']), [{'role': 'user', 'content': 'x'}], 'c-01', seed=0)   # held at the crowd reservation
    judge = Scripted(['{"done":true}'], model=JUDGE)
    with pytest.raises(app_swarm.BudgetStop, match='shared spending stop'):
        budget.call(judge, [{'role': 'user', 'content': 'x'}], 'j-01', seed=0)
    assert judge.seen == []


def test_a_judge_reply_from_another_model_is_refused(account, judge_on):
    budget = app_swarm.Budget('run-id', max_calls=2)
    with pytest.raises(RuntimeError, match='registered model'):
        budget.call(Scripted(['{}'], model=JUDGE, answer_as=hosted_cost.MODEL), [{'role': 'user', 'content': 'x'}], 'j-01', seed=0)


def test_the_screenshot_does_not_count_against_the_text_bound_but_has_its_own(account, judge_on):
    budget = app_swarm.Budget('run-img', max_calls=3)
    person = app_swarm.personas_for('See what Lumen Notes costs')[0]
    small = app_swarm.confirm_messages(person, 'Lumen Notes costs 4 dollars a month for one person.', [], image=b'\xff\xd8' + b'0' * 50_000)
    assert small[-1]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,')
    budget.call(Scripted(['{"done":false}'], model=JUDGE), small, 'j-01', seed=0)
    big = app_swarm.confirm_messages(person, 'x', [], image=b'0' * (app_swarm.MAX_IMAGE_BYTES + 1))
    with pytest.raises(app_swarm.BudgetStop, match='too large'):
        budget.call(Scripted(['{}'], model=JUDGE), big, 'j-02', seed=0)


def test_the_judge_sees_the_screen_but_still_must_quote_its_words():
    person = app_swarm.personas_for('See what Lumen Notes costs')[0]
    text = 'Lumen Notes costs 4 dollars a month for one person.'
    msgs = app_swarm.confirm_messages(person, text, [], image=b'\xff\xd8jpeg')
    assert msgs[-1]['content'][0] == {'type': 'text', 'text': text} and 'picture' in msgs[0]['content']
    assert app_swarm.confirm_messages(person, text, [])[-1]['content'] == text             # no picture, same message as before
    assert not app_swarm.confirmed({'done': True, 'evidence': 'The image shows a price table clearly'}, text)


def test_the_cache_key_moves_only_when_a_judge_is_set(monkeypatch):
    monkeypatch.delenv(hosted_cost.JUDGE_MODEL_ENV, raising=False)
    key = app_swarm.cache_key('https://striverun.app', 'Bring in and preview your work', 3)
    assert key == app_swarm.cache_key('https://striverun.app/', 'Bring in and preview your work.', 3)
    monkeypatch.setenv(hosted_cost.JUDGE_MODEL_ENV, JUDGE)
    assert app_swarm.cache_key('https://striverun.app', 'Bring in and preview your work', 3) != key


def test_a_failed_judge_call_leaves_the_claim_unconfirmed_and_the_visitor_going(account, judge_on):
    class Down(Scripted):
        def chat(self, messages, **kwargs):
            self.seen.append(messages); raise RuntimeError('chat call failed: URLError')
    verdict, call = app_swarm.judge_claim(app_swarm.Budget('run-down', max_calls=2), Down([], model=JUDGE), [{'role': 'user', 'content': 'x'}], 'j-01')
    assert verdict['done'] is False and 'judge' in verdict['why'] and call is None


def test_p1_on_the_planted_app_the_judge_sees_the_screen_and_overrules_the_crowd(tmp_path, account, judge_on):
    pytest.importorskip('playwright')
    import threading
    from functools import partial
    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(app_swarm.ControlHandler))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    claim = '{"found":true,"quote":"Lumen Notes keeps your meeting notes in one place"}'
    crowd = {'reader': [claim, '{"action":"stuck","say":"I see no price.","wish":"Put the price on the first page."}'], 'developer': [claim]}
    verdicts = {'reader': ['{"done":false,"why":"No price is on this screen."}'],
                'developer': ['{"done":true,"evidence":"Lumen Notes keeps your meeting notes in one place","why":"It says how it works."}']}
    judges = {}
    def judge_for(person):
        judges[person['id']] = Scripted(verdicts[person['id']], model=JUDGE); return judges[person['id']]
    try:
        url = f'http://127.0.0.1:{server.server_port}/control/'
        p = tmp_path / 'run'; p.mkdir()
        (p / 'result.json').write_text(json.dumps({'id': 'e' * 24, 'url': url, 'name': 'control', 'mode': 'swarm', 'status': 'queued', 'control': True,
                                                   'job': {'text': 'See what Lumen Notes costs', 'source': 'fixed'}, 'tries_planned': 1}))
        people = [x for x in app_swarm.personas_for('See what Lumen Notes costs') if x['id'] in crowd]
        out = app_swarm.run(p, personas=people, client_for=lambda person: Scripted(crowd[person['id']]), judge_for=judge_for)
    finally:
        server.shutdown()
    by = {v['id']: v for v in out['tries'][0]}
    assert (by['reader']['claimed'], by['reader']['confirmed']) == (True, False)
    assert (by['developer']['claimed'], by['developer']['confirmed'], by['developer']['outcome']) == (True, True, 'got_there')
    sent = judges['developer'].seen[0][-1]['content']
    assert sent[1]['image_url']['url'].startswith('data:image/jpeg;base64,') and len(sent[1]['image_url']['url']) < app_swarm.MAX_IMAGE_BYTES
    assert by['developer']['steps'][0]['confirm_call']['model'] == JUDGE
    rows = json.loads(account.read_text())['runs']
    assert sorted(k.rsplit('-', 1)[-1] for k in rows if rows[k]['model'] == JUDGE) == ['judge', 'judge']
    assert out['judge_model'] == JUDGE and out['spend']['models'] == sorted([hosted_cost.MODEL, JUDGE]) and out['model_calls'] == 5
