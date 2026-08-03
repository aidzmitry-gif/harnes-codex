"""Inject a small, non-mutating context-handoff reminder after compaction."""

from __future__ import annotations

import json
import sys


REMINDER = (
    "Контекст этой задачи только что был сжат. Если рабочий срез завершён или задача стала слишком широкой, "
    "предложи `$context-handoff`; не создавай и не архивируй задачи без нужного разрешения. "
    "Для активного `$goal-runner` сначала увеличь счётчик compact в родительском work item и полностью проверь "
    "standing chain authorization и весь "
    "Goal-chain authorization contract: project root, data owner, risk class, external-side-effect boundary, "
    "совпадение Approved passport revision с Plan revision, Approval provenance, checkout/worktree policy, "
    "current verified subgoal, next minimal slice с acceptance и Standing authorization scope. "
    "На безопасной границе successor можно создать автоматически только при scope `successor creation` или `both`; "
    "после его проверки автоматически продолжать реализацию можно только при scope `bounded continuation` или `both`. "
    "Иначе сохрани обычные подтверждения. Предшественника не архивируй."
)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0

    if event.get("hook_event_name") != "SessionStart" or event.get("source") != "compact":
        return 0

    payload = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": REMINDER,
        },
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
