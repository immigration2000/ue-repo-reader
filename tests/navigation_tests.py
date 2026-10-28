"""Reading-map ranking, honest reference resolution, bounded output and split links."""
import copy
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote

import navigation as N
import ue_repo_digest as D


def asset(gp, markdown="", **summary):
    return {"summary": {"path": gp, "parse_status": "ok", "issues": [], "nodes_ok": 1, "nodes_total": 1,
                        **summary}, "markdown": "# " + gp + "\n" + markdown}


def test_pagerank_order_seeds_and_dangling_nodes():
    edges = {"A": {"Hub"}, "B": {"Hub"}, "Hub": {"End"}, "End": {"Hub"}, "Isolated": set()}
    scores = N.pagerank(edges)
    assert scores["Hub"] > scores["A"] and scores["Hub"] > scores["End"]
    assert abs(sum(scores.values()) - 1) < 1e-9
    assert scores == N.pagerank(dict(reversed(list(edges.items()))))
    assert N.pagerank({}) == {}
    assert N.pagerank({"a": [], "b": []}) == {"a": .5, "b": .5}
    seeded = N.pagerank({"a": [], "b": []}, {"a"})
    assert seeded["a"] > seeded["b"]


def test_navigation_resolves_unique_and_explicit_references():
    bps = {gp: asset(gp) for gp in ("/Game/One/Duplicate", "/Game/Two/Duplicate", "/Game/Source", "/Game/Child")}
    bps["/Game/Source"] = asset("/Game/Source", "Duplicate /Game/One/Duplicate and /Unknown/Child", calls=["SNative.Run"])
    bps["/Game/Child"] = asset("/Game/Child", parent="Source_C")
    maps = {"/Game/Map": asset("/Game/Map", placed_classes={"Child_C": 1})}
    datas = {"/Game/Data": asset("/Game/Data", references=["Child"])}
    cpp = {"classes": [{"name": "ASNative"}]}
    records, entries = N.graph(bps, datas, maps, cpp, {"GameDefaultMap": "/Game/Map.Map"})
    source = records["blueprints/Game/Source.md"]["outgoing"]
    assert "blueprints/Game/One/Duplicate.md" in source
    assert "blueprints/Game/Two/Duplicate.md" not in source, "ambiguous short name guessed"
    assert "blueprints/Game/Child.md" not in source, "unknown exact path fell back to a bare name"
    assert "cpp/CLASSES.md" in source
    assert "blueprints/Game/Source.md" in records["blueprints/Game/Child.md"]["outgoing"]
    assert "blueprints/Game/Child.md" in records["maps/Game/Map.md"]["outgoing"]
    assert entries["GameDefaultMap"] == ["maps/Game/Map.md"]
    assert records == N.graph(copy.deepcopy(bps), datas, maps, cpp, {"GameDefaultMap": "/Game/Map.Map"})[0]


def test_navigation_budget_context_and_warnings():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        bps = {f"/Game/캐릭터/BP_{i}": asset(f"/Game/캐릭터/BP_{i}", "BP_0 BP_1") for i in range(300)}
        bps["/Game/캐릭터/BP_0"]["summary"].update(parse_status="partial", issues=[{"stage": "property"}])
        for gp, value in bps.items():
            path = out / ("blueprints" + gp + ".md")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value["markdown"] + "\n## Placed in levels\nMap ×2\n", encoding="utf-8")
        catalog = "# Project\nsource: fixture\nengine (EngineAssociation): 5.8\nCoverage: 300 Blueprints rendered, 0 failed; graph nodes decoded 300/300.\n"
        catalog += "\n".join(bps) + "\n## Parse report\nproperty failed\n"
        (out / "INDEX.md").write_text(catalog, encoding="utf-8")
        meta = {"config": {f"Setting_{i}": "매우긴값" * 300 for i in range(30)}}
        nav = N.build_navigation(meta, {}, bps, {}, {}, {"/Game/Broken": "failed"}, {}, {}, {}, out)
        index = (out / "INDEX.md").read_text(encoding="utf-8")
        assert len(index.encode("utf-8")) <= N.INDEX_BYTES
        assert "Coverage is incomplete" in index and "everything decoded cleanly" not in index
        assert "parse/render issues: 1" in index and "1 data assets" in index
        assert len(nav["documents"]) == 300 and (out / "CATALOG.md").read_text(encoding="utf-8") == catalog
        assert "Reading context" not in bps["/Game/캐릭터/BP_0"]["markdown"], "header polluted cacheable result"
        ranks = {r["rank"] for r in nav["documents"].values()}
        assert ranks == set(range(1, 301))
        for doc in nav["documents"]:
            body = (out / doc).read_text(encoding="utf-8")
            assert "Reading context" in body and "Placed in levels" in body
            for target in re.findall(r"\]\(<([^>]+)>\)", body):
                assert ((out / doc).parent / unquote(target)).is_file(), (doc, target)


def test_navigation_split_catalog_anchors_and_rerun():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        (out / "INDEX.md").write_text("[report](<CATALOG.md#parse-report>)", encoding="utf-8")
        (out / "CATALOG.md").write_text("## Project\n" + "a line of catalog\n" * 200 + "## Parse report\nfailed\n", encoding="utf-8")
        D.split_large_markdown(out, limit=1200)
        N.repair_catalog_links(out)
        index = (out / "INDEX.md").read_text(encoding="utf-8")
        target = re.search(r"<([^#]+)#parse-report>", index)[1]
        assert target != "CATALOG.md" and "## Parse report" in (out / target).read_text(encoding="utf-8")
        (out / "digest.json").write_text('{"tool":"ue-repo-reader 1.7.0"}', encoding="utf-8")
        # Validate with a distinct input; only recognized catalog parts are accepted.
        assert D.validate_output_dir(out, out.parent / "input") == out.resolve()
        (out / "notes.md").write_text("user notes", encoding="utf-8")
        try:
            D.validate_output_dir(out, out.parent / "input")
        except ValueError:
            pass
        else:
            raise AssertionError("unrelated Markdown accepted for replacement")
