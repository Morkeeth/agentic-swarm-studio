"""A returned navigation check must not pass by clicking inert matching prose."""
import json,os,subprocess,sys,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from sim.studio_test import generate

def test_actual_downloaded_code_rejects_missing_control_and_recovers(tmp_path):
    state={'working':True}
    class Page(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            link='<a href="#guide">Read guide</a>' if state['working'] else '<span>Read guide</span>'
            self.wfile.write(('<h1>Owned test app</h1>'+link+'<section id="guide"><h2>Guide</h2><p>This real controlled page has enough readable content for a path check.</p></section>').encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Page);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    r={'id':'controlled','url':f'http://127.0.0.1:{server.server_port}/','tries':[[{'name':'Recorded model','goal':'Read guide','outcome':'got_there','steps':[{'action':'click','target_text':'Read guide','status':'ok'}]}]]}
    test=tmp_path/'test_returned.py';test.write_text(generate(r));codes=[]
    try:
        for working in [True,False,True]:
            state['working']=working
            call=subprocess.run([sys.executable,'-m','pytest','-q',str(test)],capture_output=True,text=True,timeout=30)
            (tmp_path/f'result-{len(codes)}.log').write_text(call.stdout+call.stderr);codes.append(call.returncode)
    finally:server.shutdown();server.server_close();thread.join()
    assert codes==[0,1,0]


def test_observed_unique_control_disambiguates_without_accepting_inert_text(tmp_path):
    state={'working':True}
    class Page(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            first='<button data-tab="sources">Sources</button>' if state['working'] else '<span data-tab="sources">Sources</span>'
            self.wfile.write(('<h1>Owned controlled duplicate-label page</h1>'+first+'<button id="other">Sources</button><p>Enough readable content for a navigation smoke check.</p>').encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Page);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    result={'id':'duplicate-control','url':f'http://127.0.0.1:{server.server_port}/','tries':[[{'name':'Recorded model','goal':'Open sources','outcome':'got_there','steps':[{'action':'click','target_text':'Sources','target_locator':'[data-tab="sources"]','status':'ok'}]}]]}
    file=tmp_path/'test_duplicate.py';file.write_text(generate(result));codes=[]
    try:
        for working in [True,False,True]:
            state['working']=working
            call=subprocess.run([sys.executable,'-m','pytest','-q',str(file)],capture_output=True,text=True,timeout=30)
            (tmp_path/f'duplicate-{len(codes)}.log').write_text(call.stdout+call.stderr);codes.append(call.returncode)
    finally:server.shutdown();server.server_close();thread.join()
    assert codes==[0,1,0]
