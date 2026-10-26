"""The Show HN gate, with and without the robots split. No network: outcomes are read from disk."""
import json
import os
from pathlib import Path

import pytest

from sim import hn_gate

RUN = Path(os.environ.get('NVIDIA_HN_RUN', '/nonexistent/nvidia-hn-run'))
LABELS = ['Open the app', 'Try the first visible reading path', 'Return to the starting page']


def outcome(**over):
    snap = {'dcl_ms': 400, 'first_contentful_paint_ms': 500.0}
    o = {'steps': [{'label': x, 'status': 'passed'} for x in LABELS], 'snapshots': [dict(snap) for _ in LABELS],
         'blocked_counts': {}, 'blocked_navigation': [], 'script_errors': []}
    o.update(over)
    return o


def test_a_clean_visit_is_green_either_way():
    assert hn_gate.verdict(outcome()) == 'green' and hn_gate.verdict(outcome(), split_robots=True) == 'green'


def test_a_robots_block_fails_by_default_and_is_respected_with_the_flag():
    o = outcome(blocked_counts={'robots-rule': 14, 'write-method': 2})
    assert hn_gate.verdict(o) == 'not_green'
    assert hn_gate.verdict(o, split_robots=True) == 'respected_skipped'
    assert hn_gate.qualifies(o) is False and hn_gate.qualifies(o, split_robots=True) is False   # still not green


def test_a_reading_step_robots_refused_is_skipped_not_failed():
    o = outcome(steps=[{'label': LABELS[0], 'status': 'passed'}, {'label': LABELS[1], 'status': 'not_run'}],
                snapshots=[{'dcl_ms': 400, 'first_contentful_paint_ms': 500.0}],
                blocked_navigation=[{'kind': 'robots-rule', 'host': 'a.example', 'path': '/x'}], blocked_counts={'robots-rule': 1})
    assert hn_gate.verdict(o) == 'not_green' and hn_gate.verdict(o, split_robots=True) == 'respected_skipped'


@pytest.mark.parametrize('bad', [
    {'blocked_counts': {'robots-rule': 3, 'websocket-channel': 1}},          # a blocked socket is not a robots rule
    {'script_errors': ['TypeError']},
    {'blocked_counts': {'robots-rule': 1}, 'snapshots': [{'dcl_ms': 4000, 'first_contentful_paint_ms': 500.0}] * 3},
    {'blocked_counts': {'robots-rule': 1}, 'steps': [{'label': LABELS[0], 'status': 'passed'}, {'label': LABELS[1], 'status': 'failed'}]},
])
def test_anything_besides_robots_still_fails_with_the_flag(bad):
    assert hn_gate.verdict(outcome(**bad), split_robots=True) == 'not_green'


@pytest.mark.skipif(not RUN.is_dir(), reason='set NVIDIA_HN_RUN to the optional frozen 16 Oct evidence bundle')
def test_the_16_oct_run_recounts_to_64_by_default():
    before = {p.name: p.stat().st_mtime_ns for p in RUN.glob('outcome-*.json')}
    default = hn_gate.recount(RUN)
    assert default == {'outcomes': 222, 'skipped': 22, 'visited': 200, 'green': 64, 'not_green': 136}
    assert json.loads((RUN / 'FINAL-AUDIT.json').read_text())['clean_gate_passes'] == default['green']
    split = hn_gate.recount(RUN, split_robots=True)
    assert split['green'] == 64 and split['respected_skipped'] > 0
    assert split['green'] + split['respected_skipped'] + split['not_green'] == 200
    assert {p.name: p.stat().st_mtime_ns for p in RUN.glob('outcome-*.json')} == before   # read only
