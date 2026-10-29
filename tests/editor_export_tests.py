"""Native editor oracle export (Q12): bridge independence, pinned bytes, partial failures, text source.

No engine and no editor are needed here. A fake ``unreal`` module stands in for the editor's Python
surface and fails the test the moment the exporter reaches for anything that could change a project,
so "it did not save anything" is checked rather than assumed. The compiled plugin is exercised by the
manager against real 5.7/5.8 installs; these checks cover the Python half and the agreed JSON shape.
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import export_editor_oracle as E

# Anything on this list would load, compile, scan or save, and none of it belongs in an oracle read.
MUTATORS = ("EditorAssetLibrary", "EditorLoadingAndSavingUtils", "BlueprintEditorLibrary",
            "EditorUtilityLibrary", "EditorLevelLibrary", "AssetToolsHelpers", "AssetRegistryHelpers",
            "EditorAssetSubsystem", "get_editor_subsystem", "save_asset", "save_package",
            "save_directory", "compile_blueprint", "load_object", "load_package", "load_class",
            "new_object", "set_editor_property", "duplicate_asset", "rename_asset", "delete_asset")
OK_CALLS = {"get_engine_version", "get_project_file_path", "load_asset", "capture_blueprint"}
MISSING = object()  # load_asset answers None for this asset


class LoadError(Exception):
    """load_asset itself fails for this asset."""


class FakeAsset:
    """A loaded asset handle. It carries no graph of its own: only the bridge reports one."""

    def __init__(self, path, response):
        self.path = path
        self.response = response


class FakeUnreal:
    """The editor's Python surface, narrowed to what a read-only oracle may touch."""

    def __init__(self, project, *, engine="5.8.4-41234567+++UE5+Release-5.8", responses=None,
                 bridge=True, system=True, paths=True, on_capture=None):
        self.project = Path(project)
        self.engine = engine
        self.responses = dict(responses or {})
        self.on_capture = on_capture
        self.calls = []
        if system:
            self.SystemLibrary = SimpleNamespace(get_engine_version=self._engine_version)
        if paths:
            self.Paths = SimpleNamespace(get_project_file_path=self._project_file_path,
                                         convert_relative_path_to_full=lambda value: str(value))
        if bridge is True:
            self.RepoReaderOracleLibrary = SimpleNamespace(capture_blueprint=self._capture)
        elif bridge == "not-callable":
            self.RepoReaderOracleLibrary = SimpleNamespace(capture_blueprint=None)

    def __getattr__(self, name):
        if name in MUTATORS:
            raise AssertionError(f"the exporter reached for the editor mutator unreal.{name}")
        raise AttributeError(name)

    def _engine_version(self):
        self.calls.append(("get_engine_version",))
        return self.engine

    def _project_file_path(self):
        self.calls.append(("get_project_file_path",))
        return str(self.project)

    def load_asset(self, path):
        self.calls.append(("load_asset", path))
        response = self.responses.get(path, MISSING)
        if response is MISSING:
            return None
        if isinstance(response, LoadError):
            raise response
        return FakeAsset(path, response)

    def _capture(self, asset):
        self.calls.append(("capture_blueprint", asset.path))
        if self.on_capture is not None:
            self.on_capture(asset.path)
        if isinstance(asset.response, BaseException):
            raise asset.response
        return asset.response

    def names(self):
        return [call[0] for call in self.calls]

    def read_calls(self):
        return [call for call in self.calls if call[0] in ("load_asset", "capture_blueprint")]


def _scratch():
    cache = Path(__file__).resolve().parent / ".cache"
    cache.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="editor-oracle-", dir=cache)


def pin_type(**overrides):
    record = {"category": "text", "subcategory": "", "object_path": None, "container": 0,
              "is_reference": False, "is_const": False, "is_weak_pointer": False,
              "terminal": {"category": "", "subcategory": "", "object_path": None,
                           "is_const": False, "is_weak_pointer": False}}
    record.update(overrides)
    return record


def pin(**overrides):
    record = {"guid": "0123456789ABCDEF0123456789ABCDEF", "name": "InText", "direction": 0,
              "type": pin_type(), "default_value": "", "auto_default_value": "",
              "default_object": None, "default_text_value": "", "hidden": False,
              "orphaned_pin": False, "not_connectable": False, "advanced_view": False, "links": []}
    record.update(overrides)
    return record


