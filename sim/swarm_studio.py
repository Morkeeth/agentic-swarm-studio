"""Agentic Swarm Simulator studio: give a URL, watch a swarm of persona agents use the app, get the fix back as a test.

Local, with paid model calls:
  python -m sim.swarm_studio --store ../swarm-studio-runs --allow-models --account-key KEY --stop-usd 0.20
Replays and cases only, no model calls:
  python -m sim.swarm_studio --store ../swarm-studio-runs
Replays plus one rate-limited Nemotron explanation per button press (what the hosted page serves):
  python -m sim.swarm_studio --store ../swarm-studio-runs --allow-explain --explain-cap-usd 0.50

The studio binds 127.0.0.1. Live runs need --allow-models, a Token Factory key and a spending account.
The account key prefixes every ledger row; the stop counts every row under that key, earlier runs included.
"""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from decimal import Decimal
import argparse, fcntl, json, os, re, secrets, threading, time
from sim import app_swarm, hosted_cost, studio_explain, studio_test, tool_trial

WEB = Path(__file__).resolve().parents[1] / 'web' / 'studio'
REVIEW = Path(__file__).resolve().parents[1] / 'web' / 'review'
LANDING = Path(__file__).resolve().parents[1] / 'web' / 'landing'
FIX = WEB / 'fixtures'
REPAIR = Path(__file__).resolve().parents[1] / 'web' / 'repair'
FILES = {'/studio': ('index.html', 'text/html'), '/studio/': ('index.html', 'text/html'),
         '/studio/studio.css': ('studio.css', 'text/css'), '/studio/studio.js': ('studio.js', 'application/javascript')}
REVIEW_FILES = {'/review': ('index.html', 'text/html'), '/review/': ('index.html', 'text/html'),
                '/review/review.css': ('review.css', 'text/css'), '/review/review.js': ('review.js', 'application/javascript')}
NAME = re.compile(r'[A-Za-z0-9_-]{1,64}')
SHOT = re.compile(r'v-[a-z][a-z0-9-]{0,48}-t\d-\d\d\.png|step-\d\d\.png')
# A retained repair-loop case: exactly these files, served as recorded. No route here runs a model or repairs anything.
REPAIR_FILES = {'REPAIR.html': 'text/html', 'repair.css': 'text/css', 'REPAIR.md': 'text/plain; charset=utf-8', 'receipt.json': 'application/json',
                'test_returned_path.py': 'text/plain; charset=utf-8', 'check-before.log': 'text/plain; charset=utf-8', 'check-after.log': 'text/plain; charset=utf-8',
                'check-live.log': 'text/plain; charset=utf-8', 'portable-menu-links.patch': 'text/plain; charset=utf-8'}
REPAIR_PATH = re.compile(r'/repair/([a-z0-9-]{1,40})/(?:(visit-(?:before|after))/)?([A-Za-z0-9_.-]{0,64})')
MAX_VISITORS = 5

# A small app to point the swarm at. The broken copy has a guide link that answers 404.
DEMO_PAGE = ('<html><head><title>Notes</title></head><body><main><h1>{h}</h1><p>{p}</p>'
             '<a href="{stem}/guide">Read the guide</a><p><a href="{stem}">Back to the collection</a></p></main></body></html>')
DEMO = {'/demo/notes': ('Notes collection', 'Open our guide to learn how to organise your notes. This demo app is part of the simulator and saves nothing.'),
        '/demo/notes/guide': ('Getting started', 'Keep one collection per project. Read a note before changing it. Tag a note so you can find it again later.'),
        '/demo/notes-broken': ('Notes collection', 'Open our guide to learn how to organise your notes. This demo app is part of the simulator and saves nothing.')}


