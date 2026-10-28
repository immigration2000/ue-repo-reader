#!/usr/bin/env python3
"""Compare small, pinned, fixture-authored assets against upstream native-editor oracles."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "asset_fixtures.json"
sys.path.insert(0, str(ROOT.parent / "scripts"))
import bp_reader as B
import data_reader as D
import graph_ir as G


def blob_hash(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def fetch_file(source: dict, item: dict, cache: Path) -> Path:
    path = cache / item["path"]
    if not path.resolve().is_relative_to(cache.resolve()):
        raise ValueError("fixture path escapes its cache")
    if path.is_file() and blob_hash(path.read_bytes()) == item["blob"]:
        return path
    url = f"https://raw.githubusercontent.com/{source['repository']}/{source['commit']}/{item['path']}"
    with urllib.request.urlopen(url, timeout=45) as response:
        data = response.read()
    if blob_hash(data) != item["blob"]:
        raise ValueError(f"fixture content hash mismatch: {item['path']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    temp.write_bytes(data)
    temp.replace(path)
    return path


def check_case(case: dict, cache: Path) -> None:
    path = cache / case["asset"]["path"]
    oracle = json.loads((cache / case["oracle"]["path"]).read_text(encoding="utf-8"))
    if case["kind"] == "blueprint":
        rendered = B.read_blueprint(str(path), "/Game/KeyRepairs/BP_Keys")
        parsed, (ok, total) = B._parse(str(path))
        assert ok == total and total > 0, f"pins decoded {ok}/{total}"
        assert total == case.get("nodes", total), f"node count {total} != expected {case['nodes']}"
        nodes = {n._export_object_name: n for graph, _ in B._walk_graphs(parsed.graphs) for n in graph.nodes}
        for expected in oracle:
            name = expected["objectPath"].rsplit(".", 1)[-1]
            assert name in nodes, f"missing oracle node {name}"
            pin = nodes[name].pins[expected["pinIndex"]]
            pin_id = re.sub("[^0-9A-Fa-f]", "", str(pin.pin_id)).upper()
            # The pinned parser exposes serialized bytes; Unreal's oracle prints four uint32 GUID words.
            guid = expected["pinId"]
            stored_guid = b"".join(int(guid[i:i + 8], 16).to_bytes(4, "little") for i in range(0, 32, 8)).hex().upper()
            assert pin_id == stored_guid, f"wrong pin identity in {name}: {pin_id}"
            assert str(pin.default_text_value) == expected["source"], f"wrong text in {name}"
            assert expected["source"] in rendered["markdown"], f"text missing from Markdown: {name}"
            # New projection oracles target 5.7+; legacy assets retain their
            # previous checks. In particular the 4.27 oracle's package location
            # differs from its saved package identity; do not guess a new mapping.
            if tuple(map(int, case["engine"].split(".")[:2])) >= (5, 7):
                ir_nodes = [node for graph in rendered["summary"]["graph_ir"]["graphs"] for node in graph["nodes"]
                            if node["object_path"] == expected["objectPath"].replace(":", ".", 1)]
                assert len(ir_nodes) == 1, f"missing/ambiguous IR oracle node {expected['objectPath']}"
                assert len(ir_nodes[0]["pins"]) == len(nodes[name].pins), f"IR dropped decoded pins in {name}"
                ir_pins = [p for p in ir_nodes[0]["pins"] if p["index"] == expected["pinIndex"]]
                assert len(ir_pins) == 1, f"missing/ambiguous IR oracle pin in {name}"
                ir_guid = ir_pins[0]["guid"]
                assert isinstance(ir_guid, str) and re.sub("[^0-9A-Fa-f]", "", ir_guid).upper() == stored_guid, f"wrong IR pin identity in {name}"
                assert ir_pins[0]["defaults"]["default_text_value"] == expected["source"], f"wrong IR text in {name}"
                # Confirm the full field contract exists on the actual pinned
                # decoder, not only the synthetic models used by fast tests.
                for field in G._PIN_FIELDS:
                    assert ir_pins[0][field] == getattr(pin, field), (name, field)
                for field in G._DEFAULT_FIELDS:
                    assert ir_pins[0]["defaults"][field] == getattr(pin, field), (name, field)
                for field in G._TYPE_FIELDS:
                    assert ir_pins[0]["type"][field] == getattr(pin.pin_type, field), (name, field)
    elif case["kind"] == "string_table":
        rendered = D.read_data_asset(str(path), "/Game/Legacy/ST_LegacyText", "StringTable")
        table = next(p for p in oracle["packages"] if p["asset_name"] == "ST_LegacyText")
        assert f"Namespace: `{table['namespace']}`" in rendered["markdown"]
        for entry in table["entries"]:
            assert f"| {entry['key']} | {entry['source']} |" in rendered["markdown"], f"wrong string-table entry {entry['key']}"
    else:
        raise ValueError(f"unknown fixture kind: {case['kind']}")
    summary = rendered["summary"]
    version = B._read_summary(str(path)).saved_by_engine_version
    saved = f"{version.major}.{version.minor}.{version.patch}"
    assert saved.startswith(case["engine"] + "."), saved
    assert summary["parse_status"] == "ok" and not summary["issues"], summary["issues"]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    source = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cache = ROOT / ".cache" / "asset-fixtures" / source["commit"]
    files = {source["license"]["path"]: source["license"]}
    for case in source["cases"]:
        for key in ("asset", "oracle"):
            files[case[key]["path"]] = case[key]
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda item: fetch_file(source, item, cache), files.values()))
        B.ensure_uasset_read()
    except Exception as e:
        print(f"FAIL asset fixture setup: {type(e).__name__}: {e}", flush=True)
        return 2
    failed = 0
    for case in source["cases"]:
        try:
            check_case(case, cache)
            print(f"PASS asset {case['id']}", flush=True)
        except Exception as e:
            failed += 1
            print(f"FAIL asset {case['id']}: {type(e).__name__}: {e}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
