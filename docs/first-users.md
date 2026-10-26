# First Users

First Users starts with a public app address and one read-only task. Software visitors attempt it first; the same task can be downloaded as a project brief for verified humans through FAVOUR. The exported brief is not an integration, posting, funding or booking.

## Local front door

Install requirements-app-check.txt and Playwright Chromium as described in the README. Then run:

```sh
python -m sim.first_users --store ../first-users-private --port 3899
```

Open http://127.0.0.1:3899/. Paste an authorized running app address without credentials or query parameters. Confirm the task, acknowledge practice checkout, run a basic browser check, inspect saved screens, create a report link, and download the FAVOUR draft. Practice checkout makes no charge and supplies no real entitlement. A basic check can inspect page/link loading; it cannot establish that the chosen task was completed.

Real model visits require explicit operator enablement with --allow-models, a Token Factory key and an isolated bounded cost account. Set SIM_PROVIDER_ROOT, SIM_PROVIDER_CAP_USD and SIM_PROVIDER_STOP_USD to the approved values before starting. Model visits are read-only. The models can misinterpret tasks; check their evidence before reporting completion. The content guard rejects navigation-only pricing claims but is a bounded English heuristic and can reject valid quotes.

Stripe test checkout is enabled only by STRIPE_TEST_SECRET_KEY or a sk_test_ secret in ~/.config/keys/stripe-test.key. A live secret is refused. The return URL cannot grant a check: the server retrieves the test Checkout Session and verifies paid status, EUR1900cents and matching job metadata. No test key was available during the recorded local validation; this adapter has no Stripe runtime proof. Use Stripe-hosted confirmation for the first manual Payment Link order until the real application origin exists; never insert a fabricated hosted URL.

## Hosted sample mode

Append --sample to bind a keyless sample server. The app accepts bundled working/broken samples only; it does not visit caller URLs or run models. The pay step is practice-only even if a server key exists. It allows ten checks per anonymous tenant/day and twenty total checks per store. One worker has a45-second basic deadline. The SQLite quota is transactional; a new store resets it, so it is not a global spending cap. The sample is not an authenticated multi-tenant product.

Report links are seven-day bearer capabilities. Anyone holding the link can see that report and its screens; a new link revokes the previous one. Screens may contain sensitive target content: review before sharing. The links are local until the app is actually hosted. The public sample is not a route into private workspaces or customer URLs.

## Queue and human handoff

SQLite/WAL stores tenant ownership, immutable request identity, daily quota and micro-USD per-run cap. Fenced leases reject stale/duplicate settlement. Front-door jobs do not silently retry after a lease expires. A crashed external provider call remains a reconciliation problem, not an exactly-once inference guarantee. The local queue is single-node; distributed workers and durable object storage remain future work.

The handoff uses URL, three proposed question IDs, a reward plan and a five-card review deck. The proposed ten reviews at0.5USDC each remain unfunded. Question IDs belong to this draft format; current FAVOUR API compatibility is unverified. A human must post and sign the builder's funding. Human identity, tester supply, mobile handoff and calibrated simulation remain unverified.

## First paid offer

The first offer is First Users at EUR19 for one software check and a manually reviewed report. It includes no human-test reward budget. No payment or demand is established by the local prototype. A paid service needs an activated merchant account, real fulfillment/privacy/retention operations and outside-user acceptance; do not treat sample mode as those gates.

The basic check now uses browser Back after a successful generic reading link. It compares the starting address and normalized visible text; a changed page fails. If the reading link fails, return remains not run. This conservative check can reject dynamic text and does not establish saved or signed-in state. Hosted sample storage is ephemeral: reports and quotas reset when the instance is replaced.

## Basic-check evidence limits

Tool errors end with status error and are not a verdict that the target needs work. Each screen requires a two-second quiet window of body child/text mutations, bounded by twelve seconds. This is an observation window, not proof all future asynchronous content has loaded. Screens requiring a blocked write-shaped request are not judged. Same-page fragments do not count as the first reading path.

The basic visit allows only the exact named POST host/path pairs in sim/read_posts.json; other POSTs and every PUT remain blocked. Names such as read_ are documentation, not proof that an RPC cannot write. The shipped STRIVE read_day_card SQL was reviewed in the public source: it selects and constructs returned JSON; it does not update stored rows. A future server-side change needs a new review. No signed-in browser session or target write is supplied by this check.

## Optional single-call Nemotron explanation (OFF by default)

The browser report can optionally ask NVIDIA Nemotron-3-Nano-30B-A3B on Nebius Token Factory to explain the observed check statuses and suggest one next check. This does not change the browser verdict, simulate a person or judge task completion. No page contents, screenshots, target URL or free-form task are sent. The UI requires a separate unchecked opt-in for each job.

Enable only after separate inference authorization: append `--allow-nebius-summary --nebius-budget-db /operator-persistent-data/first-users-nebius.sqlite` to the normal server command. The named path must be outside the report store. Configure TOKEN_FACTORY_API_KEY in the server environment through the operator's secret store (or the existing local Token Factory key file). No key is sent to the browser or committed. Without the flag, no key is read and no summary call can be requested. The staged Cloud Run deployment remains OFF; do not enable there until this account file is on durable single-instance storage, not ephemeral /tmp. Keep the same budget file across restarts; deleting it or using independent replicas resets/bypasses its account and requires a new operator decision.

One fixed-model request at most per opted-in job, no retries or fallbacks, 20 second request timeout, <=2048 bytes of JSON messages and max_tokens=256 with thinking disabled. A durable SQLite transaction reserves USD0.005 before transport, never refunds it (including errors, missing usage or a crash), and rejects attempts exceeding USD0.01 total: at most two admitted attempts in this account. Duplicate job IDs cannot spend twice. A failed/blocked optional explanation leaves the browser evidence intact.

Prices checked 14 Oct 2026: USD0.06 per million input tokens and USD0.24 per million output tokens. At 1000 input + 256 output, estimate USD0.00012144/run; at the conservative 4096-input-token accounting bound + 256 output, USD0.0003072/run. Returned usage supplies the estimate; it is not an invoice. The USD0.005 reservation is >16 times that bounded estimate. This is a hard local admission ceiling, not a provider-enforced billing limit; provider rate changes, billing semantics or independently used keys are outside it. Cost source: https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference .

Rules source: https://nebiusglobalaihackathon.devpost.com/rules (14 Oct 2026). The rules define running on Nebius as a runtime Token Factory call or execution on Nebius AI Cloud, plus an NVIDIA open-source model and track requirements. This staged path addresses the runtime/model requirement only after a real call has returned with matching identity. Stubbed tests, flags, old receipts and a keyless hosted sample do not establish current runtime compliance or complete submission eligibility. Best Apps and Agents fits this minimal report explanation more directly than a claim that this step writes/runs code in Token Factory; track selection is still a submission decision.