def demo_page(path):
    if path == '/demo/notes-broken/guide': return 404, b'<html><title>Not found</title><h1>404</h1><p>This page does not exist.</p></html>'
    if path not in DEMO: return None
    h, p = DEMO[path]; stem = '/demo/notes-broken' if 'broken' in path else '/demo/notes'
    return 200, DEMO_PAGE.format(h=h, p=p, stem=stem).encode()


class StopBudget(app_swarm.Budget):
    """One account for every studio run: the stop counts all rows under the account key, not only this run's."""
    account = None; stop = Decimal('0.20'); run = ''

    def __init__(self, run_key, max_calls, run_cap_usd=None):
        super().__init__(self.account, max_calls, run_cap_usd=self.stop)

    def call(self, client, messages, label, seed, temperature=0):
        return super().call(client, messages, f'studio-{self.run}-{label}', seed, temperature)


def spent(account):
    """Accounted USD under one key in the shared ledger, held reservations included."""
    try:
        with hosted_cost.RECORD.open() as stream:
            fcntl.flock(stream, fcntl.LOCK_SH)   # the record is rewritten in place during a run
            raw = stream.read()
    except FileNotFoundError: return Decimal(0)
    runs = json.loads(raw)['runs'] if raw else {}
    return sum((Decimal(str(r['accounted_usd'])) for k, r in runs.items() if k.startswith(account + '/')), Decimal(0))


def check_url(url):
    u = urlsplit(url or '')
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.fragment:
        raise ValueError('Give an http or https address without a login or a #fragment.')
    return url


def agents_line(r):
    """Headline from the per-visitor records. The summary counts block leaves the sceptic out; the studio shows every agent that ran."""
    people = (r.get('tries') or [[]])[0]
    finished = sum(bool(v.get('confirmed')) for v in people)
    stuck = sum(v.get('outcome') == 'stuck' for v in people)
    interrupted = sum(v.get('outcome') == 'not_finished' for v in people)
    return f'{finished} of {len(people)} agents completed. {stuck} stuck.' + (f' {interrupted} interrupted.' if interrupted else '')


