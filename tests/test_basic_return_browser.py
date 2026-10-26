"""Real browser checks for the basic visit's Back observation; no model calls."""
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from sim.app_check import visit


class ReturnBrowserTests(unittest.TestCase):
    def exercise(self, variant):
        class Page(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                status = 404 if variant == 'dead-link' and self.path == '/help' else 200
                if self.path == '/help':
                    text = '<h1>Guide</h1><p>Read a note before changing it. Keep one collection per project. This is a disposable reading control, not a customer result.</p><script>sessionStorage.setItem("left", "yes")</script>'
                else:
                    text = '<h1>Collection</h1><p>Open this guide to organise a collection of project notes. This disposable control keeps its reading task simple and read only.</p><a href="/help">Read the guide</a>'
                    if variant == 'changed-return':
                        text += '<script>addEventListener("pageshow",()=>{if(sessionStorage.getItem("left"))document.querySelector("h1").textContent="Different collection"})</script>'
                self.send_response(status); self.send_header('Content-Type', 'text/html'); self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(text.encode())
        server = ThreadingHTTPServer(('127.0.0.1', 0), Page)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with TemporaryDirectory() as temp:
                p = Path(temp)
                (p/'result.json').write_text(json.dumps({'target':'custom','url':f'http://127.0.0.1:{server.server_port}/','mode':'quick','steps':[],'checks':[],'limitations':[]}))
                visit(p)
                result = json.loads((p/'result.json').read_text())
                return result
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_back_returns_to_same_address_and_visible_text(self):
        r = self.exercise('working')
        self.assertEqual(r['status'], 'complete')
        self.assertEqual(r['checks'][-1]['status'], 'passed')
        self.assertEqual(r['steps'][-1]['label'], 'Return to the starting page')
        self.assertEqual(r['steps'][0]['url'], r['steps'][-1]['url'])

    def test_same_address_with_changed_content_fails(self):
        r = self.exercise('changed-return')
        self.assertEqual(r['checks'][-1]['status'], 'failed')
        self.assertEqual(r['steps'][0]['url'], r['steps'][-1]['url'])

    def test_dead_reading_link_cannot_claim_return_checked(self):
        r = self.exercise('dead-link')
        self.assertEqual(r['checks'][1]['status'], 'failed')
        self.assertEqual(r['checks'][-1]['status'], 'not_run')


if __name__ == '__main__': unittest.main()
