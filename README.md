# Agentic Swarm Simulator

Give an app a task, let software visitors try it, and inspect the steps behind the result. NVIDIA Nemotron on Nebius Token Factory drives the optional full run. The visitors are models, not people. They read pages; they do not sign in, type, buy, upload or save in the app being tested.

The local `/review` front door is for a maker preparing to launch a web app. Paste one public or staging URL, name the job a visitor must finish, and get a journey view that separates passed checks, page errors and candidate missing features. Candidate findings remain unconfirmed until a person checks the cited screen. Full review uses Nemotron Ultra to plan and triage, Nemotron Nano for visitor steps and Nemotron 3.5 Super VL for screen checks. It keeps all calls under one explicit local spend stop.

**What it found.** We served 122 real hackathon apps from 113 Devpost hackathons exactly as published and sent three Nemotron visitors at each with one task: open a page from the app's own menu. They got stuck in five ways, and only one is a fault in the app: a link to a page that is not there (23 visitors in 10 apps). The other four are limits of our test setup or of the model, named so they are not counted against the app. For three apps, AirIQ, EduNova AI and Water Buddy, the stuck path came back as a test that is red on the published repo and green after a one-change fix in a local fork. Each kind has a replay you can open on the landing page.

## Try the judged journey

The hosted demo needs no account:

1. Open <https://agentic-swarm-studio-568004190078.us-central1.run.app/>. The first screen shows the 122-app result and the five ways visitors got stuck.
2. Press a **Replay** link under one of the five, or **Open the studio** and choose a recorded swarm, then press **Play** to inspect each visitor's path.
3. Press **Ask Nemotron now** to make one live Nemotron Nano call through Nebius Token Factory and see the model, token count, latency and listed-rate cost.
4. Open a stopped visitor and download the Playwright test for that path.

Playback makes no model call. The explanation button is rate-limited and uses the hosted service's capped budget.

`workspace/recorded-evidence.json` and the recorded replay contain selected historical excerpts and hashes; their `source` paths name the author's local evidence, which is not bundled or available as runnable paths in this snapshot.

This source snapshot starts with an empty private store. It includes the application, browser interface, model adapters, schemas and small public demo fixtures. It contains no full study archives or provider credentials; the legacy replay includes the bounded historical excerpts described above. A basic browser check works without a model key. Full inference and deeper model reports require your own Nebius Token Factory key and separate authorization to incur provider charges.

## Fix what a visitor hit, then prove it

`python -m sim.repair_loop run` takes a public repo at an exact commit, a goal and your patch. A model visitor tries the goal on the original and stops where it fails. The stopped path comes back as a Playwright check that is red on the original. Your patch is applied as its own commit, the same check goes green, and a fresh visitor reaches the same goal. `REPAIR.html` shows both visits side by side; `recheck` reruns the check with no model call. Worked case, run with NVIDIA Nemotron Nano through Token Factory on 26 October: on Overturn, a public app by the same author, every menu link answers 404 off Vercel. The visitor stopped on About; the returned check went red; the patch in `examples/overturn/` turned it green and a second Nemotron visitor reached the About page. 13 calls, 0.00113 USD at listed rates. `python -m sim.repair_loop recheck examples/overturn` reproduces red then green with no key. See [the repair loop guide](docs/repair-loop.md).

## How it uses NVIDIA Nemotron and Nebius Token Factory

