"""The repair loop on a controlled two-page app. The visitor is scripted, so this tests the mechanism, not any model."""
import json, re, shutil, subprocess, time
from pathlib import Path
from types import SimpleNamespace

import pytest

from sim import app_swarm, repair_loop
from sim.codex_visitor import SubscriptionBudget

RESULT = 'The guide explains that every settlement is checked against the frozen question first.'


class Scripted:
    """Answers the three visitor prompts from the page text alone: look, confirm and move."""
    model = 'scripted-test-visitor'

    def chat(self, messages, **_):
        system, user = messages[0]['content'], messages[-1]['content']
        if system.startswith('You check whether'):
            reply = {'done': RESULT in user, 'evidence': RESULT if RESULT in user else '', 'why': 'The sentence is on the screen.'}
        elif 'Is your task completed on this screen' in system:
            reply = {'found': RESULT in user, 'quote': RESULT if RESULT in user else ''}
        else:
            hit = re.search(r'^(\d+)\. \[link\] Guide ', user, re.M | re.I)
            reply = {'action': 'click', 'target': int(hit.group(1)), 'say': 'The guide should say it.'} if hit and 'error 404' not in user else \
                    {'action': 'stuck', 'say': 'The guide link is broken.', 'wish': 'A guide link that opens.'}
        return SimpleNamespace(text=json.dumps(reply), model=self.model, usage=None)


def scripted_visit(url, goal, output):
    p = Path(output); p.mkdir(parents=True)
    person = {**app_swarm.CAST[0], 'id': 'scripted', 'goal': goal, 'max_steps': 3}
    shared = {'blocked': [], 'errors': [], 'read_posts': []}
    row = app_swarm._visit_one(p, person, Scripted(), SubscriptionBudget(9), url, 0, time.monotonic(), lambda r: None, shared)
    result = {'schema': 'scripted-test-visitor/1', 'sponsor_model_evidence': False, 'model': Scripted.model, 'visitor': row}
    (p / 'result.json').write_text(json.dumps(result))
    return result


