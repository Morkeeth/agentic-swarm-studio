"""Finished reports, their screens and share links, kept outside the instance that made them.

Cloud Run's /tmp is memory. A report kept only there is lost when the instance stops or a
second one answers, and GET /api/reports/<id> returns 404. So each finished report is copied to
Cloud Storage, beside the Route A account object, and read back from there on a local miss.
Stdlib only, the same metadata-server token as route_a_account.GcsStore.
"""
from pathlib import Path
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

NAME = re.compile(r'[a-zA-Z0-9_-]+')


class GcsObjects:
    API = 'https://storage.googleapis.com'
    TOKEN_URL = 'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token'
    durable = True

    def __init__(self, uri, *, opener=urllib.request.urlopen, timeout=10):
        parsed = urllib.parse.urlparse(uri)
        if parsed.scheme != 'gs' or not parsed.netloc or not parsed.path.strip('/'):
            raise ValueError('The report store must be gs://BUCKET/PREFIX.')
        self.bucket, self.prefix = parsed.netloc, parsed.path.strip('/') + '/'
        self.open, self.timeout = opener, timeout

    def token(self):
        req = urllib.request.Request(self.TOKEN_URL, headers={'Metadata-Flavor': 'Google'})
        with self.open(req, timeout=self.timeout) as r:
            return json.loads(r.read())['access_token']

    def put(self, name, data, kind):
        q = urllib.parse.urlencode({'uploadType': 'media', 'name': self.prefix + name})
        req = urllib.request.Request(f'{self.API}/upload/storage/v1/b/{self.bucket}/o?{q}', data=data, method='POST',
                                     headers={'Authorization': 'Bearer ' + self.token(), 'Content-Type': kind})
        with self.open(req, timeout=self.timeout) as r:
            r.read()

    def get(self, name):
        o = urllib.parse.quote(self.prefix + name, safe='')
        req = urllib.request.Request(f'{self.API}/storage/v1/b/{self.bucket}/o/{o}?alt=media',
                                     headers={'Authorization': 'Bearer ' + self.token()})
        try:
            with self.open(req, timeout=self.timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            raise


class DirObjects:
    """Local development only. On Cloud Run a directory is memory, so App refuses it there."""
    durable = False

    def __init__(self, path):
        self.root = Path(path); self.root.mkdir(parents=True, exist_ok=True)

    def put(self, name, data, kind):
        f = self.root / name; f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(data)

    def get(self, name):
        f = self.root / name
        return f.read_bytes() if f.is_file() and not f.is_symlink() else None


class ReportStore:
    def __init__(self, objects):
        self.objects = objects

    @property
    def durable(self): return self.objects.durable

    def save(self, tenant, report, folder):
        """Screens first, then the report, so a report that is found always has its screens."""
        if not NAME.fullmatch(report['id']): raise ValueError('Bad report id.')
        for s in (report.get('result') or {}).get('screens', []):
            f = Path(folder) / s['image']
            if re.fullmatch(r'[a-zA-Z0-9_-]+\.png', s['image']) and f.is_file() and not f.is_symlink():
                self.objects.put(f"screens/{report['id']}/{s['image']}", f.read_bytes(), 'image/png')
        self.objects.put(f"{report['id']}.json", json.dumps({'tenant': tenant, 'report': report}).encode(), 'application/json')

    def _report(self, id):
        if not NAME.fullmatch(id or ''): return None
        raw = self.objects.get(f'{id}.json')
        return json.loads(raw) if raw else None

    def load(self, tenant, id):
        kept = self._report(id)
        return kept['report'] if kept and kept['tenant'] == tenant else None

    def screen(self, id, name):
        if not NAME.fullmatch(id or '') or not re.fullmatch(r'[a-zA-Z0-9_-]+\.png', name or ''): return None
        return self.objects.get(f'screens/{id}/{name}')

    def share(self, token, id, expires):
        self.objects.put(f'shares/{token}.json', json.dumps({'id': id, 'expires': expires}).encode(), 'application/json')

    def shared(self, token):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', token or ''): return None
        raw = self.objects.get(f'shares/{token}.json')
        link = json.loads(raw) if raw else None
        if not link or link['expires'] <= time.time(): return None
        kept = self._report(link['id'])
        if not kept or kept['report'].get('state') != 'complete': return None
        return {'id': link['id'], 'result': kept['report']['result']}


def from_address(address):
    return ReportStore(GcsObjects(address) if str(address).startswith('gs://') else DirObjects(address))


def on_cloud_run():
    return bool(os.environ.get('K_SERVICE'))
