"""UE 5.7+ project support policy, CLI rejection and explicit best-effort regressions (Q11)."""
import io
import json
import re
import struct
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bp_reader as B
import project_support as P
import ue_repo_digest as D

CLASSIFICATIONS = ("target", "below_minimum", "unverified_newer", "unconfirmed")
NUMERIC = re.compile(r"\d+\.\d+(?:\.\d+)?")
# A saved asset header that looks like another engine version: it must never decide the project's support.
FAKE_ASSET = (b"\xc1\x83\x2a\x9e" + struct.pack("<i", -7) + b"\x00" * 12 +
              b"++UE5+Release-5.3 saved asset\x00")
NO_LFS = {"pointers": 0, "requested": 0, "skipped_large": 0, "failed": 0, "error": None, "bytes": 0}


def _support(engine_association, **kwargs):
    """Call the policy and check the invariants every caller (CLI, MCP, output, cache) may rely on."""
    result = P.assess_project(engine_association, **kwargs)
    assert isinstance(result, dict), result
    assert result["policy_version"] == 1, result
    assert result["engine_association"] == engine_association, result
    assert result["classification"] in CLASSIFICATIONS, result
    for field in ("allowed", "best_effort_requested", "best_effort_used"):
        assert isinstance(result[field], bool), (field, result)
    assert isinstance(result["reason"], str) and result["reason"].strip(), result
    opt_in = kwargs.get("best_effort", False)
    target = result["classification"] == "target"
    assert result["best_effort_requested"] is opt_in, result
    assert result["allowed"] is (target or opt_in), result
    assert result["best_effort_used"] is (opt_in and not target), result
    declared = result["declared_version"]
    if result["classification"] == "unconfirmed":
        assert declared is None, result
    else:
        assert isinstance(declared, str) and NUMERIC.fullmatch(declared), result
    return result


def _scratch():
    cache = Path(__file__).resolve().parent / ".cache"
    cache.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="project-support-", dir=cache)


def _run_cli(args):
    """Exercise the real CLI and filesystem without git, LFS downloads, parser install or asset decoding."""
    with patch.object(D, "classify_assets", return_value={}) as classify, \
         patch.object(D, "pull_lfs", return_value=dict(NO_LFS)) as lfs, \
         patch.object(B, "ensure_uasset_read") as parser, \
         patch.object(D, "run", return_value=SimpleNamespace(stdout="", returncode=0)), \
         redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
        try:
            code = D.main([*args, "--no-asset-cache"])
        except SystemExit as exit_:
            code = exit_.code
        return SimpleNamespace(code=code, classify=classify, lfs=lfs, parser=parser,
                               text=out.getvalue() + err.getvalue())


def _project(source: Path, declaration, assets=("Content/BP_Fake.uasset",)):
    for rel in assets:
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(FAKE_ASSET)
    source.mkdir(parents=True, exist_ok=True)
    if isinstance(declaration, bytes):
        (source / "Game.uproject").write_bytes(declaration)  # undecodable bytes stay bytes here
    elif declaration is not None:
        (source / "Game.uproject").write_text(declaration, encoding="utf-8")
    return source


def _previous_output(out: Path):
    out.mkdir(parents=True)
    (out / "digest.json").write_text('{"tool":"ue-repo-reader test","source":{"engine":"5.8"}}', encoding="utf-8")
    (out / "INDEX.md").write_text("# earlier digest\nkeep these exact bytes\n", encoding="utf-8")


def _snapshot(root: Path):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _digest_support(out: Path):
    digest = json.loads((out / "digest.json").read_text(encoding="utf-8"))
    support = digest["source"]["project_support"]
    assert support["policy_version"] == 1 and str(support["reason"]).strip(), support
    assert support["classification"] in CLASSIFICATIONS, support
    return digest, support


def _head(text: str, heading: str) -> str:
    """Everything before the asset listings — a notice buried below them is not prominent."""
    return text.split(heading)[0]


def test_project_support_numeric_boundaries_and_patch_strings():
    for value in ("5.7", "5.8", "5.7.0", "5.8.3", "5.7.12"):
        result = _support(value)
        assert result["classification"] == "target", result
        assert result["declared_version"] == value, result  # no patch component is invented or dropped
    for value in ("5.6", "5.6.9", "5.1.1", "5.0", "4.27", "4.19"):
        assert _support(value)["classification"] == "below_minimum", value
    # 5.10 is newer than 5.8 and 10.0 is newer than 5.x: comparison is per numeric field, never float or text order.
    for value in ("5.9", "5.9.1", "5.10", "5.10.0", "5.11", "6.0", "6.1.2", "10.0"):
        assert _support(value)["classification"] == "unverified_newer", value
    assert _support("5.10")["declared_version"] == "5.10"
    for raw, declared in ((" 5.8 ", "5.8"), ("\t5.7\n", "5.7"), ("5.6\r\n", "5.6")):
        result = _support(raw)
        assert result["declared_version"] == declared, result
        assert result["engine_association"] == raw, result  # the raw JSON value stays visible


