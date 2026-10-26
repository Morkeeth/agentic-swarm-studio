import json, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import pytest
from sim import app_check

NAV='<nav>'+' '.join(f'<span>Menu item {i}</span>' for i in range(12))+'</nav>'
PAGES={
 '/feed':('<html><title>Feed</title><body><a href="#main">Skip to content</a>'+NAV+'<main id="main"><h1>Public runs</h1><div id="feed"></div></main>'
          '<script>setTimeout(()=>fetch("/api/feed").then(r=>r.json()).then(d=>{document.getElementById("feed").innerText=d.item}),1500)</script></body></html>'),
 '/api/feed':'{"item":"Loaded feed entry from the server"}',
 '/postfeed':('<html><title>Feed</title><body>'+NAV+'<main><h1>Public runs</h1><div id="feed"></div></main>'
          '<script>fetch("/api/feed",{method:"POST",body:"{}"}).then(r=>r.json()).then(d=>{document.getElementById("feed").innerText=d.item})</script></body></html>'),
 '/skip':('<html><title>Skip</title><body><a href="#main">Skip to content</a>'+NAV+'<main id="main"><p>'+'Welcome text. '*10+'</p>'
          '<a href="/guide">Read the getting started guide</a></main></body></html>'),
 '/guide':'<html><title>Guide</title><body><main><h1>Guide</h1><p>'+'Guide body text. '*10+'</p></main></body></html>',
}

class H(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_GET(self):
        body=PAGES.get(self.path.split('?')[0])
        if body is None:self.send_response(404);self.end_headers();return
        self.send_response(200);self.send_header('Content-Type','application/json' if self.path.startswith('/api') else 'text/html');self.end_headers();self.wfile.write(body.encode())
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length','0')));self.do_GET()

@pytest.fixture
def site():
    s=ThreadingHTTPServer(('127.0.0.1',0),H);t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
    yield f'http://127.0.0.1:{s.server_port}'
    s.shutdown()

def run_visit(tmp_path,url):
    f=tmp_path/'check';f.mkdir()
    (f/'result.json').write_text(json.dumps({'id':'t','target':'custom','url':url,'mode':'quick','status':'queued','steps':[],'checks':[],'fixes':[],'limitations':[]}))
    app_check.visit(f);return json.loads((f/'result.json').read_text()),f

def test_tool_crash_reports_error_not_a_site_verdict(tmp_path,monkeypatch):
    import playwright.sync_api
    def broken():raise RuntimeError("BrowserType.launch: Executable doesn't exist")
    monkeypatch.setattr(playwright.sync_api,'sync_playwright',broken)
    r,_=run_visit(tmp_path,'https://example.com')
    assert r['status']=='error'
    assert r['verdict']!='Needs work' and 'could not' in r['verdict'].lower()

def test_open_step_waits_for_loaded_content_or_is_not_run(tmp_path,site):
    r,f=run_visit(tmp_path,site+'/feed')
    first=r['steps'][0]
    if first['status']=='passed':
        assert 'Loaded feed entry' in (f/'step-01.txt').read_text()
    else:
        assert first['status']=='not_run'

def test_same_page_anchor_is_not_a_first_link(tmp_path,site):
    r,_=run_visit(tmp_path,site+'/skip')
    second=r['steps'][1]
    assert second['url'].rstrip('/').endswith('/guide')

def test_screen_that_needed_a_blocked_request_is_not_judged(tmp_path,site):
    r,_=run_visit(tmp_path,site+'/postfeed')
    first=r['steps'][0]
    assert r['raw']['blocked_write_requests']
    assert first['status']=='not_run' and 'blocked' in first['reason']

def test_named_read_post_is_allowed_and_others_stay_blocked(tmp_path,site,monkeypatch):
    host=site.split('//')[1].split(':')[0]
    monkeypatch.setattr(app_check,'READ_POSTS',[{'name':'Fixture feed read','host':host,'path':'/api/feed'}])
    r,f=run_visit(tmp_path,site+'/postfeed')
    assert r['steps'][0]['status']=='passed'
    assert 'Loaded feed entry' in (f/'step-01.txt').read_text()
    assert any(x.get('allowlisted')=='Fixture feed read' for x in r['raw']['read_requests'])
    assert not r['raw']['blocked_write_requests']
    assert app_check.read_post_name('POST','http://'+host+':1/api/other') is None
    assert app_check.read_post_name('PUT','http://'+host+':1/api/feed') is None

def test_shipped_allowlist_names_every_entry_and_only_read_rpcs():
    assert app_check.READ_POSTS
    for x in app_check.READ_POSTS:
        assert x['name'] and x['host'] and x['path'].rsplit('/',1)[-1].startswith('read_')

def test_equal_length_changing_text_does_not_settle():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        try:
            page=browser.new_page()
            page.set_content('<p id="changing">AAAAAAAA</p><script>setInterval(()=>{const e=document.querySelector("p");e.innerText=e.innerText==="AAAAAAAA"?"BBBBBBBB":"AAAAAAAA"},250)</script>')
            assert not app_check.settle(page,quiet_ms=1000,limit_ms=2000)
        finally:browser.close()