def snapshot(**overrides):
    """A contract-shaped snapshot, as the native bridge reports it: source text, saved package."""
    record = {"asset_class": "Blueprint", "text_values": "source", "package_dirty": False,
              "parent_class": "/Script/Engine.Actor", "variables": [], "function_graphs": [],
              "graphs": [], "widget_bindings": None, "issues": []}
    record.update(overrides)
    return record


def response(**overrides):
    return json.dumps(snapshot(**overrides), ensure_ascii=False)


def project(root, assets=("/Game/Blueprints/BP_Player",), *, name="Game"):
    """A project tree whose asset bytes are deliberately undecodable: only the bridge reports state."""
    root = Path(root)
    (root / "Content").mkdir(parents=True, exist_ok=True)
    uproject = root / f"{name}.uproject"
    uproject.write_text('{"EngineAssociation": "5.8"}', encoding="utf-8")
    for asset_path in assets:
        package = root / "Content" / (asset_path[len("/Game/"):] + ".uasset")
        package.parent.mkdir(parents=True, exist_ok=True)
        package.write_bytes(b"opaque package bytes for " + asset_path.encode("utf-8"))
    return uproject


def _previous_oracle(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"keep": "these exact bytes"}\n', encoding="utf-8")
    return path.read_bytes()


def test_editor_oracle_captures_requested_assets_in_order_with_pinned_bytes():
    with _scratch() as tmp:
        root = Path(tmp) / "프로젝트 with spaces"
        requested = ["/Game/청사진 모음/BP_플레이어", "/Game/Blueprints With Spaces/BP_Enemy"]
        uproject = project(root, requested)
        unreal = FakeUnreal(uproject, responses={path: response() for path in requested})
        out = Path(tmp) / "오라클 출력" / "oracle.json"

        record = E.export_oracle(str(out), requested, unreal_module=unreal)

        assert json.loads(out.read_text(encoding="utf-8")) == record, "the file and the return differ"
        assert record["schema_version"] == 1 and record["producer"] == "unreal-editor-native", record
        assert record["engine_version"] == unreal.engine, record
        assert record["project_file"] == uproject.resolve().as_posix(), record
        assert record["issues"] == [], record["issues"]
        assert [entry["asset_path"] for entry in record["assets"]] == requested, record["assets"]
        assert record["assets"][0]["package_file"] == "Content/청사진 모음/BP_플레이어.uasset"
        for entry in record["assets"]:
            package = root / entry["package_file"]
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            # The hashes pin the bytes that were on disk, not a value the exporter made up.
            assert entry["sha256_before"] == digest == entry["sha256_after"], entry
            assert entry["issues"] == [], entry
            assert entry["snapshot"]["text_values"] == "source", entry
        # Unicode survives the write as itself, not as an escape sequence.
        assert "청사진" in out.read_text(encoding="utf-8")
        assert b"\\u" not in out.read_bytes()


