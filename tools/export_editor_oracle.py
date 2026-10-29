#!/usr/bin/env python3
"""Capture a native Unreal Editor oracle for named Blueprint assets (export schema v1).

This runs *inside* a running Unreal Editor (5.7 or newer) whose project has the RepoReaderOracle
plugin (``tools/RepoReaderOracle``) built and enabled, for example from the editor's Python console::

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "export_editor_oracle", r"C:/work/ue-repo-reader/tools/export_editor_oracle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.export_oracle(r"D:/oracle/eg.json", ["/Game/Blueprints/BP_Player"])

It imports nothing from ``scripts/`` on purpose. The editor's own in-memory state is the independent
truth that ue-repo-reader's binary decoding is compared against, so sharing a line of decoding code
would make the comparison circular.

Nothing here writes to the project: only ``unreal.load_asset`` and the plugin's read-only bridge are
called, never a scan, compile or save. Each package's bytes are hashed before and after its capture
and a mismatch is reported as a failure of that record rather than passed over.

Why a C++ bridge at all: UE 5.8's stock Python bindings do not expose ``UBlueprint``'s
``ubergraph_pages``, ``function_graphs`` or ``new_variables``, nor ``UEdGraph.nodes``, and
``list_all_pins`` reports only visible K2 pins, so a Python-only oracle cannot see the graph the
engine actually holds.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

SCHEMA_VERSION = 1
PRODUCER = "unreal-editor-native"
MINIMUM_ENGINE = (5, 7)
BRIDGE_CLASS = "RepoReaderOracleLibrary"
BRIDGE_FUNCTION = "capture_blueprint"
MOUNT = "/Game/"
CONTENT = "Content"
# The bridge declares that every FText-derived field it reports is the authored source string.
TEXT_VALUES = "source"
# A record is only comparable against the saved package when both of these hold: the text is source
# text, and the editor was not sitting on unsaved edits that the package file cannot show.
SNAPSHOT_KEYS = ("asset_class", "text_values", "package_dirty", "parent_class", "variables",
                 "function_graphs", "graphs", "widget_bindings", "issues")
_ENGINE_VERSION = re.compile(r"^\s*(\d+)\.(\d+)(?:\D|$)")
_UNUSABLE = set('\\:*?"<>|') | {chr(code) for code in range(32)}
_CHUNK = 1 << 20


class OracleConfigError(Exception):
    """A caller or environment problem, raised before any asset is read or any output replaced."""


class _BridgeResponseError(Exception):
    """The native bridge answered with something that is not a usable snapshot."""


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}".strip()


def _engine_version(unreal) -> str:
    """The engine's own version string, rejected outright when it is unreadable or too old."""
    library = getattr(unreal, "SystemLibrary", None)
    getter = getattr(library, "get_engine_version", None) if library is not None else None
    if not callable(getter):
        raise OracleConfigError("unreal.SystemLibrary.get_engine_version is unavailable; "
                                "the engine version cannot be established and is not guessed")
    raw = getter()
    if not isinstance(raw, str) or not raw.strip():
        raise OracleConfigError(f"get_engine_version() returned {raw!r}; the engine version is unknown")
    found = _ENGINE_VERSION.match(raw)
    if found is None:
        raise OracleConfigError(f"engine version {raw!r} has no numeric major.minor prefix; "
                                "support is not guessed from an unparsable version")
    version = (int(found.group(1)), int(found.group(2)))
    if version < MINIMUM_ENGINE:
        raise OracleConfigError(
            f"engine {raw!r} is older than {MINIMUM_ENGINE[0]}.{MINIMUM_ENGINE[1]}: the oracle bridge "
            "is only built and verified for 5.7+")
    return raw


def _bridge(unreal):
    """The plugin's capture entry point, required before anything is loaded."""
    library = getattr(unreal, BRIDGE_CLASS, None)
    if library is None:
        raise OracleConfigError(
            f"unreal.{BRIDGE_CLASS} is missing: build and enable the RepoReaderOracle plugin "
            "(tools/RepoReaderOracle) in this project before exporting")
    capture = getattr(library, BRIDGE_FUNCTION, None)
    if not callable(capture):
        raise OracleConfigError(
            f"unreal.{BRIDGE_CLASS}.{BRIDGE_FUNCTION} is not callable: the installed RepoReaderOracle "
            "plugin does not match this exporter")
    return capture


