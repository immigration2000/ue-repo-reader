"""Verify the regression suite itself rejects missing assets, wrong oracles and corrupt downloads."""
import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import asset_regress as A
import bp_reader as B
import regress


def _scratch():
    cache = Path(__file__).resolve().parent / ".cache"
    cache.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="coverage-check-", dir=cache)


def test_regress_detects_missing_assets():
    with _scratch() as tmp:
        root = Path(tmp)
        (root / "INDEX.md").write_text("Coverage: 0 Blueprints rendered, 0 failed; graph nodes decoded 0/0", encoding="utf-8")
        summary = {"issues": [], "parse_status": "ok", "level_bp_nodes": [0, 0], "level_bp_status": "ok",
                   "external_actors": 1, "world_partition": True, "actor_count": 2}
        value = {"blueprints": {}, "data_assets": {}, "maps_detail": {"/Game/World": summary},
                 "failures": {}, "data_failures": {}, "map_failures": {}, "lfs": {}}
        (root / "digest.json").write_text(json.dumps(value), encoding="utf-8")
        fixture = {"expect": {"blueprints": 0, "nodes": 0, "data_assets": 1, "maps": 2, "external_actors": 2},
                   "summary_checks": [{"collection": "maps_detail", "path": "/Game/World", "fields": {"actor_count": 3}}]}
        errors = regress.check(fixture, root)
        assert any("data_assets 0 != expected 1" in e for e in errors)
        assert any("maps 1 != expected 2" in e for e in errors)
        assert any("external actors 1 != expected 2" in e for e in errors)
        assert any("actor_count 2 != expected 3" in e for e in errors)