def test_editor_oracle_records_every_failure_without_dropping_an_asset():
    cases = (
        ("/Game/Fail/BP_Absent", MISSING, "load_asset returned nothing"),
        ("/Game/Fail/BP_LoadRaises", LoadError("the asset registry is still scanning"),
         "load_asset failed: LoadError"),
        ("/Game/Fail/BP_BridgeRaises", RuntimeError("Blueprint expected, got Object"),
         "the native bridge raised RuntimeError"),
        ("/Game/Fail/BP_Truncated", '{"asset_class": "Blueprint"', "not usable JSON"),
        ("/Game/Fail/BP_NonObject", '["asset_class", "Blueprint"]', "not an object"),
        ("/Game/Fail/BP_Duplicate", '{"asset_class": "Blueprint", "asset_class": "WidgetBlueprint"}',
         "duplicate key 'asset_class'"),
        ("/Game/Fail/BP_NotANumber", '{"asset_class": NaN}', "non-JSON constant NaN"),
        ("/Game/Fail/BP_Infinite", '{"asset_class": -Infinity}', "non-JSON constant -Infinity"),
        ("/Game/Fail/BP_Empty", "   ", "returned an empty response"),
        ("/Game/Fail/BP_NotAString", 17, "returned int, not a JSON string"),
        ("/Game/Good/BP_Fine", response(), None),
    )
    with _scratch() as tmp:
        root = Path(tmp) / "partial"
        requested = [path for path, _, _ in cases]
        uproject = project(root, requested)
        responses = {path: value for path, value, _ in cases if value is not MISSING}
        unreal = FakeUnreal(uproject, responses=responses)
        out = Path(tmp) / "oracle.json"

        record = E.export_oracle(out, requested, unreal_module=unreal)

        assert out.is_file(), "a partial oracle was not written at all"
        assert [entry["asset_path"] for entry in record["assets"]] == requested, "an asset was dropped"
        for (path, _, expected), entry in zip(cases, record["assets"]):
            if expected is None:
                assert isinstance(entry["snapshot"], dict) and entry["issues"] == [], entry
                continue
            assert entry["snapshot"] is None, f"{path}: a failed capture produced a snapshot anyway"
            assert any(expected in issue for issue in entry["issues"]), (path, expected, entry["issues"])
            assert all(path in issue for issue in entry["issues"]), (path, entry["issues"])
            # Even without a snapshot the bytes stay pinned, so the failure is attributable.
            assert len(entry["sha256_before"]) == 64 and entry["sha256_before"] == entry["sha256_after"]
        failed = [path for path, value, expected in cases if expected is not None]
        assert record["issues"], "the root record claimed a clean run over failed captures"
        assert f"{len(failed)} of {len(cases)} requested assets produced no snapshot" in record["issues"][0]
        for path in failed:
            assert path in record["issues"][0], path
        assert unreal.names().count("load_asset") == len(cases), unreal.calls


def test_editor_oracle_refuses_bad_configuration_before_reading_or_replacing_anything():
    with _scratch() as tmp:
        root = Path(tmp) / "refusals"
        good = "/Game/Blueprints/BP_Player"
        uproject = project(root, [good])
        responses = {good: response()}
        out = Path(tmp) / "oracle.json"
        directory = Path(tmp) / "directory.json"
        directory.mkdir()

        cases = (
            ("engine below the supported floor", {"engine": "5.6.2-1+++UE5+Release-5.6"}, [good], out),
            ("engine version without a minor", {"engine": "5"}, [good], out),
            ("engine version empty", {"engine": "  "}, [good], out),
            ("engine version not a string", {"engine": 5.8}, [good], out),
            ("no SystemLibrary", {"system": False}, [good], out),
            ("no Paths", {"paths": False}, [good], out),
            ("bridge plugin absent", {"bridge": False}, [good], out),
            ("bridge not callable", {"bridge": "not-callable"}, [good], out),
            ("duplicate request", {}, [good, good], out),
            ("unmounted root", {}, ["/Engine/Blueprints/BP_Player"], out),
            ("script path", {}, ["/Script/Engine.Actor"], out),
            ("directory traversal", {}, ["/Game/../../secrets/BP_Player"], out),
            ("object path", {}, ["/Game/Blueprints/BP_Player.BP_Player"], out),
            ("empty segment", {}, ["/Game//BP_Player"], out),
            ("padded path", {}, ["/Game/Blueprints/BP_Player "], out),
            ("leading space path", {}, [" /Game/Blueprints/BP_Player"], out),
            ("backslash path", {}, ["/Game/Blueprints\\BP_Player"], out),
            ("control character", {}, ["/Game/Blueprints/BP_Pla\nyer"], out),
            ("path not a string", {}, [b"/Game/Blueprints/BP_Player"], out),
            ("no requests", {}, [], out),
            ("a bare string of requests", {}, good, out),
            ("output not json", {}, [good], Path(tmp) / "oracle.txt"),
            ("output suffixless", {}, [good], Path(tmp) / "oracle"),
            ("output inside Content", {}, [good], root / "Content" / "oracle.json"),
            ("output is the content root", {}, [good], root / "Content"),
            ("output relative", {}, [good], Path("oracle.json")),
            ("output is a directory", {}, [good], directory),
            ("output is bytes", {}, [good], b"oracle.json"),
        )
        for name, kwargs, paths, destination in cases:
            before = _previous_oracle(out)
            unreal = FakeUnreal(uproject, responses=responses, **kwargs)
            try:
                E.export_oracle(destination, paths, unreal_module=unreal)
            except E.OracleConfigError as error:
                assert str(error).strip(), f"{name}: refused without saying why"
            else:
                raise AssertionError(f"{name}: an unusable configuration was accepted")
            assert out.read_bytes() == before, f"{name}: an earlier oracle was replaced by a refusal"
            assert unreal.read_calls() == [], f"{name}: assets were read before the refusal: {unreal.calls}"

        # The same project and request succeed once the destination is usable: the refusals above are
        # about the configuration, not about an exporter that can never run.
        unreal = FakeUnreal(uproject, responses=responses)
        record = E.export_oracle(out, [good], unreal_module=unreal)
        assert record["assets"][0]["snapshot"]["asset_class"] == "Blueprint", record
        assert out.read_bytes() != before, "an accepted run did not replace the earlier oracle"


