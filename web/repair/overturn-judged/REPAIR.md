# Repair loop: https://github.com/Morkeeth/overturn.git

Goal: Open the About page and read why Overturn exists

| | Original `bd6a868` | Repaired `dd55810` |
|---|---|---|
| Visitor outcome | stuck | got_there |
| Visitor path | WHY THIS EXISTS → ABOUT | ABOUT |
| Returned check | red: error page | green |

What the visitor hit: Clicked 'WHY THIS EXISTS' and the page answered with error 404.
Fix: `portable-menu-links.patch` (sha256 d6faa970b033…)

Repaired: **yes** (red before, green after, and the same goal completed again).
Visitor model: nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B. Separate judge model: nvidia/Nemotron-3.5-Super-VL. 13 calls, 19,024 prompt and 637 completion tokens, 0.00268 USD at listed rates (not an invoice). Sponsor model evidence: yes.

Visitors are models, not people. The check is navigation smoke: a pass does not establish task completion by itself.
