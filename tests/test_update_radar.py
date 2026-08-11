import hashlib
import json
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import update_radar


TEST_TMP = Path(__file__).parents[1] / ".harness" / "test-tmp"


@contextmanager
def workspace_state():
    TEST_TMP.mkdir(parents=True, exist_ok=True)
    state = TEST_TMP / f"update-radar-state-{uuid4().hex}.json"
    try:
        yield state
    finally:
        state.unlink(missing_ok=True)
        for temporary in TEST_TMP.glob(f".{state.name}.*.tmp"):
            temporary.unlink(missing_ok=True)


def candidate(identifier="codex-changelog-20260811", impact=None):
    return {
        "schemaVersion": 1,
        "id": identifier,
        "product": "openai",
        "publishedDate": "2026-08-11",
        "sourceUrl": "https://learn.chatgpt.com/docs/changelog",
        "facts": ["The official changelog describes a Codex update."],
        "inferences": ["The update may affect local Harness workflows."],
        "assumptions": [],
        "impact": impact or {
            "security": 0,
            "compatibility": 0,
            "userTime": 1,
            "reliability": 1,
            "implementationCost": 0,
        },
        "affectedComponents": ["goal-runner"],
    }


def batch(*candidates):
    return {"schemaVersion": 1, "candidates": list(candidates)}


class UpdateRadarTests(unittest.TestCase):
    def test_first_scan_records_candidate_and_second_scan_suppresses_repeat(self):
        with workspace_state() as state:
            first = update_radar.scan(batch(candidate()), state)
            second = update_radar.scan(batch(candidate()), state)

        self.assertEqual("updates-need-evidence", first["status"])
        self.assertEqual("Обнаружены новые обновления, но влияние на Harness ещё требует доказательств.", first["message"])
        self.assertEqual({"input": 1, "new": 1, "repeated": 0, "significant": 0, "evaluate": 1, "ignored": 0}, first["counts"])
        self.assertTrue(first["stateChanged"])
        self.assertEqual(1, first["stateCount"])
        self.assertEqual("no-meaningful-updates", second["status"])
        self.assertEqual("Значимых обновлений для Harness нет.", second["message"])
        self.assertEqual({"input": 1, "new": 0, "repeated": 1, "significant": 0, "evaluate": 0, "ignored": 0}, second["counts"])
        self.assertFalse(second["stateChanged"])
        self.assertEqual(1, second["stateCount"])
        self.assertEqual([], second["candidates"])

    def test_mixed_new_candidates_are_sorted_and_report_significant(self):
        low = {"security": 0, "compatibility": 0, "userTime": 0, "reliability": 0, "implementationCost": 2}
        high = {"security": 2, "compatibility": 0, "userTime": 0, "reliability": 0, "implementationCost": 3}
        with workspace_state() as state:
            result = update_radar.scan(batch(candidate("z-ignore", low), candidate("a-significant", high)), state)

        self.assertEqual("meaningful-updates", result["status"])
        self.assertEqual("Есть обновления с потенциально значимым влиянием на Harness; требуется локальная проверка до внедрения.", result["message"])
        self.assertEqual(["a-significant", "z-ignore"], [item["id"] for item in result["candidates"]])
        self.assertEqual(1, result["counts"]["significant"])
        self.assertEqual(1, result["counts"]["ignored"])

    def test_duplicate_batch_id_fails_before_state_write(self):
        with workspace_state() as state:
            with self.assertRaises(update_radar.RadarError):
                update_radar.scan(batch(candidate(), candidate()), state)
            self.assertFalse(state.exists())

    def test_changed_payload_for_seen_id_fails_without_mutating_state(self):
        with workspace_state() as state:
            update_radar.scan(batch(candidate()), state)
            before = hashlib.sha256(state.read_bytes()).hexdigest()
            revised = candidate(); revised["facts"] = ["A revised but conflicting fact."]
            with self.assertRaises(update_radar.RadarError):
                update_radar.scan(batch(revised), state)
            self.assertEqual(before, hashlib.sha256(state.read_bytes()).hexdigest())

    def test_invalid_batch_and_corrupt_state_fail_closed(self):
        invalid_batches = (
            [],
            {"schemaVersion": True, "candidates": []},
            {"schemaVersion": 1.0, "candidates": []},
            {"schemaVersion": 1, "candidates": "not-a-list"},
            {"schemaVersion": 1, "candidates": [], "extra": True},
            {"schemaVersion": 1, "candidates": [candidate(str(index)) for index in range(update_radar.MAX_BATCH + 1)]},
        )
        with workspace_state() as state:
            for invalid in invalid_batches:
                with self.subTest(invalid=type(invalid).__name__):
                    with self.assertRaises(update_radar.RadarError):
                        update_radar.scan(invalid, state)
                    self.assertFalse(state.exists())
            state.write_text('{"schemaVersion":1,"seen":[]}', encoding="utf-8")
            before = state.read_bytes()
            with self.assertRaises(update_radar.RadarError):
                update_radar.scan(batch(candidate()), state)
            self.assertEqual(before, state.read_bytes())

    def test_state_capacity_fails_before_write(self):
        seen = {f"seen-{index}": "0" * 64 for index in range(update_radar.MAX_SEEN)}
        with workspace_state() as state:
            state.write_text(json.dumps({"schemaVersion": 1, "seen": seen}), encoding="utf-8")
            before = hashlib.sha256(state.read_bytes()).hexdigest()
            with self.assertRaises(update_radar.RadarError):
                update_radar.scan(batch(candidate("new-candidate")), state)
            self.assertEqual(before, hashlib.sha256(state.read_bytes()).hexdigest())

    def test_empty_batch_is_no_update_and_does_not_create_state(self):
        with workspace_state() as state:
            result = update_radar.scan(batch(), state)
            self.assertFalse(state.exists())
        self.assertEqual("no-meaningful-updates", result["status"])
        self.assertEqual(0, result["counts"]["input"])

    def test_cli_is_canonical_and_restricts_state_to_runtime_directory(self):
        repo = Path(__file__).parents[1]
        batch_path = repo / ".harness" / "test-tmp" / "update-radar-batch.json"
        state_path = repo / ".harness" / "runtime" / "test-update-radar-state.json"
        batch_path.parent.mkdir(parents=True, exist_ok=True)
        batch_path.write_text(json.dumps(batch(candidate())), encoding="utf-8")
        state_path.unlink(missing_ok=True)
        try:
            command = [sys.executable, "update_radar.py", "scan", str(batch_path), "--state", str(state_path)]
            first = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False)
            second = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False)
            escaped = subprocess.run(
                [sys.executable, "update_radar.py", "scan", str(batch_path), "--state", str(repo / "escaped.json")],
                cwd=repo,
                text=True,
                capture_output=True,
                check=False,
            )
        finally:
            batch_path.unlink(missing_ok=True)
            state_path.unlink(missing_ok=True)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual(2, escaped.returncode)
        self.assertNotIn("Traceback", escaped.stdout + escaped.stderr)
        self.assertEqual(first.stdout, json.dumps(json.loads(first.stdout), ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")
        self.assertEqual("no-meaningful-updates", json.loads(second.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
