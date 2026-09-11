# World Zero — Status

Single rolling status file. Newest entry first.

**Scheduled for 07:00 IST daily, with two-hour catch-up attempts**, by
[scripts/daily_report.py](scripts/daily_report.py). A running entry is written
before computation and replaced with its outcome afterward. The current-state
table is generated from the evidence, not maintained by hand. Reporting depends
on this host being available; it is not an always-on hosted service.

**Repo:** https://github.com/rahulatrkm/digital-life-intelligence
**Spec:** *The Origin of Machine Intelligence* (v4, Aug 2026)

---

## Current state

<!-- current-state:start -->
| Measurement | Current Record |
|---|---|
| Updated | 2026-09-11 07:00 IST |
| Study state | complete |
| Complete seeds per arm | 30-30 / 30 |
| Remaining worlds | 0 |
| Scope | Fixed-cohort fitness comparisons; a full pooled ladder is not established |
| Liveness | `worldzero status outputs/daily/progress.json` |
| Reporting | 07:00 IST trigger with 2-hour retries, while the host is available |
| Last test verification | 210 passed, 0 failed (2026-09-06 IST) |
<!-- current-state:end -->
### Research Status

The simulator, staged experiments, controls, detectors, storage and CLI are
implemented. The research claim remains open: a completed study or a single
fitness benefit is not a demonstration of the full intelligence ladder.

Earlier five-seed verdicts changed with the seed block. Re-running seeds 1-5
was not independent replication, and those seeds also overlapped the earlier
12-seed memory experiment. Matching numbers alone do not prove duplication;
the recorded shared inputs establish it here. The dated log retains the
historical observations; the current study uses a fixed cohort.

### Remaining Gaps

1. **Full pooled stage assessment needs all its measurements.** Legacy files
   retained fitness and metrics but not behavior traces. Their fitness can be
   recovered; missing trace-dependent criteria cannot be reconstructed. New
   result caches preserve those inputs.
2. **Statistical scope is limited.** The fixed-cohort report adjusts seven
   fitness comparisons together. It is not a complete pooled ladder verdict;
   non-significance does not establish absence of a capability.
3. **E1 and E7 have known design limitations.** Static food in E1 rewards
   conserving movement costs, and E7's stage-0 lifespan tiebreak is affected by
   population turnover. These were not retuned to obtain passing results.
4. **Unattended operation needs an available host.** Catch-up and restart
   recovery reduce wasted work but cannot guarantee a deadline during outages.

---

<!-- daily-entries -->

## 2026-09-11 IST

*Generated 2026-09-11 07:00 IST.*

<!-- study-state: complete -->

**Fixed-cohort study.**

The fixed cohort is complete. No additional simulations were started.

| Measurement | Current Record |
|---|---|
| Updated | 2026-09-11 07:00 IST |
| Study state | complete |
| Complete seeds per arm | 30-30 / 30 |
| Remaining worlds | 0 |
| Scope | Fixed-cohort fitness comparisons; a full pooled ladder is not established |
| Liveness | `worldzero status outputs/daily/progress.json` |
| Reporting | 07:00 IST trigger with 2-hour retries, while the host is available |
| Last test verification | 210 passed, 0 failed (2026-09-06 IST) |

| Experiment | Complete matched seeds |
|---|---|
| E0 | 30/30 |
| E1 | 30/30 |
| E2 | 30/30 |
| E3 | 30/30 |
| E4 | 30/30 |
| E5 | 30/30 |
| E6 | 30/30 |
| E7 | 30/30 |
| E8 | 30/30 |
| E9 | 30/30 |

Planned seeds: 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45.

**Fixed-cohort fitness comparisons: 30 seeds per arm.** The cohort freezes at its target. Holm adjustment covers the reported comparison family; before all comparisons reach the target, every result is provisional. These are fitness checks, not full stage detections. A non-significant result does not establish absence of an effect.

| exp | comparison | n | delta | d | p | p (Holm) | status |
|---|---|---|---|---|---|---|---|
| E2 | treatment vs scrambled_memory | 30 | +0.1541 | +0.151 | 0.2794 | 1.0000 | no significant fitness benefit |
| E3 | treatment vs no_memory | 30 | -0.0037 | -0.042 | 0.5747 | 1.0000 | no significant fitness benefit |
| E4 | treatment vs scrambled_signals | 30 | +0.0318 | +0.238 | 0.1794 | 1.0000 | no significant fitness benefit |
| E5 | treatment vs isolated | 30 | +0.3504 | +0.284 | 0.1344 | 0.9410 | no significant fitness benefit |
| E6 | treatment vs single_variant | 30 | +0.3288 | +0.135 | 0.3018 | 1.0000 | no significant fitness benefit |
| E7 | treatment vs no_markers | 30 | -1.1531 | -0.359 | 0.9170 | 1.0000 | no significant fitness benefit |
| E8 | treatment vs no_probe | 30 | +0.0189 | +0.192 | 0.2439 | 1.0000 | no significant fitness benefit |

