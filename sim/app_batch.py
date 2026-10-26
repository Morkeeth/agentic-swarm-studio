"""Local batch runner. The HTTP server never receives a provider credential."""
import argparse
import contextlib
import getpass
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

PLAN = Path(__file__).resolve().parents[1] / 'web/landing/app-plan.json'


def load_plan(path=PLAN):
    plan = json.loads(Path(path).read_text())
    apps = plan['apps']
    if not 1 <= len(apps) <= 100:
        raise ValueError('Choose between one and 100 scoped apps.')
    ids = set()
    for app in apps:
        if set(app) != {'id', 'name', 'url', 'task'}:
            raise ValueError('Use only id, name, url and task in each app.')
        if any(not isinstance(v, str) or not v.strip() or len(v) > 400 for v in app.values()):
            raise ValueError('Each app field needs short plain text.')
        u = urlsplit(app['url'])
        if u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError('Use public HTTPS app addresses without credentials or query strings.')
        if app['id'] in ids:
            raise ValueError('App IDs must be unique.')
        ids.add(app['id'])
    return plan


def redact(value, key):
    # Include dict keys: provider exceptions and model replies are untrusted.
    if isinstance(value, str):
        return value.replace(key, '[REDACTED]') if key else value
    if isinstance(value, list):
        return [redact(x, key) for x in value]
    if isinstance(value, dict):
        return {redact(k, key): redact(v, key) for k, v in value.items()}
    return value


def execute(plan, store, key, stop, studio_class=None):
    from sim import tool_trial
    from sim.adapters import tokenfactory
    from sim.swarm_studio import Studio
    store = Path(store)
    store.mkdir(parents=True, exist_ok=True)
    # A fresh folder refuses accidental overwrite of a previous queue.
    batch = store / 'batches' / (time.strftime('%Y%m%d-%H%M%S') + '-' + os.urandom(3).hex())
    batch.mkdir(parents=True)
    original_key, original_dump = tokenfactory.load_key, tool_trial.dump
    def safe_dump(path, value):
        return original_dump(path, redact(value, key))
    tokenfactory.load_key = lambda: key
    tool_trial.dump = safe_dump
    rows = [{**a, 'status': 'queued', 'run_id': None} for a in plan['apps']]
    def save():
        safe_dump(batch / 'queue.json', {'source': plan.get('source'), 'apps': rows})
    try:
        save()
        studio = (studio_class or Studio)(store, models=True, account=str(batch), stop_usd=stop)
        for row in rows:
            row['status'] = 'starting'; save()
            try:
                reply = studio.start({'url': row['url'], 'task': row['task'], 'visitors': 3})
                row.update(status='running', run_id=reply['id']); save()
                while studio.busy.locked():
                    time.sleep(.2)
                result = json.loads((store / 'runs' / reply['id'] / 'result.json').read_text())
                row['status'] = result.get('status', 'failed')
            except Exception:
                row.update(status='failed', reason='Run could not start. Check browser readiness and spending stop locally.')
            save()
    finally:
        for row in rows:
            if row['status'] in ('running', 'starting'):
                row['status'] = 'interrupted'
        save()
        tokenfactory.load_key, tool_trial.dump = original_key, original_dump
    return batch


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, default=PLAN)
    p.add_argument('--store', type=Path, required=True)
    p.add_argument('--stop-usd', required=True)
    p.add_argument('--execute', action='store_true', help='Authorize paid model calls for this local run')
    a = p.parse_args()
    plan = load_plan(a.plan)
    if not a.execute:
        print(json.dumps(plan, indent=2)); return
    key = getpass.getpass('Your Nebius key (hidden, held only in this local process): ').strip()
    if not key:
        p.error('A key is required.')
    try:
        # Third-party output must never echo credentials to a terminal or log.
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            batch = execute(plan, a.store, key, a.stop_usd)
    except Exception:
        raise SystemExit('Batch stopped. Inspect the local queue; no credential was printed.') from None
    finally:
        key = None
    print(f'Local queue saved: {batch / "queue.json"}')


if __name__ == '__main__':
    main()
