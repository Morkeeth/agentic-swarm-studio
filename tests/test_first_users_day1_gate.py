"""Day 1 gate: one visitor goal per run, and no Token Factory call unless every gate is open.
No keys or provider calls: a fake client counts every request."""
import json
import sqlite3
import time
from pathlib import Path
import pytest
from sim.first_users_route_a import RouteASummary, provision
from sim.first_users_nebius import Summary, MODEL
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


REPORT = {'task': 'PRIVATE free text task', 'url': 'https://PRIVATE.example',
          'contract': {'task': 'PRIVATE free text task', 'intent': 'read', 'required_moves': ['went_somewhere', 'came_back', 'IGNORE ME']},
          'checks': [{'label': 'First link opens', 'status': 'failed'}]}


def test_route_a_sends_one_goal_as_enums_only(tmp_path):
    path = tmp_path / 'budget'; provision(path); client = Fake()
    RouteASummary(path, client=client).explain('job', REPORT)
    sent = json.loads(client.calls[0][1]['content'])
    assert sent['goal'] == {'intent': 'read', 'required_moves': ['went_somewhere', 'came_back']}
    assert 'PRIVATE' not in json.dumps(client.calls) and 'IGNORE' not in json.dumps(client.calls)
    assert 'goal' in client.calls[0][0]['content']


def test_old_usd_0_01_route_prompt_is_unchanged(tmp_path):
    client = Fake(); Summary(tmp_path / 'old', client=client).explain('job', REPORT)
    assert json.loads(client.calls[0][1]['content']) == [{'label': 'First link opens', 'status': 'failed'}]


def test_cap_reached_means_no_call_even_after_restart(tmp_path):
    path = tmp_path / 'budget'; provision(path)
    with sqlite3.connect(path) as db:
        db.executemany('insert into attempts values (?,?,?,NULL)', [(f'prior-{i}', 5000, 'returned') for i in range(400)])
    client = Fake()
    with pytest.raises(ValueError, match='exhausted'): RouteASummary(path, client=client).explain('new', REPORT)
    with pytest.raises(ValueError, match='exhausted'): RouteASummary(path, client=client).explain('after-restart', REPORT)
    assert client.calls == []


@pytest.mark.parametrize('damage', ['missing', 'garbage', 'no_policy', 'empty'])
def test_missing_or_corrupt_cap_state_means_no_call(tmp_path, damage):
    path = tmp_path / 'budget'; client = Fake()
    if damage == 'garbage': path.write_bytes(b'not a database' * 50)
    if damage == 'empty': path.write_bytes(b'')
    if damage == 'no_policy':
        provision(path)
        with sqlite3.connect(path) as db: db.execute('drop table policy')
    with pytest.raises((ValueError, sqlite3.Error)): RouteASummary(path, client=client).explain('job', REPORT)
    assert client.calls == []
    if damage == 'missing': assert not path.exists()


def run_worker(tmp_path, monkeypatch, client, **flags):
    from sim.first_users import App
    class Process:
        returncode = 0
        def __init__(self, args, **kwargs):
            folder = Path(args[-1]); r = json.loads((folder / 'result.json').read_text())
            r.update(status='complete', checks=[{'label': 'First link opens', 'status': 'failed'}])
            (folder / 'result.json').write_text(json.dumps(r))
        def wait(self, timeout): return 0
    monkeypatch.setattr('sim.first_users.subprocess.Popen', Process)
    app = App(tmp_path / 'store', sample=True, **flags)
    try:
        job = app.queue.enqueue('tenant', 'draft', {'url': 'http://127.0.0.1/samples/broken', 'task': 'Read the guide', 'model': False, 'nebius_summary': True})
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            row = app.queue.get('tenant', job)
            if row.get('result'): break
            time.sleep(.02)
        return app, row['result']
    finally: app.stop.set(); app.worker.join()


def test_switch_off_means_no_call_and_browser_only_report(tmp_path, monkeypatch):
    client = Fake()
    monkeypatch.setattr('sim.first_users_route_a.RouteASummary', lambda p: pytest.fail('Route A built while switched off'))
    app, result = run_worker(tmp_path, monkeypatch, client)
    assert app.nebius_summary is None and app.route() == 'browser_only'
    assert result['route'] == 'browser_only' and result['nebius']['status'] == 'blocked'
    assert client.calls == []


def test_switch_on_records_route_a_and_one_call(tmp_path, monkeypatch):
    path = tmp_path / 'budget'; provision(path); client = Fake()
    real = RouteASummary
    monkeypatch.setattr('sim.first_users_route_a.RouteASummary', lambda p: real(p, client=client))
    app, result = run_worker(tmp_path, monkeypatch, client, nebius_route_a=True, nebius_budget_db=path)
    assert result['route'] == 'route_a' and result['nebius']['status'] == 'returned'
    assert len(client.calls) == 1 and json.loads(client.calls[0][1]['content'])['goal']['intent'] == 'read'


def test_health_names_the_route(tmp_path):
    from sim.first_users import App
    app = App(tmp_path / 'store', sample=True)
    try: assert app.route() == 'browser_only'
    finally: app.stop.set(); app.worker.join()