def _loader(unreal):
    load = getattr(unreal, "load_asset", None)
    if not callable(load):
        raise OracleConfigError("unreal.load_asset is unavailable; assets cannot be read")
    return load


def _checked_asset_paths(asset_paths) -> list[str]:
    """Exactly the requested mounted package paths, or an error naming the offending entry."""
    if isinstance(asset_paths, (str, bytes, bytearray)) or not isinstance(asset_paths, (list, tuple)):
        raise OracleConfigError("asset_paths must be a list or tuple of '/Game/...' package paths, "
                                f"not {type(asset_paths).__name__}")
    if not asset_paths:
        raise OracleConfigError("asset_paths is empty: this version exports exactly the assets it is "
                                "given and does not discover any itself")
    checked: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(asset_paths):
        label = f"asset_paths[{index}]"
        if not isinstance(value, str):
            raise OracleConfigError(f"{label} is {type(value).__name__}, not a string")
        if value != value.strip():
            raise OracleConfigError(f"{label}={value!r} is padded with whitespace")
        if not value.startswith(MOUNT):
            raise OracleConfigError(
                f"{label}={value!r} is not under {MOUNT}: this version reads mounted project content "
                "only, so engine, script and plugin mounts are refused rather than guessed at")
        segments = value[1:].split("/")
        if not all(segments):
            raise OracleConfigError(f"{label}={value!r} has an empty path segment")
        if any(segment in (".", "..") for segment in segments):
            raise OracleConfigError(f"{label}={value!r} traverses directories")
        unusable = [character for character in value if character in _UNUSABLE]
        if unusable:
            raise OracleConfigError(f"{label}={value!r} contains the unusable character "
                                    f"{unusable[0]!r}")
        if "." in segments[-1]:
            raise OracleConfigError(
                f"{label}={value!r} looks like an object path; pass the package path "
                "('/Game/Folder/BP_Name') so the package file it names is unambiguous")
        if value in seen:
            raise OracleConfigError(f"{label}={value!r} is requested more than once")
        seen.add(value)
        checked.append(value)
    return checked


def _project_file(unreal) -> Path:
    """The selected .uproject; its parent is the project root every package path is read under."""
    paths = getattr(unreal, "Paths", None)
    getter = getattr(paths, "get_project_file_path", None) if paths is not None else None
    if not callable(getter):
        raise OracleConfigError("unreal.Paths.get_project_file_path is unavailable; "
                                "the project root cannot be established")
    raw = getter()
    if not isinstance(raw, str) or not raw.strip():
        raise OracleConfigError(f"get_project_file_path() returned {raw!r}; the project root is unknown")
    convert = getattr(paths, "convert_relative_path_to_full", None)
    if callable(convert):
        full = convert(raw)
        if isinstance(full, str) and full.strip():
            raw = full
    project = Path(raw)
    if not project.is_absolute():
        raise OracleConfigError(f"project file {raw!r} is not absolute; the editor's working directory "
                                "is not ours to assume")
    project = project.resolve()
    if project.suffix.lower() != ".uproject":
        raise OracleConfigError(f"project file {project} is not a .uproject")
    if not project.is_file():
        raise OracleConfigError(f"project file {project} does not exist")
    return project


def _checked_output(output, project: Path) -> Path:
    """A .json destination that cannot be the project file, an asset, or anything under Content/."""
    if isinstance(output, (bytes, bytearray)):
        raise OracleConfigError("output must be a str or os.PathLike .json path, not bytes")
    try:
        target = Path(output)
    except TypeError as error:
        raise OracleConfigError(f"output {output!r} is not a usable path: {error}") from error
    if not str(target).strip() or str(target) == ".":
        raise OracleConfigError("output is empty")
    target = target.expanduser()
    if not target.is_absolute():
        raise OracleConfigError(f"output {target} must be absolute: this runs from the editor's "
                                "working directory, which is not ours to assume")
    resolved = target.resolve()
    # The suffix check is what keeps a .uproject, .uasset or .umap from ever being the destination.
    if resolved.suffix.lower() != ".json":
        raise OracleConfigError(f"output {resolved} must name a .json file")
    if resolved.is_dir():
        raise OracleConfigError(f"output {resolved} is a directory")
    if resolved == project:
        raise OracleConfigError(f"output {resolved} is the project file")
    content = (project.parent / CONTENT).resolve()
    if resolved == content or resolved.is_relative_to(content):
        raise OracleConfigError(f"output {resolved} is inside the project's content directory "
                                f"({content}); write the oracle outside the project's assets")
    parent = resolved.parent
    if parent.exists() and not parent.is_dir():
        raise OracleConfigError(f"output directory {parent} is not a directory")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_file(asset_path: str, project: Path, issues: list[str]) -> tuple[str, Path | None]:
    """The package file a mounted path names, or None with the reason its bytes cannot be pinned."""
    relative = f"{CONTENT}/{asset_path[len(MOUNT):]}.uasset"
    content = (project.parent / CONTENT).resolve()
    candidate = project.parent / relative
    try:
        resolved = candidate.resolve()
    except OSError as error:
        issues.append(f"{asset_path}: package path {candidate} cannot be resolved ({error}); "
                      "its bytes are not pinned")
        return relative, None
    # Resolved first: a symlink or junction under Content/ must not let the hash follow bytes outside it.
    if not resolved.is_relative_to(content):
        issues.append(f"{asset_path}: package file resolves to {resolved}, outside {content}; "
                      "its bytes are not pinned")
        return relative, None
    if not resolved.is_file():
        issues.append(f"{asset_path}: {relative} is not a readable file under the project; "
                      "its bytes are not pinned")
        return relative, None
    return relative, resolved


