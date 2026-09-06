"""Recover and finish a fixed cohort, reporting progress before expensive work.

    python scripts/daily_report.py --finish          all remaining worlds
    python scripts/daily_report.py --prepare-only    recover and plan, no simulation
    python scripts/daily_report.py --no-run          report existing evidence only
    python scripts/daily_report.py --no-commit       do not commit or push
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worldzero.experiments import pool as pooling  # noqa: E402
from worldzero.experiments import study  # noqa: E402
from worldzero.experiments.suite import SUITE  # noqa: E402
from worldzero.storage.locking import exclusive_file_lock  # noqa: E402
from worldzero.storage.progress import ProgressReporter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "STATUS.md"
OUTPUT = ROOT / "outputs" / "daily"
SUMMARY = OUTPUT / "suite-summary.json"
POOL = ROOT / "evidence" / "pool.json"
"""Tracked, unlike outputs/: this is the accumulated record, not run scratch."""
IST = timezone(timedelta(hours=5, minutes=30))

MARKER = "<!-- daily-entries -->"
SNAPSHOT_START = "<!-- current-state:start -->"
SNAPSHOT_END = "<!-- current-state:end -->"

SEED_EPOCH = date(2026, 8, 30)
SEED_ORIGIN = 6
"""Seeds 1-5 were spent on the runs before rotation existed; day zero starts after them."""


def seed_base(today: date, replicates: int) -> int:
    """First seed for a given day, so no two days measure the same worlds.

    Every daily run until now used seeds 1-5 against an unchanged config. The
    engine is deterministic, so those runs were one measurement reported five
    times, not five measurements. Blocking the seed space by day makes each run
    contribute worlds no earlier run has seen.
    """
    return SEED_ORIGIN + max(0, (today - SEED_EPOCH).days) * replicates


def ist_today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def ist_stamp() -> str:
    """Entries are dated in IST because the report is due at 07:00 IST, which
    falls on the previous day in most other zones. Spelling out the zone stops
    a reader in another timezone reading the heading as wrong."""
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")


def run_suite(replicates: int, base: int) -> tuple[bool, str]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    previous_write = SUMMARY.stat().st_mtime_ns if SUMMARY.exists() else None
    command = [
        sys.executable,
        "-m",
        "worldzero.cli",
        "suite",
        "--replicates",
        str(replicates),
        "--seed",
        str(base),
        "--workers",
        "0",
        "--output",
        str(OUTPUT),
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    # The suite exits non-zero whenever any experiment fails its detectors,
    # which is the normal scientific outcome, not an error.
    note = completed.stdout + completed.stderr
    if completed.returncode not in (0, 1) or not SUMMARY.exists():
        return False, note or f"suite exited {completed.returncode} without results"
    if SUMMARY.stat().st_mtime_ns == previous_write:
        return False, note + "\nNo fresh suite summary; previous results were not reused."
    data = json.loads(SUMMARY.read_text(encoding="utf-8"))
    if data.get("seeds") != list(range(base, base + replicates)):
        return False, note + "\nSuite summary seeds do not match this run."
    return True, note


def stage_mark(detections: dict[int, dict], required: set[str], stage: int) -> str:
    """PASS, fail, or n/a for a ladder stage.

    A stage the experiment never claimed to test is not a failure: stages 0 and
    1 are measured for every experiment so the ladder has a base, but only the
    declared detectors decide its verdict.
    """
    found = detections.get(stage)
    if found is None:
        return "\u2014"
    if found["detected"]:
        return "PASS"
    return "fail" if found.get("detector") in required else "n/a"


def summarise(data: dict[str, Any]) -> list[str]:
    ladder = data.get("ladder", {})
    experiments = data.get("experiments", [])

    lines = [
        f"| Ladder (contiguous) | **stage {ladder.get('highest_contiguous_stage')} — "
        f"{ladder.get('highest_contiguous_name')}** |",
        f"| Ladder (any) | stage {ladder.get('highest_any_stage')} |",
        f"| Seeds per arm | {len(data.get('seeds', []))} |",
        f"| Experiments passing | {sum(1 for e in experiments if e.get('passed'))} / "
        f"{len(experiments)} |",
        "",
        "| exp | stage 0 | stage 1 | target | detail |",
        "|---|---|---|---|---|",
    ]

    for experiment in experiments:
        detections = {d["stage"]: d for d in experiment.get("detections", [])}
        required = set(experiment.get("required_detectors", []))


        # DetectionResult serialises its name under "detector".
        target = [
            d for d in experiment.get("detections", []) if d.get("detector") in required
        ]
        if target:
            worst = min(target, key=lambda d: d["confidence"])
            failed = [c for c in worst.get("criteria", []) if not c.get("passed")]
            detail = failed[0]["detail"] if failed else "all criteria passed"
            target_text = f"{worst['stage']} {'PASS' if worst['detected'] else 'fail'}"
        else:
            detail = ""
            target_text = "—"

        lines.append(
            f"| {experiment['experiment_id']} {experiment['name']} | "
            f"{stage_mark(detections, required, 0)} | "
            f"{stage_mark(detections, required, 1)} | {target_text} | {detail[:88]} |"
        )
    return lines


def pooled_lines(pool: dict[str, Any], data: dict[str, Any]) -> list[str]:
    """Rows for the control comparisons that accumulating seeds can settle.

    Only comparisons the target detector actually rests on appear here. Listing
    every arm would invite reading down the column for whichever pairing looks
    best that morning, which is the same error as choosing a stopping rule after
    seeing the data.
    """
    comparisons = []
    for experiment_id, arm in study.FITNESS_CONTROLS.items():
        test = pooling.pooled_test(pool, experiment_id, arm)
        if test is not None:
            comparisons.append((experiment_id, "treatment", arm, test))

    if not comparisons:
        return []
    adjusted = holm_adjust([test.p_value for _, _, _, test in comparisons])
    family_complete = len(comparisons) == len(study.FITNESS_CONTROLS) and all(
        test.n_treatment == pooling.TARGET_SEEDS for _, _, _, test in comparisons
    )
    rows = []
    for (experiment_id, criterion, arm, test), adjusted_p in zip(
        comparisons, adjusted, strict=True
    ):
        if not family_complete:
            verdict = f"provisional ({test.n_treatment}/{pooling.TARGET_SEEDS})"
        elif test.statistic > 0 and adjusted_p < 0.05:
            verdict = "fitness benefit detected"
        else:
            verdict = "no significant fitness benefit"
        rows.append(
            f"| {experiment_id} | {criterion} vs {arm} | {test.n_treatment} | "
            f"{test.statistic:+.4f} | {test.effect_size:+.3f} | "
            f"{test.p_value:.4f} | {adjusted_p:.4f} | {verdict} |"
        )
    return [
        "",
        f"**Fixed-cohort fitness comparisons: {pooling.TARGET_SEEDS} seeds per arm.** "
        "The cohort freezes at its target. Holm adjustment covers the reported comparison "
        "family; before all comparisons reach the target, every result is provisional. "
        "These are fitness checks, not full stage detections. A non-significant result "
        "does not establish absence of an effect.",
        "",
        "| exp | comparison | n | delta | d | p | p (Holm) | status |",
        "|---|---|---|---|---|---|---|---|",
        *rows,
    ]


def holm_adjust(values: list[float]) -> list[float]:
    adjusted = [1.0] * len(values)
    previous = 0.0
    for rank, index in enumerate(sorted(range(len(values)), key=values.__getitem__)):
        previous = max(previous, min(1.0, values[index] * (len(values) - rank)))
        adjusted[index] = previous
    return adjusted


def build_entry(
    date: str,
    ok: bool,
    data: dict[str, Any] | None,
    note: str,
    pool: dict[str, Any] | None = None,
    seeds: list[int] | None = None,
) -> str:
    lines = [f"## {date} IST", "", f"*Generated {ist_stamp()}.*", ""]
    if ok and data:
        header = "**Automated suite run.**"
        if seeds:
            header += f" Seeds {seeds[0]}–{seeds[-1]}."
        lines += [header, ""]
        lines += ["| | |", "|---|---|"]
        lines += summarise(data)
        if pool is not None:
            lines += pooled_lines(pool, data)
    else:
        lines += [
            "**Automated suite run did not produce results.**",
            "",
            "```",
            note.strip()[-1200:] or "no output captured",
            "```",
        ]
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def splice(existing: str, date: str, entry: str) -> str:
    """Insert today's entry, replacing any entry already written for today."""
    if MARKER not in existing:
        raise SystemExit(f"STATUS.md is missing the {MARKER} marker")

    head, tail = existing.split(MARKER, 1)

    # Entries were once headed with a bare date. Match that too, or renaming
    # the format leaves the old entry orphaned beside the new one.
    for heading in (f"## {date} IST\n", f"## {date}\n"):
        while heading in tail:
            start = tail.index(heading)
            rest = tail[start + len(heading) :]
            # An entry ends at the next date heading, or at the end of the file.
            following = rest.find("\n## ")
            tail = tail[:start] + (rest[following + 1 :] if following != -1 else "")

    return f"{head}{MARKER}\n\n{entry}{tail.lstrip(chr(10))}"


