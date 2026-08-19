# World Zero

Reference implementation of *The Origin of Machine Intelligence: A Digital Life
Theory of Emergent Intelligence and a Practical Blueprint to Build the
Simulator* (v4, August 2026).

The question the paper asks is whether **intelligence can emerge from
non-intelligent computational matter**. So this repository contains no
pretrained model, no planner, no reward function and no designed language.
Cells are engineered to live, mutate, reproduce and die. They are not
engineered to think.

> **Boundary rule (§3).** The cell can be engineered to live, mutate, reproduce
> and die. It must not be engineered to think.

## Install

```bash
git clone https://github.com/rahulatrkm/digital-life-intelligence.git
cd digital-life-intelligence
pip install -e ".[dev,viz]"
```

Python 3.10+. The core simulator needs only NumPy and PyYAML; Matplotlib is
optional and used solely for the metric dashboard.

## Quickstart

```bash
# Watch a world evolve in the terminal
worldzero watch --size 48 --population 150 --every 10

# One instrumented run: event log, metrics, checkpoints, summary
worldzero run -c configs/world_zero.yaml --steps 4000 --size 64

# Run a staged experiment with its ablation controls and detectors
worldzero experiment E2 --replicates 3

# Run the whole ladder
worldzero suite --only E0 E1 E2 --steps 2000

# What is available
worldzero list
```

Every run writes to `outputs/<run_id>/`:

| File | Contents |
| --- | --- |
| `config.yaml` | the exact resolved config |
| `provenance.json` | code version, config fingerprint, seed, platform, git commit |
| `events.jsonl` | append-only event log (§12.1) |
| `metrics/series.jsonl` | metric snapshots over time |
| `summary.json` | final stats, lineage summary, fitness |
| `checkpoints/` | resumable world snapshots |

Run directories are regenerable and can reach gigabytes, so they are gitignored.

## Checkpoints

A checkpoint captures the whole world — grids, cells, genomes, energy ledger,
lineage aggregates, per-stream RNG state — so a restored run continues
*identically* rather than merely similarly.

```bash
# Snapshot every 1000 steps during a run
worldzero run --steps 5000 --set logging.checkpoint_interval=1000

# Look at one without running it
worldzero inspect reference/world_zero_step2000.json.gz

# Continue it
worldzero resume reference/world_zero_step2000.json.gz --steps 500 --save next.json.gz
```

[reference/](reference) holds one small checkpoint that ships with the
repository: a 32×32 world at step 2000, 66 KB gzipped. It is the checkpoint
format's compatibility contract — `tests/test_reference_checkpoint.py` loads and
resumes it, so a schema change that would orphan everyone's existing
checkpoints fails in CI rather than in their run. Regenerate it with
`python scripts/make_reference_checkpoint.py`.

Size matters here: gzipped, a 32×32 world is ~66 KB and a 64×64 world ~250 KB,
but uncompressed they are 0.7–4 MB and dominated by cell genomes. Committing
bulk run checkpoints would bloat history permanently, so only the curated
reference file is tracked.

## How it works

A **cell** has energy, position, age, integrity, a genome, memory registers and
nothing else (§4.1). Its genome is a **rule table** — an ordered list of
`if <sensor> <comparator> <threshold> then <action>` genes (§6.1) — chosen over
a neural genome because it is transparent, cheaply mutable and auditable.

Each timestep every living cell senses, decides, pays, acts, metabolises, maybe
reproduces and maybe dies (§7.1). Sensing costs energy, so information is never
free. Actions cost energy, so behaviour always has a tradeoff.

Nothing optimises anything. There is no fitness function in the loop — only
death, inheritance and mutation.

### The emergence ladder (§9)

| Stage | Target | How it is evidenced |
| --- | --- | --- |
| 0 | Self-maintenance | outlives a random-action baseline |
| 1 | Resource behaviour | movement becomes resource-directed |
| 2 | Memory | behaviour depends on register content, beats scrambled-memory control |
| 3 | Prediction | acts before the future state is observable |
| 4 | Communication | signals carry mutual information, beats scrambled-signal control |
| 5 | Cooperation | groups beat matched isolated individuals |
| 6 | Abstraction | generalises across surface variants, beats a memoriser |
| 7 | Culture | information outlives its author and later cells use it |
| 8 | Scientific behaviour | costly probes improve later outcomes |
| 9 | Civilization | persistent novelty accumulates |
| 10 | Intelligence acceleration | the capability growth *rate* increases |