def test_project_support_unconfirmed_declarations_and_metadata_errors():
    unconfirmed = (
        None, "", "   ",
        "{A0B1C2D3-4E5F-6071-8293-A4B5C6D7E8F9}",          # a custom/build ID instead of a numeric version
        "5.8.0-34113687+++UE5+Release-5.8", "++UE5+Release-5.8", "5.8-custom",
        5.8, 58, True, False, ["5.8"], {"EngineAssociation": "5.8"},
        "5", "5.", "5.x", "five.eight", "v5.8", "5.8.", "5.8.1.2", "-5.8", "5. 8",
    )
    for value in unconfirmed:
        result = _support(value)
        assert result["classification"] == "unconfirmed", (value, result)
        assert result["allowed"] is False, (value, result)
    for kwargs in ({"project_found": False},
                   {"metadata_error": "Expecting ',' delimiter: line 1 column 30"},
                   {"project_found": False, "metadata_error": "no .uproject in repository"}):
        assert _support(None, **kwargs)["classification"] == "unconfirmed", kwargs
    # An unreadable .uproject cannot vouch for a declaration that was read out of it.
    assert _support("5.8", metadata_error="not a JSON object")["classification"] == "unconfirmed"
    assert _support("5.8", project_found=False)["classification"] == "unconfirmed"


def test_project_support_best_effort_requires_real_booleans():
    for value in ("true", "True", "false", "1", "0", "", "yes", 1, 0, 1.0, None, [], ["5.8"]):
        try:
            P.assess_project("5.6", best_effort=value)
        except ValueError:
            continue
        raise AssertionError(f"non-bool best_effort={value!r} was accepted as an override")
    for value, classification in (("4.27", "below_minimum"), ("5.9", "unverified_newer"),
                                  (None, "unconfirmed"), ("{GUID}", "unconfirmed")):
        opted_in = _support(value, best_effort=True)
        assert opted_in["classification"] == classification, opted_in
        assert opted_in["allowed"] is True and opted_in["best_effort_used"] is True, opted_in
        refused = _support(value, best_effort=False)
        assert refused["classification"] == classification, refused
        assert refused["allowed"] is False and refused["best_effort_used"] is False, refused
    # Opting in never relabels a project as a verified target, and a target never counts as best-effort.
    for value in ("5.7", "5.8.2"):
        result = _support(value, best_effort=True)
        assert result["classification"] == "target" and result["best_effort_used"] is False, result
        assert result["best_effort_requested"] is True and result["allowed"] is True, result


def test_project_support_policy_is_pure_and_stateless():
    # The policy judges the declaration only: no asset headers, asset registry or installed engine.
    for opener in ("builtins.open", "io.open"):
        with patch(opener, side_effect=AssertionError(f"policy read a file via {opener}")), \
             patch("subprocess.run", side_effect=AssertionError("policy ran a subprocess")):
            assert P.assess_project("5.8")["classification"] == "target"
            assert P.assess_project("4.27", best_effort=True)["allowed"] is True
            assert P.assess_project(None)["classification"] == "unconfirmed"
    first = _support("5.9")
    first["classification"] = "target"
    first["allowed"] = True
    second = _support("5.9")
    assert second["classification"] == "unverified_newer" and second["allowed"] is False, second
    assert _support("5.8") == _support("5.8"), "same declaration gave different results"
    assert _support("5.8", best_effort=False) == _support("5.8"), "default best_effort is not False"
    assert _support("5.8", project_found=True) == _support("5.8"), "default project_found is not True"


