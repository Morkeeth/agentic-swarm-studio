import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
from sim.first_users_nebius import Summary, MODEL
from sim.adapters.openai_compat import ChatClient, ChatReply
from sim.first_users import App

REPORT={'checks':[{'label':'First link opens','status':'failed'}], 'task':'secret task', 'url':'https://private.invalid', 'screens':['secret.png']}

class Client:
    def __init__(self, failure=False, **reply): self.calls=[];self.failure=failure;self.reply=reply
    def chat(self, messages, **kwargs):
        self.calls.append((messages,kwargs))
        if self.failure: raise RuntimeError('credential must never reach report')
        return ChatReply(**({'text':'The link failed. Inspect the guide address.','model':MODEL,'label':'RUNTIME','usage':{'prompt_tokens':100,'completion_tokens':20},'finish_reason':'stop'}|self.reply))

def test_default_app_never_reads_key_or_constructs_provider(tmp_path,monkeypatch):
    monkeypatch.setattr('sim.first_users_nebius.tokenfactory.load_key',lambda:pytest.fail('OFF must not read key'))
    app=App(tmp_path/'reports',sample=True)
    try: assert app.nebius_summary is None
    finally: app.stop.set();app.worker.join()

def test_flag_requires_separate_budget_store(tmp_path):
    with pytest.raises(ValueError): App(tmp_path,nebius_summary=True)
    with pytest.raises(ValueError): App(tmp_path,nebius_summary=True,nebius_budget_db=tmp_path/'budget.sqlite')

def test_one_call_bound_prompt_and_receipt(tmp_path):
    client=Client();s=Summary(tmp_path/'budget',client=client);out=s.explain('job',REPORT)
    assert len(client.calls)==1 and out['status']=='returned'
    messages,kwargs=client.calls[0]
    assert kwargs['max_tokens']==256 and kwargs['chat_template_kwargs']=={'enable_thinking':False}
    assert 'secret' not in json.dumps(messages) and 'private.invalid' not in json.dumps(messages)
    assert out['estimated_usd']==0.0000108 and out['invoice_usd'] is None
    with pytest.raises(ValueError):s.explain('job',REPORT)
    assert len(client.calls)==1

@pytest.mark.parametrize('reply',[{'model':'wrong'},{'label':'LOCAL'},{'usage':{}},{'usage':{'prompt_tokens':True,'completion_tokens':1}},{'usage':{'prompt_tokens':4097,'completion_tokens':1}},{'finish_reason':'length'}])
def test_unverified_response_does_not_claim_success_or_retry(tmp_path,reply):
    client=Client(**reply);s=Summary(tmp_path/'budget',client=client);out=s.explain('job',REPORT)
    assert out['status']=='failed_or_unknown' and 'estimated_usd' not in out
    assert len(client.calls)==1

def test_failure_and_restart_do_not_refund_or_retry(tmp_path):
    path=tmp_path/'budget';client=Client(failure=True);s=Summary(path,client=client)
    assert s.explain('one',REPORT)['status']=='failed_or_unknown'
    assert 'credential' not in json.dumps(s.explain('two',REPORT))
    restarted=Summary(path,client=client)
    with pytest.raises(ValueError):restarted.explain('three',REPORT)
    with sqlite3.connect(path) as db: assert db.execute('select sum(reserve) from attempts').fetchone()[0]==10000
    assert len(client.calls)==2

def test_atomic_global_cap_across_concurrent_requests(tmp_path):
    s=Summary(tmp_path/'budget',client=Client())
    def reserve(i):
        try:s.reserve(str(i));return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=8) as pool: assert sum(pool.map(reserve,range(20)))==2

def test_actual_adapter_body_fixed_endpoint_and_one_post(tmp_path,monkeypatch):
    calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self):return json.dumps({'model':MODEL,'usage':{'prompt_tokens':100,'completion_tokens':20},'choices':[{'finish_reason':'stop','message':{'content':'Inspect the guide address.'}}]}).encode()
    def transport(req,timeout):
        calls.append((req.full_url,json.loads(req.data),timeout));return Response()
    monkeypatch.setattr('urllib.request.urlopen',transport)
    c=ChatClient(base_url='https://api.tokenfactory.nebius.com/v1',model=MODEL,label='RUNTIME',api_key='unit-test-only',timeout=20)
    assert Summary(tmp_path/'budget',client=c).explain('job',REPORT)['status']=='returned'
    assert len(calls)==1 and calls[0][0]=='https://api.tokenfactory.nebius.com/v1/chat/completions'
    assert calls[0][1]['model']==MODEL and calls[0][1]['max_tokens']==256

def test_flag_off_http_rejects_requested_paid_addon(tmp_path):
    import threading
    import urllib.request
    import urllib.error
    import http.cookiejar
    from http.server import ThreadingHTTPServer
    from sim.first_users import Handler
    app=App(tmp_path/'store',sample=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.app=app;app.port=server.server_port
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{app.port}'
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def post(path,body):
        req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Origin':base,'Content-Type':'application/json'})
        with opener.open(req) as response:return json.load(response)
    try:
        draft=post('/api/drafts',{'sample':'working','task':'Read the guide'})
        post('/api/confirm',{'id':draft['id'],'task':'Read the guide'})
        post('/api/payment',{'id':draft['id']})
        with pytest.raises(urllib.error.HTTPError) as e:post('/api/run',{'id':draft['id'],'practice_ack':True,'nebius_summary':True})
        assert e.value.code==400 and app.queue.stats()=={}
    finally:
        app.stop.set();app.worker.join();server.shutdown();server.server_close();thread.join()
