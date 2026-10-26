# Agentic Swarm Simulator

Give a web app one goal. NVIDIA Nemotron visitors try it in a browser, retain the screens and actions, and return a navigation check for a confirmed error path. After a developer supplies a patch, the repair loop runs the same check and sends a fresh visitor at the same goal. Visitors are models, not people. They only read and click; they do not sign in, type, buy, upload or save.

**[Open the hosted product](https://agentic-swarm-studio-568004190078.us-central1.run.app/)** · **[Inspect the repair report](https://agentic-swarm-studio-568004190078.us-central1.run.app/repair/overturn/)** · [Setup and commands](RUN.md) · [Evidence and provenance](docs/evidence.md)

## Try the demo

No account or key is needed for recorded playback.

1. Start with **A visitor hit a 404. The fix was proven with the same goal.** on the hosted landing page.
2. Follow the five steps: the failed visit, returned test, patch, passing check and completed second visit.
3. Use **Replay every screen** to inspect the [before visit](https://agentic-swarm-studio-568004190078.us-central1.run.app/studio#replays/overturn-nemotron-404) and [after visit](https://agentic-swarm-studio-568004190078.us-central1.run.app/studio#replays/overturn-nemotron-fixed).
4. Open the full repair report and download the exact test, patch and receipt. Reproduce its red/green check locally with the commands below.

This is one recorded repair on Overturn, an app by the same author. Serving the original as plain static files exposes an About link that returns 404. Vercel rewrites make the deployed original pass. The five-file link patch makes the static copy pass too; a second recorded visitor reaches the same goal. This establishes a host-specific reproduction and retest, not a general success rate.

Playback makes no model call. **Ask Nemotron now**, when enabled on the hosted service, is a separate live explanation of a saved record. Pressing it makes a provider call. Its instance-local limits are not a durable provider-level spending cap. It does not start a new repair.

## Run the product locally without a key

Use Python 3.10 or newer, git, and macOS or Linux. The documented verification machine uses Python 3.12. Windows is not supported by modules that use POSIX file locking. Initial dependency and Chromium installation need internet access.

```sh
git clone https://github.com/Morkeeth/agentic-swarm-studio.git
cd agentic-swarm-studio
python3 -m venv .venv-app
.venv-app/bin/python -m pip install -r requirements-app-check.txt pytest
.venv-app/bin/python -m playwright install chromium
.venv-app/bin/python -m sim.swarm_studio --store ../swarm-studio-runs --port 4100
```

Open <http://127.0.0.1:4100/> for the landing page or <http://127.0.0.1:4100/studio#replays/overturn-nemotron-404> for the saved failure. The new-run form is disabled in this mode. The private store is outside the checkout; do not publish it. If the port is busy, choose another with `--port`.

## Reproduce the repair without inference

After installing the dependencies and Chromium above, run from the repository root:

```sh
.venv-app/bin/python -m sim.repair_loop recheck examples/overturn
```

This fetches the original Overturn commit from GitHub, rebuilds the exact fixed commit from the bundled patch, serves both locally and reruns the same Playwright check. It makes no model call and needs no provider key. Expected output includes `"before": 1` and `"after": 0`. Here, 1 is the original check's expected failure; 0 is the patched check's pass. Verify those two reported codes against the retained receipt; the command prints them and does not itself assert that they match. It writes `recheck-before.log` and `recheck-after.log` beside that receipt.

The second visitor's goal completion is retained evidence, not rerun by `recheck`. A navigation check passing alone does not establish task completion. See [the repair loop guide](docs/repair-loop.md) for the paid, explicitly enabled new-run command and its limits.

## What evidence is included?

The public replay bundle contains **8 distinct real apps**, **12 saved real-app runs** and **32 visitor trajectories**. Seven apps are external projects; Overturn is author-owned. Three additional controlled demo/sample runs bring the studio total to 15 replays and 45 trajectories. Multiple visitors or before/after copies do not count as additional apps.

All bundled visitor records declare Nemotron Nano. The broader studio uses Super VL for visual checking; the two Overturn repair records use Nano for the visitor and final screen check. The Overturn receipt establishes 13 Token Factory replies carrying the requested model ID and usage: 16,317 prompt and 617 completion tokens, about $0.00113 at listed rates, not an invoice.

The wider historical 122-app / 113-hackathon survey is mentioned in older reports and product research copy. Its original classified population is not bundled here, so these instructions do not present that number as independently reproducible from this checkout. The [evidence guide](docs/evidence.md) names the exact retained runs and distinguishes the owned repair from historical before/after examples. The studio's ten historical command-line cases are another evidence type, not ten additional browser-tested apps.

## NVIDIA Nemotron and Nebius Token Factory

- **Visitor:** `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` chooses read-only browser actions through Nebius Token Factory's OpenAI-compatible endpoint.
- **Visual judge:** `nvidia/Nemotron-3.5-Super-VL` checks claimed completion in broader studio runs. A model claim, screen agreement and actual goal completion are kept separate. The Overturn pair used Nano for its screen check instead.
- **Live explanation:** one Nano call explains a saved record when the service enables it. The UI displays its model, token count, latency and listed-rate estimate.
- **New runs:** need the user's own Token Factory key and explicit paid-call enablement. Nothing in the replay or recheck setup above enables them. See [RUN.md](RUN.md).

## Limits and next work

The demonstrated repair loop serves static files. Apps needing a build or their own server are not started by that loop yet. Visitors do not complete sign-in or write tasks. Model and harness failures remain visible and must not be labelled as app defects. No outside builder adoption, time saved, sales or human usability prediction is established by the bundled evidence.

The product goal is a repeatable release rehearsal: retain a failed path as a check, then run it after the next edit. Real app server support, durable hosted spending control and comparison with consenting human first visits remain future work.

## Supporting interfaces

The [app-check workspace](docs/app-check.md) offers a no-model page-loading check and explicitly enabled model runs. [Task contracts](docs/task-contract.md) retain ordered task requirements. The [First Users prototype](docs/first-users.md) and [payment design](docs/payment-scale.md) are separate development paths; their presence does not establish live payments, human supply or calibration.

`workspace/recorded-evidence.json` contains selected historical excerpts and hashes. Absolute `source` paths there are provenance from the author's machine, not runnable setup paths for this checkout.

## Checks

```sh
.venv-app/bin/python -m pytest -q
```

Tests use local fixtures and replace provider effects. They do not make a new efficacy claim. To build the optional deployment image, use `docker build -t agentic-swarm-simulator .` with Docker installed. Its default command serves replays; live explanations require separate environment and secret configuration.

[SOURCE-ALLOWLIST.txt](SOURCE-ALLOWLIST.txt) lists the reviewed public file scope. This repository has no provider credentials or private run store. The public history starts with a clean source snapshot and contains no private ancestor history.

## License and credits

This project's source is [MIT licensed](LICENSE), copyright 2026 Oscar Morke. The python-dotenv demo target retains its [BSD notice](target/python-dotenv/LICENSE.python-dotenv). Dependencies and third-party apps retain their own licences; this project's MIT licence does not relicense their source or screenshots.

Retained external-app screens are credited below. Licence entries are the recorded GitHub API observations from 22 October 2026, not a new licence check. The three projects with no published licence are credited as evidence of observed browser behavior; no licence is granted for their code by this repository.

| App | Original project | Recorded licence | Replays |
|---|---|---|---|
| AirIQ | https://github.com/ashutosh7i/Air-IQ | none published | `airiq-about-404`, `airiq-about-fixed` |
| Blaze | https://github.com/intrepidbird/blaze | MIT | `blaze-server-routes` |
| EduNova AI | https://github.com/JananiSenthilraj01/EduNova-AI | none published | `edunova-study-404`, `edunova-study-fixed` |
| Liar's Dice | https://github.com/lastingParadox/liars-dice | 0BSD | `liarsdice-click-unseen` |
| PuppyTime | https://github.com/megler/PuppyTime | MIT | `puppytime-lost` |
| StreetEats | https://github.com/janellewong/StreetEats | MIT | `streeteats-sign-in` |
| Water Buddy | https://github.com/huangc01cph-ops/water-buddy | none published | `waterbuddy-v3-404`, `waterbuddy-v3-fixed` |
| Overturn | https://github.com/Morkeeth/overturn | Author-owned project; see its own notices | `overturn-nemotron-404`, `overturn-nemotron-fixed` |
