"""Daily status run: execute the suite, update STATUS.md, commit, push.

Scheduled for 07:00 IST. The report is written whether or not the suite
succeeds -- a day with a crashed run still needs a status entry saying so,
otherwise silence is ambiguous between "nothing happened" and "something broke".

    python scripts/daily_report.py                 full suite, commit and push
    python scripts/daily_report.py --no-run        rebuild the entry from the
                                                   last results, no simulation
    python scripts/daily_report.py --no-push       write and commit only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worldzero.experiments import pool as pooling  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "STATUS.md"
OUTPUT = ROOT / "outputs" / "daily"
SUMMARY = OUTPUT / "suite-summary.json"
POOL = ROOT / "evidence" / "pool.json"
"""Tracked, unlike outputs/: this is the accumulated record, not run scratch."""
IST = timezone(timedelta(hours=5, minutes=30))

MARKER = "<!-- daily-entries -->"

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
    return SUMMARY.exists(), completed.stdout + completed.stderr


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
    rows: list[str] = []
    for experiment in data.get("experiments", []):
        experiment_id = experiment.get("experiment_id")
        required = set(experiment.get("required_detectors", []))
        for detection in experiment.get("detections", []):
            if detection.get("detector") not in required:
                continue
            for criterion in detection.get("criteria", []):
                arm = criterion.get("control")
                if not arm:
                    continue
                test = pooling.pooled_test(pool, experiment_id, arm)
                if test is None:
                    continue
                n = test.n_treatment
                if n < pooling.TARGET_SEEDS:
                    verdict = f"provisional ({n}/{pooling.TARGET_SEEDS})"
                elif test.statistic > 0 and test.significant:
                    verdict = "**PASS**"
                else:
                    verdict = "settled null"
                rows.append(
                    f"| {experiment_id} | {criterion['name']} vs {arm} | {n} | "
                    f"{test.statistic:+.4f} | {test.effect_size:+.3f} | "
                    f"{test.p_value:.4f} | {verdict} |"
                )

    if not rows:
        return []
    return [
        "",
        f"**Pooled across runs.** Seeds accumulate at {pooling.TARGET_SEEDS} per arm, "
        "fixed before the data; below that a comparison is provisional however its "
        "p-value looks.",
        "",
        "| exp | comparison | n | delta | d | p | status |",
        "|---|---|---|---|---|---|---|",
        *rows,
    ]


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
    return body is not None and FAILED_MARKER not in body


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicates", type=int, default=5)
    parser.add_argument("--no-run", action="store_true", help="reuse the last results")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--no-pool", action="store_true", help="skip the cross-run pool")
    parser.add_argument(
        "--if-missing",
        action="store_true",
        help="do nothing when today already has a successful entry, so catch-up runs are safe",
    )
    args = parser.parse_args()

    date = ist_today()

    # The 07:00 IST trigger is skipped outright when the machine is off, and a
    # skipped run leaves no entry at all -- the ambiguous silence this report was
    # built to remove. Catch-up triggers fix that only if repeating is harmless.
    if args.if_missing and reported_successfully(STATUS.read_text(encoding="utf-8"), date):
        print(f"{date} already reported; nothing to do")
        return 0

    base = seed_base(datetime.now(IST).date(), args.replicates)
    seeds = [base + i for i in range(args.replicates)]
    note = ""
    ok = False
    data: dict[str, Any] | None = None

    try:
        if args.no_run:
            ok = SUMMARY.exists()
            note = "reused previous results" if ok else f"no summary at {SUMMARY}"
        else:
            ok, note = run_suite(args.replicates, base)
        if ok:
            data = json.loads(SUMMARY.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - the report must be written regardless
        ok = False
        note = traceback.format_exc()

    pool: dict[str, Any] | None = None
    if not args.no_pool:
        try:
            pool = pooling.load(POOL)
            if data:
                added = pooling.merge_summary(pool, data)
                pooling.save(POOL, pool)
                print(f"pooled {sum(added.values())} new observations")
        except Exception:  # noqa: BLE001 - a pool failure must not lose the report
            print(traceback.format_exc())
            pool = None

    STATUS.write_text(
        splice(
            STATUS.read_text(encoding="utf-8"),
            date,
            build_entry(date, ok, data, note, pool, seeds if ok else None),
        ),
        encoding="utf-8",
    )
    print(f"STATUS.md updated for {date} (suite ok: {ok}, seeds {seeds[0]}-{seeds[-1]})")

    git("add", "STATUS.md", "evidence/pool.json")
    if not git("diff", "--cached", "--quiet").returncode:
        print("no status change to commit")
        return 0

    committed = git("commit", "-m", f"STATUS: {date} automated daily run")
    if committed.returncode:
        print(committed.stdout + committed.stderr)
        return 1
    if not args.no_push:
        pushed = git("push", "origin", "main")
        print(pushed.stdout + pushed.stderr)
        return pushed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