---
## 2026-09-10 IST

*Generated 2026-09-10 07:00 IST.*

<!-- study-state: complete -->

**Fixed-cohort study.**

The fixed cohort is complete. No additional simulations were started.

| Measurement | Current Record |
|---|---|
| Updated | 2026-09-10 07:00 IST |
| Study state | complete |
| Complete seeds per arm | 30-30 / 30 |
| Remaining worlds | 0 |
| Scope | Fixed-cohort fitness comparisons; a full pooled ladder is not established |
| Liveness | `worldzero status outputs/daily/progress.json` |
| Reporting | 07:00 IST trigger with 2-hour retries, while the host is available |
| Last test verification | 210 passed, 0 failed (2026-09-06 IST) |

| Experiment | Complete matched seeds |
|---|---|
| E0 | 30/30 |
| E1 | 30/30 |
| E2 | 30/30 |
| E3 | 30/30 |
| E4 | 30/30 |
| E5 | 30/30 |
| E6 | 30/30 |
| E7 | 30/30 |
| E8 | 30/30 |
| E9 | 30/30 |

Planned seeds: 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45.

**Fixed-cohort fitness comparisons: 30 seeds per arm.** The cohort freezes at its target. Holm adjustment covers the reported comparison family; before all comparisons reach the target, every result is provisional. These are fitness checks, not full stage detections. A non-significant result does not establish absence of an effect.

| exp | comparison | n | delta | d | p | p (Holm) | status |
|---|---|---|---|---|---|---|---|
| E2 | treatment vs scrambled_memory | 30 | +0.1541 | +0.151 | 0.2794 | 1.0000 | no significant fitness benefit |
| E3 | treatment vs no_memory | 30 | -0.0037 | -0.042 | 0.5747 | 1.0000 | no significant fitness benefit |
| E4 | treatment vs scrambled_signals | 30 | +0.0318 | +0.238 | 0.1794 | 1.0000 | no significant fitness benefit |
| E5 | treatment vs isolated | 30 | +0.3504 | +0.284 | 0.1344 | 0.9410 | no significant fitness benefit |
| E6 | treatment vs single_variant | 30 | +0.3288 | +0.135 | 0.3018 | 1.0000 | no significant fitness benefit |
| E7 | treatment vs no_markers | 30 | -1.1531 | -0.359 | 0.9170 | 1.0000 | no significant fitness benefit |
| E8 | treatment vs no_probe | 30 | +0.0189 | +0.192 | 0.2439 | 1.0000 | no significant fitness benefit |

---
## 2026-09-07 IST

*Generated 2026-09-07 07:00 IST.*

<!-- study-state: complete -->

**Fixed-cohort study.**

The fixed cohort is complete. No additional simulations were started.

| Measurement | Current Record |
|---|---|
| Updated | 2026-09-07 07:00 IST |
| Study state | complete |
| Complete seeds per arm | 30-30 / 30 |
| Remaining worlds | 0 |
| Scope | Fixed-cohort fitness comparisons; a full pooled ladder is not established |
| Liveness | `worldzero status outputs/daily/progress.json` |
| Reporting | 07:00 IST trigger with 2-hour retries, while the host is available |
| Last test verification | 210 passed, 0 failed (2026-09-06 IST) |

| Experiment | Complete matched seeds |
|---|---|
| E0 | 30/30 |
| E1 | 30/30 |
| E2 | 30/30 |
| E3 | 30/30 |
| E4 | 30/30 |
| E5 | 30/30 |
| E6 | 30/30 |
| E7 | 30/30 |
| E8 | 30/30 |
| E9 | 30/30 |

Planned seeds: 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45.

**Fixed-cohort fitness comparisons: 30 seeds per arm.** The cohort freezes at its target. Holm adjustment covers the reported comparison family; before all comparisons reach the target, every result is provisional. These are fitness checks, not full stage detections. A non-significant result does not establish absence of an effect.