def _no_duplicate_keys(pairs):
    parsed: dict = {}
    for key, value in pairs:
        if key in parsed:
            raise ValueError(f"duplicate key {key!r}")
        parsed[key] = value
    return parsed


def _reject_constant(name):
    raise ValueError(f"the non-JSON constant {name}")


def _parse_snapshot(raw) -> dict:
    """Strict parse of the bridge's answer: a JSON object with unique keys and no NaN/Infinity."""
    if not isinstance(raw, str):
        raise _BridgeResponseError(f"the native bridge returned {type(raw).__name__}, not a JSON string")
    if not raw.strip():
        raise _BridgeResponseError("the native bridge returned an empty response, so nothing was captured")
    try:
        snapshot = json.loads(raw, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant)
    except ValueError as error:
        raise _BridgeResponseError(f"the native bridge response is not usable JSON: {error}") from error
    if not isinstance(snapshot, dict):
        raise _BridgeResponseError(
            f"the native bridge response is a JSON {type(snapshot).__name__}, not an object")
    return snapshot


def _check_snapshot(asset_path: str, snapshot: dict, issues: list[str]) -> None:
    """Keeps the snapshot either way, but says so when it is not shaped like the agreed schema."""
    missing = [key for key in SNAPSHOT_KEYS if key not in snapshot]
    if missing:
        issues.append(f"{asset_path}: the native snapshot is missing {', '.join(missing)}; "
                      "the installed plugin may not match this exporter")
    values = snapshot.get("text_values")
    if "text_values" in snapshot and values != TEXT_VALUES:
        issues.append(f"{asset_path}: the native snapshot reports text_values={values!r} instead of "
                      f"{TEXT_VALUES!r}; its text fields may be localized display strings, "
                      "not authored source text")
    # Unsaved editor edits leave the package file's bytes alone, so the hashes above cannot see them:
    # a dirty package means this snapshot describes the editor's state, not the saved asset's.
    dirty = snapshot.get("package_dirty")
    if dirty is True:
        issues.append(f"{asset_path}: the editor is holding unsaved changes to this package "
                      "(package_dirty), so the snapshot is not the saved file's state and the "
                      "unchanged file hashes do not vouch for it")
    elif "package_dirty" in snapshot and dirty is not False:
        issues.append(f"{asset_path}: the native snapshot reports package_dirty={dirty!r}, which is "
                      f"{type(dirty).__name__} and not a bool, so unsaved changes cannot be ruled out")
    native = snapshot.get("issues")
    if isinstance(native, list):
        for issue in native:
            issues.append(f"{asset_path}: native capture reported: {issue}")
    elif "issues" in snapshot:
        issues.append(f"{asset_path}: the native snapshot's issues field is "
                      f"{type(native).__name__}, not a list, so its own warnings cannot be read")


def _capture(asset_path: str, load_asset, capture, issues: list[str]) -> dict | None:
    """Loads and captures one asset; every failure becomes an issue and a null snapshot, never a guess."""
    try:
        asset = load_asset(asset_path)
    except Exception as error:  # the editor raises a variety of its own exception types
        issues.append(f"{asset_path}: load_asset failed: {_describe(error)}")
        return None
    if asset is None:
        issues.append(f"{asset_path}: load_asset returned nothing; the asset is missing, unmounted "
                      "or could not be loaded")
        return None
    try:
        raw = capture(asset)
    except Exception as error:
        issues.append(f"{asset_path}: the native bridge raised {_describe(error)}")
        return None
    try:
        return _parse_snapshot(raw)
    except _BridgeResponseError as error:
        issues.append(f"{asset_path}: {error}")
        return None


