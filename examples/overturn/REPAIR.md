# Repair loop: https://github.com/Morkeeth/overturn.git

Goal: Open the About page and read why Overturn exists

| | Original `bd6a868` | Repaired `dd55810` |
|---|---|---|
| Visitor outcome | stuck | got_there |
| Visitor path | ABOUT → WHY THIS EXISTS | ABOUT |
| Returned check | red: error page | green |

What the visitor hit: Clicked 'ABOUT' and the page answered with error 404.
Fix: `portable-menu-links.patch` (sha256 d6faa970b033…)

Repaired: **yes** (red before, green after, and the same goal completed again).
Visitor model: nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B. 13 calls, 16,317 prompt and 617 completion tokens, 0.00113 USD at listed rates (not an invoice). Sponsor model evidence: yes.

Deployed original at https://overturn-morkeeths-projects.vercel.app/: green.

Visitors are models, not people. The check is navigation smoke: a pass does not establish task completion by itself.
