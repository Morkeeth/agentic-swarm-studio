"""No keys or provider calls: exercise the real accounting and mocked transport."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import sqlite3
import pytest
from sim.first_users_route_a import RouteASummary, provision, HARD_CAP_MICROUSD, EXPIRES_AT
from sim.adapters.openai_compat import ChatReply
from sim.first_users_nebius import MODEL

class Fake:
    def __init__(self, fail=False): self.calls=[]; self.fail=fail
    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.fail: raise TimeoutError('secret transport detail')
        return ChatReply('Inspect the stopped link.',MODEL,'RUNTIME',{'prompt_tokens':129,'completion_tokens':74},'stop')

@pytest.fixture(autouse=True)
def forbid_external(monkeypatch):
    monkeypatch.setattr('sim.first_users_nebius.tokenfactory.load_key',lambda:pytest.fail('No real key use'))
    monkeypatch.setattr('urllib.request.urlopen',lambda *a,**k:pytest.fail('No external calls'))

def test_off_and_missing_budget_fail_before_key(tmp_path):
    from sim.first_users import App
    app=App(tmp_path/'store',sample=True)
    try: assert app.nebius_summary is None
    finally: app.stop.set();app.worker.join()
    with pytest.raises((ValueError, sqlite3.Error)): RouteASummary(tmp_path/'missing')
    assert not (tmp_path/'missing').exists()

def test_provision_is_exclusive_and_cap_is_fixed(tmp_path):
    path=tmp_path/'budget';provision(path)
    with pytest.raises(FileExistsError): provision(path)
    with sqlite3.connect(path) as db:
        assert db.execute('select cap from policy').fetchone()[0]==HARD_CAP_MICROUSD==2_000_000
        db.execute('update policy set cap=2000001')
    with pytest.raises(ValueError): RouteASummary(path,client=Fake())

def test_single_attempt_redaction_and_restart(tmp_path):
    path=tmp_path/'budget';provision(path);client=Fake()
    s=RouteASummary(path,client=client)
    out=s.explain('job',{'checks':[{'label':'First link opens','status':'failed'}],'task':'PRIVATE','url':'https://PRIVATE','screens':['PRIVATE']})
    assert len(client.calls)==1 and 'PRIVATE' not in json.dumps(client.calls)
    assert out['estimated_usd']==0.0000255 and out['reserved_usd']==0.005
    assert client.calls[0][1]['max_tokens']==256
    with pytest.raises(ValueError): RouteASummary(path,client=client).explain('job',{})
    assert len(client.calls)==1

def test_failures_consume_reservation_no_retry(tmp_path):
    path=tmp_path/'budget';provision(path);client=Fake(fail=True)
    out=RouteASummary(path,client=client).explain('job',{})
    assert out['status']=='failed_or_unknown' and 'secret' not in json.dumps(out)
    with pytest.raises(ValueError): RouteASummary(path,client=client).explain('job',{})
    with sqlite3.connect(path) as db: assert db.execute('select sum(reserve) from attempts').fetchone()[0]==5000
    assert len(client.calls)==1

def test_cap_boundary_atomic_across_independent_instances(tmp_path):
    path=tmp_path/'budget';provision(path)
    with sqlite3.connect(path) as db: db.executemany('insert into attempts values (?,?,?,NULL)',[(f'prior-{i}',5000,'reserved') for i in range(399)])
    def attempt(i):
        client=Fake()
        try: RouteASummary(path,client=client).explain(str(i),{});return len(client.calls)
        except ValueError: return 0
    with ThreadPoolExecutor(max_workers=8) as pool: assert sum(pool.map(attempt,range(12)))==1
    with sqlite3.connect(path) as db: assert db.execute('select sum(reserve) from attempts').fetchone()[0]==2_000_000
    with pytest.raises(ValueError): RouteASummary(path,client=Fake()).explain('restart',{})

def test_expiry_rechecked_before_every_reservation(tmp_path):
    path=tmp_path/'budget';provision(path);client=Fake()
    clock=[EXPIRES_AT-timedelta(seconds=1)]
    s=RouteASummary(path,client=client,now=lambda:clock[0])
    clock[0]=EXPIRES_AT
    with pytest.raises(ValueError): s.explain('expired',{})
    assert client.calls==[]

def test_deleted_database_never_recreated(tmp_path):
    path=tmp_path/'budget';provision(path);client=Fake();s=RouteASummary(path,client=client)
    path.unlink()
    with pytest.raises(sqlite3.Error): s.explain('job',{})
    assert not path.exists() and not client.calls

def test_app_route_a_requires_explicit_flag_and_external_db(tmp_path):
    from sim.first_users import App
    path=tmp_path/'budget';provision(path)
    with pytest.raises(ValueError): App(tmp_path/'store',nebius_route_a=True)
    with pytest.raises(ValueError): App(tmp_path/'store',nebius_route_a=True,nebius_summary=True,nebius_budget_db=path)

@pytest.mark.parametrize('broken',[False,True])
def test_app_worker_records_one_mock_explanation_without_browser_or_key(tmp_path,monkeypatch,broken):
    import time
    from pathlib import Path
    from sim.first_users import App
    path=tmp_path/'budget';provision(path);client=Fake()
    real_summary=RouteASummary
    monkeypatch.setattr('sim.first_users_route_a.RouteASummary',lambda p:real_summary(p,client=client))
    class Process:
        returncode=0
        def __init__(self,args,**kwargs):
            folder=Path(args[-1]);r=json.loads((folder/'result.json').read_text())
            r.update(status='complete',checks=[{'label':'First link opens','status':'failed' if broken else 'passed'}])
            (folder/'result.json').write_text(json.dumps(r))
        def wait(self,timeout): return 0
    monkeypatch.setattr('sim.first_users.subprocess.Popen',Process)
    app=App(tmp_path/'store',sample=True,nebius_route_a=True,nebius_budget_db=path)
    try:
        job=app.queue.enqueue('tenant','draft',{'url':'http://127.0.0.1/samples/working','task':'Read the guide','model':False,'nebius_summary':True})
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            row=app.queue.get('tenant',job)
            if row.get('result'):break
            time.sleep(.02)
        result=row['result']
        assert result['model_calls']==1 and result['nebius']['status']=='returned'
        assert result['checks'][0]['status']==('failed' if broken else 'passed')
        assert 'No complete-task claim' in result['completion_claim']
        assert len(client.calls)==1
    finally: app.stop.set();app.worker.join()


def test_actual_tokenfactory_transport_is_exactly_one_mock_post(tmp_path,monkeypatch):
    from sim.adapters.openai_compat import ChatClient
    path=tmp_path/'budget';provision(path);requests=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps({'model':MODEL,'usage':{'prompt_tokens':129,'completion_tokens':74},'choices':[{'finish_reason':'stop','message':{'content':'Inspect the failed link.'}}]}).encode()
    def transport(req,timeout):
        requests.append((req,timeout));return Response()
    monkeypatch.setattr('urllib.request.urlopen',transport)
    client=ChatClient(base_url='https://api.tokenfactory.nebius.com/v1',model=MODEL,label='RUNTIME',api_key='synthetic-test-value',timeout=20)
    out=RouteASummary(path,client=client).explain('job',{})
    assert out['status']=='returned' and len(requests)==1
    request,timeout=requests[0]
    assert request.full_url=='https://api.tokenfactory.nebius.com/v1/chat/completions'
    assert request.method=='POST' and timeout==20
    assert json.loads(request.data)['max_tokens']==256

@pytest.mark.parametrize('reason', ['stop', 'length', None])
def test_route_a_retains_raw_finish_reason_in_report_and_saved_receipt(tmp_path, reason):
    class RawReply(Fake):
        def chat(self, messages, **kwargs):
            reply = super().chat(messages, **kwargs)
            return ChatReply(reply.text, reply.model, reply.label, reply.usage, reason)
    path = tmp_path / 'budget'
    provision(path)
    out = RouteASummary(path, client=RawReply()).explain('raw-stop', {})
    assert 'finish_reason' in out and out['finish_reason'] == reason
    assert (out['status'] == 'returned') == (reason == 'stop')
    with sqlite3.connect(path) as db:
        saved = json.loads(db.execute('SELECT receipt FROM attempts WHERE id=?', ('raw-stop',)).fetchone()[0])
    assert 'finish_reason' in saved and saved['finish_reason'] == reason
