"""The front door's repair case: served exactly as recorded, bound to the receipt, and never a live repair."""
import hashlib, json, re
from pathlib import Path

import pytest

from sim import swarm_studio

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'web' / 'repair' / 'overturn'
RECEIPT = json.loads((CASE / 'receipt.json').read_text())


@pytest.fixture
def studio(tmp_path): return swarm_studio.Studio(tmp_path)


def sha(b): return hashlib.sha256(b).hexdigest()


def test_published_check_and_patch_are_the_receipts_bytes(studio):
    assert sha(studio.get('/repair/overturn/test_returned_path.py')[1]) == RECEIPT['check']['sha256']
    assert sha(studio.get('/repair/overturn/' + RECEIPT['patch']['file'])[1]) == RECEIPT['patch']['sha256']
    assert RECEIPT['repaired'] is True and RECEIPT['sponsor_model_evidence'] is True
    assert (ROOT / 'examples' / 'overturn' / 'receipt.json').read_bytes() == (CASE / 'receipt.json').read_bytes()


def test_front_door_numbers_come_from_the_receipt(studio):
    page = studio.get('/')[1].decode()
    sides = [RECEIPT['visit_before'], RECEIPT['visit_after']]
    calls = sum(v['spend']['model_calls'] for v in sides)
    prompt = sum(v['spend']['prompt_tokens'] for v in sides); done = sum(v['spend']['completion_tokens'] for v in sides)
    usd = sum(v['spend']['listed_rate_estimate_usd'] for v in sides)
    section = page[page.index('id="repair"'):page.index('id="app-queue"')]
    assert f'{calls} calls' in section and f'{prompt:,} prompt' in section and f'{done} completion' in section and f'{usd:.5f} USD' in section
    assert RECEIPT['visit_before']['model'][0] in section and RECEIPT['before_sha'][:7] in section and RECEIPT['after_sha'][:7] in section
    assert 'Recorded run' in section and 'makes no model call and repairs nothing' in section


def test_every_link_in_the_case_resolves_on_this_server(studio):
    page = studio.get('/')[1].decode(); section = page[page.index('id="repair"'):page.index('id="app-queue"')]
    for ref in set(re.findall(r'(?:href|src)="(/[^"#]*)', section)):
        status = (studio.get(ref) or (404,))[0]
        assert status in (200, 302), ref
    report = studio.get('/repair/overturn/')[1].decode()
    for ref in set(re.findall(r'(?:href|src)="([^"#:]+)"', report)):
        assert (studio.get('/repair/overturn/' + ref) or (404,))[0] == 200, ref


def test_no_loopback_or_file_links_in_hosted_case(studio):
    for path in ('/', '/repair/overturn/'):
        html = studio.get(path)[1].decode()
        assert not re.search(r'(?:href|src)="(?:file:|https?://(?:127\.0\.0\.1|localhost))', html), path


def test_replays_are_recorded_and_say_so(studio):
    for name, outcome in (('overturn-nemotron-404', 'stuck'), ('overturn-nemotron-fixed', 'got_there')):
        r = studio.get(f'/api/studio/replays/{name}')[1]
        assert r['tries'][0][0]['outcome'] == outcome
        assert 'playback makes no model call' in r['replay']['diagnosis']
        assert r['spend']['models'] == RECEIPT['visit_before']['model']


@pytest.mark.parametrize('path', ['/repair/overturn/../../../sim/app_swarm.py', '/repair/overturn/visit-before/../receipt.json',
                                  '/repair/overturn/secret.key', '/repair/other/REPAIR.html', '/repair/overturn/visit-before/notes.txt'])
def test_repair_paths_outside_the_case_are_refused(studio, path):
    assert (studio.get(path) or (404,))[0] == 404   # None: no studio route, the handler answers 404