def _write_atomic(target: Path, oracle: dict) -> None:
    """Serialize first, then replace in one step, so a failure leaves any earlier oracle untouched."""
    text = json.dumps(oracle, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def export_oracle(output, asset_paths, *, unreal_module=None) -> dict:
    """Write the native editor oracle for ``asset_paths`` to ``output`` and return the same record.

    Every requested asset gets exactly one record, in the order it was asked for. An asset that fails
    to load or capture keeps its record with a null snapshot and the reason, so a partial oracle is
    always distinguishable from a complete one; it is never silently dropped.

    Raises OracleConfigError for caller and environment problems — an unsupported engine, a missing
    bridge, unusable asset paths, an unusable destination — before any asset is read and before any
    earlier output is touched.
    """
    unreal = unreal_module
    if unreal is None:
        try:
            import unreal as unreal_runtime
        except ImportError as error:
            raise OracleConfigError(
                "the 'unreal' module is unavailable: export_oracle only runs inside the Unreal "
                "Editor's Python environment") from error
        unreal = unreal_runtime

    # Everything that can refuse the run is checked first, while nothing has been read or written.
    engine_version = _engine_version(unreal)
    capture = _bridge(unreal)
    load_asset = _loader(unreal)
    requested = _checked_asset_paths(asset_paths)
    project = _project_file(unreal)
    target = _checked_output(output, project)

    assets = []
    for asset_path in requested:
        issues: list[str] = []
        relative, package = _package_file(asset_path, project, issues)
        before = None
        if package is not None:
            try:
                before = _sha256(package)
            except OSError as error:
                issues.append(f"{asset_path}: {relative} could not be hashed before the capture "
                              f"({error})")
        snapshot = _capture(asset_path, load_asset, capture, issues)
        if snapshot is not None:
            _check_snapshot(asset_path, snapshot, issues)
        after = None
        if package is not None:
            try:
                after = _sha256(package)
            except OSError as error:
                issues.append(f"{asset_path}: {relative} could not be hashed after the capture "
                              f"({error})")
        if before is not None and after is not None and before != after:
            issues.append(f"{asset_path}: {relative} changed during the capture ({before} -> {after}); "
                          "this is not a read-only observation of the saved asset")
        elif package is not None and (before is None or after is None):
            # _package_file already explained an absent or escaping package; this covers a read that failed.
            issues.append(f"{asset_path}: {relative} is unhashed on at least one side of the capture, "
                          "so the saved bytes behind this snapshot are not pinned")
        assets.append({
            "asset_path": asset_path,
            "package_file": relative,
            "sha256_before": before,
            "sha256_after": after,
            "snapshot": snapshot,
            "issues": issues,
        })

    root_issues: list[str] = []
    failed = [record["asset_path"] for record in assets if record["snapshot"] is None]
    if failed:
        root_issues.append(f"{len(failed)} of {len(assets)} requested assets produced no snapshot: "
                           + ", ".join(failed))
    changed = [record["asset_path"] for record in assets
               if record["sha256_before"] != record["sha256_after"]]
    if changed:
        root_issues.append("package bytes changed while capturing: " + ", ".join(changed))
    # Anything other than an explicit False leaves unsaved editor state unaccounted for, including a
    # flag that is absent or not a bool: none of those may pass as a reading of the saved package.
    unsaved = [record["asset_path"] for record in assets
               if isinstance(record["snapshot"], dict)
               and record["snapshot"].get("package_dirty") is not False]
    if unsaved:
        root_issues.append("snapshots that cannot be read as the saved package's state, because the "
                           "editor held unsaved changes or reported no usable package_dirty flag: "
                           + ", ".join(unsaved))

    if [record["asset_path"] for record in assets] != requested:
        # Nothing is written: an oracle that silently lost or reordered a request is worse than none.
        raise RuntimeError("internal error: the captured records do not match the requested assets")

    oracle = {
        "schema_version": SCHEMA_VERSION,
        "producer": PRODUCER,
        "engine_version": engine_version,
        "project_file": project.as_posix(),
        "assets": assets,
        "issues": root_issues,
    }
    _write_atomic(target, oracle)
    return oracle