FAILED_MARKER = "**Automated suite run did not produce results.**"


def entry_body(text: str, date: str) -> str | None:
    heading = f"## {date} IST\n"
    if heading not in text:
        return None
    rest = text.split(heading, 1)[1]
    following = rest.find("\n## ")
    return rest if following == -1 else rest[:following]


def reported_successfully(text: str, date: str) -> bool:
    """Whether today already has an entry recording a run that produced results.

    A failed entry must not count. Treating any entry as "done" would let one
    crash at 07:00 suppress every retry for the rest of the day, which is worse
    than the missed run it was meant to guard against.
    """
    body = entry_body(text, date)
    if body is None or FAILED_MARKER in body:
        return False
    if "<!-- study-state:" in body:
        return any(f"<!-- study-state: {state} -->" in body
                   for state in ("complete", "batch-complete"))
    return "**Automated suite run.**" in body


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=120)


def update_snapshot(existing: str, snapshot: str) -> str:
    replacement = f"{SNAPSHOT_START}\n{snapshot}\n{SNAPSHOT_END}\n"
    if SNAPSHOT_START in existing and SNAPSHOT_END in existing:
        before, rest = existing.split(SNAPSHOT_START, 1)
        _, after = rest.split(SNAPSHOT_END, 1)
        return before + replacement + after.lstrip("\n")
    before, rest = existing.split("## Current state\n", 1)
    boundary = rest.find("\n### ")
    if boundary == -1:
        boundary = rest.index(MARKER)
    return before + "## Current state\n\n" + replacement + "\n" + rest[boundary:].lstrip("\n")


