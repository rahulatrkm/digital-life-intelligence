# World Zero — Status

Single rolling status file. Newest entry first. Updated each working day.

**Repo:** https://github.com/rahulatrkm/digital-life-intelligence
**Spec:** *The Origin of Machine Intelligence* (v4, Aug 2026)

---

## Current state

| | |
|---|---|
| Ladder reached | **stage 1 — resource behaviour** (contiguous), stage 1 (any) |
| Last full suite | 2026-08-19, 5 seeds/arm, ~100 worlds |
| Tests | 145 passing, ruff clean |
| Experiments viable | 10 / 10 populations survive and reproduce |
| Experiments interpretable | 6 / 10 (see open issues) |
| Throughput | 5.02× via parallel workers, identical results |
| Liveness | `worldzero status [--serve PORT]` |

### Suite result, 2026-08-19

| exp | verdict | reading |
|---|---|---|
| E0 viability | **PASS** | evolved fitness 25.6 vs random 11.0 |
| E1 resource seeking | fail | *uninterpretable* — no selection pressure |
| E2 memory | fail | **honest null** — delta 4.36, p=0.163, d=0.73 |
| E3 prediction | fail | **honest null** — delta 0.02, p=0.452 |
| E4 communication | fail | **honest null** — delta 0.42, p=0.377 |
| E5 cooperation | fail | **honest null** — delta 3.40, p=0.123, d=0.85 |
| E6 abstraction | fail | *uninterpretable* — no selection pressure |
| E7 culture | fail | *uninterpretable* — no selection pressure |
| E8 scientific | fail | **honest null** — delta 0.13, p=0.337 |
| E9 acceleration | fail | stages 9/10 **void** — broken novelty archive |

Five of nine failures are real measurements. Four are not yet evidence
about anything.

### Open issues

1. **Selection pressure absent in E1, E6, E7.** Random-action populations
   outscore evolved ones (E7: 94.3 vs 88.2; E6: 25.1 vs 22.2; E1: 60.5 vs
   23.0). The 08-19 calibration fixed §19's "all cells die quickly" and
   walked into §19's "no adaptation". Being re-calibrated 08-22.
2. **E9 stages 9/10 need a re-run.** They measured a novelty archive that
   could never accept an entry. Fixed 08-19; results not yet regenerated.
3. **E1 is terminal by construction.** `static` food never replenishes, so
   the population must eventually collapse; the open question is which
   measurement window holds a living, still-evolving population.

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

**In flight**

- Two-sided recalibration of E1/E6/E7 (84 worlds, parallel, observable).
- E9 re-run pending the novelty fix.

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
