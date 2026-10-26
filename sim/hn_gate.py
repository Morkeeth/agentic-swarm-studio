"""The Show HN clean-visit gate, with an optional robots split. Reads saved outcomes only.

The default is the 16 Oct gate, unchanged: any request our robots guard held back makes a
visit not green. With split_robots, a visit whose only problem was our own robots guard is
counted apart as "respected, skipped". It is still not green: the skipped part was never seen.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

STEPS = ['Open the app', 'Try the first visible reading path', 'Return to the starting page']
# Kinds our guard records when it obeys a site's robots rules. A blocked socket is not one of them.
ROBOTS = {'robots-rule', 'robots-unavailable-or-denied', 'positive-crawl-delay-resource-skip'}
ALLOWED = {'write-method'}          # background writes are always held back and never fail a visit


def _fast(snap):
    fcp = snap.get('first_contentful_paint_ms')
    return 0 < (snap.get('dcl_ms') or 0) <= 3000 and fcp is not None and 0 < fcp <= 3000


def _clean_except_blocks(o, steps_run):
    if o.get('skipped') or o.get('worker_error') or o.get('instrument_error') or o.get('script_errors'): return False
    steps, snaps = o.get('steps', []), o.get('snapshots', [])
    if [s.get('label') for s in steps] != STEPS[:len(steps)] or len(steps) < steps_run: return False
    if any(s.get('status') != 'passed' for s in steps[:steps_run]): return False
    if len(snaps) < steps_run or any(s.get('capture_error') for s in snaps): return False
    if any(s.get('password_fields') or s.get('must_auth') or s.get('challenge') for s in snaps): return False
    return bool(snaps) and _fast(snaps[0])


def verdict(o, split_robots=False):
    """green, respected_skipped (split_robots only) or not_green."""
    blocked = {k for k, v in o.get('blocked_counts', {}).items() if v}
    nav = o.get('blocked_navigation') or []
    if not nav and blocked <= ALLOWED and len(o.get('steps', [])) == 3 and len(o.get('snapshots', [])) == 3 \
            and _clean_except_blocks(o, 3):
        return 'green'
    if not split_robots or not blocked - ALLOWED <= ROBOTS or not all(x.get('kind') in ROBOTS for x in nav):
        return 'not_green'
    if not nav:      # every step passed; only background files were refused by robots rules
        return 'respected_skipped' if len(o.get('steps', [])) == 3 and _clean_except_blocks(o, 3) else 'not_green'
    # A step's page was refused by robots rules: the steps before it passed, it and the rest were not tried.
    steps = o.get('steps', [])
    first = next((i for i, s in enumerate(steps) if s.get('status') != 'passed'), len(steps))
    if first == len(steps) or any(s.get('status') == 'passed' for s in steps[first:]): return 'not_green'
    return 'respected_skipped' if first >= 1 and _clean_except_blocks(o, first) else 'not_green'


def qualifies(o, split_robots=False):
    return verdict(o, split_robots) == 'green'


def recount(run_dir, split_robots=False):
    outs = [json.loads(p.read_text()) for p in sorted(Path(run_dir).glob('outcome-*.json'))]
    visited = [o for o in outs if not o.get('skipped')]
    counts = {'outcomes': len(outs), 'skipped': len(outs) - len(visited), 'visited': len(visited), 'green': 0, 'not_green': 0}
    if split_robots: counts['respected_skipped'] = 0
    for o in visited: counts[verdict(o, split_robots)] += 1
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Recount a saved Show HN run. Read only, no network.')
    parser.add_argument('run_dir'); parser.add_argument('--split-robots', action='store_true')
    a = parser.parse_args()
    print(json.dumps(recount(a.run_dir, a.split_robots), indent=2))
