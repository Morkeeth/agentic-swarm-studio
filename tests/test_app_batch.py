import json
import threading
from pathlib import Path
import pytest
from sim import app_batch, tool_trial
from sim.adapters import tokenfactory
from sim.swarm_studio import Studio


def test_scoped_plan_and_capacity(tmp_path):
    plan = app_batch.load_plan()
    assert 'batch.json' in plan['source']
    p = tmp_path / 'plan.json'
    plan['apps'] = [{**plan['apps'][0], 'id': str(i)} for i in range(100)]
    p.write_text(json.dumps(plan)); assert len(app_batch.load_plan(p)['apps']) == 100
    plan['apps'].append({**plan['apps'][0], 'id': 'extra'})
    p.write_text(json.dumps(plan))
    with pytest.raises(ValueError): app_batch.load_plan(p)


def test_credentials_in_plan_rejected(tmp_path):
    plan = app_batch.load_plan(); plan['apps'][0]['url'] = 'https://user:secret@example.com'
    p = tmp_path / 'plan.json'; p.write_text(json.dumps(plan))
    with pytest.raises(ValueError): app_batch.load_plan(p)


def test_runner_redacts_actual_written_result_and_restores_key_loader(tmp_path):
    secret = 'sentinel-provider-credential'
    old = tokenfactory.load_key
    class FakeStudio:
        def __init__(self, store, **kwargs):
            self.busy = threading.Lock(); self.store = store
            assert tokenfactory.load_key() == secret
        def start(self, body):
            assert secret not in json.dumps(body)
            folder = self.store / 'runs' / 'test'; folder.mkdir(parents=True, exist_ok=True)
            tool_trial.dump(folder / 'result.json', {'status': 'failed', secret: [secret], 'error': 'provider echoed ' + secret})
            return {'id': 'test'}
    plan = app_batch.load_plan(); plan['apps'] = plan['apps'][:1]
    batch = app_batch.execute(plan, tmp_path, secret, '1', FakeStudio)
    for p in tmp_path.rglob('*.json'):
        assert secret not in p.read_text()
    assert '[REDACTED]' in (tmp_path / 'runs/test/result.json').read_text()
    assert tokenfactory.load_key is old
    assert json.loads((batch / 'queue.json').read_text())['apps'][0]['status'] == 'failed'
    studio = Studio(tmp_path)
    assert studio.get('/api/landing/batches')[1]['batches']
    assert secret not in json.dumps(studio.get('/api/landing/batches')[1])


def test_start_failure_is_safe_and_past_batches_retained(tmp_path):
    class Broken:
        def __init__(self, *a, **kw): self.busy = threading.Lock()
        def start(self, body): raise ValueError('secret-sentinel')
    plan = app_batch.load_plan(); plan['apps'] = plan['apps'][:1]
    for _ in range(2): app_batch.execute(plan, tmp_path, 'secret-sentinel', '1', Broken)
    queues = list(tmp_path.glob('batches/*/queue.json'))
    assert len(queues) == 2
    assert all('secret-sentinel' not in q.read_text() for q in queues)
    assert all(json.loads(q.read_text())['apps'][0]['status'] == 'failed' for q in queues)