def test_editor_oracle_reports_package_bytes_that_changed_during_a_capture():
    with _scratch() as tmp:
        root = Path(tmp) / "dirtied"
        requested = ["/Game/Blueprints/BP_Dirty", "/Game/Blueprints/BP_Clean"]
        uproject = project(root, requested)

        def dirty(asset_path):
            # Stands in for a bridge that resaved or re-serialized the package while reading it.
            if asset_path.endswith("BP_Dirty"):
                package = root / "Content" / (asset_path[len("/Game/"):] + ".uasset")
                package.write_bytes(package.read_bytes() + b" touched")

        unreal = FakeUnreal(uproject, responses={path: response() for path in requested},
                            on_capture=dirty)
        out = Path(tmp) / "oracle.json"

        record = E.export_oracle(out, requested, unreal_module=unreal)

        dirtied, clean = record["assets"]
        assert dirtied["sha256_before"] != dirtied["sha256_after"], dirtied
        assert any("changed during the capture" in issue for issue in dirtied["issues"]), dirtied
        assert any("not a read-only observation" in issue for issue in dirtied["issues"]), dirtied
        # The snapshot is still reported: what the editor said is observed truth, the mutation is a warning.
        assert isinstance(dirtied["snapshot"], dict), dirtied
        assert any("package bytes changed while capturing" in issue for issue in record["issues"])
        assert requested[0] in record["issues"][0] and requested[1] not in record["issues"][0]
        assert clean["issues"] == [] and clean["sha256_before"] == clean["sha256_after"], clean


def test_editor_oracle_will_not_read_a_dirty_package_as_the_saved_asset():
    with _scratch() as tmp:
        root = Path(tmp) / "unsaved"
        stored = "/Game/Blueprints/BP_Stored"
        unsaved = "/Game/Blueprints/BP_Unsaved"
        absent = "/Game/Blueprints/BP_NoFlag"
        mistyped = "/Game/Blueprints/BP_StringFlag"
        numeric = "/Game/Blueprints/BP_NumericFlag"
        requested = [stored, unsaved, absent, mistyped, numeric]
        uproject = project(root, requested)
        without = snapshot()
        without.pop("package_dirty")
        unreal = FakeUnreal(uproject, responses={
            stored: response(),
            unsaved: response(package_dirty=True),
            absent: json.dumps(without, ensure_ascii=False),
            mistyped: response(package_dirty="false"),
            numeric: response(package_dirty=1),
        })
        out = Path(tmp) / "oracle.json"

        record = E.export_oracle(out, requested, unreal_module=unreal)
        saved, dirty, missing, wrong_type, wrong_number = record["assets"]

        # An editor holding unsaved edits leaves the file's bytes alone, so the hashes agree even for
        # the dirty asset. Only package_dirty tells the two apart, which is the point of reading it.
        for entry in record["assets"]:
            assert entry["sha256_before"] == entry["sha256_after"], entry
            assert not any("changed during the capture" in issue for issue in entry["issues"]), entry
        assert saved["issues"] == [], saved["issues"]

        assert any("holding unsaved changes" in issue for issue in dirty["issues"]), dirty["issues"]
        assert any("not the saved file's state" in issue for issue in dirty["issues"]), dirty["issues"]
        assert any("hashes do not vouch for it" in issue for issue in dirty["issues"]), dirty["issues"]
        # The capture is kept: it is a true reading of the editor, just not of the saved package.
        assert isinstance(dirty["snapshot"], dict), dirty

        assert any("missing package_dirty" in issue for issue in missing["issues"]), missing["issues"]
        assert not any("not a bool" in issue for issue in missing["issues"]), missing["issues"]
        for entry, shown in ((wrong_type, "'false'"), (wrong_number, "1")):
            assert any(f"package_dirty={shown}" in issue and "not a bool" in issue
                       for issue in entry["issues"]), entry["issues"]

        # One root line names every record that cannot stand for the saved package, and only those.
        unaccounted = [issue for issue in record["issues"]
                       if "cannot be read as the saved package" in issue]
        assert len(unaccounted) == 1, record["issues"]
        for path in (unsaved, absent, mistyped, numeric):
            assert path in unaccounted[0], (path, unaccounted[0])
        assert stored not in unaccounted[0], unaccounted[0]


