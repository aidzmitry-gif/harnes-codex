#!/usr/bin/env python3
"""Portable, evidence-based acceptance gate for an agent work item.

Criteria live in .harness/acceptance/<work-item>.json. Command criteria are re-run
on every ``check``; manual criteria require both an explicit pass and evidence.
Only use commands from a profile maintained by a trusted project owner.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def root() -> Path:
    return Path(__file__).resolve().parent


def gate_path(work_item: str) -> Path:
    if not work_item.replace("-", "").replace("_", "").isalnum():
        raise ValueError("work item may contain only letters, digits, '-' and '_'")
    return root() / ".harness" / "acceptance" / f"{work_item}.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate(data: dict) -> list[dict]:
    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("gate must contain a non-empty 'criteria' array")
    seen: set[str] = set()
    for criterion in criteria:
        cid = criterion.get("id")
        kind = criterion.get("kind")
        if not isinstance(cid, str) or not cid or cid in seen:
            raise ValueError("each criterion needs a unique non-empty id")
        if kind not in ("command", "manual"):
            raise ValueError(f"{cid}: kind must be 'command' or 'manual'")
        if kind == "command" and not isinstance(criterion.get("command"), str):
            raise ValueError(f"{cid}: command criterion needs a command")
        seen.add(cid)
    return criteria


def init(args: argparse.Namespace) -> int:
    target = gate_path(args.work_item)
    if target.exists():
        print(f"FAIL gate already exists: {target}", file=sys.stderr)
        return 2
    template = load(Path(args.from_file))
    criteria = validate(template)
    for criterion in criteria:
        criterion["passes"] = False
        criterion["evidence"] = ""
    template["workItem"] = args.work_item
    save(target, template)
    print(f"PASS created {target} with {len(criteria)} criteria")
    return 0


def prove(args: argparse.Namespace) -> int:
    target = gate_path(args.work_item)
    if not target.exists():
        print("FAIL gate does not exist", file=sys.stderr)
        return 2
    data = load(target)
    criteria = validate(data)
    for criterion in criteria:
        if criterion["id"] == args.criterion:
            if criterion["kind"] != "manual":
                print("FAIL only manual criteria can be proven manually", file=sys.stderr)
                return 2
            criterion["passes"] = True
            criterion["evidence"] = args.evidence.strip()
            if not criterion["evidence"]:
                print("FAIL evidence must not be empty", file=sys.stderr)
                return 2
            save(target, data)
            print(f"PASS recorded evidence for {args.criterion}")
            return 0
    print("FAIL criterion does not exist", file=sys.stderr)
    return 2


def evaluate(criterion: dict) -> tuple[bool, str]:
    if criterion["kind"] == "manual":
        evidence = str(criterion.get("evidence", "")).strip()
        return bool(criterion.get("passes")) and bool(evidence), "manual evidence" if evidence else "missing manual evidence"
    result = subprocess.run(
        criterion["command"], shell=True, cwd=root(), capture_output=True,
        text=True, timeout=600, encoding="utf-8", errors="replace",
    )
    criterion["passes"] = result.returncode == 0
    output = (result.stdout or result.stderr).strip().splitlines()
    criterion["evidence"] = f"auto: exit {result.returncode}; {output[-1][:160] if output else 'no output'}"
    return criterion["passes"], criterion["evidence"]


def check(args: argparse.Namespace) -> int:
    target = gate_path(args.work_item)
    if not target.exists():
        print("FAIL gate does not exist", file=sys.stderr)
        return 2
    try:
        data = load(target)
        criteria = validate(data)
        results = [(criterion["id"], *evaluate(criterion)) for criterion in criteria]
        save(target, data)
    except (ValueError, json.JSONDecodeError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL invalid or uncheckable gate: {exc}", file=sys.stderr)
        return 2
    for cid, passed, note in results:
        print(f"{'PASS' if passed else 'FAIL'} {cid}: {note}")
    return 0 if all(passed for _, passed, _ in results) else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence-based acceptance gate")
    sub = parser.add_subparsers(dest="action", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("work_item")
    p_init.add_argument("--from", dest="from_file", required=True)
    p_init.set_defaults(func=init)
    p_prove = sub.add_parser("prove")
    p_prove.add_argument("work_item")
    p_prove.add_argument("criterion")
    p_prove.add_argument("--evidence", required=True)
    p_prove.set_defaults(func=prove)
    p_check = sub.add_parser("check")
    p_check.add_argument("work_item")
    p_check.set_defaults(func=check)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
