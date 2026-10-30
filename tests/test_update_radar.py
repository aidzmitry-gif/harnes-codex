import hashlib
import copy
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
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


def assessment(**changes):
    result = {"schemaVersion": 1, "evidence": ["Local check: feature unavailable; no model call executed."],
              "blocker": "The required local feature is unavailable.",
              "recheckWhen": "Recheck after the local feature or CLI version changes.",
              "prerequisites": {"cli-version": "test-1", "feature": "unavailable"}}
    result.update(changes)
    return result


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
        self.assertEqual("pending-evaluation", second["status"])
        self.assertEqual(1, second["pendingCount"])
        self.assertEqual({"input": 1, "new": 0, "repeated": 1, "significant": 0, "evaluate": 0, "ignored": 0}, second["counts"])
        self.assertFalse(second["stateChanged"])
        self.assertEqual(1, second["stateCount"])
        self.assertEqual([], second["candidates"])

    def test_pending_survives_empty_batch_without_writes_for_both_classes(self):
        high = {"security": 2, "compatibility": 0, "userTime": 0, "reliability": 0, "implementationCost": 3}
        for item in (candidate(), candidate("significant", high)):
            with self.subTest(id=item["id"]), workspace_state() as state:
                first = update_radar.scan(batch(item), state)
                before = state.read_bytes()
                empty = update_radar.scan(batch(), state)
                self.assertEqual(first["pending"], empty["pending"])
                self.assertEqual("pending-evaluation", empty["status"])
                self.assertFalse(empty["stateChanged"])
                self.assertEqual(before, state.read_bytes())

    def test_resolution_is_digest_bound_idempotent_and_never_reclassifies(self):
        item = candidate()
        digest = update_radar._digest(item)
        with workspace_state() as state:
            update_radar.scan(batch(item), state)
            with patch.object(update_radar.update_impact, "classify", side_effect=AssertionError("must not classify")):
                resolved = update_radar.resolve(item["id"], digest, "no-benefit", "1" * 64, state)
                before = state.read_bytes()
                retry = update_radar.resolve(item["id"], digest, "no-benefit", "1" * 64, state)
            self.assertTrue(resolved["stateChanged"])
            self.assertFalse(retry["stateChanged"])
            repeated = update_radar.scan(batch(item), state)
            self.assertEqual("no-meaningful-updates", repeated["status"])
            self.assertEqual(0, repeated["pendingCount"])
            self.assertEqual(before, state.read_bytes())

    def test_bad_resolution_cannot_change_history(self):
        item = candidate(); digest = update_radar._digest(item)
        with workspace_state() as state:
            update_radar.scan(batch(item), state)
            for identifier, supplied_digest, outcome, evidence in (
                ("missing", digest, "useful", "1" * 64),
                (item["id"], "0" * 64, "useful", "1" * 64),
                (item["id"], digest, "unknown", "1" * 64),
                (item["id"], digest, "useful", "not-evidence"),
                (item["id"], [], "useful", "1" * 64),
            ):
                before = state.read_bytes()
                with self.assertRaises(update_radar.RadarError):
                    update_radar.resolve(identifier, supplied_digest, outcome, evidence, state)
                self.assertEqual(before, state.read_bytes())

            update_radar.resolve(item["id"], digest, "useful", "1" * 64, state)
            before = state.read_bytes()
            for outcome, evidence in (("useful", "2" * 64), ("no-benefit", "1" * 64)):
                with self.assertRaises(update_radar.RadarError):
                    update_radar.resolve(item["id"], digest, outcome, evidence, state)
                self.assertEqual(before, state.read_bytes())

    def test_useful_resolution_suppresses_repeat_without_claiming_adoption(self):
        item = candidate()
        with workspace_state() as state:
            update_radar.scan(batch(item), state)
            receipt = update_radar.resolve(item["id"], update_radar._digest(item), "useful", "1" * 64, state)
            before = state.read_bytes()
            repeated = update_radar.scan(batch(item), state)
            self.assertEqual("evaluation-recorded", receipt["status"])
            self.assertEqual("useful", receipt["outcome"])
            self.assertEqual("no-meaningful-updates", repeated["status"])
            self.assertEqual([], repeated["pending"])
            self.assertEqual([], repeated["candidates"])
            self.assertFalse(repeated["stateChanged"])
            self.assertEqual(before, state.read_bytes())
    def test_legacy_history_stays_unknown_until_candidate_is_supplied(self):
        item = candidate()
        with workspace_state() as state:
            legacy = {"schemaVersion": 1, "seen": {item["id"]: update_radar._digest(item)}}
            state.write_text(json.dumps(legacy), encoding="utf-8")
            before = state.read_bytes()
            unknown = update_radar.scan(batch(), state)
            self.assertEqual("evaluation-history-unknown", unknown["status"])
            self.assertEqual(1, unknown["unknownEvaluationCount"])
            self.assertEqual(before, state.read_bytes())
            with self.assertRaises(update_radar.RadarError):
                update_radar.resolve(item["id"], update_radar._digest(item), "no-benefit", "1" * 64, state)
            self.assertEqual(before, state.read_bytes())
            observed = update_radar.scan(batch(item), state)
            self.assertEqual(1, observed["pendingCount"])
            self.assertEqual(0, observed["unknownEvaluationCount"])
            self.assertEqual(0, observed["counts"]["new"])
            self.assertEqual(3, json.loads(state.read_text())["schemaVersion"])

    def test_ignore_is_not_pending_or_legacy_unknown(self):
        low = {"security": 0, "compatibility": 0, "userTime": 0, "reliability": 0, "implementationCost": 2}
        item = candidate("ignored", low)
        with workspace_state() as state:
            update_radar.scan(batch(item), state)
            result = update_radar.scan(batch(), state)
            self.assertEqual("no-meaningful-updates", result["status"])
            self.assertEqual(0, result["unknownEvaluationCount"])
            with self.assertRaises(update_radar.RadarError):
                update_radar.resolve(item["id"], update_radar._digest(item), "useful", "1" * 64, state)

    def test_invalid_v2_evaluations_fail_without_writes(self):
        item = candidate(); identifier = item["id"]
        malformed = (
            [], {"missing": {"classification": "evaluate", "resolution": None}},
            {identifier: {"classification": [], "resolution": None}},
            {identifier: {"classification": "evaluate", "resolution": {"outcome": "useful", "evidenceHash": "bad"}}},
            {identifier: {"classification": "ignore", "resolution": {"outcome": "useful", "evidenceHash": "1" * 64}}},
            {identifier: {"classification": "evaluate", "resolution": None, "extra": "untrusted"}},
        )
        with workspace_state() as state:
            for evaluations in malformed:
                state.write_text(json.dumps({"schemaVersion": 2, "seen": {identifier: update_radar._digest(item)}, "evaluations": evaluations}), encoding="utf-8")
                before = state.read_bytes()
                with self.assertRaises(update_radar.RadarError):
                    update_radar.scan(batch(), state)
                self.assertEqual(before, state.read_bytes())

    def test_atomic_failure_and_output_size_limit_preserve_state(self):
        with workspace_state() as state:
            update_radar.scan(batch(candidate()), state)
            before = state.read_bytes()
            with patch.object(update_radar.os, "replace", side_effect=OSError("simulated")):
                with self.assertRaises(OSError):
                    update_radar.scan(batch(candidate("new")), state)
            self.assertEqual(before, state.read_bytes())
            with patch.object(update_radar, "MAX_INPUT_BYTES", len(before) + 1):
                with self.assertRaises(update_radar.RadarError):
                    update_radar.scan(batch(candidate("new")), state)
            self.assertEqual(before, state.read_bytes())

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

    def test_candidate_facts_survive_empty_batch_and_restart(self):
        item = candidate()
        with workspace_state() as state:
            update_radar.scan(batch(item), state)
            before = state.read_bytes()
            result = update_radar.pending(state)
            self.assertEqual(item, result["pending"][0]["candidate"])
            self.assertEqual(item, update_radar.scan(batch(), state)["pending"][0]["candidate"])
            self.assertEqual(before, state.read_bytes())

    def test_deferred_evidence_is_durable_and_exact_retry_is_noop(self):
        item = candidate(); digest = update_radar._digest(item); check = assessment()
        with workspace_state() as state:
            update_radar.scan(batch(item), state)
            first = update_radar.defer(item["id"], digest, check, state)
            before = state.read_bytes()
            second = update_radar.defer(item["id"], digest, check, state)
            result = update_radar.pending(state, check["prerequisites"])
            self.assertTrue(first["stateChanged"])
            self.assertFalse(second["stateChanged"])
            self.assertEqual(check, result["pending"][0]["assessment"])
            self.assertEqual(update_radar._digest(check), first["assessmentHash"])
            self.assertIsNone(json.loads(state.read_text())["evaluations"][item["id"]]["resolution"])
            self.assertEqual(before, state.read_bytes())

    def test_prerequisite_comparison_skips_only_confirmed_unchanged_checks(self):
        item = candidate(); check = assessment()
        with workspace_state() as state:
            update_radar.scan(batch(item), state)
            update_radar.defer(item["id"], update_radar._digest(item), check, state)
            before = state.read_bytes()
            for prerequisites, needs_recheck, reason in (
                (check["prerequisites"], False, "prerequisites-unchanged"),
                ({**check["prerequisites"], "unrelated": "new"}, False, "prerequisites-unchanged"),
                ({**check["prerequisites"], "cli-version": "test-2"}, True, "prerequisites-changed"),
                ({"cli-version": "test-1"}, True, "prerequisites-missing"),
                (None, True, "prerequisites-unknown"),
            ):
                with self.subTest(reason=reason):
                    result = update_radar.pending(state, prerequisites)
                    self.assertEqual(needs_recheck, result["pending"][0]["needsRecheck"])
                    self.assertEqual(reason, result["pending"][0]["recheckReason"])
                    self.assertEqual(int(needs_recheck), result["needsRecheckCount"])
                    self.assertEqual(int(not needs_recheck), result["deferredCount"])
                    self.assertEqual(1, result["pendingCount"])
            self.assertEqual(before, state.read_bytes())

    def test_invalid_assessment_never_changes_state(self):
        item = candidate(); digest = update_radar._digest(item)
        invalid = ([], assessment(extra=True), assessment(schemaVersion=True), assessment(schemaVersion=1.0),
                   assessment(evidence=[]), assessment(evidence=["same", "same"]),
                   assessment(evidence=["x"] * 9), assessment(evidence=["bad\x00text"]),
                   assessment(blocker=""), assessment(blocker="x" * 501), assessment(recheckWhen="multi\nline"),
                   assessment(prerequisites={}), assessment(prerequisites={"Bad key": "x"}),
                   assessment(prerequisites={"feature": False}), assessment(prerequisites={"feature": " unknown"}),
                   assessment(prerequisites={str(index): "x" for index in range(17)}))
        with workspace_state() as state:
            update_radar.scan(batch(item), state)
            before = state.read_bytes()
            for check in invalid:
                with self.subTest(check=check), self.assertRaises(update_radar.RadarError):
                    update_radar.defer(item["id"], digest, check, state)
                self.assertEqual(before, state.read_bytes())

    def test_defer_requires_matching_actionable_unresolved_history(self):
        item = candidate(); digest = update_radar._digest(item)
        ignored = candidate("ignored", {"security": 0, "compatibility": 0, "userTime": 0,
                                        "reliability": 0, "implementationCost": 0})
        with workspace_state() as state:
            update_radar.scan(batch(item, ignored), state)
            before = state.read_bytes()
            for identifier, supplied in (("missing", digest), (item["id"], "0" * 64),
                                         (item["id"], []), ("Bad id", digest),
                                         (ignored["id"], update_radar._digest(ignored))):
                with self.assertRaises(update_radar.RadarError):
                    update_radar.defer(identifier, supplied, assessment(), state)
                self.assertEqual(before, state.read_bytes())
            update_radar.resolve(item["id"], digest, "no-benefit", "1" * 64, state)
            before = state.read_bytes()
            with self.assertRaises(update_radar.RadarError):
                update_radar.defer(item["id"], digest, assessment(), state)
            self.assertEqual(before, state.read_bytes())

    def test_checkpoint_history_is_bounded_without_silent_truncation(self):
        item = candidate(); digest = update_radar._digest(item)
        first = assessment(); second = assessment(blocker="Another observed blocker.")
        with workspace_state() as state:
            update_radar.scan(batch(item), state)
            with patch.object(update_radar, "MAX_ASSESSMENTS", 2):
                update_radar.defer(item["id"], digest, first, state)
                update_radar.defer(item["id"], digest, second, state)
                before = state.read_bytes()
                self.assertFalse(update_radar.defer(item["id"], digest, second, state)["stateChanged"])
                with self.assertRaises(update_radar.RadarError):
                    update_radar.defer(item["id"], digest, assessment(blocker="Third blocker."), state)
                self.assertEqual(before, state.read_bytes())
                self.assertEqual([first, second], json.loads(state.read_text())["evaluations"][item["id"]]["assessments"])

    def test_v2_reads_without_migration_and_exact_replay_recovers_only_missing_facts(self):
        item = candidate(); digest = update_radar._digest(item)
        previous = {"outcome": "no-benefit", "evidenceHash": "1" * 64}
        legacy = {"schemaVersion": 2, "seen": {item["id"]: digest, "final": "2" * 64, "unknown": "3" * 64},
                  "evaluations": {item["id"]: {"classification": "evaluate", "resolution": None},
                                  "final": {"classification": "significant", "resolution": previous}}}
        with workspace_state() as state:
            state.write_text(json.dumps(legacy), encoding="utf-8")
            before = state.read_bytes()
            result = update_radar.pending(state)
            self.assertIsNone(result["pending"][0]["candidate"])
            self.assertEqual(1, result["unknownEvaluationCount"])
            self.assertFalse(update_radar.scan(batch(), state)["stateChanged"])
            self.assertEqual(before, state.read_bytes())
            replay = update_radar.scan(batch(item), state)
            self.assertTrue(replay["stateChanged"])
            self.assertEqual([], replay["candidates"])
            self.assertEqual(item, replay["pending"][0]["candidate"])
            saved = json.loads(state.read_text())
            self.assertEqual(3, saved["schemaVersion"])
            self.assertEqual(previous, {key: saved["evaluations"]["final"]["resolution"][key] for key in previous})
            self.assertEqual("3" * 64, saved["seen"]["unknown"])
            self.assertNotIn("unknown", saved["evaluations"])
            before = state.read_bytes()
            self.assertFalse(update_radar.scan(batch(item), state)["stateChanged"])
            self.assertEqual(before, state.read_bytes())

    def test_v3_corruption_fails_closed_without_reclassification(self):
        item = candidate(); identifier = item["id"]
        with workspace_state() as state:
            update_radar.scan(batch(item), state)
            valid = json.loads(state.read_text())
            malformed = []
            for field, value in (("candidate", candidate("wrong-id")), ("candidate", {**item, "facts": ["Changed"]}),
                                 ("candidate", {}), ("assessments", [assessment(blocker="")]),
                                 ("assessments", [assessment()] * (update_radar.MAX_ASSESSMENTS + 1)),
                                 ("resolution", {"outcome": "useful", "evidenceHash": "1" * 64, "evidence": []})):
                changed = copy.deepcopy(valid); changed["evaluations"][identifier][field] = value
                malformed.append(changed)
            malformed.extend({**valid, "schemaVersion": version} for version in (True, 3.0, 4))
            changed = copy.deepcopy(valid); changed["evaluations"][identifier]["extra"] = True
            malformed.append(changed)
            for corrupted in malformed:
                state.write_text(json.dumps(corrupted), encoding="utf-8")
                before = state.read_bytes()
                with self.assertRaises(update_radar.RadarError):
                    update_radar.pending(state)
                self.assertEqual(before, state.read_bytes())
            state.write_text(json.dumps(valid), encoding="utf-8")
            with patch.object(update_radar.update_impact, "classify", side_effect=AssertionError("must not reclassify")):
                self.assertEqual(1, update_radar.pending(state)["pendingCount"])

    def test_duplicate_json_fields_fail_closed_for_state_and_batch(self):
        with workspace_state() as state:
            for payload in ('{"schemaVersion":1,"seen":{},"seen":{}}',
                            '{"schemaVersion":1,"candidates":[],"candidates":[]}'):
                state.write_text(payload, encoding="utf-8")
                before = state.read_bytes()
                with self.assertRaises(update_radar.RadarError):
                    update_radar.pending(state)
                with self.assertRaises(update_radar.RadarError):
                    update_radar._read_batch(state)
                self.assertEqual(before, state.read_bytes())

    def test_resolution_retains_bounded_evidence_and_does_not_rewrite_it(self):
        item = candidate(); digest = update_radar._digest(item)
        evidence = ["Command: existing local regression test.", "Observed: route is not used; no change applied."]
        with workspace_state() as state:
            update_radar.scan(batch(item), state)
            update_radar.defer(item["id"], digest, assessment(), state)
            for invalid in ([], ["bad\ntext"], ["x"] * 9, "not-a-list"):
                before = state.read_bytes()
                with self.assertRaises(update_radar.RadarError):
                    update_radar.resolve(item["id"], digest, "no-benefit", "1" * 64, state, evidence=invalid)
                self.assertEqual(before, state.read_bytes())
            result = update_radar.resolve(item["id"], digest, "no-benefit", "1" * 64, state, evidence=evidence)
            before = state.read_bytes()
            retry = update_radar.resolve(item["id"], digest, "no-benefit", "1" * 64, state, evidence=evidence)
            self.assertTrue(result["stateChanged"])
            self.assertFalse(retry["stateChanged"])
            saved = json.loads(state.read_text())["evaluations"][item["id"]]
            self.assertEqual(evidence, saved["resolution"]["evidence"])
            self.assertEqual([assessment()], saved["assessments"])
            with self.assertRaises(update_radar.RadarError):
                update_radar.resolve(item["id"], digest, "no-benefit", "1" * 64, state, evidence=["Different evidence."])
            self.assertEqual(before, state.read_bytes())

    def test_checkpoint_atomic_failure_and_size_limit_preserve_history(self):
        item = candidate(); digest = update_radar._digest(item)
        with workspace_state() as state:
            update_radar.scan(batch(item), state)
            before = state.read_bytes()
            with patch.object(update_radar.os, "replace", side_effect=OSError("simulated")):
                with self.assertRaises(OSError):
                    update_radar.defer(item["id"], digest, assessment(), state)
            self.assertEqual(before, state.read_bytes())
            self.assertEqual([], list(TEST_TMP.glob(f".{state.name}.*.tmp")))
            with patch.object(update_radar, "MAX_INPUT_BYTES", len(before) + 1):
                with self.assertRaises(update_radar.RadarError):
                    update_radar.defer(item["id"], digest, assessment(), state)
            self.assertEqual(before, state.read_bytes())

    def test_pending_is_read_only_and_rejects_invalid_prerequisites(self):
        with workspace_state() as state:
            self.assertEqual(0, update_radar.pending(state)["pendingCount"])
            self.assertFalse(state.exists())
            for invalid in ({}, [], {"feature": None}, {"feature": "line\nline"}):
                with self.assertRaises(update_radar.RadarError):
                    update_radar.pending(state, invalid)
                self.assertFalse(state.exists())

    def test_pending_defer_and_evidence_cli_are_canonical_and_fail_closed(self):
        repo = Path(__file__).parents[1]
        state = repo / ".harness" / "runtime" / f"test-update-radar-state-{uuid4().hex}.json"
        item = candidate(); digest = update_radar._digest(item); check = assessment()
        def cli(*args, input_text=None):
            return subprocess.run([sys.executable, "update_radar.py", *args, "--state", str(state)],
                                  cwd=repo, input=input_text, text=True, encoding="utf-8",
                                  capture_output=True, check=False, timeout=15)
        try:
            update_radar.scan(batch(item), state)
            deferred = cli("defer", item["id"], "--digest", digest, "--assessment-json", json.dumps(check))
            self.assertEqual(0, deferred.returncode, deferred.stderr)
            before = state.read_bytes()
            pending = cli("pending", "--prerequisites-json", json.dumps(check["prerequisites"]))
            self.assertEqual(0, pending.returncode, pending.stderr)
            self.assertEqual(0, json.loads(pending.stdout)["needsRecheckCount"])
            self.assertEqual(pending.stdout, json.dumps(json.loads(pending.stdout), ensure_ascii=True,
                                                      sort_keys=True, separators=(",", ":")) + "\n")
            stdin_retry = cli("defer", item["id"], "--digest", digest, "--assessment-json", "-",
                              input_text="\ufeff" + json.dumps(check))
            self.assertEqual(0, stdin_retry.returncode, stdin_retry.stderr)
            self.assertFalse(json.loads(stdin_retry.stdout)["stateChanged"])
            stdin_pending = cli("pending", "--prerequisites-json", "-", input_text=json.dumps(check["prerequisites"]))
            self.assertEqual(pending.stdout, stdin_pending.stdout)
            for oversized_payload in (" " * (update_radar.MAX_INPUT_BYTES + 1),
                                      "\ufeff" + json.dumps(check) + " " * update_radar.MAX_INPUT_BYTES):
                oversized = cli("defer", item["id"], "--digest", digest, "--assessment-json", "-",
                                input_text=oversized_payload)
                self.assertEqual(2, oversized.returncode)
                self.assertEqual(before, state.read_bytes())
            for args in (("defer", item["id"], "--digest", digest, "--assessment-json", "{}"),
                         ("pending", "--prerequisites-json", '{"feature":"a","feature":"b"}'),
                         ("pending", "--prerequisites-json", "["),
                         ("pending", "--prerequisites-json", "[" * 1100 + "0" + "]" * 1100),
                         ("pending", "--state", str(repo / "escaped.json"))):
                # Pass an unsafe state last, so argparse cannot override it with the fixture path.
                result = (subprocess.run([sys.executable, "update_radar.py", *args], cwd=repo, text=True,
                                         capture_output=True, check=False, timeout=15)
                          if "--state" in args else cli(*args))
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(before, state.read_bytes())
            resolved = cli("resolve", item["id"], "--digest", digest, "--outcome", "no-benefit",
                           "--evidence-hash", "1" * 64, "--evidence-json", "-",
                           input_text=json.dumps(["Локальная проверка пройдена."], ensure_ascii=False))
            self.assertEqual(0, resolved.returncode, resolved.stderr)
            self.assertEqual(["Локальная проверка пройдена."], json.loads(resolved.stdout)["evidence"])
        finally:
            state.unlink(missing_ok=True)

    def test_cli_is_canonical_and_restricts_state_to_runtime_directory(self):
        repo = Path(__file__).parents[1]
        suffix = uuid4().hex
        batch_path = repo / ".harness" / "test-tmp" / f"update-radar-batch-{suffix}.json"
        state_path = repo / ".harness" / "runtime" / f"test-update-radar-state-{suffix}.json"
        batch_path.parent.mkdir(parents=True, exist_ok=True)
        batch_path.write_text(json.dumps(batch(candidate())), encoding="utf-8")
        try:
            command = [sys.executable, "update_radar.py", "scan", str(batch_path), "--state", str(state_path)]
            first = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False)
            second = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False)
            observed = json.loads(first.stdout)["pending"][0]
            resolve_command = [sys.executable, "update_radar.py", "resolve", observed["id"], "--digest", observed["digest"], "--outcome", "no-benefit", "--evidence-hash", "1" * 64, "--state", str(state_path)]
            resolved = subprocess.run(resolve_command, cwd=repo, text=True, capture_output=True, check=False)
            retry = subprocess.run(resolve_command, cwd=repo, text=True, capture_output=True, check=False)
            before = state_path.read_bytes()
            invalid = subprocess.run(resolve_command[:-4] + ["--evidence-hash", "bad", "--state", str(state_path)], cwd=repo, text=True, capture_output=True, check=False)
            self.assertEqual(before, state_path.read_bytes())
            escape_resolve = subprocess.run(resolve_command[:-1] + [str(repo / "escaped.json")], cwd=repo, text=True, capture_output=True, check=False)
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
        self.assertEqual(0, resolved.returncode, resolved.stderr)
        self.assertEqual(0, retry.returncode, retry.stderr)
        self.assertTrue(json.loads(resolved.stdout)["stateChanged"])
        self.assertFalse(json.loads(retry.stdout)["stateChanged"])
        self.assertEqual(2, invalid.returncode)
        self.assertEqual(2, escape_resolve.returncode)
        self.assertNotIn("Traceback", invalid.stdout + invalid.stderr + escape_resolve.stderr)
        self.assertEqual(2, escaped.returncode)
        self.assertNotIn("Traceback", escaped.stdout + escaped.stderr)
        self.assertEqual(first.stdout, json.dumps(json.loads(first.stdout), ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")
        self.assertEqual("pending-evaluation", json.loads(second.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