class Studio:
    def __init__(self, store, *, models=False, account=None, stop_usd='0.30', judge=True, explainer=None):
        self.store = Path(store); (self.store / 'runs').mkdir(parents=True, exist_ok=True)
        self.models = models; self.account = account; self.stop = Decimal(str(stop_usd)); self.judge = judge
        self.busy = threading.Lock(); self.port = None; self.explainer = explainer
        if models:
            if not account: raise ValueError('Live runs need --account-key, so the stop has one account to count.')
            app_swarm.require_key()

    def health(self):
        h = {'ready': True, 'live_runs': self.models, 'crowd_model': hosted_cost.MODEL, 'judge_model': hosted_cost.judge_model() if self.judge else None,
             'replays': sorted(p.name for p in (FIX / 'replays').iterdir()) if (FIX / 'replays').is_dir() else []}
        if self.models: h.update({'stop_usd': float(self.stop), 'accounted_usd': float(spent(self.account)), 'running': self.busy.locked()})
        h['live_call'] = self.explainer.status() if self.explainer else None
        return h

    def explain(self, body):
        if not self.explainer: raise ValueError('The live Nemotron explanation is off on this server.')
        f = self.folder('replays', body.get('replay'))
        if not f: raise ValueError('Pick a recorded run.')
        return self.explainer.explain(f.name, json.loads((f / 'result.json').read_text()))

    def start(self, body):
        if not self.models: raise ValueError('Live runs are off here. This page shows recorded runs. Run the studio locally with --allow-models to swarm your own URL.')
        url = check_url(body.get('url', '').strip())
        if url.startswith('/demo/'): url = f'http://127.0.0.1:{self.port}{url}'
        task = (body.get('task') or 'Read the getting started guide').strip()[:160]
        n = int(body.get('visitors') or 3)
        if not 1 <= n <= MAX_VISITORS: raise ValueError(f'Choose 1 to {MAX_VISITORS} visitors.')
        used = spent(self.account)
        if used >= self.stop: raise ValueError('The spending stop is reached. No run was started.')
        # Every visitor holds one worst-case reservation while its call is in flight, so all of them must fit under the stop.
        hold = n * max([hosted_cost.worst_case(1, hosted_cost.MODEL)] + ([hosted_cost.worst_case(1, hosted_cost.judge_model())] if self.judge else []))
        if used + hold > self.stop:
            raise ValueError(f'{n} visitors can hold up to USD {hold:.2f} at once while their calls run, and USD {used:.4f} is used. '
                             f'Raise --stop-usd to {(used + hold).quantize(Decimal("0.01"), "ROUND_UP")} or choose fewer visitors. No run was started.')
        if not self.busy.acquire(blocking=False): raise ValueError('A swarm is already running. Watch it, then start the next one.')
        try:
            rid = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3); folder = self.store / 'runs' / rid; folder.mkdir()
            people = [{**p, 'goal': task} for p in app_swarm.personas_for(task)[:n]]
            tool_trial.dump(folder / 'result.json', {'id': rid, 'url': url, 'job': {'text': task, 'source': 'you'}, 'tries_planned': 1, 'status': 'queued',
                                                     'visitors_planned': [{k: p[k] for k in ('id', 'name', 'colour', 'goal', 'max_steps')} for p in people]})
        except Exception:
            self.busy.release(); raise
        threading.Thread(target=self._run, args=(folder, rid, people), daemon=True).start()
        return {'id': rid, 'state': 'running', 'visitors': n}

    def _run(self, folder, rid, people):
        try:
            StopBudget.account, StopBudget.stop, StopBudget.run = self.account, self.stop, rid
            real = app_swarm.Budget; app_swarm.Budget = StopBudget
            try:
                judge = (lambda p: app_swarm.default_judge_for(p)) if self.judge else (lambda p: None)
                app_swarm.run(folder, personas=people, judge_for=judge)
            finally: app_swarm.Budget = real
        except Exception as e:
            r = tool_trial.read(folder / 'result.json'); r.update({'status': 'failed', 'error': f'{type(e).__name__}: {str(e)[:200]}'})
            tool_trial.dump(folder / 'result.json', r)
        finally:
            r = tool_trial.read(folder / 'result.json')
            r['account'] = {'accounted_usd_after': float(spent(self.account)), 'stop_usd': float(self.stop)}
            src = studio_test.generate(r) if r.get('status') == 'complete' else None
            if src:
                from sim.app_batch import redact
                from sim.adapters import tokenfactory
                key = tokenfactory.load_key() if self.models else None
                (folder / 'test_swarm_path.py').write_text(redact(src, key))
            r['handed_back_test'] = bool(src); tool_trial.dump(folder / 'result.json', r)
            self.busy.release()

    def folder(self, kind, name):
        if not NAME.fullmatch(name or ''): return None
        f = (FIX / 'replays' / name) if kind == 'replays' else (self.store / 'runs' / name)
        return f if (f / 'result.json').is_file() else None

    def runs(self):
        out = []
        for f in sorted((self.store / 'runs').iterdir(), reverse=True)[:20]:
            try: r = json.loads((f / 'result.json').read_text())
            except Exception: continue
            out.append({'id': f.name, 'url': r.get('url'), 'task': (r.get('job') or {}).get('text'), 'status': r.get('status'), 'headline': agents_line(r) if r.get('status') == 'complete' else None})
        return out

    def replays(self):
        out = []
        for name in self.health()['replays']:
            try: r = json.loads((FIX / 'replays' / name / 'result.json').read_text())
            except Exception: continue
            out.append({'id': name, 'label': (r.get('replay') or {}).get('label') or name, 'headline': agents_line(r)})
        return sorted(out, key=lambda x: x['id'])

    def get(self, path):
        """(status, body, content type) for a studio path, or None when the path is not the studio's."""
        if path == '/':   # counts on the page are read from the replay records, never typed
            page = (LANDING / 'index.html').read_bytes().replace(b'<!--replay-count-->', str(len(self.replays())).encode())
            return 200, page, 'text/html'
        if path == '/landing.css': return 200, (LANDING / 'landing.css').read_bytes(), 'text/css'
        if path == '/app-queue.js': return 200, (LANDING / 'app-queue.js').read_bytes(), 'application/javascript'
        if path == '/landing.js': return 200, (LANDING / 'landing.js').read_bytes(), 'application/javascript'
        if path == '/api/landing/outside-run':
            result = LANDING / 'outside-run.json'
            return (200, result.read_bytes(), 'application/json') if result.is_file() else (200, {'status': 'pending', 'tools': []}, None)
        landing_media = {'swarm-paths.png', 'before-after.png', 'evidence-library.png'}
        if path.startswith('/landing-media/'):
            name = path.removeprefix('/landing-media/')
            if name == 'swarm-replay.mp4': return 200, (LANDING / name).read_bytes(), 'video/mp4'
            return (200, (LANDING / name).read_bytes(), 'image/png') if name in landing_media else (404, b'Not found', 'text/plain')
        m = REPAIR_PATH.fullmatch(path)
        if m:
            case, sub, name = m[1], m[2], m[3] or 'REPAIR.html'
            if sub: kind = 'application/json' if name == 'result.json' else 'image/png' if SHOT.fullmatch(name) else None
            else: kind = REPAIR_FILES.get(name)
            f = REPAIR / case / (sub or '') / name
            if kind and f.is_file() and not f.is_symlink(): return 200, f.read_bytes(), kind
            return 404, {'error': 'Not found'}, None
        if path == '/repair': return 302, b'/repair/overturn/', 'redirect'
        if path in FILES:
            name, kind = FILES[path]; return 200, (WEB / name).read_bytes(), kind
        if path in REVIEW_FILES:
            name, kind = REVIEW_FILES[path]; return 200, (REVIEW / name).read_bytes(), kind
        if path.startswith('/demo/'):
            d = demo_page(path); return (d[0], d[1], 'text/html') if d else (404, b'Not found', 'text/plain')
        if path.startswith('/studio/evidence/'):
            name = path.removeprefix('/studio/evidence/')
            kinds = {'library.json': 'application/json', 'route-a.png': 'image/png', 'historical-film.mp4': 'video/mp4', 'hn-first-visits.txt': 'text/plain; charset=utf-8', 'hn-patterns.txt': 'text/plain; charset=utf-8', 'harness-audit.txt': 'text/plain; charset=utf-8'}
            if name in kinds: return 200, (FIX / 'evidence' / name).read_bytes(), kinds[name]
            return 404, {'error': 'Not found'}, None
        if path == '/api/landing/app-plan':
            from sim.app_batch import load_plan
            return 200, load_plan(), None
        if path == '/api/landing/batches':
            batches = []
            for q in sorted((self.store / 'batches').glob('*/queue.json'), reverse=True):
                try: batches.append({'id': q.parent.name, **json.loads(q.read_text())})
                except (ValueError, OSError): continue
            return 200, {'batches': batches, 'runs': self.runs(), 'replays': self.replays()}, None
        if path == '/api/studio/health': return 200, self.health(), None
        if path == '/api/studio/cases': return 200, (FIX / 'cases.json').read_bytes(), 'application/json'
        if path == '/api/studio/runs': return 200, {'runs': self.runs(), 'replays': self.replays()}, None
        m = re.fullmatch(r'/api/studio/cases/(CASE-\d\d)\.diff', path)
        if m:
            f = FIX / 'cases' / f'{m[1]}.diff'; return (200, f.read_bytes(), 'text/plain') if f.is_file() else (404, {'error': 'No patch for this case'}, None)
        m = re.fullmatch(r'/api/studio/(replays|runs)/([^/]+)(?:/(.+))?', path)
        if m:
            f = self.folder(m[1], m[2])
            if not f: return 404, {'error': 'Run not found'}, None
            if not m[3]:
                r = json.loads((f / 'result.json').read_text()); r.pop('raw', None)
                return 200, r, None
            if m[3] == 'test.py':
                # Preserve historical saved source untouched, but return a check
                # generated by the current bounded navigation rules.
                src = studio_test.generate(json.loads((f / 'result.json').read_text()))
                return (200, src.encode(), 'text/x-python') if src else (404, {'error': 'No visitor clicked anything, so there is no path to test.'}, None)
            if SHOT.fullmatch(m[3]) and (f / m[3]).is_file() and not (f / m[3]).is_symlink(): return 200, (f / m[3]).read_bytes(), 'image/png'
            return 404, {'error': 'Not found'}, None
        return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, status, body, kind=None):
        if kind == 'redirect':
            self.send_response(302); self.send_header('Location', body.decode()); self.send_header('Content-Length', '0'); self.end_headers(); return
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status); self.send_header('Content-Type', kind or 'application/json'); self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self'; media-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        r = self.server.studio.get(urlsplit(self.path).path)
        return self.send(*r) if r else self.send(404, {'error': 'Not found'})

    def do_POST(self):
        origin = self.headers.get('Origin'); host = self.headers.get('Host')
        if not origin or urlsplit(origin).netloc != host: return self.send(403, {'error': 'Same-origin request required'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size < 4000: raise ValueError('Small request required.')
            body = json.loads(self.rfile.read(size))
            if urlsplit(self.path).path == '/api/studio/runs': return self.send(200, self.server.studio.start(body))
            if urlsplit(self.path).path == '/api/studio/explain': return self.send(200, self.server.studio.explain(body))
            return self.send(404, {'error': 'Not found'})
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e: return self.send(400, {'error': str(e)[:200]})


def main():
    a = argparse.ArgumentParser(description='Agentic Swarm Simulator studio')
    a.add_argument('--store', required=True); a.add_argument('--port', type=int, default=4100)
    a.add_argument('--allow-models', action='store_true'); a.add_argument('--account-key'); a.add_argument('--stop-usd', default='0.30')
    a.add_argument('--no-judge', action='store_true'); a.add_argument('--host', default='127.0.0.1')
    a.add_argument('--allow-explain', action='store_true', help='one rate-limited Nemotron Nano call per press, prompt built from recorded runs only')
    a.add_argument('--explain-cap-usd', default='0.50'); a.add_argument('--explain-daily-calls', type=int, default=100); o = a.parse_args()
    if o.host != '127.0.0.1' and o.allow_models: raise SystemExit('Network binding is replay-only. Live model runs must stay on loopback.')
    if o.allow_models and not o.no_judge: os.environ['TOKEN_FACTORY_JUDGE_MODEL'] = os.environ.get('TOKEN_FACTORY_JUDGE_MODEL') or hosted_cost.JUDGE_MODEL
    try:
        explainer = studio_explain.Explainer(Path(o.store) / 'explain-record.json', cap_usd=o.explain_cap_usd, daily_calls=o.explain_daily_calls) if o.allow_explain else None
        studio = Studio(o.store, models=o.allow_models, account=o.account_key, stop_usd=o.stop_usd, judge=not o.no_judge, explainer=explainer)
    except Exception as e: raise SystemExit(f'{type(e).__name__}: {e}')
    server = ThreadingHTTPServer((o.host, o.port), Handler); server.studio = studio; studio.port = server.server_port
    print(f'Agentic Swarm Simulator on http://127.0.0.1:{studio.port}/studio  live runs={studio.models}  live explain={bool(explainer)}', flush=True)
    try: server.serve_forever()
    finally: server.server_close()


if __name__ == '__main__': main()
