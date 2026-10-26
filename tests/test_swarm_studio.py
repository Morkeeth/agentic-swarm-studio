"""Swarm studio: replay routes, the spending stop, the handed-back test and the read-only mount in First Users."""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from sim import app_swarm, hosted_cost, studio_test, swarm_studio

FIX = Path(__file__).resolve().parents[1] / 'web' / 'studio' / 'fixtures'


@pytest.fixture
def studio(tmp_path):
    return swarm_studio.Studio(tmp_path)


def test_page_and_replays_served_without_a_key(studio):
    landing = studio.get('/')
    assert landing[0] == 200 and landing[2] == 'text/html'
    assert b'Agentic Swarm Simulator' in landing[1] and b'/studio' in landing[1]
    assert studio.get('/landing.css')[2] == 'text/css'
    assert studio.get('/landing.js')[2] == 'application/javascript'
    outside = json.loads(studio.get('/api/landing/outside-run')[1])
    assert outside['status'] == 'complete' and len(outside['tools']) == 3
    assert studio.get('/landing-media/swarm-paths.png')[2] == 'image/png'
    assert studio.get('/landing-media/swarm-replay.mp4')[2] == 'video/mp4'
    assert studio.get('/landing-media/not-allowed.png')[0] == 404
    assert studio.get('/studio')[0] == 200
    assert studio.get('/review')[0] == 200
    assert studio.get('/review/review.css')[2] == 'text/css'
    assert studio.get('/review/review.js')[2] == 'application/javascript'
    css = studio.get('/landing.css')[1].decode().lower()
    assert not any(s in css for s in ('1f6b4e', '--green', 'box-shadow', 'gradient'))
    health = studio.get('/api/studio/health')[1]
    assert health['live_runs'] is False and set(health['replays']) == {'broken-demo-0003', 'swarm-2326', 'rerun-2335', 'airiq-about-404', 'airiq-about-fixed',
                                                                        'edunova-study-404', 'edunova-study-fixed', 'waterbuddy-v3-404', 'waterbuddy-v3-fixed',
                                                                        'blaze-server-routes', 'liarsdice-click-unseen', 'streeteats-sign-in', 'puppytime-lost',
                                                                        'overturn-nemotron-404', 'overturn-nemotron-fixed'}
    r = studio.get('/api/studio/replays/swarm-2326')
    assert r[0] == 200 and 'raw' not in r[1] and len(r[1]['tries'][0]) == 5
    shot = r[1]['tries'][0][0]['steps'][0]['screenshot']
    assert studio.get(f'/api/studio/replays/swarm-2326/{shot}')[2] == 'image/png'


@pytest.mark.parametrize('path', ['/api/studio/replays/../../etc/passwd', '/api/studio/replays/swarm-2326/result.json',
                                  '/api/studio/replays/swarm-2326/..%2fresult.json', '/api/studio/runs/nope', '/api/studio/cases/CASE-99.diff'])
def test_paths_outside_the_studio_are_refused(studio, path):
    r = studio.get(path)
    assert r is None or r[0] == 404


def test_cases_carry_ten_scored_fixes(studio):
    cases = json.loads(studio.get('/api/studio/cases')[1])['cases']
    scored = [c for c in cases if c['before'].get('runs') == 10]
    assert len(scored) == 10 and all(c['diff'] for c in scored)
    assert studio.get('/api/studio/cases/CASE-07.diff')[0] == 200


def test_live_run_refused_when_models_are_off(studio):
    with pytest.raises(ValueError, match='Live runs are off'):
        studio.start({'url': 'https://example.com'})


def test_stop_counts_every_row_under_the_account(tmp_path, monkeypatch):
    # Seed the ledger just under the stop; the next reservation must be refused before any provider call.
    monkeypatch.setattr(hosted_cost, 'RECORD', tmp_path / 'cost.json'); monkeypatch.setattr(hosted_cost, 'PRIOR', tmp_path / 'prior.json')
    hosted_cost.PRIOR.write_text('{"runs":[]}')
    hosted_cost.RECORD.write_text(json.dumps({'runs': {'acct/earlier-run': {'accounted_usd': 0.199}}}))
    swarm_studio.StopBudget.account, swarm_studio.StopBudget.stop, swarm_studio.StopBudget.run = 'acct', Decimal('0.20'), 'x'

    class Never:
        model = hosted_cost.MODEL
        def chat(self, *a, **k): raise AssertionError('provider must not be called')
    with pytest.raises(app_swarm.BudgetStop):
        swarm_studio.StopBudget('ignored', 10).call(Never(), [{'role': 'user', 'content': 'probe'}], 'probe', 0)
    assert swarm_studio.spent('acct') == Decimal('0.199')


