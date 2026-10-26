"""Regression from P1 nvidia-swarm-2326: all five quote the guide link at step 2."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from sim import app_swarm, hosted_cost
from types import SimpleNamespace


def test_rejected_guide_link_claim_is_explained_before_another_move(tmp_path, monkeypatch):
    # Exact visible words retained from the actual guide trajectory, not a success oracle.
    content = 'Getting startedKeep one collection per project. Read a note before changing it. This public sample needs no account and does not save data.'
    class Guide(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header('Content-Type', 'text/html'); self.end_headers()
            self.wfile.write(b'<main><h1>Getting started</h1><p>Keep one collection per project. Read a note before changing it. This public sample needs no account and does not save data.</p><a href="/help">Read the guide</a><a href="/">Back to the collection</a></main>')
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Guide)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(hosted_cost, 'PRIOR', tmp_path/'prior.json')
    monkeypatch.setattr(hosted_cost, 'RECORD', tmp_path/'cost.json')
    (tmp_path/'prior.json').write_text('{"runs":[]}')
    calls = []
    class Visitor:
        model = hosted_cost.MODEL
        def chat(self, messages, **kwargs):
            calls.append(messages)
            text = '{"found":true,"quote":"Read the guide"}' if len(calls)==1 else '{"action":"stuck","say":"No further move."}'
            return SimpleNamespace(text=text, model=self.model, usage={'prompt_tokens':100,'completion_tokens':20}, finish_reason='stop')
    class NoJudge:
        model = hosted_cost.JUDGE_MODEL
        def chat(self, *args, **kwargs): raise AssertionError('Navigation label must not reach judge')
    person = {**app_swarm.personas_for('Read the getting started guide')[0], 'max_steps':1}
    try:
        row = app_swarm._visit_one(tmp_path, person, Visitor(), app_swarm.Budget('guide-regression',4),
            f'http://127.0.0.1:{server.server_port}/help', 0, time.monotonic(), lambda r:None,
            {'blocked':[], 'read_posts':[], 'errors':[]}, judge=NoJudge())
    finally: server.shutdown(); server.server_close()
    assert len(calls)==2
    assert 'Your completion quote was rejected before any judge ran' in calls[1][-1]['content']
    assert 'at least 20 characters' in calls[1][-1]['content']
    assert 'Page content (links and controls removed):\n'+content in calls[0][-1]['content']
    assert not row['confirmed'] and not row['screen_confirmed']
    assert row['steps'][0]['look']['rejection_reason']
    assert row['steps'][0]['page_evidence_text']==content
