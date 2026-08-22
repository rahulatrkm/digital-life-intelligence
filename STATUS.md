# World Zero — Status

Single rolling status file. Newest entry first. Updated each working day.

**Repo:** https://github.com/rahulatrkm/digital-life-intelligence
**Spec:** *The Origin of Machine Intelligence* (v4, Aug 2026)

---

## Current state

| | |
|---|---|
| Ladder reached | **stage 1 — resource behaviour** (contiguous), stage 1 (any) |
| Last full suite | 2026-08-22 (v5), 5 seeds/arm, ~170 worlds |
| Tests | 149 passing, ruff clean |
| Experiments viable | 10 / 10 populations survive and reproduce |
| Reaching stage 0 | 8 / 10 (was 4) |
| Reaching stage 1 | 6 / 10 (was 3) |
| Throughput | 5.02× via parallel workers, identical results |
| Liveness | `worldzero status [--serve PORT]` |

### Suite result, 2026-08-22 (v5)

| exp | stage 0 | stage 1 | target stage | reading |
|---|---|---|---|---|
| E0 viability | PASS | PASS | — | **PASS** |
| E1 resource seeking | — | fail | 1 | structural, see below |
| E2 memory | PASS | PASS | 2 fail | null: p=0.163, d=0.73 |
| E3 prediction | PASS | n/a | 3 fail | null: p=0.452, d=0.08 |
| E4 communication | PASS | PASS | 4 fail | null: p=0.377, d=0.43 |
| E5 cooperation | PASS | PASS | 5 fail | null: p=0.123, d=0.85 |
| E6 abstraction | PASS | PASS | 6 fail | null: p=0.409, spread 0.34 |
| E7 culture | n/a | PASS | 7 fail | null: delta −2.38 |
| E8 scientific | PASS | n/a | 8 fail | null: p=0.337, d=0.27 |
| E9 acceleration | PASS | PASS | 9,10 fail | archive 2.20 (want ≥3); IAR −0.0001, 2/5 seeds |

**Stages 2–10 are honest nulls.** Live populations, adequate statistical
power, untouched §14 detectors. No capability above stage 1 is detected.

### Open issues

1. **E1 cannot express resource seeking.** `static` food never
   replenishes, so with movement at 1.0 against idling at 0.1 the
   longest-lived strategy is to forage *less*. A random arm is
   accidentally frugal and wins. This is a property of the E1 design in
   §5.4, not a tuning gap — recorded rather than tuned away.
2. **E7 fails stage 0 on the lifespan tiebreak** (108.6 vs random
   123.3) while passing stage 1. Both arms survive, so persistence ties
   and the turnover-confounded measure decides it.
3. **E9 stage 9 is close**: archive 2.20 against a threshold of 3.
   Stage 10 shows no acceleration (2/5 seeds positive).
4. **Five ladder metrics have been found to invert under selection.**
   See the log below. Stages 0–1 have now been revised four times; the
   §14 detectors have not been touched.

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