| exp | comparison | n | delta | d | p | p (Holm) | status |
|---|---|---|---|---|---|---|---|
| E2 | treatment vs scrambled_memory | 30 | +0.1541 | +0.151 | 0.2794 | 1.0000 | no significant fitness benefit |
| E3 | treatment vs no_memory | 30 | -0.0037 | -0.042 | 0.5747 | 1.0000 | no significant fitness benefit |
| E4 | treatment vs scrambled_signals | 30 | +0.0318 | +0.238 | 0.1794 | 1.0000 | no significant fitness benefit |
| E5 | treatment vs isolated | 30 | +0.3504 | +0.284 | 0.1344 | 0.9410 | no significant fitness benefit |
| E6 | treatment vs single_variant | 30 | +0.3288 | +0.135 | 0.3018 | 1.0000 | no significant fitness benefit |
| E7 | treatment vs no_markers | 30 | -1.1531 | -0.359 | 0.9170 | 1.0000 | no significant fitness benefit |
| E8 | treatment vs no_probe | 30 | +0.0189 | +0.192 | 0.2439 | 1.0000 | no significant fitness benefit |

---
## 2026-09-06 IST

*Generated 2026-09-06 13:00 IST.*

<!-- study-state: complete -->

**Fixed-cohort study.**

The fixed cohort is complete. No additional simulations were started.

| Measurement | Current Record |
|---|---|
| Updated | 2026-09-06 13:00 IST |
| Study state | complete |
| Complete seeds per arm | 30-30 / 30 |
| Remaining worlds | 0 |
| Scope | Fixed-cohort fitness comparisons; a full pooled ladder is not established |
| Liveness | `worldzero status outputs/daily/progress.json` |
| Reporting | 07:00 IST trigger with 2-hour retries, while the host is available |
| Last test verification | 210 passed, 0 failed (2026-09-06 IST) |

| Experiment | Complete matched seeds |
|---|---|
| E0 | 30/30 |
| E1 | 30/30 |
| E2 | 30/30 |
| E3 | 30/30 |
| E4 | 30/30 |
| E5 | 30/30 |
| E6 | 30/30 |
| E7 | 30/30 |
| E8 | 30/30 |
| E9 | 30/30 |

Planned seeds: 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45.

**Fixed-cohort fitness comparisons: 30 seeds per arm.** The cohort freezes at its target. Holm adjustment covers the reported comparison family; before all comparisons reach the target, every result is provisional. These are fitness checks, not full stage detections. A non-significant result does not establish absence of an effect.

| exp | comparison | n | delta | d | p | p (Holm) | status |
|---|---|---|---|---|---|---|---|
| E2 | treatment vs scrambled_memory | 30 | +0.1541 | +0.151 | 0.2794 | 1.0000 | no significant fitness benefit |
| E3 | treatment vs no_memory | 30 | -0.0037 | -0.042 | 0.5747 | 1.0000 | no significant fitness benefit |
| E4 | treatment vs scrambled_signals | 30 | +0.0318 | +0.238 | 0.1794 | 1.0000 | no significant fitness benefit |
| E5 | treatment vs isolated | 30 | +0.3504 | +0.284 | 0.1344 | 0.9410 | no significant fitness benefit |
| E6 | treatment vs single_variant | 30 | +0.3288 | +0.135 | 0.3018 | 1.0000 | no significant fitness benefit |
| E7 | treatment vs no_markers | 30 | -1.1531 | -0.359 | 0.9170 | 1.0000 | no significant fitness benefit |
| E8 | treatment vs no_probe | 30 | +0.0189 | +0.192 | 0.2439 | 1.0000 | no significant fitness benefit |

---
## 2026-08-31 IST

*Generated 2026-08-31 07:29 IST.*

**Automated suite run.** Seeds 11–15.

| | |
|---|---|
| Ladder (contiguous) | **stage 1 — resource behaviour** |
| Ladder (any) | stage 1 |
| Seeds per arm | 5 |
| Experiments passing | 1 / 10 |

| exp | stage 0 | stage 1 | target | detail |
|---|---|---|---|---|
| E0 Viability | PASS | PASS | 0 PASS | all criteria passed |
| E1 Resource seeking | n/a | fail | 1 fail | surviving descendants per founder 0.193 vs random 0.942 (gross births 4.0 vs 2.1) |
| E2 Memory pressure | PASS | PASS | 2 fail | fitness delta 0.2095, p=0.3254, d=0.311 |
| E3 Prediction pressure | PASS | n/a | 3 fail | fitness delta 0.0455, p=0.2302, d=0.448 |
| E4 Communication pressure | PASS | PASS | 4 fail | fitness delta -0.0393, p=0.7222, d=-0.375 |
| E5 Cooperation pressure | PASS | PASS | 5 fail | fitness delta -0.9593, p=0.8929, d=-0.813 |
| E6 Abstraction pressure | n/a | n/a | 6 fail | relative spread of outcome across signatures = 0.3762 (want < 0.25) |
| E7 Culture pressure | n/a | PASS | 7 fail | mean normalised I(marker; action) = 0.0189 |
| E8 Scientific behaviour pressure | PASS | n/a | 8 fail | fitness delta 0.0707, p=0.2183, d=0.516 |
| E9 Intelligence acceleration | PASS | PASS | 10 fail | mean IAR (second-half slope minus first-half slope) = -0.000084 |