def app_repo(root):
    """A site whose menu uses a clean URL that only a rewriting host can answer. CSS shows the label as GUIDE; its accessible name is Guide."""
    repo = root / 'app'; (repo / 'web').mkdir(parents=True)
    filler = '<p>' + 'This is a small owned app used to exercise the repair loop end to end. ' * 3 + '</p>'
    (repo / 'web/index.html').write_text(f'<title>Home</title><h1>Fixture home</h1>{filler}<nav style="text-transform:uppercase"><a href="/guide">Guide</a></nav>')
    (repo / 'web/guide.html').write_text(f'<title>Guide</title><h1>Guide</h1><p>{RESULT}</p>{filler}')
    for cmd in (['init', '-q'], ['add', '.'], ['-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'base']):
        subprocess.run(['git', *cmd], cwd=repo, check=True)
    sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    patch = root / 'portable-guide-link.patch'
    (repo / 'web/index.html').write_text((repo / 'web/index.html').read_text().replace('href="/guide"', 'href="/guide.html"'))
    patch.write_text(subprocess.run(['git', 'diff'], cwd=repo, check=True, capture_output=True, text=True).stdout)
    subprocess.run(['git', 'checkout', '-q', '--', '.'], cwd=repo, check=True)
    return repo, sha, patch


def test_red_before_green_after_and_same_goal_completes(tmp_path):
    repo, sha, patch = app_repo(tmp_path)
    r = repair_loop.loop(str(repo), sha[:7], 'web', 'Find out how settlements are checked', patch, tmp_path / 'out', scripted_visit)
    assert r['before_sha'] == sha and r['after_sha'] != sha
    assert r['visit_before']['outcome'] == 'stuck' and 'answered with error 404' in r['visit_before']['error_hit']['what_happened']
    assert r['check_before']['red_reason'] == 'error_page' and r['check_after']['exit'] == 0
    assert r['visit_after']['outcome'] == 'got_there' and r['visit_after']['confirmed']
    assert r['repaired'] is True and r['sponsor_model_evidence'] is False
    assert repair_loop.recheck(tmp_path / 'out') == {'before': 1, 'after': 0}
    assert 'Repaired: **yes**' in (tmp_path / 'out' / 'REPAIR.md').read_text()
    page = (tmp_path / 'out' / 'REPAIR.html').read_text()
    assert 'Repaired: yes' in page and 'red: error page' in page and 'download' in page


def test_recheck_refuses_an_edited_check(tmp_path):
    repo, sha, patch = app_repo(tmp_path)
    repair_loop.loop(str(repo), sha, 'web', 'Find out how settlements are checked', patch, tmp_path / 'out', scripted_visit)
    test = tmp_path / 'out' / 'test_returned_path.py'; test.write_text(test.read_text().replace('code < 400', 'code < 999'))
    with pytest.raises(ValueError, match='changed'): repair_loop.recheck(tmp_path / 'out')


def test_a_patch_that_does_not_fix_is_not_called_repaired(tmp_path):
    repo, sha, _ = app_repo(tmp_path)
    noop = tmp_path / 'copy-only.patch'
    (repo / 'web/index.html').write_text((repo / 'web/index.html').read_text().replace('Fixture home', 'Fixture home page'))
    noop.write_text(subprocess.run(['git', 'diff'], cwd=repo, check=True, capture_output=True, text=True).stdout)
    subprocess.run(['git', 'checkout', '-q', '--', '.'], cwd=repo, check=True)
    r = repair_loop.loop(str(repo), sha, 'web', 'Find out how settlements are checked', noop, tmp_path / 'out', scripted_visit)
    assert r['check_before']['red_reason'] == 'error_page' and r['check_after']['red_reason'] == 'error_page'
    assert r['visit_after']['outcome'] != 'got_there' and r['repaired'] is False


def test_wrong_ref_and_remote_visit_are_refused(tmp_path):
    repo, sha, patch = app_repo(tmp_path)
    with pytest.raises(subprocess.CalledProcessError):
        repair_loop.loop(str(repo), 'deadbeef', 'web', 'Find it', patch, tmp_path / 'out', scripted_visit)
    with pytest.raises(ValueError, match='loopback'):
        repair_loop.nemotron_visit('https://example.com/', 'Find it', tmp_path / 'v')


def test_only_an_error_page_counts_as_reproducing_the_failure():
    assert repair_loop.red_reason("AssertionError: clicking 'About' opened a page that answered 404") == 'error_page'
    assert repair_loop.red_reason('Locator expected to have count \'1\'\nActual value: 0') == 'control_not_found'
    assert repair_loop.red_reason('ModuleNotFoundError: playwright') == 'other'


def test_recheck_rebuilds_both_trees_from_the_repo_and_patch(tmp_path, monkeypatch):
    repo, sha, patch = app_repo(tmp_path)
    r = repair_loop.loop(str(repo), sha, 'web', 'Find out how settlements are checked', patch, tmp_path / 'out', scripted_visit)
    for side in ('before', 'after'): shutil.rmtree(tmp_path / 'out' / f'app-{side}')
    monkeypatch.chdir(tmp_path)
    assert repair_loop.recheck('out') == {'before': 1, 'after': 0}   # relative folder; the rebuilt fix lands on the recorded commit
    assert r['after_sha'] == json.loads((tmp_path / 'out' / 'receipt.json').read_text())['after_sha']


def test_recheck_refuses_a_tree_edited_after_the_loop(tmp_path):
    repo, sha, patch = app_repo(tmp_path)
    repair_loop.loop(str(repo), sha, 'web', 'Find out how settlements are checked', patch, tmp_path / 'out', scripted_visit)
    (tmp_path / 'out' / 'app-before' / 'web' / 'about.html').write_text('<p>planted</p>')
    with pytest.raises(ValueError, match='edits'): repair_loop.recheck(tmp_path / 'out')


def test_nemotron_visit_accounts_every_call_and_names_the_model(tmp_path, monkeypatch):
    """Dry run of the sponsor path: real Budget and spend record, redirected to tmp; the client is scripted."""
    from sim import hosted_cost
    prior = tmp_path / 'prior.json'; prior.write_text(json.dumps({'runs': []}))
    monkeypatch.setattr(hosted_cost, 'PRIOR', prior); monkeypatch.setattr(hosted_cost, 'RECORD', tmp_path / 'cost.json')
    monkeypatch.setenv('TOKEN_FACTORY_API_KEY', 'test-value-never-sent')
    class Nano(Scripted):
        model = hosted_cost.MODEL
        def chat(self, messages, **kw):
            reply = super().chat(messages); reply.model = self.model; reply.usage = {'prompt_tokens': 900, 'completion_tokens': 40}; return reply
    monkeypatch.setattr(app_swarm, 'default_client_for', lambda person: Nano())
    repo, sha, patch = app_repo(tmp_path)
    r = repair_loop.loop(str(repo), sha, 'web', 'Find out how settlements are checked', patch, tmp_path / 'out',
                         lambda url, goal, out: repair_loop.nemotron_visit(url, goal, out, max_steps=3, run_cap_usd=0.05))
    assert r['repaired'] is True and r['sponsor_model_evidence'] is True
    spend = r['visit_before']['spend']
    assert spend['model_calls'] > 0 and spend['prompt_tokens'] == 900 * spend['model_calls'] and spend['provider_invoice_usd'] is None
    assert r['visit_before']['model'] == [hosted_cost.MODEL]
    assert len(json.loads((tmp_path / 'cost.json').read_text())['runs']) == spend['model_calls'] + r['visit_after']['spend']['model_calls']


def test_a_reply_from_another_model_is_not_sponsor_evidence(tmp_path, monkeypatch):
    from sim import hosted_cost
    prior = tmp_path / 'prior.json'; prior.write_text(json.dumps({'runs': []}))
    monkeypatch.setattr(hosted_cost, 'PRIOR', prior); monkeypatch.setattr(hosted_cost, 'RECORD', tmp_path / 'cost.json')
    monkeypatch.setenv('TOKEN_FACTORY_API_KEY', 'test-value-never-sent')
    class Other(Scripted):
        model = hosted_cost.MODEL
        def chat(self, messages, **kw):
            reply = super().chat(messages); reply.model = 'someone/else'; reply.usage = {'prompt_tokens': 900, 'completion_tokens': 40}; return reply
    monkeypatch.setattr(app_swarm, 'default_client_for', lambda person: Other())
    repo, sha, patch = app_repo(tmp_path)
    r = repair_loop.loop(str(repo), sha, 'web', 'Find out how settlements are checked', patch, tmp_path / 'out',
                         lambda url, goal, out: repair_loop.nemotron_visit(url, goal, out, max_steps=3))
    assert r['visit_before']['sponsor_model_evidence'] is False and r.get('repaired') is False
