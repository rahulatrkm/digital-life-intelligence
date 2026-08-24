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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "STATUS.md"
OUTPUT = ROOT / "outputs" / "daily"
SUMMARY = OUTPUT / "suite-summary.json"
IST = timezone(timedelta(hours=5, minutes=30))

MARKER = "<!-- daily-entries -->"


def ist_today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def ist_stamp() -> str:
    """Entries are dated in IST because the report is due at 07:00 IST, which
    falls on the previous day in most other zones. Spelling out the zone stops
    a reader in another timezone reading the heading as wrong."""
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")


def run_suite(replicates: int) -> tuple[bool, str]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "worldzero.cli",
        "suite",
        "--replicates",
        str(replicates),
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


def build_entry(date: str, ok: bool, data: dict[str, Any] | None, note: str) -> str:
    lines = [f"## {date} IST", "", f"*Generated {ist_stamp()}.*", ""]
    if ok and data:
        lines += ["**Automated suite run.**", ""]
        lines += ["| | |", "|---|---|"]
        lines += summarise(data)
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


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicates", type=int, default=5)
    parser.add_argument("--no-run", action="store_true", help="reuse the last results")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()

    date = ist_today()
    note = ""
    ok = False
    data: dict[str, Any] | None = None

    try:
        if args.no_run:
            ok = SUMMARY.exists()
            note = "reused previous results" if ok else f"no summary at {SUMMARY}"
        else:
            ok, note = run_suite(args.replicates)
        if ok:
            data = json.loads(SUMMARY.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - the report must be written regardless
        ok = False
        note = traceback.format_exc()

    STATUS.write_text(
        splice(STATUS.read_text(encoding="utf-8"), date, build_entry(date, ok, data, note)),
        encoding="utf-8",
    )
    print(f"STATUS.md updated for {date} (suite ok: {ok})")

    git("add", "STATUS.md")
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