def test_editor_oracle_pins_nothing_it_cannot_read_but_still_captures_the_asset():
    with _scratch() as tmp:
        root = Path(tmp) / "unpinned"
        present = "/Game/Blueprints/BP_Present"
        absent = "/Game/Blueprints/BP_NoPackage"
        folder = "/Game/Blueprints/BP_IsAFolder"
        uproject = project(root, [present])
        (root / "Content" / "Blueprints" / "BP_IsAFolder.uasset").mkdir(parents=True)
        requested = [present, absent, folder]
        unreal = FakeUnreal(uproject, responses={path: response() for path in requested})
        out = Path(tmp) / "oracle.json"

        record = E.export_oracle(out, requested, unreal_module=unreal)

        pinned, missing, directory = record["assets"]
        assert len(pinned["sha256_before"]) == 64 and pinned["issues"] == [], pinned
        for entry, expected in ((missing, "is not a readable file under the project"),
                                (directory, "is not a readable file under the project")):
            assert entry["sha256_before"] is None and entry["sha256_after"] is None, entry
            assert any(expected in issue for issue in entry["issues"]), entry
            assert any("not pinned" in issue for issue in entry["issues"]), entry
            # Unpinnable bytes do not cost us the native reading, and do not drop the request either.
            assert isinstance(entry["snapshot"], dict), entry
        assert [entry["asset_path"] for entry in record["assets"]] == requested


def test_editor_oracle_preserves_native_text_source_and_flags_display_text():
    # An ordinary empty source string, non-ASCII, newlines, tabs, quotes, a backslash, a trailing
    # space and a literal no-break space plus zero-width space (deliberately invisible in this
    # source): all of it is the author's text, and all of it has to come back unchanged.
    exact = ["", "한글 source", "line one\nline two\twith a tab", ' "quoted" \\ backslash ',
             "trailing space ", " nbsp​"]
    with _scratch() as tmp:
        root = Path(tmp) / "text"
        requested = ["/Game/Text/BP_Source", "/Game/Text/BP_Display", "/Game/Text/BP_Undeclared",
                     "/Game/Text/BP_NativeIssues"]
        uproject = project(root, requested)
        pins = [pin(name=f"In{index}", default_text_value=value) for index, value in enumerate(exact)]
        pins.append(pin(name="Greeting", default_text_value="Hello"))
        pins.append(pin(name="NoSource", default_text_value=None))
        graphs = [{"object_path": "/Game/Text/BP_Source.BP_Source:EventGraph", "name": "EventGraph",
                   "nodes": [{"object_path": "/Game/Text/BP_Source.BP_Source:EventGraph.K2Node_0",
                              "class": "K2Node_CallFunction", "guid": "A" * 32, "pins": pins,
                              "function_metadata": None}]}]
        # The same Greeting pin as a Korean-culture editor would render it. A project whose source text
        # is "Hello" must never be compared against this, which is why display text carries a warning.
        localized = [{"object_path": "/Game/Text/BP_Display.BP_Display:EventGraph", "name": "EventGraph",
                      "nodes": [{"object_path": "/Game/Text/BP_Display.BP_Display:EventGraph.K2Node_0",
                                 "class": "K2Node_CallFunction", "guid": "B" * 32,
                                 "pins": [pin(name="Greeting", default_text_value="안녕하세요")],
                                 "function_metadata": None}]}]
        declared = snapshot(graphs=graphs)
        undeclared = snapshot(graphs=graphs)
        undeclared.pop("text_values")
        responses = {
            requested[0]: json.dumps(declared, ensure_ascii=False),
            requested[1]: json.dumps(snapshot(graphs=localized, text_values="display"),
                                     ensure_ascii=False),
            requested[2]: json.dumps(undeclared, ensure_ascii=False),
            requested[3]: response(issues=["pin 'Msg' of node 'K2Node_1': text field "
                                           "'default_text_value' has no source string"]),
        }
        unreal = FakeUnreal(uproject, responses=responses)
        out = Path(tmp) / "oracle.json"

        record = E.export_oracle(out, requested, unreal_module=unreal)
        written = json.loads(out.read_text(encoding="utf-8"))["assets"]

        source, display, undeclared_record, native = written
        captured = source["snapshot"]["graphs"][0]["nodes"][0]["pins"]
        # Every source string, including the ordinary empty one, survives the round trip unchanged.
        assert [entry["default_text_value"] for entry in captured[:len(exact)]] == exact, captured
        assert captured[0]["default_text_value"] == "", "an empty source string became something else"
        assert captured[-1]["default_text_value"] is None, "an absent source string became a string"
        assert source["issues"] == [], source["issues"]

        assert captured[len(exact)]["default_text_value"] == "Hello", captured[len(exact)]

        assert any("text_values='display'" in issue for issue in display["issues"]), display["issues"]
        assert any("not authored source text" in issue for issue in display["issues"]), display["issues"]
        assert isinstance(display["snapshot"], dict), "a display-text snapshot was discarded"
        # Culture-rendered text reaches the record only with the warning attached: the same pin reads
        # "Hello" as source and "안녕하세요" as display, and nothing here lets the latter pass as source.
        rendered = display["snapshot"]["graphs"][0]["nodes"][0]["pins"][0]
        assert rendered["name"] == "Greeting" and rendered["default_text_value"] == "안녕하세요", rendered
        assert rendered["default_text_value"] != captured[len(exact)]["default_text_value"]

        assert any("missing text_values" in issue for issue in undeclared_record["issues"]), \
            undeclared_record["issues"]

        # Issues the native side reported about its own reads reach the record instead of staying there.
        assert any("native capture reported:" in issue and "no source string" in issue
                   for issue in native["issues"]), native["issues"]


