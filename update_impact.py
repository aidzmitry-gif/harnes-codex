#!/usr/bin/env python3
"""Classify one structured local update candidate without external side effects."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


SCHEMA_VERSION = 1
ALLOWED_HOSTS = {
    "developers.openai.com",
    "platform.openai.com",
    "learn.chatgpt.com",
}
ROOT_FIELDS = {
    "schemaVersion", "id", "product", "publishedDate", "sourceUrl", "facts",
    "inferences", "assumptions", "impact", "affectedComponents",
}
IMPACT_FIELDS = {"security", "compatibility", "userTime", "reliability", "implementationCost"}
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
COMPONENT = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class CandidateError(ValueError):
    """Candidate input is unsafe or outside the supported schema."""


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or "\n" in value or "\r" in value or len(value) > 500:
        raise CandidateError(f"{name} must be a single-line string of 1..500 characters")
    return value


def _text_list(value: object, name: str, minimum: int) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= 8:
        raise CandidateError(f"{name} must contain {minimum}..8 entries")
    items = [_require_text(item, f"{name} entry") for item in value]
    if len(set(items)) != len(items):
        raise CandidateError(f"{name} entries must be unique")
    return items


def _bounded_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 3:
        raise CandidateError(f"impact.{name} must be an integer from 0 to 3")
    return value


def _validate_url(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 2048
        or any(character.isspace() for character in value)
        or any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in value)
    ):
        raise CandidateError("sourceUrl must be a 1..2048 character string without whitespace or control characters")
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme == "https" and parsed.netloc in ALLOWED_HOSTS and parsed.username is None and parsed.password is None and parsed.port is None
    except ValueError as exc:
        raise CandidateError("sourceUrl must use https and an allowed exact OpenAI hostname without credentials or port") from exc
    if not valid:
        raise CandidateError("sourceUrl must use https and an allowed exact OpenAI hostname without credentials or port")
    return value


def validate_candidate(candidate: object) -> dict[str, object]:
    """Return a validated candidate or reject every unsupported input shape."""
    if not isinstance(candidate, dict) or set(candidate) != ROOT_FIELDS:
        raise CandidateError("candidate must contain exactly the schema v1 fields")
    if not isinstance(candidate["schemaVersion"], int) or isinstance(candidate["schemaVersion"], bool) or candidate["schemaVersion"] != SCHEMA_VERSION:
        raise CandidateError("schemaVersion must be integer 1")
    identifier = candidate["id"]
    if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
        raise CandidateError("id must be a bounded lowercase identifier")
    if candidate["product"] != "openai":
        raise CandidateError("product must be openai")
    published = candidate["publishedDate"]
    if not isinstance(published, str):
        raise CandidateError("publishedDate must be ISO YYYY-MM-DD")
    try:
        if date.fromisoformat(published).isoformat() != published:
            raise ValueError
    except ValueError as exc:
        raise CandidateError("publishedDate must be a real ISO YYYY-MM-DD date") from exc
    components = candidate["affectedComponents"]
    if not isinstance(components, list) or not 1 <= len(components) <= 16:
        raise CandidateError("affectedComponents must contain 1..16 entries")
    if any(not isinstance(component, str) or not COMPONENT.fullmatch(component) for component in components) or len(set(components)) != len(components):
        raise CandidateError("affectedComponents must contain unique bounded IDs")
    impact = candidate["impact"]
    if not isinstance(impact, dict) or set(impact) != IMPACT_FIELDS:
        raise CandidateError("impact must contain exactly the supported dimensions")
    facts = _text_list(candidate["facts"], "facts", 1)
    inferences = _text_list(candidate["inferences"], "inferences", 0)
    assumptions = _text_list(candidate["assumptions"], "assumptions", 0)
    if len(set(facts + inferences + assumptions)) != len(facts) + len(inferences) + len(assumptions):
        raise CandidateError("evidence strings must not be reused across facts, inferences, or assumptions")
    return {
        "id": identifier,
        "sourceUrl": _validate_url(candidate["sourceUrl"]),
        "facts": facts,
        "inferences": inferences,
        "assumptions": assumptions,
        "impact": {name: _bounded_int(impact[name], name) for name in sorted(IMPACT_FIELDS)},
        "affectedComponents": components,
    }


def classify(candidate: object) -> dict[str, object]:
    """Produce the bounded, deterministic local recommendation for one candidate."""
    valid = validate_candidate(candidate)
    impact = valid["impact"]
    assert isinstance(impact, dict)
    score = impact["security"] * 3 + impact["compatibility"] * 2 + impact["userTime"] + impact["reliability"] * 2 - impact["implementationCost"]
    reasons = ["score=%d (security*3 + compatibility*2 + userTime + reliability*2 - implementationCost)" % score]
    if impact["security"] >= 2:
        classification = "significant"
        reasons.append("security impact meets override threshold 2")
    elif impact["compatibility"] >= 2:
        classification = "significant"
        reasons.append("compatibility impact meets override threshold 2")
    elif score >= 6:
        classification = "significant"
        reasons.append("score meets significant threshold 6")
    elif score >= 2:
        classification = "evaluate"
        reasons.append("score meets evaluate threshold 2 but not significant threshold 6")
    else:
        classification = "ignore"
        reasons.append("score is below evaluate threshold 2")
    recommendation = {
        "significant": "run-local-evaluation",
        "evaluate": "collect-more-evidence",
        "ignore": "no-action",
    }[classification]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "id": valid["id"],
        "classification": classification,
        "significant": classification == "significant",
        "score": score,
        "reasons": reasons,
        "affectedComponents": valid["affectedComponents"],
        "recommendation": recommendation,
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] != "classify":
        print("usage: update_impact.py classify CANDIDATE.json", file=sys.stderr)
        return 2
    try:
        candidate = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        result = classify(candidate)
    except (OSError, json.JSONDecodeError, CandidateError) as exc:
        print(f"FAIL INPUT: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