def test_handed_back_test_follows_the_error_path():
    r = {'id': 'x', 'url': 'http://h/demo/notes-broken', 'tries': [[
        {'name': 'A', 'goal': 'g', 'outcome': 'stuck', 'steps': [{'action': 'scroll', 'status': 'no_effect'}]},
        {'name': 'B', 'goal': 'g', 'outcome': 'stuck', 'steps': [{'action': 'click', 'target_text': 'Read the guide', 'status': 'error_page',
                                                                 'hit': {'what_happened': 'error 404'}}]}]]}
    src = studio_test.generate(r)
    assert 'PATH = ["Read the guide"]' in src and 'Visitor: B' in src
    compile(src, 'generated.py', 'exec')
    assert studio_test.generate({'url': 'u', 'tries': [[{'name': 'A', 'goal': 'g', 'steps': []}]]}) is None


def test_demo_app_has_a_planted_404():
    assert swarm_studio.demo_page('/demo/notes/guide')[0] == 200
    assert swarm_studio.demo_page('/demo/notes-broken/guide')[0] == 404


def test_first_users_mounts_the_studio_read_only(tmp_path):
    from sim import first_users
    app = first_users.App(tmp_path, sample=True)
    try:
        assert app.studio.models is False
        assert app.studio.get('/api/studio/health')[1]['live_runs'] is False
    finally:
        app.stop.set()


def test_all_five_recorded_agents_are_counted(studio):
    runs = {r['id']: r for r in studio.replays()}
    assert runs['swarm-2326']['headline'] == '0 of 5 agents completed. 5 stuck.'
    assert runs['rerun-2335']['headline'] == '0 of 5 agents completed. 4 stuck. 1 interrupted.'


def test_library_has_saved_study_and_rejects_arbitrary_files(studio):
    status, body, kind = studio.get('/studio/evidence/library.json')
    data = json.loads(body)
    assert status == 200 and kind == 'application/json'
    assert len(data['hn']) == 20
    counts = data['counts']
    assert counts['clean'] + counts['untested'] + counts['not_green'] == counts['visited'] == 200
    assert studio.get('/studio/evidence/../../../etc/passwd')[0] == 404


def test_live_run_list_counts_every_recorded_agent(studio):
    r = json.loads((FIX / 'replays' / 'rerun-2335' / 'result.json').read_text())
    assert r['counts']['visitors'] == 4 and len(r['tries'][0]) == 5
    run = studio.store / 'runs' / 'run-0001'; run.mkdir(parents=True)
    (run / 'result.json').write_text(json.dumps(r))
    assert studio.runs()[0]['headline'] == '0 of 5 agents completed. 4 stuck. 1 interrupted.'


def test_start_refuses_when_the_stop_cannot_hold_every_visitor(tmp_path, monkeypatch):
    # Each visitor holds one worst-case reservation while its call is in flight. Five at once must fit under the stop,
    # or the last visitor is cut off mid-run with almost nothing spent (live run 19 Oct, stop USD 0.20).
    monkeypatch.setattr(hosted_cost, 'RECORD', tmp_path / 'cost.json'); monkeypatch.setenv('TOKEN_FACTORY_JUDGE_MODEL', hosted_cost.JUDGE_MODEL)
    monkeypatch.setattr(app_swarm, 'require_key', lambda: None)
    s = swarm_studio.Studio(tmp_path / 'store', models=True, account='acct', stop_usd='0.20')
    with pytest.raises(ValueError, match='Raise --stop-usd'):
        s.start({'url': 'https://example.com', 'visitors': 5})
    assert not list((tmp_path / 'store' / 'runs').iterdir())


def test_spent_reads_the_record_under_the_shared_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(hosted_cost, 'RECORD', tmp_path / 'cost.json')
    hosted_cost.RECORD.write_text(json.dumps({'runs': {'acct/a': {'accounted_usd': 0.01}}}))
    seen = []
    import fcntl
    monkeypatch.setattr(fcntl, 'flock', lambda f, op: seen.append(op))
    assert swarm_studio.spent('acct') == Decimal('0.01')
    assert fcntl.LOCK_SH in seen


