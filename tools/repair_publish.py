"""Publish one retained repair-loop run into the hosted app, with no model call.

Writes two studio replays (the visit before the fix and the visit after it) and a
static copy of the report, check, patch and receipt under web/repair/<name>/.
Every value comes from the retained files; nothing is re-run or re-scored.

    python tools/repair_publish.py examples/overturn overturn
"""
import hashlib, json, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim import app_swarm, repair_loop  # noqa: E402

REPLAYS = ROOT / 'web' / 'studio' / 'fixtures' / 'replays'
SHIPPED = ('REPAIR.html', 'repair.css', 'REPAIR.md', 'receipt.json', 'test_returned_path.py', 'check-before.log', 'check-after.log', 'check-live.log')


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def replay(src, r, side, name):
    raw = json.loads((src / f'visit-{side}' / 'result.json').read_text()); v = raw['visitor']
    s = app_swarm.summarize([[v]], False); spend = raw.get('spend') or {}
    sha_side = r['before_sha'] if side == 'before' else r['after_sha']
    before = side == 'before'
    diagnosis = (f"Outside app: Overturn, public repo by the same author, commit {sha_side[:7]}, served as plain files (no Vercel rewrites). "
                 + ("The NVIDIA Nemotron Nano visitor clicked About and the page answered 404, tried Why this exists, got 404 again and gave up. "
                    "Its path came back as the test below, which is red on this commit." if before else
                    "This is the same goal after the fix commit. The visitor opened About and a second Nemotron call agreed the screen shows why Overturn exists. "
                    "The same test is green here.")
                 + f" Recorded on {r['started_at'][:10]}; playback makes no model call. Full before and after: /repair/{name}/")
    out = {'id': f'{name}-nemotron-{"404" if before else "fixed"}', 'url': v['steps'][0]['url'] if v.get('steps') else '', 'status': 'complete',
           'browser': 'Playwright Chromium', 'provider': raw.get('provider'), 'model': raw.get('model_requested'), 'judge_model': raw.get('model_requested'),
           'tries_planned': 1, 'visitors_planned': 1, 'tries': [[v]], 'rounds': [{'try': 1, 'elapsed_ms': v.get('end_ms', 0)}],
           'job': {'text': r['goal'], 'source': 'operator', 'label': 'Goal set by the developer'}, 'baseline': [],
           'visitors': s['visitors'], 'findings': s['findings'], 'fixes': s['findings'], 'fixes_note': s['findings_note'], 'seen_once': s['seen_once'],
           'sceptic': s['sceptic'], 'set_aside': s['set_aside'], 'headline': s['headline'], 'verdict': s['headline'],
           'counts': {**s['counts'], 'steps': len(v.get('steps', []))}, 'spend': spend, 'model_calls': spend.get('model_calls'),
           'model_cost_usd': spend.get('listed_rate_estimate_usd'), 'held_back': 0, 'finished_at': r.get('finished_at'),
           'limitations': ['One NVIDIA Nemotron Nano visitor, not a person. It only reads.',
                           'Recorded run. Playback makes no model call and does not repair anything on this server.',
                           'Listed-rate cost is an estimate from returned token counts, not a provider invoice.'],
           'replay': {'name': f'{name}-nemotron-{"404" if before else "fixed"}',
                      'label': f'Repair loop {"before" if before else "after"} the fix, Overturn {sha_side[:7]}, Nemotron Nano, {r["started_at"][:10]}',
                      'diagnosis': diagnosis, 'source': f'examples/{name}/visit-{side}/result.json', 'sha256': sha(src / f'visit-{side}' / 'result.json')}}
    d = REPLAYS / out['id']
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / 'result.json').write_text(json.dumps(out, indent=2) + '\n')
    for png in (src / f'visit-{side}').glob('*.png'): shutil.copy2(png, d / png.name)
    return out['id']


def publish(src, name):
    src = Path(src); r = json.loads((src / 'receipt.json').read_text())
    if not r.get('repaired') or not r.get('sponsor_model_evidence'): raise ValueError('Only a repaired run with sponsor model evidence is published.')
    repair_loop.report(src)   # current report layout, from the retained receipt
    web = ROOT / 'web' / 'repair' / name
    if web.exists(): shutil.rmtree(web)
    web.mkdir(parents=True)
    for f in (*SHIPPED, r['patch']['file']): shutil.copy2(src / f, web / f)
    for side in ('before', 'after'):
        (web / f'visit-{side}').mkdir()
        for f in (src / f'visit-{side}').iterdir(): shutil.copy2(f, web / f'visit-{side}' / f.name)
    if sha(web / 'test_returned_path.py') != r['check']['sha256'] or sha(web / r['patch']['file']) != r['patch']['sha256']:
        raise ValueError('Published check or patch does not match the receipt.')
    return [replay(src, r, 'before', name), replay(src, r, 'after', name)]


if __name__ == '__main__':
    print(json.dumps(publish(sys.argv[1], sys.argv[2])))