def test_cli_rejects_unsupported_projects_and_preserves_output():
    cases = (("legacy", '{"EngineAssociation": "5.6"}'),
             ("future", '{"EngineAssociation": "5.9"}'),
             ("guid", '{"EngineAssociation": "{A0B1C2D3-4E5F-6071-8293-A4B5C6D7E8F9}"}'),
             ("label", '{"EngineAssociation": "5.8.0-34113687+++UE5+Release-5.8"}'),
             ("malformed", '{"EngineAssociation": "5.8"'),
             ("nonobject", '["EngineAssociation", "5.8"]'),
             ("undecodable", b'{"EngineAssociation": "5.8\xff\xfe"}'),
             ("nan", '{"EngineAssociation": NaN}'),
             ("absent", None))
    with _scratch() as tmp:
        base = Path(tmp)
        for name, declaration in cases:
            source = _project(base / f"{name}-원본", declaration)
            out = base / f"{name}-digest"
            _previous_output(out)
            before = _snapshot(out)
            with patch.object(D.shutil, "rmtree", side_effect=AssertionError(f"{name}: output deleted")):
                run = _run_cli([str(source), "--out", str(out)])
            assert run.code == 2, (name, run.code, run.text)
            assert _snapshot(out) == before, f"{name}: recognized earlier output was not preserved byte for byte"
            assert run.classify.call_count == 0, f"{name}: classified assets of an unsupported project"
            assert run.lfs.call_count == 0, f"{name}: downloaded LFS objects of an unsupported project"
            assert run.parser.call_count == 0, f"{name}: installed the parser for an unsupported project"
            assert re.search(r"best[- ]effort", run.text, re.I), f"{name}: refusal did not name the opt-in: {run.text}"


def test_cli_best_effort_keeps_unsupported_status_in_digest_and_indexes():
    cases = (("미확정", '{"EngineAssociation": "{A0B1C2D3-4E5F-6071-8293-A4B5C6D7E8F9}"}', "unconfirmed", None),
             ("broken", '{"EngineAssociation": "5.8"', "unconfirmed", None),
             ("undecodable", b'{"EngineAssociation": "5.8\xff\xfe"}', "unconfirmed", None),
             ("absent", None, "unconfirmed", None),
             ("legacy", '{"EngineAssociation": "4.27"}', "below_minimum", "4.27"),
             ("future", '{"EngineAssociation": "5.9"}', "unverified_newer", "5.9"))
    with _scratch() as tmp:
        base = Path(tmp)
        for name, declaration, classification, declared in cases:
            source = _project(base / f"{name}-source", declaration)
            out = base / f"{name}-digest"
            _previous_output(out)
            run = _run_cli([str(source), "--out", str(out), "--best-effort"])
            assert run.code == 0, (name, run.code, run.text)
            assert run.classify.call_count == 1 and run.lfs.call_count == 1, (name, "digest did not run")
            support = _digest_support(out)[1]
            assert support["classification"] == classification, (name, support)
            assert support["declared_version"] == declared, (name, support)
            assert support["allowed"] is True, (name, support)
            assert support["best_effort_requested"] is True and support["best_effort_used"] is True, (name, support)
            index = (out / "INDEX.md").read_text(encoding="utf-8")
            catalog = (out / "CATALOG.md").read_text(encoding="utf-8")
            assert "keep these exact bytes" not in index, f"{name}: allowed run did not replace the earlier digest"
            for label, text, heading in (("INDEX.md", index, "## Reading priority"),
                                         ("CATALOG.md", catalog, "## Blueprints (")):
                head = _head(text, heading)
                assert re.search(r"best[- ]effort", head, re.I), \
                    f"{name}: {label} does not state the best-effort opt-in before its listings"
                if classification == "unconfirmed":
                    assert "unconfirmed" in head.lower(), f"{name}: {label} hides the unconfirmed engine version"
                # Decoding every asset of an unsupported project proves nothing about project support.
                assert "everything decoded cleanly" not in text.lower(), \
                    f"{name}: {label} reports a clean read of a {classification} project"
            assert "target" not in support["classification"], support


def test_cli_project_selection_uses_declaration_not_asset_bytes():
    with _scratch() as tmp:
        base = Path(tmp)
        source, out = base / "repo", base / "digest"
        _project(source, '{"EngineAssociation": "5.6"}')
        modern = _project(source / "Modern", None, assets=("Content/BP_Old.uasset",))
        (modern / "Modern.uproject").write_text('{"EngineAssociation": "5.8"}', encoding="utf-8")

        run = _run_cli([str(source), "--out", str(out)])  # default selection is the legacy root project
        assert run.code == 2, (run.code, run.text)
        assert not (out / "INDEX.md").exists(), "a rejected run produced output"
        assert run.classify.call_count == 0 and run.lfs.call_count == 0 and run.parser.call_count == 0

        for extra in ([], ["--best-effort"]):
            run = _run_cli([str(source), "--out", str(out), "--project", "Modern", *extra])
            assert run.code == 0, (extra, run.code, run.text)
            digest, support = _digest_support(out)
            # The selected project's root JSON decides, even though its asset bytes name another engine.
            assert support["classification"] == "target", (extra, support)
            assert support["engine_association"] == "5.8" and support["declared_version"] == "5.8", support
            assert support["allowed"] is True and support["best_effort_used"] is False, support
            assert support["best_effort_requested"] is bool(extra), support
            assert digest["source"].get("engine") == "5.8", digest["source"].get("engine")
            assert run.classify.call_count == 1, "the supported project's assets were not classified"