The ladder is reported as the **highest stage with no gaps below it**. A
communication result with no memory result underneath is far more likely to be a
measurement artefact than a leapfrog.

### Detectors are built to say no

Every detector (§14) reports named criteria and claims detection **only when all
of them pass**. Each one declares the ablation it requires and returns
"unavailable" rather than a verdict when that control is missing, so a forgotten
control surfaces as a gap instead of a false positive.

A signal channel that is merely busy is not communication: §19 lists "signals
spammed with no information" as a named failure mode, so the communication
detector measures mutual information, not volume.

### Controls remove, never add (§17)

All twelve controls in `configs/ablations.yaml` *remove* a mechanism. None add
one and none change the resource economy, so a fitness gap between a treatment
and its control is attributable to the missing mechanism rather than to a
different world.

The subtle one is `scrambled_memory`. Disabling memory changes the architecture;
scrambling it preserves the architecture and destroys only the *content*, which
is what isolates whether stored data is doing work.

## Experiments (§16)

`E0` viability · `E1` resource seeking · `E2` memory · `E3` prediction ·
`E4` communication · `E5` cooperation · `E6` abstraction · `E7` culture ·
`E8` scientific behaviour · `E9` intelligence acceleration

Staging is enforced structurally, not by convention: `cell.max_sensor_stage`
gates which sensors and actions mutation can reach, so a cell in E1 physically
cannot signal. That is what stops a later mechanism from quietly carrying an
earlier result.

## Repository layout

```
src/worldzero/
  core/          simulation kernel, physics, config, RNG, energy ledger, lineage
  genome/        gene format, sensors, execution, mutation operators
  environments/  6 resource regimes, 6 hazard regimes
  metrics/       core metrics, information theory, novelty archive, traces
  detectors/     the section 14 detectors and the emergence ladder
  experiments/   staged suite E0-E9, ablation controls, runner
  storage/       event log, checkpoints, run containment
  viz/           terminal render, sparklines, replay
configs/         world_zero.yaml (Appendix A), ablations.yaml (§17)
tests/           Appendix C unit tests and the §21 checklist
```

## Determinism (§11.2)

Every run has an explicit seed, and randomness comes only from controlled
generators. Stochastic decisions belonging to a *cell* draw from a stream
derived from that cell's identity rather than from a shared cursor, so sharding
a population across workers cannot change what evolves.

Same config plus same seed reproduces the same event log, byte for byte. That is
asserted in the test suite, not merely intended.

## Energy conservation (§21)

Every joule is attributed to a bucket, and the identity

```
injected == in_living_cells + spent + lost_at_death - initial_endowment
```

is checked directly in `tests/test_checklist.py`, including through total
population extinction. Without a ledger, "all costs and gains balance" would be
unfalsifiable.

## Tests

```bash
pytest
```

`tests/test_appendix_c.py` implements the ten unit tests the paper names in
Appendix C. `tests/test_checklist.py` covers the §21 checklist: reproducibility,
energy accounting, lineage integrity, event logging, checkpoint round-trip and
exact-versus-accelerated validation.

## Safety and containment (§20)

The simulator is closed. Evolved genomes are **data, never executable host
code** — they are interpreted by a rule-table evaluator that can only emit the
fixed action set. Organisms have no network access and no filesystem access;
every write is resolved through `RunDirectory`, which raises `ContainmentError`
on any path that escapes the run directory. Each run records full provenance.

## Status

The kernel, genome engine, environments, metrics, detectors, ladder, experiment
suite, storage and CLI are implemented and tested. What this repository does
*not* yet claim is a result: running the suite tells you which stages a given
configuration reaches, and the honest default answer for a short run on a laptop
is "the lower ones".

## License

MIT — see [LICENSE](LICENSE).
