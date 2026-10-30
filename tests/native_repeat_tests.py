"""Hand-authored native repeat observations and adversarial cases for the repeat audit.

Every capture here is written by hand as a native editor observation. No digest, reader
output or exporter output is used as either side, and a difference the audit records is
treated as an observation only, never as a verdict about the binary reader or the engine.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile

_ROOT = Path(__file__).resolve().parent.parent
for _directory in (_ROOT / "tools", _ROOT / "tests"):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))
import compare_editor_oracle as C
import compare_native_repeats as R
from editor_compare_tests import snapshot

SHA = "a1" * 32
OTHER_SHA = "b2" * 32
ASSET = "/Game/한국어/BP"


def observation():
    """One hand-authored native snapshot with declarations as well as a graph."""
    native = snapshot()
    kind = copy.deepcopy(native["graphs"][0]["nodes"][0]["pins"][0]["type"])
    native["variables"] = [{"name": "Health", "type": copy.deepcopy(kind), "flags": "4",
                            "category": "Stats", "default_value": "100"},
                           {"name": "Ammo", "type": copy.deepcopy(kind), "flags": "0",
                            "category": "", "default_value": ""}]
    native["function_graphs"] = ["/Game/한국어/BP.BP:Reload", "/Game/한국어/BP.BP:Fire"]
    return native


def asset(asset_path=ASSET, native=None, sha=SHA):
    return {"asset_path": asset_path,
            "package_file": "Content/" + asset_path[len("/Game/"):] + ".uasset",
            "sha256_before": sha, "sha256_after": sha,
            "snapshot": observation() if native is None else native, "issues": []}


def capture(assets=None):
    return {"schema_version": 1, "producer": "unreal-editor-native", "engine_version": "5.8.4-test",
            "project_file": "D:/repeat audit/Project.uproject", "issues": [],
            "assets": [asset()] if assets is None else assets}


def refused(left, right, context):
    try:
        R.audit_repeats(left, right)
    except C.OracleError:
        return
    raise AssertionError(f"malformed repeat input accepted: {context}")


def test_native_repeats_identical_clean_capture_is_stable_under_reordering():
    left, right = capture(), capture()
    native = right["assets"][0]["snapshot"]
    native["graphs"][0]["nodes"].reverse()
    native["variables"].reverse()
    native["function_graphs"].reverse()
    native["graphs"][0]["nodes"][0]["pins"][0]["links"].reverse()
    report = R.audit_repeats(left, right)
    assert report["status"] == "stable" and report["checked"] > 25, report
    assert not report["issues"] and len(report["assets"]) == 1
    assert not report["assets"][0]["mismatches"] and not report["assets"][0]["unavailable"]
    assert report["schema_version"] == 1 and report["exclusions"] == C.EXCLUSIONS
    assert "native" in report["scope"] and "no package bytes are read" in report["basis"]
    assert "observation" in report["caveat"] and "load-time fixup" in report["caveat"]
    assert set(report) == {"schema_version", "status", "engine_version", "project_file", "scope",
                           "basis", "caveat", "exclusions", "issues", "assets", "checked"}, report
    assert set(report["assets"][0]) == {"asset_path", "checked", "mismatches", "unavailable"}
    # A metadata-only repeat is still a compared repeat; an empty asset set never is.
    for side in (left, right):
        side["assets"][0]["snapshot"]["graphs"] = []
    thin = R.audit_repeats(left, right)
    assert thin["status"] == "stable" and thin["checked"] > 0, thin
    refused(capture([]), capture([]), "empty asset set")


def test_native_repeats_scalar_guid_and_hidden_changes_are_retained():
    def pin(side):
        return side["assets"][0]["snapshot"]["graphs"][0]["nodes"][0]["pins"][0]
    left = capture()
    for mutate in (lambda p: p.__setitem__("default_value", "wrong"),
                   lambda p: p.__setitem__("hidden", True),
                   lambda p: p.__setitem__("guid", "0f0e0d0c0b0a09080706050403020100"),
                   lambda p: p["type"].__setitem__("category", "bool"),
                   lambda p: p.__setitem__("links", []),
                   lambda p: p.__setitem__("default_text_value", "다른 설명")):
        right = capture()
        mutate(pin(right))
        report = R.audit_repeats(left, right)
        assert report["status"] == "changed" and report["assets"][0]["mismatches"], mutate
        for record in report["assets"][0]["mismatches"]:
            assert set(record) >= {"path", "expected", "actual"} and record["path"].startswith("snapshot/")
    right = capture()
    pin(right)["hidden"] = True
    hidden = R.audit_repeats(left, right)["assets"][0]["mismatches"]
    # A hidden pin is never suppressed and the observed values are kept as they were reported.
    assert any(m["path"].endswith("/hidden") and m["expected"] is False and m["actual"] is True
               for m in hidden), hidden
    right = capture()
    pin(right)["guid"] = "0f0e0d0c0b0a09080706050403020100"
    pin(right)["name"] = "then"
    guid = R.audit_repeats(left, right)["assets"][0]["mismatches"]
    # Two different pin GUIDs are two different pins, whatever their names say.
    assert sum(m.get("reason") == "missing or extra identity/field" for m in guid) >= 2, guid
    right = capture()
    right["assets"][0]["snapshot"]["variables"][0]["default_value"] = "50"
    declared = R.audit_repeats(left, right)
    assert declared["status"] == "changed"
    assert any(m["expected"] == "100" and m["actual"] == "50"
               for m in declared["assets"][0]["mismatches"]), declared


def test_native_repeats_package_hash_engine_and_project_drift_fail_closed():
    for key, value, fragment in (("package_file", "Content/Other.uasset", "package_file"),
                                 ("package_file", None, "package_file"),
                                 ("sha256_after", OTHER_SHA, "changed during the right capture"),
                                 ("sha256_before", SHA.upper(), "lower-case sha256"),
                                 ("sha256_before", None, "lower-case sha256")):
        right = capture()
        right["assets"][0][key] = value
        report = R.audit_repeats(capture(), right)
        assert report["status"] == "incomplete" and not report["assets"][0]["mismatches"], (key, value)
        assert fragment in report["assets"][0]["unavailable"][0]["reason"], (key, value)
    drifted = capture([asset(sha=OTHER_SHA)])
    report = R.audit_repeats(capture(), drifted)
    assert report["status"] == "incomplete", report
    assert "not repeat observations of the same bytes" in report["assets"][0]["unavailable"][0]["reason"]
    for field, value in (("schema_version", True), ("schema_version", 2), ("schema_version", "1"),
                         ("producer", "ue-repo-reader digest"), ("engine_version", "5.6.2"),
                         ("engine_version", "5.8"), ("project_file", ".uproject"),
                         ("project_file", "Project.uasset"), ("project_file", None)):
        for side in ("left", "right"):
            left, right = capture(), capture()
            (left if side == "left" else right)[field] = value
            refused(left, right, f"{side} {field}={value!r}")
    for field, value in (("engine_version", "5.7.1-other"), ("project_file", "D:/other/Project.uproject")):
        right = capture()
        right[field] = value
        refused(capture(), right, f"{field} drift")


def test_native_repeats_dirty_and_failed_captures_are_never_stable():
    for key, value in (("package_dirty", True), ("package_dirty", None), ("package_dirty", 0),
                       ("text_values", "display"), ("issues", ["notify graph not loaded"])):
        for side in ("left", "right"):
            left, right = capture(), capture()
            (left if side == "left" else right)["assets"][0]["snapshot"][key] = value
            report = R.audit_repeats(left, right)
            assert report["status"] == "incomplete", (side, key, value)
            assert report["assets"][0]["unavailable"] and not report["assets"][0]["mismatches"]
    for record in ({"issues": ["asset failed to load"]}, {"snapshot": None}, {"snapshot": []}):
        right = capture()
        right["assets"][0].update(record)
        report = R.audit_repeats(capture(), right)
        assert report["status"] == "incomplete" and report["assets"][0]["unavailable"], record
    # A malformed asset record is that asset's gap, not a reason to drop the whole audit.
    report = R.audit_repeats(capture(), capture([{**asset(), "issues": "load failed"}]))
    assert report["status"] == "incomplete" and report["assets"][0]["unavailable"], report
    # Reported root gaps outrank both stable and changed, and keep the mismatch records.
    gapped = capture()
    gapped["issues"] = ["2 of 3 assets could not be opened"]
    report = R.audit_repeats(gapped, capture())
    assert report["status"] == "incomplete" and report["issues"] == ["left capture: 2 of 3 assets could not be opened"]
    right = capture()
    right["assets"][0]["snapshot"]["graphs"][0]["nodes"][0]["pins"][0]["hidden"] = True
    report = R.audit_repeats(gapped, right)
    assert report["status"] == "incomplete" and report["assets"][0]["mismatches"], report


def test_native_repeats_asset_membership_gaps_and_duplicates_refused():
    other = "/Game/한국어/Second"
    left = capture([asset(), asset(other)])
    report = R.audit_repeats(left, capture())
    assert report["status"] == "incomplete" and len(report["assets"]) == 2, report
    absent = [a for a in report["assets"] if a["asset_path"] == other][0]
    present = [a for a in report["assets"] if a["asset_path"] == ASSET][0]
    assert absent["unavailable"][0]["reason"] == "absent from the right capture"
    assert present["checked"] > 0 and not present["mismatches"]
    assert any(other in issue and "absent from the right capture" in issue for issue in report["issues"])
    extra = R.audit_repeats(capture(), left)
    assert extra["status"] == "incomplete" and len(extra["assets"]) == 2
    assert any("absent from the left capture" in i["reason"]
               for a in extra["assets"] for i in a["unavailable"])
    refused(capture([asset(), asset()]), capture(), "duplicate asset identity")
    for bad in ("/Game/../Outside", "/Game/A\\B", "/Game/A.B", "/Other/BP", "/Game//BP", "/Game/", "", None):
        record = dict(asset(), asset_path=bad)
        refused(capture([record]), capture([record]), f"asset path {bad!r}")


def test_native_repeats_one_bad_record_keeps_other_asset_results():
    other = "/Game/한국어/Second"
    left = capture([asset(), asset(other)])
    for break_it in (lambda n: n["variables"][0].__setitem__("flags", "not-a-uint64"),
                     lambda n: n["graphs"][0]["nodes"][0]["pins"][0].pop("guid"),
                     lambda n: n.pop("graphs"),
                     lambda n: n["graphs"][0]["nodes"][0]["pins"][0].__setitem__("direction", 7)):
        right = capture([asset(), asset(other)])
        broken = [a for a in right["assets"] if a["asset_path"] == other][0]
        break_it(broken["snapshot"])
        right["assets"][0]["snapshot"]["graphs"][0]["nodes"][0]["pins"][0]["hidden"] = True
        report = R.audit_repeats(left, right)
        good = [a for a in report["assets"] if a["asset_path"] == ASSET][0]
        bad = [a for a in report["assets"] if a["asset_path"] == other][0]
        # One asset's gap never deletes the other's compared observations or mismatch rows,
        # and it keeps the whole audit short of a verdict.
        assert report["status"] == "incomplete" and report["checked"] > 0, break_it
        assert good["checked"] > 0 and good["mismatches"], break_it
        assert bad["checked"] == 0 and bad["unavailable"] and not bad["mismatches"], break_it


def test_native_repeats_any_gap_outranks_a_proven_mismatch():
    """A difference on one asset plus an unobserved other asset is incomplete, not changed."""
    other = "/Game/한국어/Second"
    left = capture([asset(), asset(other)])
    complete = capture([asset(), asset(other)])
    changed_pin = complete["assets"][0]["snapshot"]["graphs"][0]["nodes"][0]["pins"][0]
    changed_pin["default_value"] = "9"
    verdict = R.audit_repeats(left, complete)
    rows = [a for a in verdict["assets"] if a["asset_path"] == ASSET][0]["mismatches"]
    assert verdict["status"] == "changed" and rows, verdict
    # Exactly the same observed difference, now beside one gapped asset, per gap kind.
    for gap in (lambda c: c["assets"][1].update(issues=["asset failed to load"]),
                lambda c: c["assets"][1]["snapshot"].update(package_dirty=True),
                lambda c: c["assets"][1].update(sha256_before=OTHER_SHA, sha256_after=OTHER_SHA),
                lambda c: c["assets"][1].update(package_file="Content/Elsewhere.uasset"),
                lambda c: c["assets"].pop(1),
                lambda c: c["assets"][1]["snapshot"].update(variables="unreadable")):
        gapped = copy.deepcopy(complete)
        gap(gapped)
        report = R.audit_repeats(left, gapped)
        kept = [a for a in report["assets"] if a["asset_path"] == ASSET][0]
        assert report["status"] == "incomplete", gap
        assert kept["mismatches"] == rows and kept["checked"] > 0, gap
        assert report["checked"] == kept["checked"] and report["checked"] > 0, gap
        assert any(a["unavailable"] for a in report["assets"] if a["asset_path"] == other), gap
    # The gap on the compared asset itself also outranks its own mismatch rows.
    partial = copy.deepcopy(complete)
    partial["assets"][0]["snapshot"]["graphs"][0]["nodes"][0]["pins"][0]["links"] = C.unknown("link unresolved")
    report = R.audit_repeats(left, partial)
    first = [a for a in report["assets"] if a["asset_path"] == ASSET][0]
    assert report["status"] == "incomplete" and first["mismatches"] and first["unavailable"], report


def test_native_repeats_empty_and_malformed_input_refused():
    for field, value in (("assets", []), ("assets", "x"), ("assets", None), ("assets", [None]),
                         ("assets", [{"snapshot": observation()}]), ("issues", "ignored"),
                         ("issues", [1]), ("issues", None), ("producer", None)):
        left, right = capture(), capture()
        left[field] = value
        refused(left, right, f"{field}={value!r}")
    for value in ([], "", None, 0, ["capture"]):
        refused(value, capture(), f"root {value!r}")
        refused(capture(), value, f"root {value!r}")
    for text in ("[]", '{"x":NaN}', '{"assets":[],"assets":[]}', "not json"):
        try:
            C.load_json(text)
        except C.OracleError:
            continue
        raise AssertionError(f"malformed capture text accepted: {text}")
    # An empty graph stays an excluded scope on both sides; the declarations are still compared.
    thin = capture()
    thin["assets"][0]["snapshot"] = {**observation(), "graphs": [{"object_path": "/Game/한국어/BP.BP:Empty",
                                                                  "name": "Empty", "nodes": []}]}
    report = R.audit_repeats(copy.deepcopy(thin), copy.deepcopy(thin))
    assert report["status"] == "stable" and report["checked"] > 0, report


def test_native_repeats_cli_preserves_existing_outputs_and_reports_exit_codes():
    def run(*argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = R.main([str(a) for a in argv])
        return code, out.getvalue() + err.getvalue()
    with tempfile.TemporaryDirectory(prefix="repeat-한글 ") as tmp:
        root = Path(tmp)
        left, right = root / "left.json", root / "right.json"
        for path in (left, right):
            path.write_text(json.dumps(capture(), ensure_ascii=False), encoding="utf-8")
        report = root / "audit.json"
        code, text = run(left, right, "--out", report)
        assert code == 0 and "stable" in text and "observation only" in text, (code, text)
        written = report.read_text(encoding="utf-8")
        assert json.loads(written)["status"] == "stable"
        code, text = run(left, right, "--out", report)
        assert code == 2 and "error:" in text and report.read_text(encoding="utf-8") == written
        for bad in (root / "audit.txt", root / "missing" / "audit.json", left, root / "audit.json"):
            code, _ = run(left, right, "--out", bad)
            assert code == 2, bad
        assert not (root / "missing").exists() and not (root / "audit.txt").exists()
        assert json.loads(left.read_text(encoding="utf-8"))["producer"] == "unreal-editor-native"
        changed = capture()
        changed["assets"][0]["snapshot"]["graphs"][0]["nodes"][0]["pins"][0]["default_value"] = "9"
        right.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
        fresh = root / "changed.json"
        code, text = run(left, right, "--out", fresh)
        assert code == 1 and json.loads(fresh.read_text(encoding="utf-8"))["status"] == "changed"
        code, text = run(left, right)
        assert code == 1 and json.loads(text[text.index("{"):])["status"] == "changed"
        drifted = capture()
        drifted["engine_version"] = "5.7.0-other"
        right.write_text(json.dumps(drifted, ensure_ascii=False), encoding="utf-8")
        refused_out = root / "refused.json"
        code, text = run(left, right, "--out", refused_out)
        assert code == 2 and not refused_out.exists(), (code, text)
        code, _ = run(root / "absent.json", right)
        assert code == 2
