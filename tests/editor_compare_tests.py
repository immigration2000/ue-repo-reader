"""Independent, hand-authored native observations and adversarial comparison cases."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import compare_editor_oracle as C


def test_editor_oracle_absolute_import_paths_are_not_prefixed_twice():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import bp_reader as B
    ctx = object.__new__(B.Ctx)
    imported = SimpleNamespace(object_name="/Script/Engine.Default__KismetSystemLibrary",
                               get_full_name=lambda: "/Script/CoreUObject./Script/Engine.Default__KismetSystemLibrary")
    assert ctx.full_name(imported) == "/Script/Engine.Default__KismetSystemLibrary"
    package = SimpleNamespace(object_name="/Script/Engine", outer=SimpleNamespace(object_name="/Script/CoreUObject"))
    child = SimpleNamespace(object_name="Actor", outer=package,
                            get_full_name=lambda: "/Script/CoreUObject./Script/Engine.Actor")
    assert ctx.full_name(child) == "/Script/Engine.Actor"
    short = SimpleNamespace(object_name="BP.Child", get_full_name=lambda: "/Game/BP.BP.Child")
    assert ctx.full_name(short) == "/Game/BP.BP.Child"


def snapshot():
    # Display GUID word conversion must not be replaced by punctuation stripping.
    a, b = "0102030405060708090a0b0c0d0e0f10", "ffeeddccbbaa99887766554433221100"
    t = {"category": "exec", "subcategory": "None", "object_path": None, "container": 0,
         "is_reference": False, "is_const": False, "is_weak_pointer": False,
         "terminal": {"category": "None", "subcategory": "None", "object_path": None,
                      "is_const": False, "is_weak_pointer": False}}
    def pin(guid, name, direction, owner, target):
        return {"guid": guid, "name": name, "direction": direction, "type": copy.deepcopy(t),
                "default_value": "", "auto_default_value": "", "default_object": None,
                "default_text_value": "설명\n`literal`", "hidden": False, "orphaned_pin": False,
                "not_connectable": False, "advanced_view": False,
                "links": [{"owner_path": owner, "guid": target}]}
    base = "/Game/한국어/BP.BP:EventGraph"
    nodes = [{"object_path": base + ".Branch", "class": "K2Node_IfThenElse", "guid": "unused",
              "pins": [pin(a, "then", 1, base + ".Call", b)], "function_metadata": None},
             {"object_path": base + ".Call", "class": "K2Node_CallFunction", "guid": "unused2",
              "pins": [pin(b, "execute", 0, base + ".Branch", a)], "function_metadata": None}]
    return {"asset_class": "Blueprint", "text_values": "source", "package_dirty": False,
            "parent_class": "/Script/Engine.Actor", "variables": [],
            "function_graphs": [], "graphs": [{"object_path": base, "name": "EventGraph", "nodes": nodes}],
            "widget_bindings": None, "issues": []}


def test_editor_compare_word_order_owner_scope_and_order_independence():
    assert C.display_guid_to_serialized("0102030405060708090a0b0c0d0e0f10") == "04030201080706050c0b0a09100f0e0d"
    want, got = snapshot(), snapshot()
    got["graphs"][0]["nodes"].reverse()
    got["graphs"][0]["nodes"][0]["pins"][0]["type"]["category"] = "Exec"
    got["graphs"][0]["nodes"][0]["object_path"] = got["graphs"][0]["nodes"][0]["object_path"].replace(":", ".")
    result = C.compare_snapshots(want, got)
    assert result["checked"] > 25 and not result["mismatches"] and not result["unavailable"], result
    got["graphs"][0]["nodes"][0]["pins"][0]["links"][0]["owner_path"] += "WrongOwner"
    assert C.compare_snapshots(want, got)["mismatches"], "same pin GUID on wrong owner accepted"


def test_editor_compare_semantic_mutations_and_loss_are_visible():
    expected = snapshot()
    def first(value):
        return value["graphs"][0]["nodes"][0]["pins"][0]
    mutations = [lambda x: first(x).__setitem__("default_text_value", "wrong"),
                 lambda x: first(x).__setitem__("direction", 0),
                 lambda x: first(x).__setitem__("hidden", True),
                 lambda x: first(x).__setitem__("default_object", "/Game/Wrong.Wrong"),
                 lambda x: first(x)["type"].__setitem__("category", "bool"),
                 lambda x: first(x).__setitem__("links", []),
                 lambda x: first(x)["links"].append(copy.deepcopy(first(x)["links"][0])),
                 lambda x: x["graphs"][0]["nodes"].pop(),
                 lambda x: x["graphs"][0]["nodes"][0]["pins"].clear(),
                 lambda x: x["graphs"][0]["nodes"][0].__setitem__("class", "K2Node_Knot")]
    for mutate in mutations:
        actual = copy.deepcopy(expected)
        mutate(actual)
        result = C.compare_snapshots(expected, actual)
        assert result["mismatches"], mutate


def test_editor_compare_unknown_never_becomes_default_or_success():
    actual = snapshot()
    actual["graphs"][0]["nodes"][0]["pins"][0]["default_value"] = C.unknown("not decoded")
    result = C.compare_snapshots(snapshot(), actual)
    assert result["unavailable"] and not result["mismatches"], result
    actual["graphs"][0]["nodes"][0]["pins"][0]["links"] = C.unknown("ambiguous target")
    assert len(C.compare_snapshots(snapshot(), actual)["unavailable"]) == 2
    actual["graphs"][0]["nodes"][0]["pins"][0]["default_value"] = {"status": "unknown", "reason": "not exposed by decoder"}
    result = C.compare_snapshots(snapshot(), actual)
    assert len(result["unavailable"]) == 2 and not result["mismatches"], "IR unknown was mislabeled as a wrong value"
    expected, decoded = snapshot(), snapshot()
    expected["variables"] = [{"name": "Map", "type": copy.deepcopy(expected["graphs"][0]["nodes"][0]["pins"][0]["type"]),
                              "flags": "0", "category": "", "default_value": ""}]
    decoded["variables"] = copy.deepcopy(expected["variables"])
    decoded["variables"][0]["type"] = C.unknown("opaque native type blob")
    result = C.compare_snapshots(expected, decoded)
    assert result["unavailable"] and not result["mismatches"], "opaque declaration fabricated an empty map terminal"


def test_editor_compare_duplicate_and_malformed_identity_refused():
    for kind in ("graph", "node", "pin"):
        actual = snapshot()
        records = (actual["graphs"] if kind == "graph" else actual["graphs"][0]["nodes"] if kind == "node"
                   else actual["graphs"][0]["nodes"][0]["pins"])
        records.append(copy.deepcopy(records[0]))
        try:
            C.compare_snapshots(snapshot(), actual)
        except C.OracleError:
            pass
        else:
            raise AssertionError(f"duplicate {kind} was overwritten")
    for guid in ("0" * 32, "not-a-guid", True, None):
        try:
            C.display_guid_to_serialized(guid)
        except C.OracleError:
            pass
        else:
            raise AssertionError("invalid pin identity accepted")


def fixture(root):
    source = root / "Content/한국어/BP.uasset"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"independent bytes; not a real Unreal package")
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    asset = {"asset_path": "/Game/한국어/BP", "package_file": "Content/한국어/BP.uasset", "sha256_before": sha,
             "sha256_after": sha, "snapshot": snapshot(), "issues": []}
    return {"schema_version": 1, "producer": "unreal-editor-native", "engine_version": "5.8.4-test",
            "project_file": "D:/different machine/Project.uproject", "assets": [asset], "issues": []}, source


def test_editor_compare_hash_binding_and_binary_read_race():
    with tempfile.TemporaryDirectory(prefix="oracle-한글 ") as tmp:
        root = Path(tmp)
        oracle, source = fixture(root)
        read = lambda *_: snapshot()
        assert C.compare_oracle(oracle, root, reader=read)["status"] == "passed"
        oracle["assets"][0]["sha256_after"] = "f" * 64
        calls = []
        report = C.compare_oracle(oracle, root, reader=lambda *args: calls.append(args))
        assert report["status"] == "incomplete" and not calls, report
        oracle["assets"][0]["sha256_after"] = oracle["assets"][0]["sha256_before"]
        def racing_reader(*_):
            source.write_bytes(b"changed while decoding")
            return snapshot()
        report = C.compare_oracle(oracle, root, reader=racing_reader)
        assert report["status"] == "incomplete" and report["assets"][0]["unavailable"], report


def test_editor_compare_provenance_partial_and_empty_inputs_fail_closed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        baseline, _ = fixture(root)
        for field, value in (("schema_version", True), ("producer", "ue-repo-reader digest"), ("engine_version", "4.27.0"),
                             ("project_file", None), ("issues", "ignored"), ("assets", [])):
            oracle = copy.deepcopy(baseline)
            oracle[field] = value
            try:
                C.compare_oracle(oracle, root, reader=lambda *_: snapshot())
            except C.OracleError:
                pass
            else:
                raise AssertionError((field, value))
        for root_issue, asset_issue, native in ((["capture gap"], [], snapshot()), ([], ["load failed"], None)):
            oracle = copy.deepcopy(baseline)
            oracle["issues"] = root_issue
            oracle["assets"][0].update(issues=asset_issue, snapshot=native)
            assert C.compare_oracle(oracle, root, reader=lambda *_: snapshot())["status"] == "incomplete"


def test_editor_compare_paths_and_strict_json_cannot_hide_gaps():
    for text in ('[]', '{"x":NaN}', '{"x":{"a":1,"a":2}}', '{"schema_version":1,"schema_version":2}'):
        try:
            C.load_json(text)
        except C.OracleError:
            pass
        else:
            raise AssertionError(text)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        oracle, _ = fixture(root)
        for bad in ("/Game/../Outside", "/Game/A\\B", "/Game/A.B", "/Other/BP", "/Game//BP"):
            record = copy.deepcopy(oracle)
            record["assets"][0]["asset_path"] = bad
            calls = []
            report = C.compare_oracle(record, root, reader=lambda *args: calls.append(args))
            assert report["status"] == "incomplete" and not calls, bad


def test_editor_compare_dirty_display_text_and_profile_exclusions_are_explicit():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        oracle, _ = fixture(root)
        for state in (True, None, 0):
            native = copy.deepcopy(oracle)
            native["assets"][0]["snapshot"]["package_dirty"] = state
            assert C.compare_oracle(native, root, reader=lambda *_: snapshot(), profile="graph")["status"] == "incomplete"
        native = copy.deepcopy(oracle)
        native["assets"][0]["snapshot"]["text_values"] = "display"
        assert C.compare_oracle(native, root, reader=lambda *_: snapshot())["status"] == "incomplete"
        actual = snapshot()
        actual["parent_class"] = C.unknown("parent not available")
        full = C.compare_oracle(oracle, root, reader=lambda *_: actual)
        graph = C.compare_oracle(oracle, root, reader=lambda *_: actual, profile="graph")
        assert full["status"] == "incomplete" and graph["status"] == "passed"
        assert graph["profile"] == "graph" and any("parent" in text for text in graph["exclusions"])


def test_editor_compare_partial_assets_keep_other_results_and_metadata_still_compares():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        oracle, _ = fixture(root)
        bad = copy.deepcopy(oracle["assets"][0])
        bad["asset_path"] = "/Game/Missing"
        bad["package_file"] = "Content/Missing.uasset"
        bad["sha256_before"] = None
        oracle["assets"].append(bad)
        result = C.compare_oracle(oracle, root, reader=lambda *_: snapshot())
        assert result["status"] == "incomplete" and result["assets"][0]["checked"] > 0
        assert result["assets"][1]["checked"] == 0 and result["assets"][1]["unavailable"]
        expected, actual = snapshot(), snapshot()
        expected["graphs"][0]["nodes"][0]["function_metadata"] = {"tooltip": "authored", "category": "", "call_in_editor": True}
        actual["graphs"][0]["nodes"][0]["function_metadata"] = {"tooltip": "wrong", "category": C.unknown("not stored"), "call_in_editor": True}
        compared = C.compare_snapshots(expected, actual)
        assert compared["mismatches"] and compared["unavailable"], "unknown metadata suppressed the real text comparison"
        empty = snapshot()
        empty["graphs"] = []
        compared = C.compare_snapshots(empty, empty, profile="graph")
        assert compared["checked"] == 0 and compared["unavailable"], "asset class alone passed the graph profile"


def test_native_replay_rejects_wrong_values_and_new_gaps():
    from editor_oracle_regress import check_capture
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        oracle, package = fixture(root)
        oracle["fixture_source"] = {"repository": "independent/test", "commit": "a" * 40}
        oracle["known_reader_gaps"] = []
        saved = root / "oracle.json"
        saved.write_text(json.dumps(oracle), encoding="utf-8")
        actual = snapshot()
        with patch.object(C, "read_snapshot", return_value=actual):
            check_capture(saved, package, repository="independent/test", commit="a" * 40)
            actual["graphs"][0]["nodes"][0]["pins"][0]["links"] = []
            try:
                check_capture(saved, package, repository="independent/test", commit="a" * 40)
            except AssertionError:
                pass
            else:
                raise AssertionError("wrong binary links passed the native fixture replay")
            actual = snapshot()
        actual["graphs"][0]["nodes"][0]["pins"][0]["default_value"] = C.unknown("new gap")
        with patch.object(C, "read_snapshot", return_value=actual):
            try:
                check_capture(saved, package, repository="independent/test", commit="a" * 40)
            except AssertionError:
                pass
            else:
                raise AssertionError("new missing observation was accepted under a pinned baseline")
