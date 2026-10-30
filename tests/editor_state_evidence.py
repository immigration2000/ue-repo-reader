"""Replay independent loaded observations against exact source-byte evidence.

Frozen excerpts are native data, never reader-made expected values. Raw byte
spans are checked against the pinned source package before interpreting them.
Evidence grouping by pin name is descriptive only: no production GUID is remapped.
"""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tools")]
import bp_reader as B
import data_reader as D
import compare_editor_oracle as C
from editor_oracle_regress import check_git_blob


def span(raw, record, *, offset="offset", value="raw_hex"):
    start = record[offset]
    assert type(start) is int and start >= 0
    expected = bytes.fromhex(record[value])
    assert expected and raw[start:start + len(expected)] == expected, "saved byte evidence changed"
    return expected


def source(project, record, commit):
    path = Path(project) / record["package_file"]
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == record["sha256"], "evidence package hash mismatch"
    check_git_blob(project, commit, record["package_file"], record["git_blob"])
    return path, raw


def membership(record, path, raw, summary):
    evidence = record["membership"]
    payload = span(raw, evidence["saved_nodes_tag"])
    count = struct.unpack_from("<i", payload)[0]
    assert len(payload) == 4 + 4 * count
    indices = list(struct.unpack_from("<" + "i" * count, payload, 4))
    assert indices == evidence["saved_node_exports"]
    assert not set(indices) & set(evidence["unlisted_node_exports"])
    graph_path = evidence.get("owner_path", evidence.get("graph"))
    matches = [g for g in summary["graph_ir"]["graphs"] if g["id"] == graph_path]
    assert len(matches) == 1
    assert set(n["export_index"] for n in matches[0]["nodes"]) == set(indices)
    detached = summary["unlisted_graph_nodes"]
    assert not detached["issues"]
    assert {n["export_index"] for g in detached["graphs"] for n in g["nodes"]} == set(evidence["unlisted_node_exports"])
    if "native_graph_first" in evidence:
        assert evidence["native_graph_first"] == evidence["native_graph_fresh"]
        decoded = C.read_snapshot(path, record["asset_path"], native_class="AnimBlueprint")
        graphs = [g for g in decoded["graphs"] if C.object_path(g["object_path"]) == graph_path]
        expected = {"asset_class": "AnimBlueprint", "text_values": "source", "package_dirty": False,
                    "parent_class": None, "variables": [], "function_graphs": [], "widget_bindings": None,
                    "graphs": [evidence["native_graph_first"]], "issues": []}
        result = C.compare_snapshots(expected, {**expected, "graphs": graphs}, profile="graph")
        assert result["checked"] > 0 and not result["mismatches"] and not result["unavailable"], result
    return count