**Pooled across runs.** Seeds accumulate at 30 per arm, fixed before the data; below that a comparison is provisional however its p-value looks.

| exp | comparison | n | delta | d | p | status |
|---|---|---|---|---|---|---|
| E2 | beats_scrambled_memory vs scrambled_memory | 10 | +0.3840 | +0.445 | 0.1649 | provisional (10/30) |
| E3 | beats_reactive_baseline vs no_memory | 10 | +0.0125 | +0.129 | 0.3818 | provisional (10/30) |
| E4 | beats_scrambled_signals vs scrambled_signals | 10 | +0.0471 | +0.349 | 0.2094 | provisional (10/30) |
| E5 | groups_beat_isolated vs isolated | 10 | +0.1511 | +0.123 | 0.3898 | provisional (10/30) |
| E6 | beats_memorisation_baseline vs single_variant | 10 | +0.0462 | +0.017 | 0.4798 | provisional (10/30) |
| E7 | removing_layer_reduces_performance vs no_markers | 10 | +0.3394 | +0.133 | 0.3983 | provisional (10/30) |
| E8 | information_improves_outcomes vs no_probe | 10 | +0.0736 | +0.664 | 0.0800 | provisional (10/30) |

---
## 2026-08-30 IST

*Generated 2026-08-30 23:26 IST.*

**Automated suite run.** Seeds 6–10.

| | |
|---|---|
| Ladder (contiguous) | **stage 1 — resource behaviour** |
| Ladder (any) | stage 9 |
| Seeds per arm | 5 |
| Experiments passing | 2 / 10 |

| exp | stage 0 | stage 1 | target | detail |
|---|---|---|---|---|
| E0 Viability | PASS | PASS | 0 PASS | all criteria passed |
| E1 Resource seeking | n/a | fail | 1 fail | surviving descendants per founder 0.356 vs random 0.888 (gross births 3.7 vs 2.0) |
| E2 Memory pressure | PASS | PASS | 2 fail | fitness delta 0.5586, p=0.2222, d=0.520 |
| E3 Prediction pressure | PASS | n/a | 3 fail | fitness delta -0.0205, p=0.6389, d=-0.224 |
| E4 Communication pressure | PASS | PASS | 4 fail | fitness delta 0.1334, p=0.1032, d=0.852 |
| E5 Cooperation pressure | PASS | PASS | 5 PASS | all criteria passed |
| E6 Abstraction pressure | PASS | PASS | 6 fail | relative spread of outcome across signatures = 0.3611 (want < 0.25) |
| E7 Culture pressure | n/a | PASS | 7 fail | fitness delta -0.2999, p=0.5833, d=-0.120 |
| E8 Scientific behaviour pressure | PASS | n/a | 8 fail | fitness delta 0.0765, p=0.0952, d=0.930 |
| E9 Intelligence acceleration | PASS | PASS | 10 fail | mean IAR (second-half slope minus first-half slope) = -0.000079 |

**Pooled across runs.** Seeds accumulate at 30 per arm, fixed before the data; below that a comparison is provisional however its p-value looks.

| exp | comparison | n | delta | d | p | status |
|---|---|---|---|---|---|---|
| E2 | beats_scrambled_memory vs scrambled_memory | 5 | +0.5586 | +0.520 | 0.2222 | provisional (5/30) |
| E3 | beats_reactive_baseline vs no_memory | 5 | -0.0205 | -0.224 | 0.6389 | provisional (5/30) |
| E4 | beats_scrambled_signals vs scrambled_signals | 5 | +0.1334 | +0.852 | 0.1032 | provisional (5/30) |
| E5 | groups_beat_isolated vs isolated | 5 | +1.2616 | +1.265 | 0.0397 | provisional (5/30) |
| E6 | beats_memorisation_baseline vs single_variant | 5 | -0.2965 | -0.264 | 0.6190 | provisional (5/30) |
| E7 | removing_layer_reduces_performance vs no_markers | 5 | -0.2999 | -0.120 | 0.5833 | provisional (5/30) |
| E8 | information_improves_outcomes vs no_probe | 5 | +0.0765 | +0.930 | 0.0952 | provisional (5/30) |

