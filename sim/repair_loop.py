"""Outside-app repair loop: a visitor fails on an app you own, you get a check, you fix, the same goal is tried again.

Order is fixed and every result is kept apart:
1. Clone the app at one exact commit and serve its static site on a loopback port as a plain static host.
2. One read-only model visitor tries the goal. Its steps and screens are retained.
3. The stopped path is handed back as a Playwright check (sim.studio_test). It must be red on the original.
4. The developer's patch is applied to a copy and committed, so the repaired tree has its own exact commit.
5. The same check runs on the repaired copy, then a fresh visitor tries the same goal on it.

`repaired` is true only when the check was red before, green after, and the second visitor completed the goal.
A green check alone is navigation smoke, not task completion. Visitors are models, not people.
`recheck` re-serves the retained trees and reruns the check with no model call.
"""
from __future__ import annotations

import argparse, contextlib, functools, hashlib, json, os, shutil, subprocess, sys, tempfile, threading, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from sim import app_swarm, hosted_cost, studio_test

SCHEMA = 'outside-repair-loop/1'
FIX_AUTHOR = ['-c', 'user.name=Repair Loop', '-c', 'user.email=repair-loop@example.invalid']
FIX_DATE = {'GIT_AUTHOR_DATE': '2026-10-26T00:00:00Z', 'GIT_COMMITTER_DATE': '2026-10-26T00:00:00Z'}


def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(cwd, *args, env=None):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, **(env or {})}).stdout.strip()


def checkout(repo, ref, dest):
    """The app exactly as committed. A short ref must resolve to one commit that starts with it."""
    subprocess.run(['git', 'clone', '--quiet', repo, str(dest)], check=True, capture_output=True, text=True)
    git(dest, 'checkout', '--quiet', '--detach', ref)
    sha = git(dest, 'rev-parse', 'HEAD')
    if not sha.startswith(ref): raise ValueError(f'{ref!r} resolved to {sha}, not the commit asked for.')
    return sha


def apply_fix(before, patch, after):
    """Copy the original, apply the patch, commit it. A patch that does not apply stops the loop."""
    shutil.copytree(before, after, symlinks=True)
    git(after, 'apply', '--check', str(Path(patch).resolve()))
    git(after, 'apply', str(Path(patch).resolve()))
    git(after, *FIX_AUTHOR, 'commit', '--quiet', '-am', 'Repair loop: apply ' + Path(patch).name, env=FIX_DATE)
    return git(after, 'rev-parse', 'HEAD'), git(after, 'diff', '--stat', 'HEAD~1', 'HEAD')


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass


@contextlib.contextmanager
def serve(directory):
    """A plain static host on loopback: files as they are, no rewrites, no clean URLs."""
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(_Quiet, directory=str(directory)))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}/'
    finally: server.shutdown(); server.server_close(); thread.join()


def red_reason(output):
    """Why a check was red. Only an error page reproduces the visitor's failure; a control the check cannot find does not."""
    if 'opened a page that answered' in output or 'start page answered' in output: return 'error_page'
    if 'to have count' in output or 'missing or ambiguous' in output: return 'control_not_found'
    return 'other'


def run_check(test, start_url, log):
    """Result of the handed-back check against one start URL: exit code and, when red, why. The full output is kept."""
    env = {**os.environ, 'SWARM_START_URL': start_url}; test = Path(test).resolve()
    call = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--rootdir', str(Path(test).parent), str(test)],
                          capture_output=True, text=True, timeout=120, env=env, cwd=Path(test).parent)
    Path(log).write_text(call.stdout + call.stderr)
    return {'exit': call.returncode, 'red_reason': red_reason(call.stdout) if call.returncode else None, 'log': Path(log).name}


def _loopback(url):
    u = urlsplit(url)
    if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost', '::1') or u.username or u.password:
        raise ValueError('Visitors only run against a loopback copy of an app you own.')


