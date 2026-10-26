"""Reports outlive the instance that made them. No network: the bucket is a fake with Cloud Storage rules."""
import io
import json
import urllib.error
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import threading

import pytest

from sim import report_store
from sim.first_users import App, Handler

TENANT = 'a' * 48


class FakeBucket:
    """Answers the Cloud Storage JSON API calls GcsObjects makes. One instance stands for the bucket."""
    def __init__(self): self.objects = {}; self.requests = []

    def __call__(self, req, timeout=None):
        url = req.full_url; self.requests.append((req.get_method(), url))
        if url == report_store.GcsObjects.TOKEN_URL:
            return io.BytesIO(json.dumps({'access_token': 'fake'}).encode())
        assert req.headers.get('Authorization') == 'Bearer fake'
        if req.get_method() == 'POST':
            name = url.split('name=')[1].split('&')[0].replace('%2F', '/')
            self.objects[name] = req.data
            return io.BytesIO(json.dumps({'name': name, 'generation': '1'}).encode())
        name = url.split('/o/')[1].split('?')[0].replace('%2F', '/')
        if name not in self.objects:
            raise urllib.error.HTTPError(url, 404, 'Not Found', {}, io.BytesIO(b'{}'))
        return io.BytesIO(self.objects[name])


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: pytest.fail('No external calls'))


def instance(tmp_path, name, bucket):
    """One Cloud Run instance: its own memory disk, the shared bucket."""
    app = App(tmp_path / name, report_store=report_store.ReportStore(report_store.GcsObjects('gs://bucket/reports', opener=bucket)))
    app.stop.set()           # no browser worker in these tests
    return app


def finish_one(app):
    id = app.queue.enqueue(TENANT, 'draft-1', {'url': 'https://example.com', 'task': 'Read the guide', 'model': False, 'nebius_summary': False})
    job = app.queue.lease()
    folder = app.store / 'checks' / job['id']; folder.mkdir(parents=True)
    (folder / 'step-01.png').write_bytes(b'\x89PNG fake screen')
    view = {'headline': 'Recorded check', 'screens': [{'image': 'step-01.png', 'label': 'Home'}], 'model_calls': 1,
            'nebius': {'status': 'returned', 'text': 'Fix the guide link.'}}
    assert app.record(job, view, cost=5000)
    return id


def get(app, path):
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.app = app; app.port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        c = HTTPConnection('127.0.0.1', server.server_port); c.request('GET', path, headers={'Cookie': 'first_users=' + TENANT})
        r = c.getresponse(); return r.status, r.read()
    finally:
        server.shutdown(); server.server_close()


def test_a_report_made_on_one_instance_opens_on_another(tmp_path):
    bucket = FakeBucket(); a = instance(tmp_path, 'a', bucket); id = finish_one(a)
    b = instance(tmp_path, 'b', bucket)                         # a fresh instance: empty /tmp, same bucket
    assert b.queue.get(TENANT, id) is None
    status, body = get(b, '/api/reports/' + id)
    report = json.loads(body)
    assert status == 200 and report['state'] == 'complete' and report['result']['nebius']['text'] == 'Fix the guide link.'
    assert report['cost_microusd'] == 5000
    assert get(b, f'/screen/{id}/step-01.png') == (200, b'\x89PNG fake screen')


def test_another_visitor_cannot_open_the_report(tmp_path):
    bucket = FakeBucket(); id = finish_one(instance(tmp_path, 'a', bucket))
    assert instance(tmp_path, 'b', bucket).report_store.load('b' * 48, id) is None


def test_a_share_link_works_on_another_instance(tmp_path):
    bucket = FakeBucket(); a = instance(tmp_path, 'a', bucket); id = finish_one(a)
    token = a.share(TENANT, id)
    status, body = get(instance(tmp_path, 'b', bucket), '/api/shared/' + token)
    assert status == 200 and json.loads(body)['id'] == id


def test_without_a_durable_store_the_report_is_lost_on_restart(tmp_path):
    # The old behaviour, kept as a witness: memory-only storage gives the 404 seen on 17 Oct.
    a = App(tmp_path / 'a'); a.stop.set(); id = finish_one(a)
    b = App(tmp_path / 'b'); b.stop.set()
    assert get(b, '/api/reports/' + id)[0] == 404


@pytest.mark.parametrize('store', [None, 'dir'])
def test_cloud_run_refuses_to_start_with_reports_in_memory(tmp_path, monkeypatch, store):
    monkeypatch.setenv('K_SERVICE', 'simulated-market-judge')
    rs = report_store.ReportStore(report_store.DirObjects(tmp_path / 'reports')) if store else None
    with pytest.raises(ValueError, match='memory'):
        App(tmp_path / 'store', sample=True, report_store=rs)


def test_cloud_run_starts_with_a_bucket_store(tmp_path, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'simulated-market-judge')
    app = instance(tmp_path, 'a', FakeBucket())
    assert app.report_store.durable


def test_the_store_address_must_be_a_bucket_path():
    for bad in ('reports', 'gs://', 'gs://bucket', 'https://bucket/reports'):
        with pytest.raises(ValueError):
            report_store.GcsObjects(bad)
    assert report_store.from_address('gs://bucket/reports/').objects.prefix == 'reports/'
