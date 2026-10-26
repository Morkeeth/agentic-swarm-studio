from types import SimpleNamespace
import pytest
from sim.check_queue import Queue
from sim import first_users_payment
from sim.favour_handoff import project_draft

def test_fenced_lease_rejects_late_writer_and_reclaims(tmp_path, monkeypatch):
    clock=[1000.]
    monkeypatch.setattr('sim.check_queue.time',SimpleNamespace(time=lambda:clock[0]))
    q=Queue(tmp_path/'q.sqlite',lease_seconds=.01)
    key=q.enqueue('alice','one',{'task':'read'})
    old=q.lease();clock[0]+=.03;new=q.lease()
    assert old['fence']!=new['fence']
    assert not q.settle(key,old['fence'],{'wrong':True})
    assert q.settle(key,new['fence'],{'right':True})
    assert not q.settle(key,new['fence'],{'duplicate':True})
    assert q.get('alice',key)['result']=={'right':True}
    assert q.get('bob',key) is None

def test_paid_jobs_do_not_silently_retry_after_expiry(tmp_path, monkeypatch):
    clock=[1000.]
    monkeypatch.setattr('sim.check_queue.time',SimpleNamespace(time=lambda:clock[0]))
    q=Queue(tmp_path/'q.sqlite',lease_seconds=.01,max_attempts=1)
    key=q.enqueue('alice','paid',{});q.lease();clock[0]+=.03
    assert q.lease() is None and q.get('alice',key)['state']=='failed'

def test_durable_quota_total_and_duplicate_identity(tmp_path):
    q=Queue(tmp_path/'q.sqlite',quota=1,max_total=2)
    key=q.enqueue('alice','one',{'task':'read'})
    assert q.enqueue('alice','one',{'task':'read'})==key
    with pytest.raises(ValueError):q.enqueue('alice','two',{})
    with pytest.raises(ValueError):q.enqueue('alice','one',{'task':'different'})
    q.enqueue('bob','one',{})
    with pytest.raises(ValueError):q.enqueue('carol','one',{})
    assert Queue(q.path).get('alice',key) is not None

def test_over_cap_result_is_not_completed_and_share_is_scoped(tmp_path):
    q=Queue(tmp_path/'q.sqlite');key=q.enqueue('alice','over',{},cap_microusd=1);job=q.lease()
    assert q.settle(key,job['fence'],{'done':True},cost_microusd=2)
    assert q.get('alice',key)['state']=='failed'
    with pytest.raises(ValueError):q.share('alice',key)
    key=q.enqueue('alice','good',{});job=q.lease();q.settle(key,job['fence'],{'screens':[]})
    with pytest.raises(ValueError):q.share('bob',key)
    old=q.share('alice',key);new=q.share('alice',key)
    assert q.shared(old) is None and q.shared(new)['id']==key

def test_no_live_key_or_client_paid_flag(monkeypatch):
    monkeypatch.setenv('STRIPE_TEST_SECRET_KEY','sk_live_invalid_example')
    with pytest.raises(ValueError):first_users_payment.test_key()
    assert not first_users_payment.verified('client-says-paid','job')

def test_human_handoff_does_not_claim_publication_or_funding():
    d=project_draft('http://127.0.0.1:8080/samples/working','Read the guide and return')
    assert d['status']=='DRAFT_NOT_POSTED' and d['public_url_needed']
    assert d['reward_plan']['funding_status']=='UNFUNDED'
    assert d['reward_plan']['requires_builder_signature']
    assert len(d['test_deck'])==5 and d['test_deck'][3]['required']
    assert d['project']['task']['required_moves']==['went_somewhere','came_back']
    with pytest.raises(ValueError):project_draft('https://user:password@example.invalid/','Read')


def test_handoff_has_live_favour_destination_without_changing_tested_project():
    d=project_draft('https://customer.example/guide','Read the guide and return')
    assert d['handoff']['destination_url']=='https://world-relay.vercel.app/'
    assert d['handoff']['mode']=='MANUAL_DRAFT_ONLY'
    assert d['project']['url']=='https://customer.example/guide'
    assert d['status']=='DRAFT_NOT_POSTED'
    assert d['verification']['accepted_reviews']==0

@pytest.mark.parametrize('sample', ['working','broken'])
def test_sample_handoff_exports_public_target_but_keeps_worker_loopback(tmp_path,monkeypatch,sample):
    from sim.first_users import App
    monkeypatch.delenv('FIRST_USERS_PUBLIC_ORIGIN',raising=False)
    app=App(tmp_path,sample=True)
    try:
        draft={'url':f'http://127.0.0.1:8080/samples/{sample}','task':'Read the guide and return'}
        status,result=handoff_response(app,draft)
        assert status==200
        assert result['project']['url']==f'https://simulated-market-judge-568004190078.us-central1.run.app/samples/{sample}'
        assert draft['url']==f'http://127.0.0.1:8080/samples/{sample}'
        assert not result['public_url_needed']
        assert result['project']['task']['required_moves']==['went_somewhere','came_back']
        assert result['reward_plan']['funding_status']=='UNFUNDED'
    finally:app.stop.set();app.worker.join(timeout=2)

@pytest.mark.parametrize('origin', ['http://127.0.0.1:8080','https://user:secret@example.com','https://example.com/path','https://example.com?query=1','https://localhost','https://10.0.0.1'])
def test_sample_handoff_rejects_nonpublic_or_nonorigin_config(tmp_path,monkeypatch,origin):
    from sim.first_users import App
    monkeypatch.setenv('FIRST_USERS_PUBLIC_ORIGIN',origin)
    app=App(tmp_path,sample=True)
    try:
        status,_=handoff_response(app,{'url':'http://127.0.0.1:8080/samples/working','task':'Read the guide'})
        assert status==400
    finally:app.stop.set();app.worker.join(timeout=2)

def test_local_customer_handoff_keeps_target_and_needs_public_url(tmp_path):
    from sim.first_users import App
    app=App(tmp_path)
    try:
        status,d=handoff_response(app,{'url':'http://127.0.0.1:3999/customer','task':'Read the guide'})
        assert status==200
        assert d['project']['url']=='http://127.0.0.1:3999/customer' and d['public_url_needed']
    finally:app.stop.set();app.worker.join(timeout=2)



def test_sample_handoff_uses_operator_origin_not_request_host(tmp_path,monkeypatch):
    from sim.first_users import App
    monkeypatch.setenv('FIRST_USERS_PUBLIC_ORIGIN','https://review.example/')
    app=App(tmp_path,sample=True)
    try:
        status,d=handoff_response(app,{'url':'http://127.0.0.1:8080/samples/working','task':'Read the guide'})
        assert status==200 and d['project']['url']=='https://review.example/samples/working'
        assert d['handoff']['destination_url']=='https://world-relay.vercel.app/'
    finally:app.stop.set();app.worker.join(timeout=2)

def handoff_response(app,draft):
    """Exercise the real owned-draft HTTP endpoint; never enqueue a visitor."""
    import json
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.request import Request,urlopen
    from urllib.error import HTTPError
    from sim.first_users import Handler
    tenant='a'*48
    app.save(tenant,'owned-draft',draft)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.app=app;app.port=server.server_port
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    origin=f'http://127.0.0.1:{app.port}'
    request=Request(origin+'/api/handoff',data=json.dumps({'id':'owned-draft'}).encode(),headers={'Origin':origin,'Content-Type':'application/json','Cookie':'first_users='+tenant})
    try:
        try:
            with urlopen(request) as r:return r.status,json.load(r)
        except HTTPError as r:return r.code,json.load(r)
    finally:server.shutdown();server.server_close();thread.join()
