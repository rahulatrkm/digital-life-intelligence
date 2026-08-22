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
| Tests | 126 passing, ruff clean |
| Experiments viable | 10 / 10 populations survive and reproduce |
| Experiments interpretable | 6 / 10 (see open issues) |

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

**Done**

- Replaced the stage-1 criterion `occupies_resource_tiles`, which ran
  backwards. It measured the fraction of samples taken while standing on a
  tile that still held resource — but a cell that successfully forages eats
  the tile to zero and is then recorded as never having found it. Evolved
  populations scored 0.055 against random's 0.441 in E2 while *outliving
  them three to one*. Replaced with `harvest_efficiency`, energy won per
  unit of energy spent winning it, taken from the energy ledger: scale-free,
  comparable across arms of different size and duration, and rising with
  foraging skill rather than falling.
- Added `harvested` and `harvest_efficiency` to the metric engine.
- Started the two-sided re-calibration of E1/E6/E7 (viability **and**
  selection), criterion fixed before any detector runs.

**In flight**

- Re-calibration sweep for E1, E6, E7.
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
