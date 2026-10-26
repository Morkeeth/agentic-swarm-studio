# Repair loop: fix what a visitor hit on your own app, then prove the same goal works

Customer: a developer about to ship a change to a web app they own. They name one goal a first visitor should reach. A model visitor tries it, stops on a real failure, and the stopped path comes back as an executable check. The developer writes the fix. The loop applies it as its own commit, runs the same check, and sends a fresh visitor at the same goal.

```sh
.venv-app/bin/python -m sim.repair_loop run \
  --repo https://github.com/Morkeeth/overturn.git \
  --ref bd6a868294bf61155917457eba7b384c9e0a5a76 --site-dir web \
  --goal "Open the About page and read why Overturn exists" \
  --patch examples/overturn/portable-menu-links.patch \
  --visitor nemotron --live-url https://overturn-morkeeths-projects.vercel.app/ \
  --output ../repair-overturn
```

`--visitor nemotron` uses NVIDIA Nemotron Nano through Nebius Token Factory and needs `TOKEN_FACTORY_API_KEY` plus `CONFIRM_SPONSOR_SPEND=RUN`. Each of the two visits is reserved against the local spend record and stops at `--run-cap-usd` (default 0.05). `--visitor codex` uses a signed-in Codex CLI instead and is labelled as not sponsor evidence.

The output folder holds:

- `REPAIR.html`: both visits side by side, the check, the patch, for a person to read.
- `receipt.json`: exact commits before and after, patch hash, check hash, each check's exit code and why it was red, each visitor's outcome, model identity and token use.
- `test_returned_path.py`: the returned check. Point it anywhere with `SWARM_START_URL`.
- `app-before/`, `app-after/`: the two trees. `python -m sim.repair_loop recheck ../repair-overturn` re-serves both and reruns the check with no model call.

## What counts as repaired

All three must hold: the check was red on the original **because a page on the path answered with an error**, the check is green with the fix, and the second visitor completed the goal. A check that is red because it cannot find the recorded control does not reproduce the failure, so the loop stops there instead of crediting a fix. A fix that changes nothing stays red and is reported as not repaired.

## The Overturn case

Overturn is a public app by the same author. Its menu links are clean URLs (`/about`) that only work because `vercel.json` rewrites them. On any other static host (a local preview, GitHub Pages, a plain file server) every menu link answers 404. The fix points the links at the real files (`/about.html`), which also still works on Vercel. The deployed original passes the same check, which shows the failure depends on the host, and the report says so.

The bundled run in `examples/overturn/` used NVIDIA Nemotron Nano (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`) on 26 October 2026. Before the fix: 8 calls, the visitor clicked About, got 404, tried "Why this exists", got 404 again and gave up. After the fix: 5 calls, About opened and a second call agreed the screen shows why Overturn exists. Every reply carried usage and the requested model id. 16,317 prompt and 617 completion tokens, 0.00113 USD at listed rates, not a provider invoice.

## Limits

- Static sites served as files. Apps that need their own server or build step are not started by this loop yet.
- The check is navigation smoke. The second visit, not the check, is what shows the goal was reached.
- One visitor per side. This is a reproduction and a rerun, not a success rate.
- Visitors are models, not people. They only read: no typing, sign-in, purchase or upload.