---
## 2026-08-28 IST

*Generated 2026-08-28 09:10 IST.*

**Automated suite run.**

| | |
|---|---|
| Ladder (contiguous) | **stage 2 — memory** |
| Ladder (any) | stage 2 |
| Seeds per arm | 5 |
| Experiments passing | 2 / 10 |

| exp | stage 0 | stage 1 | target | detail |
|---|---|---|---|---|
| E0 Viability | PASS | PASS | 0 PASS | all criteria passed |
| E1 Resource seeking | n/a | fail | 1 fail | surviving descendants per founder 0.385 vs random 0.856 (gross births 3.8 vs 2.0) |
| E2 Memory pressure | PASS | PASS | 2 PASS | all criteria passed |
| E3 Prediction pressure | PASS | n/a | 3 fail | fitness delta -0.0625, p=0.8413, d=-0.648 |
| E4 Communication pressure | PASS | PASS | 4 fail | fitness delta 0.2138, p=0.1389, d=0.754 |
| E5 Cooperation pressure | PASS | PASS | 5 fail | fitness delta 0.8171, p=0.1508, d=0.727 |
| E6 Abstraction pressure | PASS | PASS | 6 fail | relative spread of outcome across signatures = 0.3536 (want < 0.25) |
| E7 Culture pressure | n/a | PASS | 7 fail | mean normalised I(marker; action) = 0.0151 |
| E8 Scientific behaviour pressure | PASS | n/a | 8 fail | fitness delta 0.0227, p=0.4643, d=0.170 |
| E9 Intelligence acceleration | PASS | PASS | 10 fail | mean IAR (second-half slope minus first-half slope) = -0.000110 |

---
## 2026-08-27 IST

*Generated 2026-08-27 09:12 IST.*

**Automated suite run.**

| | |
|---|---|
| Ladder (contiguous) | **stage 2 — memory** |
| Ladder (any) | stage 2 |
| Seeds per arm | 5 |
| Experiments passing | 2 / 10 |

| exp | stage 0 | stage 1 | target | detail |
|---|---|---|---|---|
| E0 Viability | PASS | PASS | 0 PASS | all criteria passed |
| E1 Resource seeking | n/a | fail | 1 fail | surviving descendants per founder 0.385 vs random 0.856 (gross births 3.8 vs 2.0) |
| E2 Memory pressure | PASS | PASS | 2 PASS | all criteria passed |
| E3 Prediction pressure | PASS | n/a | 3 fail | fitness delta -0.0625, p=0.8413, d=-0.648 |
| E4 Communication pressure | PASS | PASS | 4 fail | fitness delta 0.2138, p=0.1389, d=0.754 |
| E5 Cooperation pressure | PASS | PASS | 5 fail | fitness delta 0.8171, p=0.1508, d=0.727 |
| E6 Abstraction pressure | PASS | PASS | 6 fail | relative spread of outcome across signatures = 0.3536 (want < 0.25) |
| E7 Culture pressure | n/a | PASS | 7 fail | mean normalised I(marker; action) = 0.0151 |
| E8 Scientific behaviour pressure | PASS | n/a | 8 fail | fitness delta 0.0227, p=0.4643, d=0.170 |
| E9 Intelligence acceleration | PASS | PASS | 10 fail | mean IAR (second-half slope minus first-half slope) = -0.000110 |

---
## 2026-08-26 IST

*Generated 2026-08-26 09:10 IST.*

**Automated suite run.**

| | |
|---|---|
| Ladder (contiguous) | **stage 2 — memory** |
| Ladder (any) | stage 2 |
| Seeds per arm | 5 |
| Experiments passing | 2 / 10 |

| exp | stage 0 | stage 1 | target | detail |
|---|---|---|---|---|
| E0 Viability | PASS | PASS | 0 PASS | all criteria passed |
| E1 Resource seeking | n/a | fail | 1 fail | surviving descendants per founder 0.385 vs random 0.856 (gross births 3.8 vs 2.0) |
| E2 Memory pressure | PASS | PASS | 2 PASS | all criteria passed |
| E3 Prediction pressure | PASS | n/a | 3 fail | fitness delta -0.0625, p=0.8413, d=-0.648 |
| E4 Communication pressure | PASS | PASS | 4 fail | fitness delta 0.2138, p=0.1389, d=0.754 |
| E5 Cooperation pressure | PASS | PASS | 5 fail | fitness delta 0.8171, p=0.1508, d=0.727 |
| E6 Abstraction pressure | PASS | PASS | 6 fail | relative spread of outcome across signatures = 0.3536 (want < 0.25) |
| E7 Culture pressure | n/a | PASS | 7 fail | mean normalised I(marker; action) = 0.0151 |
| E8 Scientific behaviour pressure | PASS | n/a | 8 fail | fitness delta 0.0227, p=0.4643, d=0.170 |
| E9 Intelligence acceleration | PASS | PASS | 10 fail | mean IAR (second-half slope minus first-half slope) = -0.000110 |