def test_asset_oracle_rejects_wrong_text():
    from graph_ir_tests import pin as make_pin, node as make_node, project
    with _scratch() as tmp:
        root = Path(tmp)
        expected = [{"objectPath": "/Game/Keys.BP:EventGraph.split", "pinIndex": 0,
                     "pinId": "0102030405060708090A0B0C0D0E0F10", "source": "oracle source"}]
        (root / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
        case = {"kind": "blueprint", "engine": "5.8", "asset": {"path": "BP.uasset"}, "oracle": {"path": "expected.json"}}
        pin = make_pin("04030201080706050C0B0A09100F0E0D", default_text_value="wrong text")
        node = make_node("split", 1, [pin])
        graph = NS(nodes=[node], subgraphs=[])
        ir = project([node])
        ir["graphs"][0]["nodes"][0]["object_path"] = "/Game/Keys.BP.EventGraph.split"
        ir_pin = ir["graphs"][0]["nodes"][0]["pins"][0]
        ir_pin["defaults"]["default_text_value"] = "oracle source"
        rendered = {"markdown": "oracle source", "summary": {"issues": [], "parse_status": "ok",
                    "graph_ir": ir}}
        with patch.object(B, "read_blueprint", return_value=rendered), \
             patch.object(B, "_parse", return_value=(NS(graphs=[graph]), (1, 1))), \
             patch.object(B, "_read_summary", return_value=NS(saved_by_engine_version=NS(major=5, minor=8, patch=3))):
            try:
                A.check_case(case, root)
            except AssertionError as e:
                assert "wrong text" in str(e)
            else:
                raise AssertionError("wrong pin text passed its native oracle")
            pin.default_text_value = "oracle source"
            A.check_case(case, root)
            ir_pin["defaults"]["default_text_value"] = "incorrect IR text"
            try:
                A.check_case(case, root)
            except AssertionError as e:
                assert "wrong IR text" in str(e)
            else:
                raise AssertionError("corrupted public IR passed with correct parser/Markdown text")


def _pinned_digest(exp: dict) -> dict:
    """Synthesize the digest.json that a fixture's per-asset pins describe.

    Lets the pinned baseline (and every way of breaking it) be exercised without a clone, and
    keeps the pins honest: if they no longer describe a decodable digest, these tests fail.
    """
    known = exp.get("known_issues") or {}

    def issues(collection, gp):
        return [{"stage": s[0], "context": s[1], "message": s[2]}
                for s in ((known.get(collection) or {}).get(gp) or [])]

    digest = {"source": {"project_support": exp.get("project_support", {})},
              "blueprints": {}, "data_assets": {}, "maps_detail": {},
              "failures": {}, "data_failures": {}, "map_failures": {}, "lfs": {}}
    for gp, (ok, total) in exp["blueprint_nodes"].items():
        found = issues("blueprints", gp)
        digest["blueprints"][gp] = {"nodes_ok": ok, "nodes_total": total, "issues": found,
                                    "parse_status": "partial" if found or ok < total else "ok"}
    for gp, (ok, total, status) in exp["level_blueprints"].items():
        found = issues("maps_detail", gp)
        digest["maps_detail"][gp] = {"level_bp_nodes": [ok, total], "level_bp_status": status,
                                     "external_actors": 0, "issues": found,
                                     "parse_status": "partial" if found else "ok"}
    return digest


def _write_pinned(root: Path, digest: dict) -> None:
    # Coverage line is derived from the digest, so a per-asset mutation that preserves the repo
    # totals (node redistribution) stays invisible to the aggregate check.
    ok = sum(s["nodes_ok"] for s in digest["blueprints"].values())
    total = sum(s["nodes_total"] for s in digest["blueprints"].values())
    (root / "INDEX.md").write_text(f"Coverage: {len(digest['blueprints'])} Blueprints rendered, 0 failed; "
                                   f"graph nodes decoded {ok}/{total}", encoding="utf-8")
    (root / "digest.json").write_text(json.dumps(digest), encoding="utf-8")


def _bt_expect() -> dict:
    """The real bt fixture's expectations, without its file-content checks (no documents here)."""
    return json.loads(regress.FIXTURES.read_text(encoding="utf-8"))["bt"]["expect"]


def test_regress_project_support_must_match_pinned_declaration():
    exp = _bt_expect()
    with _scratch() as tmp:
        root = Path(tmp)
        baseline = _pinned_digest(exp)
        _write_pinned(root, baseline)
        assert regress.check({"expect": exp}, root) == []
        for field, wrong in (("declared_version", "5.8"), ("classification", "target"),
                             ("best_effort_requested", False), ("best_effort_used", 1),
                             ("project_file", "Other.uproject")):
            actual = json.loads(json.dumps(baseline))
            actual["source"]["project_support"][field] = wrong
            _write_pinned(root, actual)
            assert any(f"project support {field}" in e for e in regress.check({"expect": exp}, root)), field


def test_regress_accepts_only_pinned_parse_issues():
    exp = _bt_expect()
    assert "allow_issues" not in exp, "bt must pin its known issues, not allow any issue"
    main_menu, battleground = "/Game/_Levels/MainMenu", "/Game/_Levels/BattleGround"
    with _scratch() as tmp:
        root = Path(tmp)
        _write_pinned(root, _pinned_digest(exp))
        assert regress.check({"expect": exp}, root) == [], "the pinned bt baseline must stay accepted"

        # Re-introducing the blanket flag fails instead of quietly granting permission again.
        assert any("allow_issues" in e for e in regress.check({"expect": {**exp, "allow_issues": True}}, root))

        # A new issue inside an asset that is already allowed to have known issues.
        digest = _pinned_digest(exp)
        digest["maps_detail"][main_menu]["issues"].append(
            {"stage": "properties", "context": "Brush_9", "message": "invalid property type None"})
        _write_pinned(root, digest)
        assert any("unexpected parse issue" in e and "Brush_9" in e for e in regress.check({"expect": exp}, root))

        # A new kind of issue inside a Blueprint, even one with pinned projection gaps.
        digest = _pinned_digest(exp)
        digest["blueprints"]["/Game/Tank/Tank_BP"]["issues"].append(
            {"stage": "graph_render", "context": "EventGraph", "message": "ValueError: injected"})
        _write_pinned(root, digest)
        errors = regress.check({"expect": exp}, root)
        assert any("unexpected parse issue" in e and "injected" in e for e in errors), errors

        # A changed signature of an allowed issue is a different issue, not the pinned one.
        digest = _pinned_digest(exp)
        digest["maps_detail"][battleground]["issues"][0]["message"] = "0/4 nodes decoded"
        _write_pinned(root, digest)
        errors = regress.check({"expect": exp}, root)
        assert any("unexpected parse issue" in e and "0/4 nodes decoded" in e for e in errors), errors
        assert any("no longer reported" in e and "0/2 nodes decoded" in e for e in errors), errors

        # An extra occurrence of an already allowed issue.
        digest = _pinned_digest(exp)
        reported = digest["maps_detail"][main_menu]["issues"]
        reported.append(dict(reported[0]))
        _write_pinned(root, digest)
        assert any("unexpected parse issue (×1)" in e for e in regress.check({"expect": exp}, root))

        # A stale pin (the issue stopped being reported) fails too, so pins cannot rot into permission.
        digest = _pinned_digest(exp)
        digest["maps_detail"][main_menu].update(issues=[], parse_status="ok")
        _write_pinned(root, digest)
        errors = regress.check({"expect": exp}, root)
        assert len([e for e in errors if "no longer reported" in e]) == len(exp["known_issues"]["maps_detail"][main_menu]), errors

        # "partial" is derived from the pins: an unexplained partial status is not accepted.
        digest = _pinned_digest(exp)
        # Q9 exposes projection gaps even in the 4.12 BPs with decoded pins;
        # the empty SpringTestBed map remains a confirmed clean reference case.
        digest["maps_detail"]["/Game/_Levels/SpringTestBed"]["parse_status"] = "partial"
        _write_pinned(root, digest)
        assert any("parse status 'partial' != expected 'ok'" in e for e in regress.check({"expect": exp}, root))

        # An explicit null status is neither a confirmed success nor a pinned partial state. The key
        # is present, so the structural check stays quiet: only the derived-status check may catch it.
        for gp, collection, want in (("/Game/_Levels/SpringTestBed", "maps_detail", "'ok'"),
                                     ("/Game/Tank/Tank_BP", "blueprints", "'partial'"),
                                     (main_menu, "maps_detail", "'partial'")):
            digest = _pinned_digest(exp)
            digest[collection][gp]["parse_status"] = None
            _write_pinned(root, digest)
            errors = regress.check({"expect": exp}, root)
            assert any(f"{gp}: parse status None != expected {want}" in e for e in errors), (gp, errors)
            assert not any("missing structured parse status/issues" in e for e in errors), errors
            # Nothing else about these assets changed, so the null status is the only complaint.
            assert len(errors) == 1, errors

        # A missing parse_status key fails too, and is additionally reported as a structural gap.
        digest = _pinned_digest(exp)
        del digest["blueprints"]["/Game/Tank/Tank_BP"]["parse_status"]
        _write_pinned(root, digest)
        errors = regress.check({"expect": exp}, root)
        assert any("parse status None != expected 'partial'" in e for e in errors), errors
        assert any("missing structured parse status/issues" in e for e in errors), errors


def test_regress_detects_node_and_level_blueprint_coverage_loss():
    exp = _bt_expect()
    with _scratch() as tmp:
        root = Path(tmp)
        # Redistribution: Tank_BP loses two nodes, ConstraintTest gains two, repo totals unchanged.
        digest = _pinned_digest(exp)
        digest["blueprints"]["/Game/Tank/Tank_BP"].update(nodes_ok=12, nodes_total=39)
        digest["blueprints"]["/Game/Experiments/ConstraintTest"].update(nodes_ok=6, nodes_total=6)
        _write_pinned(root, digest)
        errors = regress.check({"expect": exp}, root)
        assert not any(e.startswith(("nodes decoded", "node total")) for e in errors), errors
        assert any("Tank_BP: nodes decoded 12/39 != pinned 14/41" in e for e in errors), errors
        assert any("ConstraintTest: nodes decoded 6/6 != pinned 4/4" in e for e in errors), errors

        # Coverage loss inside a Blueprint whose partial decoding is already pinned.
        digest = _pinned_digest(exp)
        digest["blueprints"]["/Game/Tank/Tank_BP"]["nodes_ok"] = 13
        _write_pinned(root, digest)
        assert any("nodes decoded 13/41 != pinned 14/41" in e for e in regress.check({"expect": exp}, root))

        # A Blueprint nobody pinned must decode completely, and new Blueprints must be pinned.
        digest = _pinned_digest(exp)
        digest["blueprints"]["/Game/New_BP"] = {"nodes_ok": 1, "nodes_total": 4, "issues": [],
                                                "parse_status": "partial"}
        _write_pinned(root, digest)
        errors = regress.check({"expect": exp}, root)
        assert any("/Game/New_BP: nodes decoded 1/4 != pinned 4/4" in e for e in errors), errors
        assert any("not pinned in blueprint_nodes" in e for e in errors), errors

        # A Level Blueprint that decoded completely must not become partial.
        digest = _pinned_digest(exp)
        digest["maps_detail"]["/Game/_Levels/SpringTestBed"].update(level_bp_nodes=[1, 3], level_bp_status="partial")
        _write_pinned(root, digest)
        assert any("SpringTestBed: Level Blueprint 1/3 partial != pinned 0/0 ok" in e
                   for e in regress.check({"expect": exp}, root))

        # …and a Level Blueprint already known to be partial must not decode even less.
        digest = _pinned_digest(exp)
        movement = digest["maps_detail"]["/Game/_Levels/BattleGround_MovementTest"]
        movement["level_bp_nodes"] = [0, 2]
        movement["issues"][0]["message"] = "0/2 nodes decoded"
        _write_pinned(root, digest)
        assert any("Level Blueprint 0/2 partial != pinned 1/2 partial" in e
                   for e in regress.check({"expect": exp}, root))

        # A map dropping out of the digest cannot silently retire its pinned limitation.
        digest = _pinned_digest(exp)
        del digest["maps_detail"]["/Game/_Levels/MainMenu"]
        _write_pinned(root, digest)
        errors = regress.check({"expect": exp}, root)
        assert any("no longer rendered" in e for e in errors), errors
        assert any("known issues pinned for an asset that is no longer rendered" in e for e in errors), errors


def test_asset_download_hash_guard():
    with _scratch() as tmp:
        root = Path(tmp)
        with patch.object(A.urllib.request, "urlopen", return_value=io.BytesIO(b"corrupt")):
            try:
                A.fetch_file({"repository": "example/fixture", "commit": "a" * 40},
                             {"path": "asset.uasset", "blob": "b" * 40}, root)
            except ValueError as e:
                assert "hash mismatch" in str(e)
            else:
                raise AssertionError("corrupt asset was published")
        assert not (root / "asset.uasset").exists()