- **Crowd:** each visitor is NVIDIA Nemotron Nano (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`), called through Nebius Token Factory. It reads the screen, picks the next click and says whether the task is done.
- **Judge:** NVIDIA Nemotron 3.5 Super VL (`nvidia/Nemotron-3.5-Super-VL`), also on Token Factory, looks at the screenshot and checks each visitor's claim against what the screen shows. It runs in full local runs; the recorded run `broken-demo-0003` used it. The hosted demo does not run the judge.
- **Live explanation:** the hosted demo's **Ask Nemotron now** button makes one Nemotron Nano call through Token Factory and shows the model id, tokens, latency and listed-rate cost under the answer.
- **Why Token Factory:** one OpenAI-compatible endpoint served both models, so the fast Nano calls for every visitor step and the vision checks for the judge share one key and one spend stop.

## Watch a swarm: the studio

The studio is the product view. Give it one staging URL and one goal. The front door sends three persona agents into separate headless browsers to try the task. A phone-readable progress strip shows who is moving and who stopped. A floor plan then shows each screen they reached, each visitor's steps, the trails between screens, the controls they clicked most, and a ring where a visitor stopped stuck. The result keeps the visitor's claim, the screen check and task completion separate, then hands an error path back as a Playwright check. Directly below the result, the evidence library compares the run with saved app defects, model failures and simulator limits from the 122-app collection. A second tab keeps ten recorded command-line before-and-after fixes. These are distinct evidence types, not browser or human-success scores.

Replays and cases only, no key, no model calls:

```sh
python3 -m venv .venv-app
.venv-app/bin/python -m pip install -r requirements-app-check.txt
.venv-app/bin/python -m playwright install chromium
.venv-app/bin/python -m sim.swarm_studio --store ../swarm-studio-runs
```

Open http://127.0.0.1:4100/studio. If port 4100 is busy, add `--port 4101` and open that port instead. The form is off and says why. The default replay is the five-agent working-guide run: 0/5 completed. The harness repair is integrated; its recorded rerun also completed 0/5.

The hosted page adds one live call: `--allow-explain` shows an **Ask Nemotron now** button on each recorded run. One press makes one Nemotron Nano call through Token Factory that explains the run in plain words. The prompt is built from the recorded run only, never from visitor text. Calls are spaced at least 10 s apart, limited to `--explain-daily-calls` (100) per UTC day and stopped at `--explain-cap-usd` (0.50) at listed rates. Each call is written to `explain-record.json` in the store and printed as one JSON line on stdout. It needs the same key as below.

Live swarms on your own URL make paid calls to NVIDIA Nemotron on Nebius Token Factory. Put your key in `TOKEN_FACTORY_API_KEY` (or `~/.config/keys/tokenfactory.key`), then:

```sh
.venv-app/bin/python -m sim.swarm_studio --store ../swarm-studio-runs --allow-models --account-key my-studio --stop-usd 0.30
```

The crowd is Nemotron Nano. The judge is Nemotron 3.5 Super VL, which sees the screenshot; add `--no-judge` to keep the crowd as its own checker. Every call is reserved in the spend record before it is sent. The run stops before any call that would take the total under `--account-key` past `--stop-usd`. Rates are listed rates, not a provider invoice. To try it without your own app, press **Notes** or **Notes, broken guide** in the form: a small demo app served by the studio itself. The broken copy has a guide link that answers 404, so the handed-back test is red there and green on the working copy.

The visitors only read. They do not type, sign in or send forms. They are models, not people.

## Start with a basic check

Use macOS or Linux with Python 3.10 or newer. The verified cold install used Python 3.12 on macOS. Windows is not supported by the workspace's file locking. The first dependency and browser installation needs internet access.

```sh
python3 -m venv .venv-app
.venv-app/bin/python -m pip install -r requirements-app-check.txt
.venv-app/bin/python -m playwright install chromium
.venv-app/bin/python -m sim workspace --store ../private-app-check-store --port 3878
```

Choose a new private store outside the checkout. Open the private link printed by the command. Select **Basic check · does it load**, paste the address of a running app and start. Inspect the checks and saved screens, then reload and reopen the same saved result. A code-only repository link returns an explanation; source from that repository is not installed or run.

This startup command keeps model visitors, model reports and sponsor execution off. A basic check can establish that a page opens and a reading link works; it cannot establish complete task success or human usability. The saved store is private and must not be committed or put on a public server.

## Model visitors

See [the app-check guide](docs/app-check.md) for the full-run interface, its limits and explicit enablement. The configured model is NVIDIA Nemotron Nano through Nebius Token Factory. Full model use makes billable inference requests. It is distinct from the basic check and from replaying saved screens. No judge-hosted deployment, human validation, revenue forecast or prediction accuracy is established by this source snapshot.

## First Users

The ambition is to pair simulated visitors with verified human first visits: run a bounded task with software visitors, then ask paid, verified humans through FAVOUR to attempt the same task. Keep both reports separate and measure where they agree. That human flow, its supply, payments and calibration are planned; no integration or human result is claimed here. The first offer is First Users at EUR19 for one software check, before subscription plans. There are no sales or live payments.

## Supporting paths

`sim/task_contract.py` and `sim/task_rail.py` preserve ordered read-only task requirements. Explicitly requested `sim/docs_rescue.py` searches official documentation with Tavily; it requires paid-call authorization and does not establish task completion. `sim/payment_stub.py` is a labelled local billing prototype, not a checkout or live entitlement service. See [task contracts](docs/task-contract.md) and [payment and scale design](docs/payment-scale.md). The `/tools` workspace is the app-check interface.

## Source scope

[SOURCE-ALLOWLIST.txt](SOURCE-ALLOWLIST.txt) records the reviewed file set used to create the public source snapshot. The snapshot excludes the private submission folder, build lock notes and unselected rehearsal attempts. It includes the public recorded browser fixtures needed by the judge UI. Account configuration and the optional local Codex diagnostic store are never part of this export. The original private repository remains intact. The public history starts with a fresh source snapshot; later reviewed changes contain no private ancestor history.

The earlier document/CLI comparison code and its public python-dotenv fixture remain available as supporting modules. Their original working reports, studies and internal build guide are not included. The main supported startup path here is the app-check workspace above.

## Checks

From a fresh clone on Python 3.10 or newer:

```sh
python3 -m venv .venv-app
.venv-app/bin/python -m pip install -r requirements-app-check.txt pytest
.venv-app/bin/python -m playwright install chromium
.venv-app/bin/python -m pytest -q
docker build -t agentic-swarm-simulator .
```

The third line downloads the Chromium build that Playwright drives (about 150 MB, once per machine). Without it, every browser test and every swarm run stops at once with one line that names Chromium and this command, instead of visitors that end as not finished.

The tests use local fixtures and replace provider effects. They do not establish new live inference or real human use. The container starts in replay-only mode unless `STUDIO_EXPLAIN=1` and a Token Factory key are supplied.

## License and third-party material

The project source is under [MIT](LICENSE). The public python-dotenv demo target retains its BSD license at [target/python-dotenv/LICENSE.python-dotenv](target/python-dotenv/LICENSE.python-dotenv). Keep third-party notices when distributing the source. Dependency installation fetches packages governed by their own licenses.

The replay folders under `web/studio/fixtures/replays/` hold screenshots of seven public hackathon apps, taken while our visitors used them. Each app is listed below with its licence as the GitHub API reported it on 22 October 2026 (`gh api repos/<owner>/<repo>`, field `license`). Three of the seven publish no licence. Their screenshots are shown to report a fault we found in the public app and its fix.

| App | Repo | Licence | Replays |
|---|---|---|---|
| AirIQ | https://github.com/ashutosh7i/Air-IQ | none published | `airiq-about-404`, `airiq-about-fixed` |
| Blaze | https://github.com/intrepidbird/blaze | MIT | `blaze-server-routes` |
| EduNova AI | https://github.com/JananiSenthilraj01/EduNova-AI | none published | `edunova-study-404`, `edunova-study-fixed` |
| Liar's Dice | https://github.com/lastingParadox/liars-dice | 0BSD | `liarsdice-click-unseen` |
| PuppyTime | https://github.com/megler/PuppyTime | MIT | `puppytime-lost` |
| StreetEats | https://github.com/janellewong/StreetEats | MIT | `streeteats-sign-in` |
| Water Buddy | https://github.com/huangc01cph-ops/water-buddy | none published | `waterbuddy-v3-404`, `waterbuddy-v3-fixed` |

## First Users front door

The local front door adds URL → approved task → clearly labelled practice/Stripe TEST step → check → saved report → capability share → downloadable FAVOUR project draft. Start with `python -m sim.first_users --store ../first-users-private --port 3899`; model calls stay off. Use `--sample` for bundled examples only. See [First Users setup and limits](docs/first-users.md). No live payment or automatic FAVOUR posting is included.

The 18 October local assembly and current inventory are in `docs/swarm-simulator/INVENTORY-20261018.json`. Run application checks with `python3 -m pytest -q`; downloadable historical test files under replay fixtures are excluded from discovery. `--host 0.0.0.0` permits serving replays on a network, but refuses `--allow-models`. Public hosting still needs separate authorization.