---
## 2026-08-25 IST

*Generated 2026-08-25 09:12 IST.*

**Automated suite run.**

| | |
|---|---|
| Ladder (contiguous) | **stage 2 — memory** |
| Ladder (any) | stage 2 |
| Seeds per arm | 5 |
| Experiments passing | 2 / 10 |

| exp | stage 0 | stage 1 | target | detail |
|---|---|---|---|---|
| E0 Viability | PASS | PASS | 0 PASS | all criteria passed |
| E1 Resource seeking | n/a | fail | 1 fail | surviving descendants per founder 0.385 vs random 0.856 (gross births 3.8 vs 2.0) |
| E2 Memory pressure | PASS | PASS | 2 PASS | all criteria passed |
| E3 Prediction pressure | PASS | n/a | 3 fail | fitness delta -0.0625, p=0.8413, d=-0.648 |
| E4 Communication pressure | PASS | PASS | 4 fail | fitness delta 0.2138, p=0.1389, d=0.754 |
| E5 Cooperation pressure | PASS | PASS | 5 fail | fitness delta 0.8171, p=0.1508, d=0.727 |
| E6 Abstraction pressure | PASS | PASS | 6 fail | relative spread of outcome across signatures = 0.3536 (want < 0.25) |
| E7 Culture pressure | n/a | PASS | 7 fail | mean normalised I(marker; action) = 0.0151 |
| E8 Scientific behaviour pressure | PASS | n/a | 8 fail | fitness delta 0.0227, p=0.4643, d=0.170 |
| E9 Intelligence acceleration | PASS | PASS | 10 fail | mean IAR (second-half slope minus first-half slope) = -0.000110 |

---
## 2026-08-24 IST

*Generated 2026-08-24 12:04 IST.*

**Automated suite run.**

| | |
|---|---|
| Ladder (contiguous) | **stage 2 — memory** |
| Ladder (any) | stage 2 |
| Seeds per arm | 5 |
| Experiments passing | 2 / 10 |

| exp | stage 0 | stage 1 | target | detail |
|---|---|---|---|---|
| E0 Viability | PASS | PASS | 0 PASS | all criteria passed |
| E1 Resource seeking | n/a | fail | 1 fail | surviving descendants per founder 0.385 vs random 0.856 (gross births 3.8 vs 2.0) |
| E2 Memory pressure | PASS | PASS | 2 PASS | all criteria passed |
| E3 Prediction pressure | PASS | n/a | 3 fail | fitness delta -0.0625, p=0.8413, d=-0.648 |
| E4 Communication pressure | PASS | PASS | 4 fail | fitness delta 0.2138, p=0.1389, d=0.754 |
| E5 Cooperation pressure | PASS | PASS | 5 fail | fitness delta 0.8171, p=0.1508, d=0.727 |
| E6 Abstraction pressure | PASS | PASS | 6 fail | relative spread of outcome across signatures = 0.3536 (want < 0.25) |
| E7 Culture pressure | n/a | PASS | 7 fail | mean normalised I(marker; action) = 0.0151 |
| E8 Scientific behaviour pressure | PASS | n/a | 8 fail | fitness delta 0.0227, p=0.4643, d=0.170 |
| E9 Intelligence acceleration | PASS | PASS | 10 fail | mean IAR (second-half slope minus first-half slope) = -0.000110 |

---
## 2026-08-23 IST

*Entries are dated in IST, since the report is due at 07:00 IST — which
falls on the previous day in the Americas.*

**Stage 2 reached: memory emerges once runs are long enough.**

The ladder moved from stage 1 to **stage 2**, the first capability found
above resource behaviour. Not a better detector and not a tuned
parameter — a default.

`BASE_OVERRIDES` used 4,000 steps because that was *"small enough that
the whole suite runs on a laptop"*. Measured at 12 seeds per arm, with
only `stop.max_steps` varying:

| steps | d | p |
|---|---|---|
| 4,000 | 0.073 | 0.419 |
| 6,000 | 0.168 | 0.322 |
| 8,000 | 0.231 | 0.287 |
| 12,000 | 0.565 | 0.097 |
| **16,000** | **1.023** | **0.0120** |

