"""Route A spend account on ONE Cloud Storage object, updated by compare-and-swap.

Why not SQLite on a Cloud Storage FUSE mount: "Cloud Storage FUSE does not support file locking"
and "is not POSIX compliant" (docs.cloud.google.com/storage/docs/cloud-storage-fuse/overview).
A write with ifGenerationMatch "proceeds if the generation of the target resource matches";
otherwise it "fails with a 412 Precondition Failed response", and value 0 means "only proceeds if
no object with the specified name exists" (docs.cloud.google.com/storage/docs/request-preconditions).

Rules: reserve BEFORE the call, fail closed on any read, parse, policy or precondition error,
never refund a reservation, and record the actual usage after the call.
"""
from datetime import datetime, timezone
import json
import urllib.error
import urllib.parse
import urllib.request

HARD_CAP_MICROUSD = 2_000_000
RESERVE_MICROUSD = 5000
EXPIRES_AT = datetime(2026, 12, 16, tzinfo=timezone.utc)
MAX_CAS_TRIES = 5


class PreconditionFailed(Exception):
    """Another writer changed the object between our read and our write."""


class AccountError(ValueError):
    """Fail closed: no provider call may follow this error."""


def initial_state():
    return {'policy': {'cap': HARD_CAP_MICROUSD, 'expires': EXPIRES_AT.isoformat()}, 'attempts': {}}


def charged(entry):
    # A reservation is never refunded. Actual usage counts only if it is higher.
    return max(entry['reserve'], entry.get('actual_microusd') or 0)


class CasAccount:
    def __init__(self, store, *, now=None, tries=MAX_CAS_TRIES):
        self.store = store
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.tries = tries

    def load(self):
        try:
            generation, raw = self.store.read()
            state = json.loads(raw)
        except Exception as e:
            raise AccountError('Route A spend account is unreadable.') from e
        self.check(state)
        return generation, state

    def check(self, state):
        if not isinstance(state, dict) or state.get('policy') != initial_state()['policy'] or not isinstance(state.get('attempts'), dict):
            raise AccountError('Route A requires the fixed USD 2 account policy.')
        for entry in state['attempts'].values():
            if not isinstance(entry, dict) or entry.get('reserve') != RESERVE_MICROUSD:
                raise AccountError('Route A spend account has an invalid attempt.')
        if self.now() >= EXPIRES_AT:
            raise AccountError('Route A budget expired after 15 December 2026 UTC.')

    def spent(self):
        return sum(charged(e) for e in self.load()[1]['attempts'].values())

    def _update(self, change):
        for _ in range(self.tries):
            generation, state = self.load()
            change(state)
            try:
                self.store.write(json.dumps(state, sort_keys=True), generation)
                return
            except PreconditionFailed:
                continue
            except Exception as e:
                raise AccountError('Route A spend account write failed.') from e
        raise AccountError('Route A spend account is busy; no call made.')

    def reserve(self, job):
        def change(state):
            if job in state['attempts']:
                raise AccountError('This report already used its one-call attempt; retries are disabled.')
            total = sum(charged(e) for e in state['attempts'].values())
            if total + RESERVE_MICROUSD > HARD_CAP_MICROUSD:
                raise AccountError('The USD 2 Route A controller cap is exhausted.')
            state['attempts'][job] = {'reserve': RESERVE_MICROUSD, 'status': 'reserved'}
        self._update(change)

    def finish(self, job, status, actual_microusd):
        def change(state):
            entry = state['attempts'][job]
            entry['status'] = status
            entry['actual_microusd'] = actual_microusd
        try:
            self._update(change)
        except AccountError:
            # The reservation stays counted at its full value, so a lost update cannot under-count.
            pass


class GcsStore:
    """One object, JSON API, metadata-server token. Stdlib only, no client library."""
    API = 'https://storage.googleapis.com'
    TOKEN_URL = 'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token'

    def __init__(self, uri, *, opener=urllib.request.urlopen, timeout=10):
        parsed = urllib.parse.urlparse(uri)
        if parsed.scheme != 'gs' or not parsed.netloc or not parsed.path.strip('/'):
            raise AccountError('Route A spend account must be gs://BUCKET/OBJECT.')
        self.bucket, self.name = parsed.netloc, parsed.path.lstrip('/')
        self.open, self.timeout = opener, timeout

    def token(self):
        req = urllib.request.Request(self.TOKEN_URL, headers={'Metadata-Flavor': 'Google'})
        with self.open(req, timeout=self.timeout) as r:
            return json.loads(r.read())['access_token']

    def read(self):
        o = urllib.parse.quote(self.name, safe='')
        req = urllib.request.Request(f'{self.API}/storage/v1/b/{self.bucket}/o/{o}?alt=media',
                                     headers={'Authorization': 'Bearer ' + self.token()})
        with self.open(req, timeout=self.timeout) as r:
            generation = r.headers.get('x-goog-generation')
            if not generation or not generation.isdigit():
                raise AccountError('Cloud Storage did not return the object generation.')
            return int(generation), r.read().decode()

    def write(self, text, generation):
        q = urllib.parse.urlencode({'uploadType': 'media', 'name': self.name, 'ifGenerationMatch': generation})
        req = urllib.request.Request(f'{self.API}/upload/storage/v1/b/{self.bucket}/o?{q}', data=text.encode(), method='POST',
                                     headers={'Authorization': 'Bearer ' + self.token(), 'Content-Type': 'application/json'})
        try:
            with self.open(req, timeout=self.timeout) as r:
                return int(json.loads(r.read())['generation'])
        except urllib.error.HTTPError as e:
            if e.code == 412:
                raise PreconditionFailed() from e
            raise


class MemoryStore:
    """Test fake with Cloud Storage semantics: generation numbers and a 412 on mismatch.
    One instance stands for the bucket; two accounts on it stand for two Cloud Run instances."""
    def __init__(self, text=None):
        import threading
        self.lock = threading.Lock()
        self.generation, self.text = (1, text) if text is not None else (0, None)
        self.writes = 0

    def read(self):
        with self.lock:
            if self.text is None:
                raise FileNotFoundError('404')
            return self.generation, self.text

    def write(self, text, generation):
        with self.lock:
            if generation != self.generation:
                raise PreconditionFailed()
            self.generation += 1
            self.text = text
            self.writes += 1
            return self.generation