def nemotron_visit(url, goal, output, max_steps=4, run_cap_usd=0.05, judge=None):
    """One NVIDIA Nemotron Nano visitor through Nebius Token Factory. Every call is reserved against the spend record first.
    With `judge`, a separate model checks the completion claim instead of the visitor confirming its own."""
    _loopback(url)
    if app_swarm.needs_write(goal): raise ValueError('Only a read-only goal is permitted.')
    if judge and hosted_cost.judge_model() != judge.model:   # the spend stop prices only the operator-set judge
        raise ValueError(f'Set {hosted_cost.JUDGE_MODEL_ENV}={hosted_cost.JUDGE_MODEL} before running with a judge.')
    p = Path(output); p.mkdir(parents=True, exist_ok=False)
    app_swarm.require_key(); app_swarm.require_browser()
    person = {**app_swarm.CAST[0], 'id': 'nemotron-nano', 'goal': goal, 'max_steps': max_steps}
    budget = app_swarm.Budget(str(p.resolve()) + '/repair-loop', max_steps * 3, run_cap_usd)
    shared = {'blocked': [], 'errors': [], 'read_posts': []}
    def publish(row): (p / 'visitor.json').write_text(json.dumps(row, indent=2) + '\n')
    row = app_swarm._visit_one(p, person, app_swarm.default_client_for(person), budget, url, 0, time.monotonic(), publish, shared, judge=judge)
    spend = budget.summary()
    returned = spend['models']
    result = {'schema': 'nemotron-visitor/1', 'provider': app_swarm.PROVIDER, 'model_requested': spend['model'], 'models_returned': returned,
              'sponsor_model_evidence': spend['model'] in returned and set(returned) <= {spend['model'], *([judge.model] if judge else [])}
                                        and spend['calls_without_usage'] < spend['model_calls'],
              'judge_model': judge.model if judge else None, 'spend': spend, 'visitor': row, 'browser': shared,
              'limits': ['One model visitor, not a person.',
                         f'A separate judge model, {judge.model}, checked the completion claim.' if judge else
                         'The crowd model confirms its own claim; no independent judge in this visit.',
                         'Listed-rate estimate, not a provider invoice.']}
    (p / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def codex_visit(url, goal, output, max_steps=4):
    from sim import codex_visitor
    return codex_visitor.run(url, goal, output, max_steps)


VISITORS = {'nemotron': nemotron_visit, 'codex': codex_visit}


def _evidence(result):
    v = result['visitor']
    hit = next((s.get('hit') for s in v.get('steps', []) if s.get('status') == 'error_page'), None)
    return {'schema': result.get('schema'), 'sponsor_model_evidence': bool(result.get('sponsor_model_evidence')),
            'model': result.get('models_returned') or (result.get('model_identity') or {}).get('transport') or result.get('model'),
            'outcome': v.get('outcome'), 'confirmed': bool(v.get('confirmed')), 'steps': len(v.get('steps', [])),
            'path': [s.get('target_text') for s in v.get('steps', []) if s.get('action') == 'click'],
            'error_hit': hit and {'label': hit.get('label'), 'what_happened': hit.get('what_happened'), 'screenshot': hit.get('screenshot')},
            'last_words': next((s.get('wish') or s.get('say') for s in reversed(v.get('steps', [])) if s.get('wish') or s.get('say')), None),
            'spend': result.get('spend') and {k: result['spend'][k] for k in ('model_calls', 'prompt_tokens', 'completion_tokens', 'listed_rate_estimate_usd', 'provider_invoice_usd')},
            'subscription_calls': result.get('subscription_calls'), 'judge_model': result.get('judge_model')}


def loop(repo, ref, site_dir, goal, patch, output, visit, live_url=None, visit_after=None):
    """Run the whole loop once. `visit(url, goal, output)` returns a visitor result; every other step makes no model call.
    `visit_after`, when given, replaces `visit` for the repaired tree only, e.g. a visitor whose claim a separate judge checks."""
    out = Path(output); out.mkdir(parents=True, exist_ok=False)
    before, after = out / 'app-before', out / 'app-after'
    receipt = {'schema': SCHEMA, 'repo': repo, 'goal': goal, 'site_dir': site_dir, 'host': 'a plain static host on loopback (no rewrites, no clean URLs)',
               'started_at': app_swarm.stamp(), 'repaired': False}
    receipt['before_sha'] = checkout(repo, ref, before)
    def write(): (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    with serve(before / site_dir) as url:
        receipt['visit_before'] = _evidence(visit(url, goal, out / 'visit-before'))
        raw = json.loads((out / 'visit-before' / 'result.json').read_text())
        code = studio_test.generate({'id': 'repair-loop-' + receipt['before_sha'][:7], 'url': url, 'tries': [[raw['visitor']]]})
        write()
        if not code:
            receipt['stopped'] = 'The visitor clicked nothing, so there is no path to hand back as a check.'; write(); return receipt
        test = out / 'test_returned_path.py'; test.write_text(code)
        receipt['check'] = {'file': test.name, 'sha256': sha256(test), 'generated_from': 'visit-before/result.json',
                            'scope': 'Replays the recorded clicks and fails on an error page. Navigation smoke, not task completion.'}
        receipt['check_before'] = run_check(test, url, out / 'check-before.log')
    write()
    if receipt['check_before']['red_reason'] != 'error_page':
        receipt['stopped'] = ('The returned check is green on the original, so it does not reproduce the failure.' if not receipt['check_before']['exit'] else
                              'The returned check is red on the original for a reason other than the error page the visitor hit, so it does not reproduce the failure.')
        write(); return receipt
    receipt['patch'] = {'file': Path(patch).name, 'sha256': sha256(patch)}
    shutil.copy2(patch, out / Path(patch).name)
    receipt['after_sha'], receipt['patch']['diffstat'] = apply_fix(before, patch, after)
    with serve(after / site_dir) as url:
        receipt['check_after'] = run_check(test, url, out / 'check-after.log')
        write()
        receipt['visit_after'] = _evidence((visit_after or visit)(url, goal, out / 'visit-after'))
    if live_url:   # read-only GETs against the deployed original, for comparison only
        receipt['check_live_original'] = {'url': live_url, **run_check(test, live_url, out / 'check-live.log')}
    receipt['repaired'] = receipt['check_before']['red_reason'] == 'error_page' and receipt['check_after']['exit'] == 0 and receipt['visit_after']['outcome'] == 'got_there'
    receipt['sponsor_model_evidence'] = receipt['visit_before']['sponsor_model_evidence'] and receipt['visit_after']['sponsor_model_evidence']
    receipt['finished_at'] = app_swarm.stamp(); write(); (out / 'REPAIR.md').write_text(summary(receipt)); report(out)
    return receipt


REPORT_CSS = ''':root{--paper:#FFF6EC;--ink:#1E1A17;--coral:#FF7F5C;--green:#1F6B4E;--line:#D9CFC4;--mute:#5E554E;--card:#FFFDF9;--sans:'Avenir Next','Avenir','Nunito Sans','Segoe UI',sans-serif;--mono:ui-monospace,'SF Mono',Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 var(--sans)}main{max-width:1180px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:clamp(24px,3.4vw,38px);line-height:1.15;margin:0 0 10px;max-width:30ch}.lede{color:var(--mute);max-width:70ch;margin:0 0 22px}
.verdict{display:flex;flex-wrap:wrap;gap:10px 22px;align-items:center;padding:14px 16px;border:1px solid var(--line);background:var(--card);border-radius:10px;margin-bottom:26px}
.chip{font:600 13px var(--mono);padding:3px 9px;border-radius:99px;color:#fff}.chip.good,.out.good{background:var(--green)}.chip.bad,.out.bad{background:#B23A1E}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:22px}@media(max-width:760px){.cols{grid-template-columns:1fr}}
section h2{font-size:18px;margin:0 0 6px}.out{display:inline-block;color:#fff;font-weight:600;padding:2px 10px;border-radius:6px;margin:0 0 12px}
ol{list-style:none;padding:0;margin:0;display:grid;gap:12px}li{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}li.bad{border-color:#B23A1E}li.good{border-color:var(--green)}
li img{width:100%;border-radius:6px;border:1px solid var(--line);display:block;margin-bottom:8px}li b{display:block}q{display:block;color:var(--mute);font-size:14px;margin-top:4px}
h3{margin:34px 0 8px;font-size:18px}pre{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;overflow:auto;font:12.5px/1.45 var(--mono)}
pre .add{color:var(--green)}pre .del{color:#B23A1E}.small{color:var(--mute);font-size:14px;max-width:80ch}a{color:var(--ink)}
'''


def _step_line(s):
    if s.get('status') == 'error_page': return f"Clicked “{s.get('target_text')}”: the page answered {s.get('http_status') or 'an error'}"
    if s.get('status') == 'got_there': return 'Read it here, and a second check of the screen agreed'
    if s.get('action') == 'click': return f"Clicked “{s.get('target_text')}”"
    if s.get('action') == 'back': return 'Went back'
    if s.get('action') == 'stuck': return 'Gave up'
    return (s.get('action') or s.get('status') or '').replace('_', ' ')


def provenance(r):
    """One plain line: which model answered, how many calls, tokens and listed-rate cost. Only what the receipt holds."""
    sides = [r[k] for k in ('visit_before', 'visit_after') if r.get(k)]
    judges = sorted({v['judge_model'] for v in sides if v.get('judge_model')})
    models = sorted({m for v in sides for m in (v['model'] if isinstance(v['model'], list) else [v['model']]) if m and m not in judges})
    line = 'Visitor model: ' + (', '.join(models) or 'unknown') + '.' + (f" Separate judge model: {', '.join(judges)}." if judges else '')
    spends = [v['spend'] for v in sides if v.get('spend')]
    if spends:
        line += (f" {sum(s['model_calls'] for s in spends)} calls, {sum(s['prompt_tokens'] for s in spends):,} prompt and "
                 f"{sum(s['completion_tokens'] for s in spends):,} completion tokens, {sum(s['listed_rate_estimate_usd'] for s in spends):.5f} USD at listed rates (not an invoice).")
    return line + f" Sponsor model evidence: {'yes' if r.get('sponsor_model_evidence') else 'no'}."


def report(output):
    """One self-contained page for a person: both visits side by side, the check, the patch. Reads only the retained files."""
    import html
    out = Path(output); r = json.loads((out / 'receipt.json').read_text()); e = html.escape
    def column(side, sha):
        raw = json.loads((out / f'visit-{side}' / 'result.json').read_text())['visitor']
        cards = []
        for s in raw.get('steps', []):
            shot = s.get('screenshot'); words = s.get('quote') or s.get('wish') or s.get('say') or ''
            bad = s.get('status') in ('error_page', 'stuck')
            if s.get('status') == 'error_page' and (s.get('hit') or {}).get('screenshot'): shot = s['hit']['screenshot']
            cards.append(f'<li class="{"bad" if bad else "good" if s.get("status") == "got_there" else ""}">'
                         + (f'<img src="visit-{side}/{e(shot)}" alt="Screen at step {s.get("order")}" loading="lazy">' if shot else '')
                         + f'<b>{e(_step_line(s))}</b>' + (f'<q>{e(words[:220])}</q>' if words else '') + '</li>')
        verdict = {'got_there': 'Reached the goal', 'stuck': 'Stuck'}.get(raw.get('outcome'), (raw.get('outcome') or '').replace('_', ' '))
        return (f'<section><h2>{"Original" if side == "before" else "With the fix"} <code>{e(sha[:7])}</code></h2>'
                f'<p class="out {"good" if raw.get("outcome") == "got_there" else "bad"}">{e(verdict)}</p><ol>{"".join(cards)}</ol></section>')
    chip = lambda c: f'<span class="chip {"good" if c["exit"] == 0 else "bad"}">{"green" if c["exit"] == 0 else "red: " + e(c["red_reason"].replace("_", " "))}</span>'
    hit = (r['visit_before'].get('error_hit') or {}).get('what_happened') or ''
    live = r.get('check_live_original')
    patch = (out / r['patch']['file']).read_text()
    lines = ''.join(f'<span class="{"add" if l.startswith("+") and not l.startswith("+++") else "del" if l.startswith("-") and not l.startswith("---") else ""}">{e(l)}</span>\n' for l in patch.splitlines())
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Repair loop: {e(r['goal'])}</title>
<link rel="stylesheet" href="repair.css"><main>
<h1>{e(r['goal'])}</h1>
<p class="lede">A model visitor tried this on <a href="{e(r['repo'].removesuffix('.git'))}">{e(r['repo'].removesuffix('.git').split('github.com/')[-1])}</a>, served by {e(r['host'])}. {e(hit)} The stopped path came back as a check, the fix was applied as its own commit, and the same goal was tried again.</p>
<div class="verdict"><b>Repaired: {"yes" if r['repaired'] else "no"}</b><span>Check on original {chip(r['check_before'])}</span><span>Check with fix {chip(r['check_after'])}</span>{f'<span>Check on the deployed original {chip(live)}</span>' if live else ''}</div>
<div class="cols">{column('before', r['before_sha'])}{column('after', r.get('after_sha', ''))}</div>
<h3>The returned check · <a href="{e(r['check']['file'])}" download>download</a></h3>
<p class="small">Replays the visitor's recorded clicks and fails on an error page. It is navigation smoke: a pass alone does not show the goal was completed; the second visit above is what shows that.</p>
<pre>{e((out / r['check']['file']).read_text())}</pre>
<h3>The fix · <a href="{e(r['patch']['file'])}" download>{e(r['patch']['file'])}</a></h3><pre>{lines}</pre>
<p class="small">{e(provenance(r))} Visitors are models, not people; they only read. Source commits: original {e(r['before_sha'])}, fixed {e(r.get('after_sha', ''))}.</p>
</main></html>
'''
    (out / 'REPAIR.html').write_text(page); (out / 'repair.css').write_text(REPORT_CSS)
    return out / 'REPAIR.html'


def rebuild(r, out, work):
    """Recreate both trees from the repo and the retained patch. The fix commit is deterministic, so it must land on the recorded commit."""
    patch = out / r['patch']['file']
    if sha256(patch) != r['patch']['sha256']: raise ValueError('The patch changed since the loop ran.')
    checkout(r['repo'], r['before_sha'], work / 'app-before')
    apply_fix(work / 'app-before', patch, work / 'app-after')
    return work


def recheck(output):
    """Rerun the retained check on the before/after trees, rebuilt from the repo when the folder holds none. No model call."""
    out = Path(output); r = json.loads((out / 'receipt.json').read_text()); test = out / r['check']['file']
    if sha256(test) != r['check']['sha256']: raise ValueError('The check file changed since the loop ran.')
    with contextlib.ExitStack() as stack:
        trees = out if (out / 'app-before').exists() else rebuild(r, out, Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='repair-recheck-'))))
        return _recheck(r, out, trees, test)


class RecheckMismatch(ValueError):
    """The rerun check did not reproduce the recorded red before and green after."""


def _recheck(r, out, trees, test):
    recorded = {'before': r['check_before']['exit'], 'after': r['check_after']['exit']}
    if recorded['before'] == 0 or recorded['after'] != 0:
        raise RecheckMismatch(f'The receipt does not record red before and green after: {recorded}.')
    codes = {}
    for side in ('before', 'after'):
        tree = trees / f'app-{side}'
        if git(tree, 'rev-parse', 'HEAD') != r[f'{side}_sha']: raise ValueError(f'app-{side} is not at the recorded commit.')
        if git(tree, 'status', '--porcelain'): raise ValueError(f'app-{side} has edits on top of the recorded commit.')
        with serve(tree / r['site_dir']) as url: codes[side] = run_check(test, url, out / f'recheck-{side}.log')['exit']
    if codes != recorded: raise RecheckMismatch(f'Rerun codes {codes} differ from the recorded {recorded}.')
    return codes


def summary(r):
    vb, va = r['visit_before'], r.get('visit_after') or {}
    red = lambda c: 'green' if c['exit'] == 0 else f"red: {c['red_reason'].replace('_', ' ')}"
    lines = [f"# Repair loop: {r['repo']}", '', f"Goal: {r['goal']}", '',
             f"| | Original `{r['before_sha'][:7]}` | Repaired `{r.get('after_sha', '')[:7]}` |", '|---|---|---|',
             f"| Visitor outcome | {vb['outcome']} | {va.get('outcome')} |",
             f"| Visitor path | {' → '.join(p for p in vb['path'] if p) or '(none)'} | {' → '.join(p for p in va.get('path', []) if p) or '(none)'} |",
             f"| Returned check | {red(r['check_before'])} | {red(r['check_after'])} |", '',
             f"What the visitor hit: {(vb.get('error_hit') or {}).get('what_happened') or 'no error page'}",
             f"Fix: `{r['patch']['file']}` (sha256 {r['patch']['sha256'][:12]}…)", '',
             f"Repaired: **{'yes' if r['repaired'] else 'no'}** (red before, green after, and the same goal completed again).",
             provenance(r), '']
    if r.get('check_live_original'): lines += [f"Deployed original at {r['check_live_original']['url']}: {red(r['check_live_original'])}.", '']
    lines += ['Visitors are models, not people. The check is navigation smoke: a pass does not establish task completion by itself.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = a.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run'); r.add_argument('--repo', required=True); r.add_argument('--ref', required=True); r.add_argument('--site-dir', default='.')
    r.add_argument('--goal', required=True); r.add_argument('--patch', required=True); r.add_argument('--output', required=True)
    r.add_argument('--visitor', choices=sorted(VISITORS), required=True); r.add_argument('--max-steps', type=int, default=4)
    r.add_argument('--run-cap-usd', type=float, default=0.05); r.add_argument('--live-url')
    r.add_argument('--judge-after', action='store_true', help=f'a separate {hosted_cost.JUDGE_MODEL} judge checks the repaired visit (paid, nemotron only)')
    c = sub.add_parser('recheck'); c.add_argument('output')
    h = sub.add_parser('report'); h.add_argument('output')
    x = a.parse_args()
    if x.cmd == 'recheck':
        try: print(json.dumps(recheck(x.output)))
        except RecheckMismatch as e: sys.exit(f'recheck failed: {e}')
    elif x.cmd == 'report': print(report(x.output))
    else:
        if x.visitor == 'nemotron':
            if os.environ.get('CONFIRM_SPONSOR_SPEND') != 'RUN': a.error('Set CONFIRM_SPONSOR_SPEND=RUN to authorize the bounded Token Factory calls.')
            visit = functools.partial(nemotron_visit, max_steps=x.max_steps, run_cap_usd=x.run_cap_usd)
        else:
            if x.judge_after: a.error('--judge-after needs --visitor nemotron.')
            visit = functools.partial(codex_visit, max_steps=x.max_steps)
        visit_after = None
        if x.judge_after:
            os.environ[hosted_cost.JUDGE_MODEL_ENV] = hosted_cost.JUDGE_MODEL
            visit_after = functools.partial(nemotron_visit, max_steps=x.max_steps, run_cap_usd=x.run_cap_usd,
                                            judge=app_swarm.default_judge_for(app_swarm.CAST[0]))
        res = loop(x.repo, x.ref, x.site_dir, x.goal, x.patch, x.output, visit, x.live_url, visit_after)
        print(json.dumps({k: res.get(k) for k in ('repaired', 'before_sha', 'after_sha', 'check_before', 'check_after', 'stopped')}))
