"""Exercise the subprocess/auth boundary with a synthetic CLI, never a model call."""
import json, os
from pathlib import Path
from unittest.mock import patch
import pytest
from sim.codex_visitor import CodexClient, run


def test_api_auth_is_refused_before_any_decision(tmp_path):
    cli=tmp_path/'codex';cli.write_text('#!/bin/sh\necho "Logged in using an API key"\n');cli.chmod(0o755)
    with patch('sim.codex_visitor.shutil.which',return_value=str(cli)):
        with pytest.raises(RuntimeError,match='API-key fallback is prohibited'):
            CodexClient(tmp_path/'calls')


def test_page_decision_isolates_config_and_environment(tmp_path,monkeypatch):
    cli=tmp_path/'codex'
    cli.write_text('''#!/usr/bin/env python3
import os,sys,json
from pathlib import Path
if sys.argv[1:]==['login','status']:
 print('Logged in using ChatGPT');sys.exit(0)
assert 'OPENAI_API_KEY' not in os.environ
assert 'TOKEN_FACTORY_API_KEY' not in os.environ
assert Path(os.environ['CODEX_HOME'],'auth.json').is_symlink()
assert not Path(os.environ['CODEX_HOME'],'AGENTS.md').exists()
assert '--disable' in sys.argv and 'shell_tool' in sys.argv
assert 'private sentinel' not in sys.stdin.read()
Path(sys.argv[sys.argv.index('-o')+1]).write_text('{"found":false,"quote":""}')
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':5,'output_tokens':3}}))
''');cli.chmod(0o755)
    home=tmp_path/'home';(home/'.codex').mkdir(parents=True);(home/'.codex/auth.json').write_text('synthetic-auth-fixture')
    (home/'.codex/AGENTS.md').write_text('private sentinel')
    monkeypatch.setenv('OPENAI_API_KEY','not-a-real-key');monkeypatch.setenv('TOKEN_FACTORY_API_KEY','not-a-real-key')
    with patch('sim.codex_visitor.shutil.which',return_value=str(cli)),patch('sim.codex_visitor.Path.home',return_value=home):
        r=CodexClient(tmp_path/'calls').chat([{'role':'user','content':'Synthetic public page'}])
    assert json.loads(r.text)['found'] is False
    assert r.usage['input_tokens']==5


def test_nonlocal_and_write_tasks_stop_before_browser_or_auth(tmp_path):
    with pytest.raises(ValueError,match='loopback'):
        run('https://example.org','Read the guide',tmp_path/'never')
    with pytest.raises(ValueError,match='read-only'):
        run('http://127.0.0.1:4127','Submit a payment',tmp_path/'never')
    assert not (tmp_path/'never').exists()