A monotonic climb across five independent lengths is far stronger than a
single pass: a fluke does not produce a dose-response curve. A
convenience default had become a scientific bound.

**Controls that make it credible**

- Longer runs are *not* a universal fix — E3, E4, E6, E8 at 16,000 gave
  d = −0.373, 0.643, −0.018, 0.414. Had everything improved, long runs
  would look like a general inflator, and memory with them.
- E2 passes at **5 seeds inside the full suite**, independently of the
  12-seed isolated run that found it.

**Two large effects were noise, and more data proved it**

E2 at 4k: d = 2.576 → 0.727 → 0.073 as n went 3 → 5 → 12. E5: 0.847 →
0.447. Decaying-toward-zero is noise; deflating-but-stable (2.333 →
1.023) is a real effect first measured optimistically. Had the threshold
been relaxed to p<0.15 instead of adding seeds, both would have passed —
two false positives, and stage 2 would have been indistinguishable.

**A sixth criterion that could never fire**

`acts_before_future_state` demanded an exact key `(timestep + lag, x, y)`,
but tiles are recorded every `trace_interval` = 20 while lags come from
`cue_lead_time` = 12. Lags 6/12/24 returned **0 pairs, always**, against a
requirement of 50 — stage 3 had never been tested. Now matched to the
nearest observation within one sampling interval. E3 moves to confidence
0.67, so its failure is a measured null rather than a missing measurement.

**Throughput ≈ 7.3×**

1.16× per-step (double dict lookups, linear scans, re-sorting an
immutable genome) × 5.02× parallel × 1.25× from raising the worker cap to
15 once measurement showed SMT does help this pure-Python loop. Every
step verified to leave results bit-identical.

**Automation:** the 07:00 IST job ran unattended for the first time and
produced the entry above it.

---
## 2026-08-22

**Throughput — 5× faster**

| E0, 3 arms × 5 seeds × 1200 steps | |
|---|---|
| sequential | 81.7 s |
| parallel ×8 | 16.3 s |
| **speedup** | **5.02×** — identical `final_stats` |

The machine has 8 cores and the runner used one. §11.2 requires parallel
execution not to change biological outcomes, which holds by construction:
a run is fully determined by config and seed, and every cell-level draw
comes from a stream keyed on that cell's identity rather than a shared
cursor. Every arm of an experiment now shares one worker pool.
`--workers 0` auto-detects. Tests assert sequential and parallel agree on
`final_stats`, seed ordering, control grouping and ladder verdict.

Profiled first rather than guessing: `read_sensor` is 18% of CPU and
genome evaluation ~40% — real, but not where the win was.

**Observability — because a job died silently**

Yesterday's calibration sweep vanished, leaving an empty log and an
untouched output directory, which from outside is identical to a job
still working.

```
worldzero status outputs/progress.json             # exit 0 if alive
worldzero status outputs/progress.json --serve 8787
```

`/status` and `/healthz`, the latter returning 503 when not alive so a
watchdog needs no parsing. Liveness is decided by **staleness** — a run
that stops refreshing without recording an outcome reads as `stale`, not
`running`. Failures capture the exception rather than just stopping.

**Fixed — stage 1 criterion ran backwards**

`occupies_resource_tiles` measured the fraction of samples taken while
standing on a tile that *still held* resource. A cell that forages
successfully eats the tile to zero and is recorded as never having found
it. In E2 the evolved population scored 0.055 against random's 0.441
while outliving it three to one. Replaced with `harvest_efficiency` —
energy won per unit spent winning it, from the ledger. Scale-free and
rises with skill instead of falling.

**Three bugs found in my own new code, each by measurement**

1. **Windows spawn footgun.** Workers re-import `__main__`, so the
   unguarded benchmark script had 8 workers re-run it, deleting the
   output directory under the parent. The tests could not have caught
   this — under pytest `__main__` is pytest, which is import-safe.
   `BrokenProcessPool` now re-raises naming both cause and fix.
2. **Heartbeat was a side effect of work finishing.** With runs taking
   up to 300 s, a healthy job crossed the 120 s staleness threshold and
   read as dead. Liveness now has its own thread.
3. **A status poller could kill the writer.** Windows refuses to replace
   a file another handle has open, so polling raised `PermissionError`
   inside the heartbeat thread. Replace now retries then drops the
   update — a missed refresh is recoverable, a crashed run is not.

**Recalibrated E6 and E7 for selection, not just survival**

