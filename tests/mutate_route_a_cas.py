"""Each mutation must turn tests/test_route_a_cas_account.py red. Run from the repo root."""
import pathlib, subprocess, sys
M = [
 ('lost update: stale state on retry', 'sim/route_a_account.py',
  "        for _ in range(self.tries):\n            generation, state = self.load()\n            change(state)\n",
  "        generation, state = self.load()\n        change(state)\n        for _ in range(self.tries):\n            generation = self.store.read()[0]\n"),
 ('no retry after a lost race', 'sim/route_a_account.py', 'for _ in range(self.tries):', 'for _ in range(1):'),
 ('busy account does not fail closed', 'sim/route_a_account.py', "        raise AccountError('Route A spend account is busy; no call made.')", '        return'),
 ('unreadable account treated as empty', 'sim/route_a_account.py',
  "            generation, raw = self.store.read()\n            state = json.loads(raw)\n        except Exception as e:\n            raise AccountError('Route A spend account is unreadable.') from e",
  "            generation, raw = self.store.read()\n            state = json.loads(raw)\n        except Exception as e:\n            return 0, initial_state()"),
 ('cap check ignores the new reservation', 'sim/route_a_account.py', 'if total + RESERVE_MICROUSD > HARD_CAP_MICROUSD:', 'if total > HARD_CAP_MICROUSD:'),
 ('no generation precondition on write', 'sim/route_a_account.py', "'name': self.name, 'ifGenerationMatch': generation}", "'name': self.name}"),
 ('412 not mapped to a lost race', 'sim/route_a_account.py', 'if e.code == 412:', 'if e.code == 999:'),
 ('actual usage not recorded', 'sim/first_users_route_a.py', '        self.account.finish(job, status, actual)', '        pass'),
]
bad = 0
for name, f, old, new in M:
    path = pathlib.Path(f); src = path.read_text(); assert src.count(old) == 1, name
    path.write_text(src.replace(old, new))
    try:
        r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-x', 'tests/test_route_a_cas_account.py'], capture_output=True, text=True, timeout=120)
    finally:
        path.write_text(src)
    red = r.returncode != 0
    bad += not red
    print(('RED  ' if red else 'GREEN (BAD) ') + name)
print(f'{len(M) - bad} of {len(M)} mutations caught'); sys.exit(1 if bad else 0)