class StubExplainer:
    """Stands in for the Nemotron call in a browser test. No network."""
    def __init__(self, delay=0.0): self.delay = delay
    def status(self):
        return {'model': hosted_cost.MODEL, 'provider': 'Nebius Token Factory', 'calls_total': 0, 'calls_today': 0,
                'daily_calls': 100, 'accounted_usd': 0.0, 'cap_usd': 0.5, 'min_interval_s': 10}
    def explain(self, replay, result):
        import time; time.sleep(self.delay)
        return {'text': 'Five agents got stuck.', 'model': hosted_cost.MODEL, 'provider': 'Nebius Token Factory', 'call': 1,
                'prompt_tokens': 278, 'completion_tokens': 43, 'latency_ms': 821, 'estimated_usd': 0.000027}


@pytest.fixture
def explain_page(tmp_path):
    sync = pytest.importorskip('playwright.sync_api')
    import threading
    from http.server import ThreadingHTTPServer
    def start(delay=0.0, route=None):
        studio = swarm_studio.Studio(tmp_path, explainer=StubExplainer(delay))
        server = ThreadingHTTPServer(('127.0.0.1', 0), swarm_studio.Handler); server.studio = studio
        threading.Thread(target=server.serve_forever, daemon=True).start(); servers.append(server)
        pw = sync.sync_playwright().start(); handles.append(pw)
        page = pw.chromium.launch().new_page()
        if route: page.route('**/api/studio/explain', route)
        page.goto(f'http://127.0.0.1:{server.server_port}/studio#replays/swarm-2326')
        page.wait_for_selector('#explain:not([hidden])')
        return page
    servers, handles = [], []
    yield start
    for s in servers: s.shutdown()
    for h in handles: h.stop()


def note_after_press(page, wait_ms=3000):
    page.click('#explain-go')
    page.wait_for_function("() => !document.querySelector('#explain-note').textContent.startsWith('Calling')", timeout=wait_ms)
    return page.inner_text('#explain-note')


def test_explain_shows_the_answer_with_model_and_cost(explain_page):
    note = note_after_press(explain_page())
    assert note.startswith('Live answer from nvidia/') and 'USD 0.000027' in note


def test_explain_never_stays_on_calling_when_the_reply_hangs(explain_page):
    page = explain_page(delay=4)
    page.evaluate("document.querySelector('#explain').dataset.timeoutMs = '500'")
    note = note_after_press(page, wait_ms=2500)
    assert note.startswith('No answer from Nemotron within')


def test_explain_names_a_rate_limit_in_plain_words(explain_page):
    page = explain_page(route=lambda route: route.fulfill(status=429, content_type='text/html', body='<html>Too Many Requests</html>'))
    assert note_after_press(page).startswith('Too many requests')


def test_the_real_app_replays_show_the_404_then_the_fixed_page(studio):
    """AirIQ, a real hackathon entry, unedited: all three visitors hit the 404 behind About Us; on the fork all three open the page."""
    before = studio.get('/api/studio/replays/airiq-about-404')[1]; after = studio.get('/api/studio/replays/airiq-about-fixed')[1]
    hit = [s for v in before['tries'][0] for s in v['steps'] if (s.get('hit') or {}).get('kind') == 'error_page']
    assert len(hit) == 3 and {s['target_text'] for s in hit} == {'About Us'} and {s['http_status'] for s in hit} == {404}
    opened = [s for v in after['tries'][0] for s in v['steps'] if s.get('target_text') == 'About Us']
    assert len(opened) == 3 and all(s['status'] == 'ok' and s['http_status'] == 200 for s in opened)
    assert after['counts']['screen_confirmed'] == 3 and after['counts']['confirmed'] == 0      # the strict job-done check is reported as it is
    src = (FIX / 'replays' / 'airiq-about-404' / 'test_swarm_path.py').read_text()
    returned = studio.get('/api/studio/replays/airiq-about-404/test.py')[1].decode()
    assert returned == studio_test.generate(json.loads((FIX / 'replays' / 'airiq-about-404' / 'result.json').read_text()))
    assert 'target.count() == 1' in returned  # an inert matching paragraph is not a control
    assert 'PATH = ["About Us"]' in src and 'PATH = ["About Us"]' in returned
    assert before['replay']['diagnosis'].startswith('A real hackathon app')


