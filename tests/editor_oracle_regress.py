"""Editor-free replay of immutable, independently captured native observations."""
from collections import Counter
import hashlib
import json
import re
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import compare_editor_oracle as C


def check_capture(capture_file, package, *, repository, commit):
    oracle = C.load_json(Path(capture_file).read_text(encoding="utf-8"))
    assert oracle["schema_version"] == 1 and type(oracle["schema_version"]) is int
    assert oracle["producer"] == "unreal-editor-native" and oracle["issues"] == []
    version = re.match(r"(\d+)\.(\d+)\.", str(oracle.get("engine_version", "")))
    assert version and tuple(map(int, version.groups())) >= (5, 7), "native engine provenance is missing or below target"
    assert isinstance(oracle.get("project_file"), str) and oracle["project_file"].endswith(".uproject")
    assert oracle["fixture_source"]["repository"] == repository
    assert oracle["fixture_source"]["commit"] == commit
    assert len(oracle["assets"]) == 1, "fixture scope changed"
    record = oracle["assets"][0]
    assert record["issues"] == [] and record["snapshot"]["issues"] == []
    before = hashlib.sha256(Path(package).read_bytes()).hexdigest()
    assert record["sha256_before"] == record["sha256_after"] == before, "native oracle/package hash mismatch"
    actual = C.read_snapshot(package, record["asset_path"], native_class=record["snapshot"]["asset_class"])
    assert hashlib.sha256(Path(package).read_bytes()).hexdigest() == before, "package changed during oracle replay"
    assert not actual.get("issues"), "decoder reported gaps during native oracle replay"
    graph = C.compare_snapshots(record["snapshot"], actual, profile="graph")
    assert graph["checked"] > 0 and not graph["mismatches"] and not graph["unavailable"], graph
    full = C.compare_snapshots(record["snapshot"], actual)
    assert not full["mismatches"], full["mismatches"]
    known = oracle["known_reader_gaps"]
    assert isinstance(known, list) and all(set(i) == {"path", "reason"} and all(isinstance(v, str) for v in i.values()) for i in known)
    key = lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True)
    assert Counter(map(key, full["unavailable"])) == Counter(map(key, known)), "native comparison gaps changed; inspect rather than silently widen the baseline"
    return graph, full


def check_shed(case, fixture_cache, source):
    capture = ROOT / "tests/editor_oracles" / (case["id"] + ".json")
    oracle = C.load_json(capture.read_text(encoding="utf-8"))
    assert oracle["fixture_source"]["asset"] == case["asset"]
    assert oracle["fixture_source"]["license"] == source["license"]
    assert oracle["engine_version"].startswith(case["engine"] + "."), "wrong editor minor for native fixture"
    return check_capture(capture, Path(fixture_cache) / case["asset"]["path"], repository=source["repository"], commit=source["commit"])


def check_eg(project, commit):
    capture = ROOT / "tests/editor_oracles/eg-bfl-util.json"
    oracle = C.load_json(capture.read_text(encoding="utf-8"))
    package = oracle["fixture_source"]["package_file"]
    assert oracle["engine_version"].startswith("5.8."), "wrong eg native editor provenance"
    assert package == "Content/DeltaForce/Blueprints/Core/BFL_Util.uasset"
    check_git_blob(project, commit, package, oracle["fixture_source"]["git_blob"])
    return check_capture(capture, Path(project) / package, repository="immigration2000/ExtractionGame_Fin", commit=commit)


def check_git_blob(project, commit, package, expected):
    actual = subprocess.run(["git", "-C", str(project), "rev-parse", commit + ":" + package],
                            check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()
    assert actual == expected, "native fixture source Git blob does not match the pinned commit/path"


def check_eg_declarations(project, commit):
    """Native scalar/object/text, struct array and map-value declarations, not reader-made expectations."""
    results = []
    for name in ("bpc-inventorysystem", "pda-stash", "wbp-keybtn", "wbp-playerinventory", "bp-knife"):
        capture = ROOT / "tests/editor_oracles" / ("eg-" + name + ".json")
        oracle = C.load_json(capture.read_text(encoding="utf-8"))
        assert oracle["engine_version"].startswith("5.8.")
        package = oracle["fixture_source"]["package_file"]
        assert oracle["assets"][0]["package_file"] == package
        check_git_blob(project, commit, package, oracle["fixture_source"]["git_blob"])
        graph, full = check_capture(capture, Path(project) / package,
                                    repository="immigration2000/ExtractionGame_Fin", commit=commit)
        results.append((name, graph, full))
    return results
