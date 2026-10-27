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


def test_recheck_fails_when_the_rerun_does_not_match_the_receipt(tmp_path, monkeypatch):
    repo, sha, patch = app_repo(tmp_path)
    repair_loop.loop(str(repo), sha, 'web', 'Find out how settlements are checked', patch, tmp_path / 'out', scripted_visit)
    real = repair_loop.run_check
    monkeypatch.setattr(repair_loop, 'run_check', lambda test, url, log: {**real(test, url, log), 'exit': 0})   # a check that never goes red
    with pytest.raises(repair_loop.RecheckMismatch, match='differ from the recorded'): repair_loop.recheck(tmp_path / 'out')


def test_recheck_refuses_a_receipt_without_red_before_and_green_after(tmp_path):
    repo, sha, patch = app_repo(tmp_path)
    repair_loop.loop(str(repo), sha, 'web', 'Find out how settlements are checked', patch, tmp_path / 'out', scripted_visit)
    receipt = tmp_path / 'out' / 'receipt.json'; r = json.loads(receipt.read_text())
    r['check_before']['exit'] = 0; receipt.write_text(json.dumps(r))
    with pytest.raises(repair_loop.RecheckMismatch, match='does not record red before'): repair_loop.recheck(tmp_path / 'out')


def test_recheck_cli_exits_nonzero_on_mismatch(tmp_path):
    import sys
    repo, sha, patch = app_repo(tmp_path)
    repair_loop.loop(str(repo), sha, 'web', 'Find out how settlements are checked', patch, tmp_path / 'out', scripted_visit)
    receipt = tmp_path / 'out' / 'receipt.json'; r = json.loads(receipt.read_text())
    r['check_after']['exit'] = 1; receipt.write_text(json.dumps(r))
    run = subprocess.run([sys.executable, '-m', 'sim.repair_loop', 'recheck', str(tmp_path / 'out')], capture_output=True, text=True,
                         cwd=Path(repair_loop.__file__).resolve().parents[1])
    assert run.returncode != 0 and 'recheck failed' in run.stderr


def test_a_separate_judge_checks_only_the_repaired_visit(tmp_path, monkeypatch):
    """Dry run: Nano visitor and Super VL judge are both scripted. No provider call is made."""
    from sim import hosted_cost
    prior = tmp_path / 'prior.json'; prior.write_text(json.dumps({'runs': []}))
    monkeypatch.setattr(hosted_cost, 'PRIOR', prior); monkeypatch.setattr(hosted_cost, 'RECORD', tmp_path / 'cost.json')
    monkeypatch.setenv('TOKEN_FACTORY_API_KEY', 'test-value-never-sent'); monkeypatch.setenv(hosted_cost.JUDGE_MODEL_ENV, hosted_cost.JUDGE_MODEL)
    usage = {'prompt_tokens': 900, 'completion_tokens': 40}
    class Nano(Scripted):
        model = hosted_cost.MODEL
        def chat(self, messages, **kw):
            reply = super().chat(messages); reply.model = self.model; reply.usage = usage; return reply
    class Judge(Scripted):
        model = hosted_cost.JUDGE_MODEL
        seen = []
        def chat(self, messages, **kw):
            Judge.seen.append(messages[0]['content'][:30])
            screen = messages[-1]['content']   # a judge that reads images gets text plus a JPEG of the screen
            if isinstance(screen, list):
                assert any(x.get('type') == 'image_url' for x in screen)
                messages = messages[:-1] + [{'role': 'user', 'content': next(x['text'] for x in screen if x.get('type') == 'text')}]
            reply = super().chat(messages); reply.model = self.model; reply.usage = usage; return reply
    monkeypatch.setattr(app_swarm, 'default_client_for', lambda person: Nano())
    repo, sha, patch = app_repo(tmp_path)
    r = repair_loop.loop(str(repo), sha, 'web', 'Find out how settlements are checked', patch, tmp_path / 'out',
                         lambda url, goal, out: repair_loop.nemotron_visit(url, goal, out, max_steps=3),
                         visit_after=lambda url, goal, out: repair_loop.nemotron_visit(url, goal, out, max_steps=3, judge=Judge()))
    assert Judge.seen and all(s.startswith('You check whether') for s in Judge.seen)
    assert r['visit_before']['judge_model'] is None and r['visit_after']['judge_model'] == hosted_cost.JUDGE_MODEL
    assert r['repaired'] is True and r['sponsor_model_evidence'] is True
    assert sorted(r['visit_after']['model']) == sorted([hosted_cost.MODEL, hosted_cost.JUDGE_MODEL])
    after = json.loads((tmp_path / 'out' / 'visit-after' / 'result.json').read_text())
    assert any('separate judge model' in x for x in after['limits'])
    assert 'Separate judge model: ' + hosted_cost.JUDGE_MODEL in (tmp_path / 'out' / 'REPAIR.md').read_text()


def test_a_judge_that_says_no_keeps_the_repair_unproven(tmp_path, monkeypatch):
    from sim import hosted_cost
    prior = tmp_path / 'prior.json'; prior.write_text(json.dumps({'runs': []}))
    monkeypatch.setattr(hosted_cost, 'PRIOR', prior); monkeypatch.setattr(hosted_cost, 'RECORD', tmp_path / 'cost.json')
    monkeypatch.setenv('TOKEN_FACTORY_API_KEY', 'test-value-never-sent'); monkeypatch.setenv(hosted_cost.JUDGE_MODEL_ENV, hosted_cost.JUDGE_MODEL)
    usage = {'prompt_tokens': 900, 'completion_tokens': 40}
    class Nano(Scripted):
        model = hosted_cost.MODEL
        def chat(self, messages, **kw):
            reply = super().chat(messages); reply.model = self.model; reply.usage = usage; return reply
    class Sceptic(Nano):
        model = hosted_cost.JUDGE_MODEL
        def chat(self, messages, **kw):
            return SimpleNamespace(text=json.dumps({'done': False, 'evidence': '', 'why': 'Not shown.'}), model=self.model, usage=usage)
    monkeypatch.setattr(app_swarm, 'default_client_for', lambda person: Nano())
    repo, sha, patch = app_repo(tmp_path)
    r = repair_loop.loop(str(repo), sha, 'web', 'Find out how settlements are checked', patch, tmp_path / 'out',
                         lambda url, goal, out: repair_loop.nemotron_visit(url, goal, out, max_steps=3),
                         visit_after=lambda url, goal, out: repair_loop.nemotron_visit(url, goal, out, max_steps=3, judge=Sceptic()))
    assert r['check_after']['exit'] == 0 and r['visit_after']['outcome'] != 'got_there' and r['repaired'] is False


def test_a_judge_without_the_operator_setting_is_refused(tmp_path, monkeypatch):
    from sim import hosted_cost
    monkeypatch.delenv(hosted_cost.JUDGE_MODEL_ENV, raising=False)
    judge = SimpleNamespace(model=hosted_cost.JUDGE_MODEL)
    with pytest.raises(ValueError, match=hosted_cost.JUDGE_MODEL_ENV):
        repair_loop.nemotron_visit('http://127.0.0.1:9/', 'Find out how settlements are checked', tmp_path / 'v', judge=judge)
    assert not (tmp_path / 'v').exists()
