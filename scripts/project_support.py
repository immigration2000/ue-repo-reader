"""Project declaration policy; deliberately independent of asset saved-by versions.

The 5.7/5.8 window comes from this repository's pinned project fixtures, not a
claim that every package or gameplay behavior in those versions is verified.
No registry lookup, installed-engine inference or maximum/modal asset version.
"""
from __future__ import annotations

import json
import re

POLICY_VERSION = 1
MIN_PROJECT = (5, 7)
MAX_TESTED_PROJECT = (5, 8)
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?")


def parse_descriptor(text):
    """Reject ambiguous/invalid JSON instead of choosing one conflicting declaration."""
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate field {key!r} in project descriptor")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"invalid JSON constant {value}")

    result = json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    if not isinstance(result, dict):
        raise ValueError("project descriptor must be a JSON object")
    json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return result


def assess_project(engine_association, *, best_effort=False, project_found=True, metadata_error=None):
    """Classify a declaration. Only an explicit bool can opt into exploratory work."""
    if type(best_effort) is not bool:
        raise ValueError("best_effort must be a boolean")
    try:
        json.dumps(engine_association, ensure_ascii=False, allow_nan=False).encode("utf-8")
        raw = engine_association
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raw = {"invalid_type_or_encoding": type(engine_association).__name__}
    version = engine_association.strip() if isinstance(engine_association, str) else ""
    match = _VERSION.fullmatch(version) if len(version) <= 64 else None
    classification, declared = "unconfirmed", None
    if not project_found:
        reason = "No .uproject selected; the project engine is unconfirmed."
    elif metadata_error is not None:
        reason = "Project descriptor could not be read as unambiguous UTF-8 JSON; the engine is unconfirmed."
    elif not match:
        reason = "EngineAssociation is missing or not a numeric declaration (major.minor[.patch]); build IDs are unconfirmed."
    else:
        declared = version  # Do not invent patch 0 for a declaration without one.
        pair = (int(match[1]), int(match[2]))
        if pair < MIN_PROJECT:
            classification = "below_minimum"
            reason = "Project declaration is below the UE 5.7 minimum; legacy project expansion is outside the target."
        elif pair > MAX_TESTED_PROJECT:
            classification = "unverified_newer"
            reason = "Project declaration is newer than the current fixture-backed 5.7/5.8 window; compatibility is unverified."
        else:
            classification = "target"
            reason = "Project declaration is in the current 5.7/5.8 target window; package coverage and semantics require separate checks."
    return {"policy_version": POLICY_VERSION, "target": "UE 5.7+ projects",
            "normal_project_minors": ["5.7", "5.8"], "engine_association": raw,
            "declared_version": declared, "classification": classification,
            "allowed": classification == "target" or best_effort,
            "best_effort_requested": best_effort,
            "best_effort_used": classification != "target" and best_effort,
            "reason": reason}


def declaration_text(value):
    """Bounded one-line display; preserve the original separately in digest.json."""
    text = json.dumps(value, ensure_ascii=True, allow_nan=False)
    return text.replace("`", "\\u0060").replace("|", "\\u007c")[:180]


def support_notice(support):
    """The same explicit support notice for INDEX and the full catalog."""
    if not isinstance(support, dict):
        return ["> Project support: **unconfirmed** · policy record unavailable. "
                "This document cannot confirm a project target without assessed support metadata.", ""]
    classification = support["classification"]
    mode = "explicit best-effort" if support["best_effort_used"] else "normal"
    return [f"> Project support: **{classification}** · {mode} · EngineAssociation={declaration_text(support['engine_association'])}. "
            + support["reason"],
            "> Project target is UE 5.7+; normal mode currently covers declared 5.7/5.8 projects. "
            "Older-saved assets inside them are still decoded per package. A matching declaration is not a guarantee of semantic accuracy.", ""]