def test_editor_oracle_touches_no_editor_mutators_and_shares_no_reader_code():
    with _scratch() as tmp:
        root = Path(tmp) / "independence"
        requested = ["/Game/Blueprints/BP_Player"]
        uproject = project(root, requested)
        unreal = FakeUnreal(uproject, responses={requested[0]: response()})

        E.export_oracle(Path(tmp) / "oracle.json", requested, unreal_module=unreal)

        assert set(unreal.names()) <= OK_CALLS, f"the exporter called more than it needs: {unreal.calls}"
        assert unreal.names().count("capture_blueprint") == 1, unreal.calls
        # The guard above only means something if the fake would actually object.
        for name in MUTATORS:
            try:
                getattr(unreal, name)
            except AssertionError:
                continue
            raise AssertionError(f"the fake editor failed to guard unreal.{name}")

        # The oracle is only an oracle if it decodes nothing of its own: no reader, no parser, no shell.
        source = Path(E.__file__).read_text(encoding="utf-8")
        for borrowed in ("bp_reader", "data_reader", "map_reader", "ue_repo_digest", "uasset_read",
                         "project_support", "navigation", "subprocess", "shutil"):
            assert f"import {borrowed}" not in source, f"the exporter imported {borrowed}"
            assert f"from {borrowed}" not in source, f"the exporter imported from {borrowed}"


def test_editor_oracle_write_failure_keeps_the_previous_oracle_and_leaves_no_debris():
    with _scratch() as tmp:
        root = Path(tmp) / "atomic"
        requested = ["/Game/Blueprints/BP_Player"]
        uproject = project(root, requested)
        unreal = FakeUnreal(uproject, responses={requested[0]: response()})
        out = Path(tmp) / "output" / "oracle.json"
        before = _previous_oracle(out)

        with patch.object(E.os, "replace", side_effect=OSError("no space left on device")):
            try:
                E.export_oracle(out, requested, unreal_module=unreal)
            except OSError:
                pass
            else:
                raise AssertionError("a failed write was reported as a successful export")

        assert out.read_bytes() == before, "a failed write damaged the earlier oracle"
        assert list(out.parent.glob("*.tmp")) == [], "a temporary file was left behind"
        assert sorted(path.name for path in out.parent.iterdir()) == ["oracle.json"]
