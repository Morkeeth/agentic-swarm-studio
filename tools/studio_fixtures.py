"""Copy the recorded swarm runs and the ten before/after cases into the studio, so it serves them without the state folder.

Run: python3 tools/studio_fixtures.py NIGHT_DIR
NIGHT_DIR holds nvidia-swarm-2326, nvidia-harness-2335 and nvidia-cases-2320. Each copied file keeps its sha256 in SOURCES.json.
"""
import hashlib, json, shutil, sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'web' / 'studio' / 'fixtures'
REPLAYS = {'broken-demo-0003': ('swarm-product-2350/store/runs/20261018-000344-dd00ad', 'Three visitors, broken demo app, Super VL judge, 18 Oct 00:03'),
           'swarm-2326': ('nvidia-swarm-2326', 'Five visitors, working sample, 17 Oct 23:26'),
           'rerun-2335': ('nvidia-harness-2335', 'Five visitors after the quote repair, 17 Oct 23:38')}
DROP = ('raw',)


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(night):
    night = Path(night); sources = {}
    if OUT.exists(): shutil.rmtree(OUT)
    for name, (folder, label) in REPLAYS.items():
        src = night / folder; dst = OUT / 'replays' / name; dst.mkdir(parents=True)
        r = json.loads((src / 'result.json').read_text())
        for k in DROP: r.pop(k, None)
        r['replay'] = {'name': name, 'label': label, 'source': f'{folder}/result.json', 'sha256': sha(src / 'result.json')}
        shots = {s['screenshot'] for t in r['tries'] for v in t for s in v['steps'] if s.get('screenshot')}
        shots |= {(s.get('hit') or {}).get('screenshot') for t in r['tries'] for v in t for s in v['steps']} - {None}
        if (src / 'test_swarm_path.py').is_file(): shutil.copy2(src / 'test_swarm_path.py', dst / 'test_swarm_path.py')
        for s in sorted(shots):
            if (src / s).is_file(): shutil.copy2(src / s, dst / s); sources[f'replays/{name}/{s}'] = sha(src / s)
        (dst / 'result.json').write_text(json.dumps(r))
        sources[f'replays/{name}/result.json'] = r['replay']['sha256']
    cases_src = night / 'nvidia-cases-2320'; d = json.loads((cases_src / 'CASES.json').read_text()); cases = []
    for c in d['cases']:
        folder = c['fix'].get('patch_receipt', '').split('/')[0] if c.get('fix') else ''
        diff = cases_src / folder / 'fix.diff'
        row = {k: c.get(k) for k in ('id', 'flow', 'task', 'scope', 'delta', 'status')}
        row.update({'fix': (c.get('fix') or {}).get('description'), 'files': (c.get('fix') or {}).get('changed_files', []),
                    'judge': (c.get('judge') or {}).get('name'), 'before': c.get('before'), 'after': c.get('after'), 'paired': c.get('paired')})
        if diff.is_file():
            (OUT / 'cases').mkdir(parents=True, exist_ok=True); shutil.copy2(diff, OUT / 'cases' / f"{c['id']}.diff")
            row['diff'] = f"{c['id']}.diff"; sources[f"cases/{c['id']}.diff"] = sha(diff)
        cases.append(row)
    (OUT / 'cases.json').write_text(json.dumps({'cases': cases, 'limitations': d.get('limitations'), 'score_comparability': d.get('score_comparability'),
                                                 'source': 'nvidia-cases-2320/CASES.json', 'sha256': sha(cases_src / 'CASES.json')}, indent=1))
    (OUT / 'SOURCES.json').write_text(json.dumps(sources, indent=1, sort_keys=True))
    print(f'{len(REPLAYS)} replays, {len(cases)} cases, {len(sources)} files into {OUT}')


if __name__ == '__main__': main(sys.argv[1])
