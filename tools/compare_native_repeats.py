"""Audit one native editor capture against an independent repeat capture of the same project.

Both sides are native observations; neither side is the saved package and neither is a
digest. A difference recorded here means only that the editor reported different values
in two captures: it is not proof that our binary reader misreads the asset, and it does
not identify an engine load-time fixup. Separating those causes is Q14's recapture work.

Nothing is decoded or canonicalised here. The comparison scope, field canonicalisation
and exclusions are exactly ``compare_editor_oracle``'s native scope, reused as-is. Apart
from the two capture files named on the command line, no file is read, no absolute asset
path is resolved and no source asset is modified: the audit sees input data only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

_TOOLS = str(Path(__file__).resolve().parent)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
import compare_editor_oracle as C

SCOPE = ("native editor capture versus an independent repeat capture, in the same canonical "
         "native comparison scope as the saved-package oracle adapter")
BASIS = ("the two capture files as given: no package bytes are read, no absolute filesystem path "
         "is resolved and no source asset is modified")
OBSERVATION_ONLY = ("a difference between two native captures is a recorded observation only; it does "
                    "not show the binary reader wrong and does not identify an engine load-time fixup")
_HEX64 = re.compile(r"[a-f0-9]{64}")


def _package_file(asset_path):
    """The one Content path a /Game package may have, by compare_editor_oracle's rule minus its file lookup."""
    if (not isinstance(asset_path, str) or not asset_path.startswith("/Game/") or "\\" in asset_path
            or any(part in ("", ".", "..") for part in asset_path[len("/Game/"):].split("/"))
            or "." in asset_path.rsplit("/", 1)[-1]):
        raise C.OracleError(f"only unambiguous /Game package paths are supported: {asset_path!r}")
    return "Content/" + asset_path[len("/Game/"):] + ".uasset"


def _provenance(capture, label):
    """Root gates: what makes the pair unusable as a repeat raises; capture-reported gaps do not."""
    if not isinstance(capture, dict):
        raise C.OracleError(f"{label} capture must be a JSON object")
    if type(capture.get("schema_version")) is not int or capture["schema_version"] != 1:
        raise C.OracleError(f"unsupported {label} capture schema")
    if capture.get("producer") != "unreal-editor-native":
        raise C.OracleError(f"{label} capture producer is not the native editor")
    engine = capture.get("engine_version")
    match = re.match(r"(\d+)\.(\d+)\.", engine if isinstance(engine, str) else "")
    if not match or tuple(map(int, match.groups())) < (5, 7):
        raise C.OracleError(f"{label} capture requires an identified UE 5.7+ editor")
    project = capture.get("project_file")
    if not isinstance(project, str) or not project.endswith(".uproject") or len(project) <= len(".uproject"):
        raise C.OracleError(f"{label} capture has no source project identity")
    if not isinstance(capture.get("issues"), list) or any(type(item) is not str for item in capture["issues"]):
        raise C.OracleError(f"{label} capture issues must be an array of strings")
    assets = C._indexed(capture.get("assets"), lambda a: a["asset_path"], f"{label} asset")
    if not assets:
        raise C.OracleError(f"an empty {label} capture cannot show a repeat to be stable")
    for asset_path in assets:
        # The pairing identity has to be sound before any asset is paired at all.
        _package_file(asset_path)
    return assets


def _bytes_identity(record, asset_path, label):
    """The saved bytes this capture observed; both digests must name the same unchanged package."""
    if record.get("package_file") != _package_file(asset_path):
        raise C.OracleError(f"{label} package_file does not match the mounted asset path")
    digests = []
    for key in ("sha256_before", "sha256_after"):
        value = record.get(key)
        if not isinstance(value, str) or not _HEX64.fullmatch(value):
            raise C.OracleError(f"{label} {key} is not a lower-case sha256 digest")
        digests.append(value)
    if digests[0] != digests[1]:
        raise C.OracleError(f"the saved package changed during the {label} capture")
    return digests[0]


def _snapshot(record, label):
    """A clean, complete native observation, or an explicit gap: never a partial pass."""
    issues = record.get("issues")
    if not isinstance(issues, list) or any(type(item) is not str for item in issues):
        raise C.OracleError(f"{label} asset issues must be an array of strings")
    if issues:
        raise C.OracleError(f"{label} capture gap: " + "; ".join(issues))
    snapshot = record.get("snapshot")
    if not isinstance(snapshot, dict):
        raise C.OracleError(f"{label} capture reports no native snapshot object")
    if snapshot.get("package_dirty") is not False:
        raise C.OracleError(f"{label} snapshot has unsaved or unconfirmed package state")
    if snapshot.get("issues"):
        raise C.OracleError(f"{label} snapshot reports capture gaps")
    C.validate_native_snapshot(snapshot)
    return snapshot