84 worlds swept in parallel, 8.5 min. Criterion two-sided and fixed
before any detector ran: survives every seed **and** beats a
random-action arm.

| | before | after | evolved vs random |
|---|---|---|---|
| E6 | 0.16 / 0.10 | **0.12 / 0.07** | 18.9v10.9, 13.7v9.7, 18.8v10.2 |
| E7 | 0.60 / 0.40 | **0.40 / 0.25** | 51.4v34.9, 50.4v36.7, 51.3v39.3 |

E1 has no such setting and was left alone — see open issues.

**Five ladder metrics found inverted under selection**

Each was defined on a quantity that *successful* behaviour depletes,
dilutes or turns over, so it scored adaptation downwards:

| metric | rewarded | evidence |
|---|---|---|
| `occupies_resource_tiles` | not eating | E2: evolved 0.055 vs random 0.441 while outliving it 3× |
| extinct-arm births-per-capita | dying | E3: dead arm scored 2062 vs living 107 |
| novelty `_bucket` hash | never varying | archive 0 after 12k steps, gen 253 |
| stage-0 `mean_lifespan` | not breeding | E4: extinct arm 112 vs thriving 42 |
| gross births | churning | E0: random 2× births, 236 cells vs 331 |

Fixing them moved stage 0 from 4/10 to 8/10 experiments and stage 1
from 3/10 to 6/10. The §14 detectors for stages 2–10 remain untouched,
so every claim above stage 1 still rests on the original criteria.

**Result: ladder still reaches stage 1.** Stages 2–10 are now honest
nulls rather than artefacts — live populations, adequate power.

---
## 2026-08-19

**Fixed — four defects, each of which silently invalidated results**

1. **Seasonal catastrophe fired at t=0.** `0 % season_period == 0`, so the
   catastrophe triggered during initialisation. Measured: 51% of the world
   lethal at t=1 (up from 2%), ~half the 200 founders standing in it, peak
   hazard 4.0 killing a cell in ~2 steps. E7 and E9 lost half their founding
   population within three steps of world creation.
2. **Control comparisons could never reach significance.** Two-sided
   permutation test over 3v3 runs: only C(6,3)=20 labellings, and the
   observed split plus its mirror always qualify, so p could not fall below
   ≈0.10 against a p<0.05 bar. *Every* control-comparison detector failed by
   construction. Now directional (all §17 controls remove a mechanism),
   exactly enumerated for small samples, and reports `underpowered` rather
   than a false null. Default replicates 3 → 5.
3. **Extinct arms inflated the stage-1 rate.** `births / max(1, population)`
   returned total births for a dead arm — E3's extinct random control scored
   2062 "per capita" against a living treatment's 107. Now per founder.
4. **Novelty archive could never accept an entry.** Candidates were keyed on
   `hash(round(signature, 2))` of a continuous 12-D population average, so a
   behaviour drifting by a thousandth became a new candidate. Measured: 30
   observations, 18 keys, 12 repeats, 0 archived, best candidate reached 1 of
   the 3 generations needed. `novelty_archive` was constant zero, and since
   IAR is its slope, IAR was identically 0. Now matched by distance.

**Calibrated** — at published settings 9 of 10 experiments went extinct in
200–500 steps, so their detectors compared dead worlds. Criterion fixed in
advance: survives every seed, max_generation ≥ 10, carrying-capacity fields
only. Three mechanics decided which knob works, each found by measurement
after a wasted sweep:

- `hidden` never reads `regen_rate` (it schedules from the patch mask)
- `scarce` applies `scarcity_factor` twice → 0.5 compounds to 0.25, ~4
  patches in a 64×64 world
- every regime clips at `max_per_tile`, so past a point extra regen is
  discarded and only raises boom-bust amplitude

**Added** — checkpoint CLI (`inspect`, `resume`) plus a committed 66 KB
reference checkpoint as the format's compatibility contract.

**Notable non-result** — E2's memory effect measured `d=2.576` at 3 seeds and
`d=0.727` at 5. The large effect was small-sample noise. Adding seeds rather
than lowering the threshold is what kept that from becoming a false positive.

---

## 2026-08-18

Completed the implementation from the whitepaper: the missing `worldzero.cli`
entry point (declared in `pyproject.toml` but absent, so an installed package
failed on first invocation), `configs/`, the Appendix C unit tests, the §21
checklist tests, README, LICENSE.

Fixed checkpoints losing RNG stream state, which made a resumed world diverge
from the run it was meant to continue despite the module claiming an exact
round-trip. Fixed experiment verdicts counting detectors the spec never
declared, so E0 failed on resource seeking — E1's target, not E0's.