@pytest.mark.parametrize('name, label', [('edunova-study', 'Study Mentor'), ('waterbuddy-v3', 'Earlier V3 exploration \u2197')])
def test_more_real_apps_show_the_404_then_none_after_the_fork_fix(studio, name, label):
    """Two more entries from the 122-app sweep: two of three visitors hit a 404 on the original, no visitor hits one on the fork."""
    before = studio.get(f'/api/studio/replays/{name}-404')[1]; after = studio.get(f'/api/studio/replays/{name}-fixed')[1]
    hit = [(v['id'], s['target_text'], s['http_status']) for v in before['tries'][0] for s in v['steps'] if s.get('status') == 'error_page']
    assert sorted(hit) == [('buyer', label, 404), ('newcomer', label, 404)]
    assert not [s for v in after['tries'][0] for s in v['steps'] if s.get('status') == 'error_page']
    assert before['replay']['diagnosis'].startswith('A real hackathon app') and after['counts']['confirmed'] == 0


def test_the_landing_counts_the_replay_records_and_links_one_replay_per_kind(studio, tmp_path, monkeypatch):
    import re, shutil
    page = studio.get('/')[1].decode()
    n = len([p for p in (FIX / 'replays').iterdir() if (p / 'result.json').is_file()])
    assert '<!--replay-count-->' not in page and f'All {n} recorded swarms' in page and f'<dd>{n}</dd>' in page
    assert re.search(r'122 real hackathon apps, 113 hackathons', page)
    linked = set(re.findall(r'/studio#replays/([\w-]+)', page))
    assert linked <= set(studio.health()['replays'])           # every replay the page links exists
    # one more replay record moves the number without touching the page
    fix = tmp_path / 'fix'; shutil.copytree(FIX / 'replays', fix / 'replays'); shutil.copytree(FIX / 'replays' / 'swarm-2326', fix / 'replays' / 'zz-copy')
    monkeypatch.setattr(swarm_studio, 'FIX', fix)
    assert f'All {n + 1} recorded swarms' in studio.get('/')[1].decode()


def test_the_landing_leads_with_fresh_outside_evidence_then_one_try_entry(studio):
    page = studio.get('/')[1].decode()
    result = page.index('class="result-board"')
    apps = page.index('id="apps"')
    assert result < apps
    assert 'Three public tools. Three visitors each. One checked task.' in page
    assert 'No earlier tool trial or cached case is substituted here.' in page
    assert '19% → 70%' not in page and '10 of 10' not in page
    assert page.count('Open the release rehearsal') == 1
    assert 'GitHub repo import needs OAuth registration' in page


def test_the_landing_hero_uses_real_replays_and_spells_out_the_journey(studio):
    page = studio.get('/')[1].decode()
    assert 'id="swarm-map"' in page and 'Recorded release rehearsal' in page
    assert all(f'data-replay="{name}"' in page for name in ('puppytime-lost', 'airiq-about-404', 'liarsdice-click-unseen'))
    assert all(step in page for step in ('Land', 'Pick an app', 'Watch rehearsal', 'Read result'))
    assert 'Replay recorded paths' in page
    assert 'Loading the retained run' not in page and 'Loading fresh evidence' not in page
    script = studio.get('/landing.js')[1].decode()
    assert '/api/studio/replays/' in script and 'prefers-reduced-motion: reduce' in script
    assert "result.textContent = 'Loading" not in script
    assert not any(word in page for word in ('🚀', '✨', '🔥'))


def test_the_recorded_result_page_labels_its_play_control_as_playback(studio):
    page = studio.get('/studio')[1].decode()
    assert 'Play recorded path' in page
    assert 'Pick a recorded run.' in page


def test_the_landing_keeps_the_original_palette_and_animates_agents_safely(studio):
    css = studio.get('/landing.css')[1].decode().lower()
    script = studio.get('/landing.js')[1].decode().lower()
    assert all(token in css for token in ('--paper:#fff6ec', '--ink:#1e1a17', '--coral:#ff7f5c'))
    assert 'border-radius:6px' in css and '@keyframes pulse' in css
    assert '@keyframes path-flow' in css and '@media(prefers-reduced-motion:reduce)' in css
    assert "const colours = ['#ff7f5c', '#1e1a17', '#9c351b']" in script
    assert "class: 'moving-agent'" in script and "'aria-hidden': 'true'" in script
    assert 'y: y + 23' in script
    assert 'y: y - 14' not in script
    assert '.swarm-stage{order:-1' in css