def audit_repeats(left, right):
    """Compare two native captures of the same project; the result is schema 1 JSON data.

    ``status`` is ``stable`` only when the whole scoped check compared something and found
    no gap, ``changed`` when a difference was observed across a complete check, and
    ``incomplete`` otherwise. Any gap -- a reported capture issue, a differing asset set or
    a single unavailable record anywhere -- outranks ``changed``, because a partially
    observed repeat cannot say what the unobserved part did. Every mismatch is kept in the
    report with its original path and expected/actual values whatever the status.
    """
    left_assets, right_assets = _provenance(left, "left"), _provenance(right, "right")
    if left["engine_version"] != right["engine_version"]:
        raise C.OracleError("the captures come from different editor builds; that is not a repeat")
    if left["project_file"] != right["project_file"]:
        raise C.OracleError("the captures come from different projects; that is not a repeat")
    report = {"schema_version": 1, "status": "incomplete", "engine_version": left["engine_version"],
              "project_file": left["project_file"], "scope": SCOPE, "basis": BASIS,
              "caveat": OBSERVATION_ONLY, "exclusions": list(C.EXCLUSIONS),
              "issues": [f"left capture: {i}" for i in left["issues"]] + [f"right capture: {i}" for i in right["issues"]],
              "assets": [], "checked": 0}
    for asset_path in sorted(left_assets.keys() | right_assets.keys()):
        item = {"asset_path": asset_path, "checked": 0, "mismatches": [], "unavailable": []}
        report["assets"].append(item)
        if asset_path not in left_assets or asset_path not in right_assets:
            side = "left" if asset_path not in left_assets else "right"
            # The repeat covered a different asset set; that is a scope gap, not a difference.
            report["issues"].append(f"asset {asset_path} is absent from the {side} capture")
            item["unavailable"].append({"path": asset_path, "reason": f"absent from the {side} capture"})
            continue
        try:
            records = (left_assets[asset_path], right_assets[asset_path])
            digests = [_bytes_identity(record, asset_path, label)
                       for record, label in zip(records, ("left", "right"))]
            if digests[0] != digests[1]:
                raise C.OracleError("the saved package differs between the captures; "
                                    "these are not repeat observations of the same bytes")
            # compare_snapshots validates its expected side; both sides are native here.
            snapshots = [_snapshot(record, label) for record, label in zip(records, ("left", "right"))]
            item.update(C.compare_snapshots(snapshots[0], snapshots[1], profile="all"))
            if not item["checked"] and not item["unavailable"]:
                item["unavailable"].append({"path": asset_path, "reason": "no observations compared for this asset"})
            report["checked"] += item["checked"]
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
            reason = str(error) if isinstance(error, C.OracleError) else f"{type(error).__name__}: {error}"
            item["unavailable"].append({"path": asset_path, "reason": reason})
    # Gaps outrank differences: the retained mismatch rows stay exactly as they were observed,
    # but a repeat with any unobserved part is reported as incomplete, never as a verdict.
    if report["issues"] or any(asset["unavailable"] for asset in report["assets"]):
        report["status"] = "incomplete"
    elif any(asset["mismatches"] for asset in report["assets"]):
        report["status"] = "changed"
    elif report["checked"]:
        report["status"] = "stable"
    return report


def _destination(out, inputs):
    """A new .json file in an existing directory: no input and no existing report is touched."""
    destination = out.resolve()
    if destination.suffix.lower() != ".json":
        raise C.OracleError("the audit output must be a new .json file")
    if destination in inputs:
        raise C.OracleError("the audit output must not be one of the input captures")
    if destination.exists():
        raise C.OracleError("the audit output already exists; existing files are preserved")
    if not destination.parent.is_dir():
        raise C.OracleError("the audit output directory does not exist; this tool creates no directories")
    return destination


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path, help="native capture (compare_editor_oracle oracle schema 1)")
    parser.add_argument("right", type=Path, help="independent repeat capture of the same project")
    parser.add_argument("--out", type=Path, help="write a new .json audit report; existing files are preserved")
    args = parser.parse_args(argv)
    try:
        inputs = {args.left.resolve(), args.right.resolve()}
        destination = _destination(args.out, inputs) if args.out else None
        captures = [C.load_json(path.read_text(encoding="utf-8-sig")) for path in (args.left, args.right)]
        report = audit_repeats(*captures)
        text = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)
        if destination is not None:
            with open(destination, "x", encoding="utf-8") as output:
                output.write(text + "\n")
        print(f"{report['status']}: {len(report['assets'])} assets; {report['checked']} compared native "
              f"observations. Scoped repeat audit only; {OBSERVATION_ONLY}.")
        if destination is None:
            print(text)
        return 0 if report["status"] == "stable" else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
