# Local headless batch

Run in this repository with a real Chromium-capable machine, outside the Codex sandbox. No execution was made by this lane. Model calls cost money; the runner requires explicit execution and a chosen stop.

```sh
python3 -m pip install -r requirements-app-check.txt pytest
python3 -m playwright install chromium
python3 -m sim.app_batch --store /private/tmp/nvidia-app-runs --stop-usd 1
python3 -m sim.app_batch --store /private/tmp/nvidia-app-runs --stop-usd 1 --execute
```

The first batch command previews only. The execution command prompts for a Nebius Token Factory key without echo. Do not put a key in command arguments, shell history, a plan, or a log. No key is submitted to the studio server, persisted in environment variables or written to disk. Provider authentication necessarily sends it to Nebius. Input page text and screenshots go to the configured model. The local process holds the key until exit. It does not use a saved account key file.

The stop is a user-selected USD ceiling, not measured cost. The existing account reservation system enforces it across the batch. After exhaustion, later apps are marked failed rather than presented as visited. The runner uses the existing default crowd and judge models; pin the exact permitted model IDs through the project's documented TOKEN_FACTORY_MODEL and judge settings before running.

In another terminal, serve the same store without enabling server-side model calls:

```sh
python3 -m sim.swarm_studio --store /private/tmp/nvidia-app-runs --port 4100
```

Open http://127.0.0.1:4100/ locally. The queue refreshes from persisted rows. Saved runs and bundled replays remain visible after restart. Raw results are under runs/<id>/result.json. Batch queue source is batches/<batch>/queue.json. Screenshots and traces remain beside each result. A complete run status does not mean a task succeeded: inspect the result and browser evidence. Human confirmation is separate.

The default plan is web/landing/app-plan.json, copied from the engine lane's batch.json named in its source field. It has only the apps actually scoped there. No invented apps fill capacity. To expand, copy the plan, add real scoped id/name/url/task rows and use --plan /absolute/path/plan.json. Validation permits at most 100 rows. No automatic discovery or claim of 100 tested apps is made.

Browser check before a paid run:

```sh
python3 -c 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); page=b.new_page(); page.goto("data:text/html,ready"); assert page.inner_text("body")=="ready"; b.close(); p.stop()'
```

If interrupted, the runner marks in-flight queue rows interrupted. Pending rows remain queued and are not counted as attempts. Re-run creates a separate batch, preserving history. Visual checks still required on phone and desktop; this lane was instructed to do code only.

### Optional local Codex subscription visitor

`python3 -m sim.codex_visitor --url http://127.0.0.1:4127/ --goal 'Find which models this app uses' --output /absolute/new/evidence-folder`

This explicitly separate diagnostic uses existing ChatGPT CLI authentication, not
Nebius or an API-key fallback. It only permits an owned loopback read-only target.
The CLI receives rendered page text in an isolated temporary working/config folder;
screenshots remain local. Each run has a bounded call count and retains actual
browser actions and model event output. Subscription use still consumes quota;
zero incremental API spend is not a free-compute claim. Resolved model identity
is unknown when CLI events omit it. No sponsored model or human result is inferred.

A completed retained Codex visit can return a no-model regression candidate:
`python3 -m sim.retained_visit_check --record /absolute/visit/result.json --output /absolute/new/check-folder`
It replays the recorded read-only links and requires the retained quoted answer
at the same final address. This is a narrow local regression, not a general task
oracle. A missing or ambiguous link fails rather than being silently skipped.