def test_tool_cards_refuse_to_reuse_the_old_curated_score(studio):
    page = studio.get('/')[1].decode()
    assert 'id="outside-results"' in page and 'No earlier tool trial or cached case is substituted here.' in page
    assert '19% → 70%' not in page and 'Scored runs</dt><dd>200' not in page
    script = studio.get('/landing.js')[1].decode()
    assert '/api/landing/outside-run' in script


def test_fresh_outside_result_is_served_without_rewriting_it(studio, tmp_path, monkeypatch):
    landing = tmp_path / 'landing'; landing.mkdir()
    payload = {'status': 'complete', 'tools': [{'name': 'Git'}, {'name': 'ripgrep'}, {'name': 'jq'}]}
    (landing / 'outside-run.json').write_text(json.dumps(payload))
    monkeypatch.setattr(swarm_studio, 'LANDING', landing)
    status, body, kind = studio.get('/api/landing/outside-run')
    assert status == 200 and kind == 'application/json' and json.loads(body) == payload


def test_every_third_party_replay_names_its_repo_and_licence_and_the_landing_marks_the_unlicensed(studio):
    """Screens of other people's apps ship only with a README row for the app: repo, licence as GitHub reports it, date checked."""
    import re
    own = {'broken-demo-0003', 'swarm-2326', 'rerun-2335', 'overturn-nemotron-404', 'overturn-nemotron-fixed'}   # Overturn: same author, MIT
    rows = {a: (repo, lic) for a, repo, lic in re.findall(r'^\| ([^|]+?) \| (https://github\.com/\S+) \| ([^|]+?) \|', (FIX.parents[2] / 'README.md').read_text(), re.M)}
    page = studio.get('/')[1].decode()
    for p in sorted((FIX / 'replays').iterdir()):
        if p.name in own:
            continue
        app = re.match(r'Three visitors, (.+?)(?: \(| after )', json.loads((p / 'result.json').read_text())['replay']['label']).group(1)
        assert app in rows, f'{p.name}: no licence row for {app}'
        if rows[app][1] == 'none published':
            row = re.search(rf'<th scope="row">{re.escape(app)}</th>.*?</tr>', page)
            assert row and 'no licence' in row.group(0), f'{app}: Table 0 does not say the repo has no licence'


def test_the_landing_speaks_to_the_person_who_builds_the_app_not_to_us(studio):
    """A judge reads the front page as an app builder would: it says who it is for and uses none of our in-house words."""
    page = studio.get('/')[1].decode().lower()
    assert not [w for w in ('harness', 'hash-routed', 'floor plan', 'software visitors') if w in page]
    assert 'for anyone who builds a web app' in page


def test_release_rehearsal_is_the_studio_front_door_and_research_sits_under_the_result(studio):
    """The approved 1a loop is primary, while 1b supports the result instead of becoming a second product."""
    page = studio.get('/studio')[1].decode()
    assert 'Try your product before your users do.' in page
    assert '<input type="hidden" name="visitors" value="3">' in page
    assert page.index('id="run"') < page.index('id="live-progress"') < page.index('class="stage"')
    assert page.index('class="research-result"') > page.index('id="limits"')
    assert 'Does this look like earlier rehearsals?' in page
    replay_ids = set(studio.health()['replays'])
    assert {'airiq-about-404', 'puppytime-lost', 'liarsdice-click-unseen'} <= replay_ids


def test_generated_test_redacts_provider_key_before_disk(tmp_path, monkeypatch):
    from sim import tool_trial
    from sim.adapters import tokenfactory
    secret = 'fake-provider-key-never-write-this'
    studio = swarm_studio.Studio(tmp_path)
    studio.models = True
    studio.account = 'test'
    folder = tmp_path / 'runs' / 'redaction'
    folder.mkdir()
    tool_trial.dump(folder / 'result.json', {'status': 'complete'})
    monkeypatch.setattr(app_swarm, 'run', lambda *a, **k: None)
    monkeypatch.setattr(swarm_studio, 'spent', lambda *a: Decimal(0))
    monkeypatch.setattr(tokenfactory, 'load_key', lambda: secret)
    monkeypatch.setattr(studio_test, 'generate', lambda result: '# echoed ' + secret)
    studio.busy.acquire()
    studio._run(folder, 'redaction', [])
    written = (folder / 'test_swarm_path.py').read_text()
    assert secret not in written
    assert '[REDACTED]' in written
    assert not studio.busy.locked()