def check_eg_loaded_state(project, commit):
    evidence = json.loads((ROOT / "tests/editor_evidence/eg-loaded-state.json").read_text(encoding="utf-8"))
    assert evidence["commit"] == commit and len(evidence["assets"]) == 7
    assert evidence["same_process_mismatches"] == 0 and evidence["fresh_process_identity_mismatches"] == 34
    categories = unstable = stable_differences = memberships = 0
    for asset in evidence["assets"]:
        path, raw = source(project, asset, commit)
        assert asset["package_dirty_first"] is asset["package_dirty_fresh"] is False
        product = B.read_blueprint(str(path), asset["asset_path"])
        summary = product["summary"]
        assert not summary["issues"]
        variables = summary["declaration_ir"]["variables"]
        variables = {v["name"]: v for v in variables} if isinstance(variables, list) else {}
        for category in asset["invariant_categories"]:
            data = span(raw, category)
            assert data[4] == 255 and struct.unpack_from("<i", data, 5)[0] == 1
            length = struct.unpack_from("<i", data, 9)[0]
            assert length > 0 and len(data) == 13 + length and data[-1] == 0
            saved = data[13:-1].decode("ascii")
            assert saved == category["native_first"] == category["native_fresh"]
            assert variables[category["variable"]]["category"] == saved
            rows = [l for l in product["markdown"].splitlines() if l.startswith("| " + category["variable"] + " |")]
            assert len(rows) == 1 and "| " + saved + " |" in rows[0], "authored category missing from variable table"
            categories += 1
        graph_pins = {(n["object_path"], p["guid"].replace("-", "").lower()): p
                      for g in summary["graph_ir"]["graphs"] for n in g["nodes"] for p in n["pins"]}
        for pin in asset["pins"]:
            guid = bytes.fromhex(pin["saved_guid"])
            assert raw[pin["saved_guid_offset"]:pin["saved_guid_offset"] + 16] == guid
            actual = graph_pins[(pin["owner"], pin["saved_guid"])]
            assert actual["pin_name"] == pin["pin_name"] and actual["direction"] == pin["direction"]
            first, fresh = pin["native_first"], pin["native_fresh"]
            assert first["name"] == fresh["name"] == pin["pin_name"]
            assert first["direction"] == fresh["direction"] == pin["direction"]
            if pin["pin_name"] == "ErrorTolerance":
                assert first["hidden"] is fresh["hidden"] is True and first["guid"] != fresh["guid"]
                left, right = copy.deepcopy(first), copy.deepcopy(fresh)
                del left["guid"], right["guid"]
                assert left == right, "native repeat changed more than its ID"
                # Stored pin GUID is still present in the product; never rewritten to a native GUID.
                assert actual["guid"].replace("-", "").lower() == pin["saved_guid"]
                unstable += 1
            else:
                assert first == fresh
                assert C.display_guid_to_serialized(first["guid"]) == pin["saved_guid"]
                data = span(raw, pin, offset="type_offset", value="type_hex")
                assert len(data) == 69  # verified modern non-map type, const archive bool at 57
                saved_const = bool(struct.unpack_from("<i", data, 57)[0])
                assert saved_const is pin["saved_is_const"] is actual["type"]["is_const"]
                default = span(raw, pin, offset="default_offset", value="default_hex")
                length = struct.unpack_from("<i", default)[0]
                assert length >= 0 and len(default) == 4 + length
                saved_default = default[4:-1].decode("ascii") if length else ""
                assert saved_default == pin["saved_default_value"] == actual["defaults"]["default_value"]
                assert saved_const != first["type"]["is_const"] or saved_default != first["default_value"]
                stable_differences += 1
        if asset.get("membership"):
            assert membership(asset, path, raw, summary) == 39
            memberships += 1
    assert (categories, unstable, stable_differences, memberships) == (8, 17, 2, 1)
    probe = json.loads((ROOT / "tests/editor_evidence/ansi-native-probe.json").read_text(encoding="utf-8"))
    raw = (Path(project) / probe["package_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == probe["original_sha256"]
    changed = bytearray(raw)
    changed[probe["changed_byte_offset"]] = 0xe9
    assert hashlib.sha256(changed).hexdigest() == probe["copy_sha256"] == probe["copy_sha256_after"]
    assert probe["package_dirty"] is False and probe["native_source"] == "\uffe9nnerFunctions"
    try:
        D.invariant_text_source(bytes.fromhex(probe["raw_hex"]))
    except UnicodeError:
        pass
    else:
        raise AssertionError("noncanonical narrow bytes were assigned an inferred ANSI codepage")
    return categories, unstable, stable_differences


def check_ar_saved_membership(project, commit):
    evidence = json.loads((ROOT / "tests/editor_evidence/ar-unlisted-state-node.json").read_text(encoding="utf-8"))
    assert evidence["commit"] == commit and evidence["repository"] == "tomlooman/ActionRoguelike"
    path, raw = source(project, evidence, commit)
    product = B.read_blueprint(str(path), "/Game/" + Path(evidence["package_file"]).relative_to("Content").with_suffix("").as_posix())
    assert not product["summary"]["issues"]
    assert "Unlisted node exports" in product["markdown"]
    return membership(evidence, path, raw, product["summary"])
