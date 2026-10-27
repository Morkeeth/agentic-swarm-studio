# Evidence included in this public source

Counts below describe the replay bundle at the accepted product source. They are not a claim about every historical experiment. App identity uses the original repository, because unrelated app runs reuse the same loopback host and port.

## Browser replay population

| App | Saved run folders | Visitor trajectories |
|---|---|---|
| ashutosh7i/Air-IQ | [airiq-about-404](../web/studio/fixtures/replays/airiq-about-404/result.json), [airiq-about-fixed](../web/studio/fixtures/replays/airiq-about-fixed/result.json) | 6 |
| intrepidbird/blaze | [blaze-server-routes](../web/studio/fixtures/replays/blaze-server-routes/result.json) | 3 |
| JananiSenthilraj01/EduNova-AI | [edunova-study-404](../web/studio/fixtures/replays/edunova-study-404/result.json), [edunova-study-fixed](../web/studio/fixtures/replays/edunova-study-fixed/result.json) | 6 |
| lastingParadox/liars-dice | [liarsdice-click-unseen](../web/studio/fixtures/replays/liarsdice-click-unseen/result.json) | 3 |
| Morkeeth/overturn | [overturn-nemotron-404](../web/studio/fixtures/replays/overturn-nemotron-404/result.json), [overturn-nemotron-fixed](../web/studio/fixtures/replays/overturn-nemotron-fixed/result.json) | 2 |
| megler/PuppyTime | [puppytime-lost](../web/studio/fixtures/replays/puppytime-lost/result.json) | 3 |
| janellewong/StreetEats | [streeteats-sign-in](../web/studio/fixtures/replays/streeteats-sign-in/result.json) | 3 |
| huangc01cph-ops/water-buddy | [waterbuddy-v3-404](../web/studio/fixtures/replays/waterbuddy-v3-404/result.json), [waterbuddy-v3-fixed](../web/studio/fixtures/replays/waterbuddy-v3-fixed/result.json) | 6 |

**8 distinct real apps, 12 saved real-app runs, 32 visitor trajectories.** Seven apps are external; Overturn is author-owned. The additional `broken-demo-0003`, `swarm-2326` and `rerun-2335` are three controlled demo/sample runs with 13 trajectories. Total: 15 replays and 45 trajectories. A before/after run or another visitor does not create another app.

Every result declares Nemotron Nano as its visitor model. Thirteen declare Super VL as judge; the two Overturn results declare Nano as judge. Declared configuration is not proof that a judge call happened on every visit.

## The owned full repair case

[Overturn receipt](../examples/overturn/receipt.json), [original returned check](../examples/overturn/test_returned_path.py), [patch](../examples/overturn/portable-menu-links.patch), [before log](../examples/overturn/check-before.log), [after log](../examples/overturn/check-after.log) and [both recorded visits](../examples/overturn/REPAIR.html) are retained together.

The original check failed on an About 404 when served as plain files. The five-file patch passed the same check. A new recorded visitor reached the same goal. The original deployed Vercel host also passes; the reproduced fault depends on the host. This is one reproduction and retest, not a repair rate or an estimate of human usability.

The receipt contains 13 Nemotron Nano replies with model ID and usage: 16,317 prompt tokens and 617 completion tokens. The listed-rate estimate is USD 0.0011271, not a provider invoice. Rechecking the navigation path makes no new model call.

## The same case with a separate judge (27 Oct 2026)

[Judged receipt](../examples/overturn-judged/receipt.json), [report](../examples/overturn-judged/REPAIR.html), [before log](../examples/overturn-judged/check-before.log) and [after log](../examples/overturn-judged/check-after.log) record one fresh run of the same Overturn case with `--judge-after`. The original commit again failed the returned check on the About 404. The same five-file patch produced the same fixed commit, which passed. A new Nano visitor reached the About page, and its completion claim was checked by a separate `nvidia/Nemotron-3.5-Super-VL` judge, which agreed twice and quoted sentences that are on that screen.

The receipt holds 13 Token Factory replies with model ID and usage: 11 from Nano and 2 from Super VL, 19,024 prompt and 637 completion tokens, USD 0.00268 at listed rates, not a provider invoice. `recheck` on this folder returns before 1 and after 0 with no model call. This is one judged pair on a plain static host, run from the command line; it is not a success rate and not the hosted service.

## Historical evidence kept separate

The AirIQ, EduNova AI and Water Buddy before/after folders are historical examples, not three more instances of the new owned repair loop. The historical Water Buddy red/green proof used a hand-written link check. The studio also retains ten controlled command-line cases; they are not ten additional browser-tested apps.

Older copy reports a 122-app / 113-hackathon survey from 22 October. Its original classified population is not included in this public snapshot, so the aggregate cannot be independently recounted from this repository. The exact eight-app replay bundle above is available for inspection; it is not a claim that only eight apps have ever been tried.

No outside-builder adoption, time saved, sales, customer conversion or human calibration result is established here. Model and harness failures must be distinguished from defects in the app.