def write_report(
    date_label: str, pool: dict[str, Any], data: dict[str, Any], state: str, note: str
) -> None:
    counts = {experiment_id: pooling.sample_size(pool, experiment_id) for experiment_id in SUITE}
    remaining = None
    if "study" in pool and state != "failed":
        remaining = len(study.pending_jobs(pool, specs=SUITE))
    rows = [
        "| Measurement | Current Record |", "|---|---|",
        f"| Updated | {ist_stamp()} |",
        f"| Study state | {state} |",
        f"| Complete seeds per arm | {min(counts.values(), default=0)}-"
        f"{max(counts.values(), default=0)} / {pooling.TARGET_SEEDS} |",
        f"| Remaining worlds | {remaining if remaining is not None else 'not planned'} |",
        "| Scope | Fixed-cohort fitness comparisons; a full pooled ladder is not established |",
        "| Liveness | `worldzero status outputs/daily/progress.json` |",
        "| Reporting | 07:00 IST trigger with 2-hour retries, while the host is available |",
    ]
    verification = ROOT / "outputs" / "verification" / "pytest.xml"
    if verification.exists():
        suites = ET.parse(verification).getroot().iter("testsuite")
        totals = {name: 0 for name in ("tests", "failures", "errors", "skipped")}
        for suite in suites:
            for name in totals:
                totals[name] += int(suite.get(name, "0"))
        passed = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
        checked = datetime.fromtimestamp(verification.stat().st_mtime, IST).strftime("%Y-%m-%d IST")
        rows.append(
            f"| Last test verification | {passed} passed, "
            f"{totals['failures'] + totals['errors']} failed ({checked}) |"
        )
    entry = [
        f"## {date_label} IST", "", f"*Generated {ist_stamp()}.*", "",
        f"<!-- study-state: {state} -->", "", "**Fixed-cohort study.**", "", note, "",
        *rows, "", "| Experiment | Complete matched seeds |", "|---|---|",
        *(f"| {experiment_id} | {count}/{pooling.TARGET_SEEDS} |"
          for experiment_id, count in counts.items()),
    ]
    if pool.get("study"):
        entry += ["", "Planned seeds: " + ", ".join(map(str, pool["study"]["seeds"])) + "."]
    entry += pooled_lines(pool, data)
    entry += ["", "---", ""]
    existing = STATUS.read_text(encoding="utf-8")
    updated = splice(update_snapshot(existing, "\n".join(rows)), date_label, "\n".join(entry))
    temporary = STATUS.with_name(f"{STATUS.name}.{os.getpid()}.tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.replace(STATUS)
    print(f"STATUS updated: {state}; complete seeds {counts}; remaining worlds {remaining}")


def publish(args: argparse.Namespace, date_label: str) -> int:
    if args.no_commit:
        return 0
    paths = [str(path.relative_to(ROOT)) for path in (STATUS, POOL) if path.exists()]
    staged = git("add", "--", *paths)
    if staged.returncode:
        print(staged.stderr)
        return staged.returncode
    if git("diff", "--cached", "--quiet", "--", *paths).returncode:
        committed = git(
            "commit", "--only", "-m", f"STATUS: {date_label} fixed-cohort study", "--", *paths
        )
        if committed.returncode:
            print(committed.stdout + committed.stderr)
            return committed.returncode
    if args.no_push:
        return 0
    pushed = git("push", "origin", "main")
    print(pushed.stdout + pushed.stderr)
    return pushed.returncode


def run_daily(args: argparse.Namespace) -> int:
    date_label = ist_today()
    if args.if_missing and datetime.now(IST).hour < 7:
        print("Before the 07:00 IST reporting window; no scheduled work due")
        return 0
    if args.if_missing and reported_successfully(STATUS.read_text(encoding="utf-8"), date_label):
        return publish(args, date_label)

    pool = pooling.empty()
    data = {}
    try:
        pool = pooling.load(POOL)
        if SUMMARY.exists():
            data = json.loads(SUMMARY.read_text(encoding="utf-8"))
        if not args.no_run and not args.no_pool:
            recovered = study.recover(pool, OUTPUT, specs=SUITE)
            print(f"Recovered {sum(recovered.values())} previously unpooled arm/seed measurements")
            study.ensure_plan(pool, specs=SUITE)
            pooling.save(POOL, pool)
        if args.no_run or args.no_pool or args.prepare_only:
            write_report(
                date_label, pool, data, "report-only", "Existing evidence only; no simulations run."
            )
            return publish(args, date_label)
        if pooling.complete(pool, list(SUITE)):
            write_report(
                date_label, pool, data, "complete",
                "The fixed cohort is complete. No additional simulations were started.",
            )
            return publish(args, date_label)

        write_report(
            date_label, pool, data, "running",
            "Recovering completed worlds and running only missing cohort measurements. "
            "Results are saved after each completed world.",
        )
        publish(args, date_label)
        with ProgressReporter(OUTPUT / "progress.json", command="fixed-cohort study") as progress:
            completed = study.run_pending(
                pool, POOL, OUTPUT, workers=args.workers,
                per_experiment=None if args.finish else args.replicates,
                progress=progress, specs=SUITE,
            )
        state = "complete" if pooling.complete(pool, list(SUITE)) else "batch-complete"
        write_report(
            date_label, pool, data, state,
            f"Completed {completed} previously missing worlds. "
            "No detector thresholds or world dynamics were changed.",
        )
        return publish(args, date_label)
    except Exception:
        note = traceback.format_exc()
        print(note)
        write_report(
            date_label, pool, data, "failed", f"{FAILED_MARKER}\n\n```text\n{note[-1800:]}\n```"
        )
        publish(args, date_label)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicates", type=int, default=5)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument(
        "--finish", action="store_true", help="finish all missing cohort worlds now"
    )
    parser.add_argument(
        "--prepare-only", action="store_true", help="recover and plan without simulation"
    )
    parser.add_argument(
        "--no-run", action="store_true", help="report existing evidence without simulation"
    )
    parser.add_argument(
        "--no-pool", action="store_true", help="report only; do not change pooled evidence"
    )
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--no-commit", action="store_true", help="do not commit or push")
    parser.add_argument(
        "--if-missing", action="store_true", help="retry only incomplete daily reports"
    )
    args = parser.parse_args()
    if args.replicates < 1 or args.workers < 0:
        parser.error("replicates must be positive and workers must be non-negative")
    with exclusive_file_lock(OUTPUT / ".daily.lock") as acquired:
        if not acquired:
            print("A daily study process is already active; no duplicate work started")
            return 0
        return run_daily(args)


if __name__ == "__main__":
    raise SystemExit(main())
