"""Bounded reading map and per-document context, derived from saved asset references.

PageRank is implemented directly from the published algorithm; no graph dependency.
Name mentions are navigation hints, never evidence of a runtime call or dependency.
"""
from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from pathlib import PurePosixPath
from urllib.parse import quote

INDEX_BYTES = 9_000  # roughly 2–4k tokens; actual tokenizer/language may differ
WORDS = re.compile(r"[^\W\d]\w*", re.UNICODE)
ASSET_PATH = re.compile(r"/[\w-]+(?:/[\w-]+)+", re.UNICODE)


def pagerank(edges, seeds=(), damping=0.85):
    nodes = sorted(edges)
    if not nodes:
        return {}
    weights = {node: 5.0 if node in seeds else 1.0 for node in nodes}
    total = sum(weights.values())
    weights = {node: weight / total for node, weight in weights.items()}
    scores = dict(weights)
    node_set = set(nodes)
    links = {node: sorted(set(edges[node]) & node_set - {node}) for node in nodes}
    for _ in range(100):
        dangling = sum(scores[node] for node in nodes if not links[node])
        next_scores = {node: (1 - damping + damping * dangling) * weights[node] for node in nodes}
        for node in nodes:
            if links[node]:
                share = damping * scores[node] / len(links[node])
                for target in links[node]:
                    next_scores[target] += share
        delta = sum(abs(scores[node] - next_scores[node]) for node in nodes)
        scores = next_scores
        if delta < 1e-10:
            break
    return scores


def short(value, limit=100):
    value = re.sub(r"\s+", " ", str(value)).strip()
    value = re.sub(r"[\[\]<>`|\\]", "", value)
    return value if len(value) <= limit else value[:limit - 1] + "…"


def link(doc, label=None, origin="INDEX.md"):
    relative = posixpath.relpath(doc, posixpath.dirname(origin) or ".")
    return f"[{short(label or PurePosixPath(doc).stem, 70)}](<{quote(relative, safe='/.-_')}>)"


def repair_catalog_links(out):
    """A full catalog can split; keep INDEX's section links on the actual part."""
    targets = {}
    for path in [out / "CATALOG.md", *sorted(out.glob("CATALOG.part*.md"))]:
        if not path.is_file():
            continue
        for heading in re.findall(r"^## (.+)$", path.read_text(encoding="utf-8"), re.M):
            targets[heading.lower().replace(" ", "-")] = path.name
    index = out / "INDEX.md"
    text = index.read_text(encoding="utf-8")
    text = re.sub(r"CATALOG\.md#([a-z-]+)", lambda m: targets.get(m[1], "CATALOG.md") + "#" + m[1], text)
    index.write_text(text, encoding="utf-8")


def graph(bps, datas, levels, cpp, config):
    nodes, names, paths = {}, defaultdict(set), defaultdict(set)
    for folder, kind, group in (("blueprints", "Blueprint", bps), ("data", "data", datas), ("maps", "map", levels)):
        for gp, value in sorted(group.items()):
            doc = folder + gp + ".md"
            nodes[doc] = {"path": gp, "kind": kind, "summary": value["summary"], "markdown": value["markdown"]}
            paths[gp].add(doc)
            name = gp.rsplit("/", 1)[-1]
            names[name].add(doc)
            if folder == "blueprints":
                names[name + "_C"].add(doc)
    if cpp.get("classes"):
        doc = "cpp/CLASSES.md"
        nodes[doc] = {"path": "project C++ types", "kind": "C++", "summary": {}, "markdown": ""}
        for cls in cpp["classes"]:
            name = cls["name"]
            names[name].add(doc)
            names[re.sub(r"^[AUF](?=[A-Z])", "", name)].add(doc)

    def resolve(value):
        exact = set()
        package_paths = ASSET_PATH.findall(str(value))
        for path in package_paths:
            candidates = paths.get(path, ())
            if len(candidates) == 1:
                exact.update(candidates)
        if package_paths and not str(value).startswith("/Script/"):
            return exact
        matches = set()
        for word in WORDS.findall(str(value)):
            candidates = names.get(word, ())
            if len(candidates) == 1:
                matches.update(candidates)
        return matches

    edges = {doc: {} for doc in nodes}
    for doc, value in nodes.items():
        summary = value["summary"]
        structured = [summary.get("parent", ""), summary.get("game_mode", "")]
        for field in ("interfaces", "references", "calls", "mapped_actions"):
            structured.extend(summary.get(field) or [])
        structured.extend((summary.get("placed_classes") or {}).keys())
        for ref in structured:
            for target in resolve(ref) - {doc}:
                edges[doc].setdefault(target, set()).add("saved reference/name")
        # Exact package paths disambiguate duplicates; bare names must be unique.
        bare_text = re.sub(ASSET_PATH.pattern + r"(?:\.\w+)?", " ", value["markdown"])
        for ref in [*ASSET_PATH.findall(value["markdown"]), *set(WORDS.findall(bare_text))]:
            for target in resolve(ref) - {doc}:
                edges[doc].setdefault(target, set()).add("name mention")
    entries = {key: sorted(resolve(value)) for key, value in sorted(config.items())}
    seeds = {doc for docs in entries.values() for doc in docs}
    scores = pagerank(edges, seeds)
    order = sorted(nodes, key=lambda doc: (-scores[doc], doc))
    incoming = {doc: [] for doc in nodes}
    for source in sorted(edges):
        for target in edges[source]:
            incoming[target].append(source)
    records = {}
    for rank, doc in enumerate(order, 1):
        records[doc] = {"rank": rank, "score": round(scores[doc], 10), "path": nodes[doc]["path"],
                        "kind": nodes[doc]["kind"], "incoming": sorted(incoming[doc]),
                        "outgoing": {target: sorted(reasons) for target, reasons in sorted(edges[doc].items())}}
    return records, entries


def build_navigation(meta, cpp, bps, failures, datas, data_failures, levels, map_failures, lfs, out):
    catalog = (out / "INDEX.md").read_text(encoding="utf-8")
    (out / "CATALOG.md").write_text(catalog, encoding="utf-8")
    config = meta.get("config") or {}
    records, entries = graph(bps, datas, levels, cpp, config)
    document_summaries = {folder + gp + ".md": result["summary"]
                          for folder, group in (("blueprints", bps), ("data", datas), ("maps", levels))
                          for gp, result in group.items()}
    summaries = [result["summary"] for group in (bps, datas, levels) for result in group.values()]
    issues = sum(len(s.get("issues") or []) for s in summaries)
    partial = sum(s.get("parse_status", "ok") != "ok" for s in summaries)
    newer = sum(bool(s.get("newer_format")) for s in summaries)
    enum_unknown = sum(s.get("enum_resolution", {}).get("unresolved", 0) for s in summaries)
    level_bad = sum(s["summary"].get("level_bp_status") != "ok" for s in levels.values())
    external_bad = sum(sum(s["summary"].get(field, 0) for field in
                          ("external_actor_errors", "external_actors_truncated", "external_actors_not_downloaded"))
                       for s in levels.values())
    coverage = re.search(r"Coverage: .*", catalog).group(0)
    parse_bad = issues or partial or newer or level_bad or external_bad or failures or data_failures or map_failures or lfs.get("failed") or enum_unknown
    clean = not parse_bad and all(r["summary"].get("nodes_ok") == r["summary"].get("nodes_total") for r in bps.values())
    md = [short(catalog.splitlines()[0], 140), "", "Read this map first, then follow links for the question at hand.",
          short(next((line for line in catalog.splitlines() if line.startswith("source:")), ""), 240),
          short(next((line for line in catalog.splitlines() if line.startswith("engine (")), ""), 180), "",
          "## Coverage and limits", "", "- " + coverage,
          f"- Rendered: {len(datas)} data assets, {len(levels)} maps, {len(cpp.get('classes') or [])} C++ types.",
          f"- Failed: {len(failures)} Blueprints, {len(data_failures)} data assets, {len(map_failures)} maps.",
          f"- Partial assets: {partial}; parse/render issues: {issues}; newer formats: {newer}; "
          f"incomplete Level Blueprints: {level_bad}; missing/failed/truncated external actors: {external_bad}.",
          f"- Unresolved enum labels: {enum_unknown} rendered values (saved names/numbers retained).",
          ("- everything decoded cleanly (rendered assets)." if clean else
           "- ⚠ Coverage is incomplete. Read the full parse report and each affected document's Parse warnings."),
          f"- LFS: {lfs.get('failed', 0)} download failures, {lfs.get('skipped_large', 0)} skipped large/non-asset files; "
          f"git size filter skipped {(meta.get('skipped_large_files') or {}).get('count', 0)} files; "
          f"{meta.get('external_objects', 0)} external-object packages counted only.",
          f"- Unsupported asset types are counted in the catalog, not decoded. Selected project only; "
          f"{len(meta.get('other_projects') or [])} other projects.",
          "- [Full parse report](<CATALOG.md#parse-report>) · [All catalogs and notation](<CATALOG.md>). "
          "Follow continuation parts when a document is split.", "", "## Configured entry points", ""]
    entry_bytes = 0
    for key, value in sorted(config.items()):
        targets = entries[key]
        row = f"- {short(key, 50)}: " + (", ".join(link(doc) for doc in targets[:3]) if targets else
                                      f"`{short(value, 130)}` (no rendered document)")
        entry_bytes += len(row.encode("utf-8"))
        if entry_bytes > 1_600:
            md.append("- More entry settings: [full Project section](<CATALOG.md#project>).")
            break
        md.append(row)
    if not config:
        md.append("- No entry-point settings found in DefaultEngine/DefaultInput.ini.")
    md += ["", "## Reading priority", "",
           "PageRank over saved references and unique-name mentions (damping 0.85; configured entries get 5× seed weight). "
           "This suggests reading order; it does not establish runtime calls, dependencies or gameplay importance. "
           "Duplicate short names are left unresolved. In/out counts refer to this static document graph.", "",
           "| Rank | Document | Kind | In / out | Score |", "|---|---|---|---|---|"]
    tail = ["", "## Follow the context", "",
            "Each asset document starts with its path, parse status, rank and nearby incoming/outgoing document links. "
            "Those links mix saved references and name mentions; confirm behavior in the actual graphs or sources. "
            "Ranks cover every rendered asset; this page shows only a bounded selection. "
            "Use [CATALOG.md](<CATALOG.md>) for every map, Blueprint, data asset, C++ mapping, Enhanced Input check and GameplayTag summary.", "",
            "## Pseudo-code quick key", "",
            "- `event`, `input`, `function F(...) -> Out: T`: entry points; `return <value>`: function outputs.",
            "- `Target.Func(Arg=value)`: executed statement with inlined data inputs. `#N = Func(...)`: reused impure output; "
            "`$N`: shared pure expression in the graph's `// where` block.",
            "- `[true]`, `[cast ok]`, `[LoopBody]`: execution branches. `→ goto #N` joins the line marked `[#N]`. "
            "`Pin=∅` is an unconnected object input; `⚠ disconnected execution chains` marks disconnected flow.",
            "- Anim pose trees use `←`; transitions use `A → B when <rule>`. `when auto (...)` waits for the current "
            "animation to finish; `when never` is constant False. Flags describe saved function/variable settings.",
            "- Saved data is static. Missing values after a parse failure are unknown; an unreadable Level Blueprint "
            "is unknown, not empty. Node N/N counts decoded pins only. Read Parse warnings even at N/N.",
            "- `Map<K, V>` shows key/value types; `?` in a type means unspecified or unreadable, with no concrete type inferred.",
            "- `…(+N)` counts entries/fields omitted by compact display. CDO previews also count opaque/native values and "
            "unexpanded subobjects. Omitted values are unknown here, not defaults; a display notice is not a parse failure.",
            "- Map tables are previews; full decoded actor/root-component saved properties: `digest.json` → `maps_detail[map_path].actors`.",
            "  Check `properties_status`: partial actor records are incomplete; absent properties are unknown, not defaults.",
            '- Typed data-asset enum arrays use `Enum::Enumerator(number, display="Label")`. '
            'Unresolved values retain their saved name/number; ordinary byte arrays stay numeric.',
            "- `// Function metadata` / `// Function tooltip` describe saved Category, CallInEditor and ToolTip on function entries. "
            "They are descriptive comments; absent fields are not inferred.",
            "- [Full legend](<CATALOG.md#how-to-read-this-digest>) · [C++ index](<cpp/CLASSES.md>): "
            "read real C++ sources for implementations. Skip `digest.json` when reading; it repeats facts for scripts.", ""]
    shown = 0
    for doc, record in records.items():
        row = f"| {record['rank']} | {link(doc)} | {record['kind']} | {len(record['incoming'])} / {len(record['outgoing'])} | {record['score']:.4f} |"
        if shown >= 30 or len("\n".join(md + [row] + tail).encode("utf-8")) > INDEX_BYTES - 250:
            continue
        md.append(row)
        shown += 1
    md += [f"\nShowing {shown}/{len(records)} documents. Full list: [CATALOG.md](<CATALOG.md>)."] + tail
    text = "\n".join(md) + "\n"
    # Ordinary INDEX is about 2–4k tokens; small projects naturally need fewer.
    # Pathological config values/paths cannot grow it indefinitely.
    if len(text.encode("utf-8")) > INDEX_BYTES:
        start = md.index("## Configured entry points")
        end = md.index("## Reading priority")
        md[start + 1:end] = ["", "Entry settings exceed the reading budget; see [Project](<CATALOG.md#project>).", ""]
        text = "\n".join(md) + "\n"
    (out / "INDEX.md").write_text(text, encoding="utf-8")

    for doc, record in records.items():
        path = out / doc
        if not path.is_file():
            continue
        def nearby(docs):
            ordered = sorted(docs, key=lambda d: (records[d]["rank"], d))
            return ", ".join(link(d, origin=doc) for d in ordered[:4]) or "none resolved"
        status = document_summaries.get(doc, {}).get("parse_status", "source index")
        header = (f"> Reading context: `{record['path']}` · {record['kind']} · parse: {status} · rank {record['rank']}/{len(records)}.\n"
                  f"> Incoming ({len(record['incoming'])}): {nearby(record['incoming'])}.\n"
                  f"> Outgoing ({len(record['outgoing'])}): {nearby(record['outgoing'])}.\n"
                  f"> Static saved references/name mentions; confirm in content. {link('INDEX.md', 'Reading map', doc)} · "
                  f"{link('CATALOG.md', 'Full catalog', doc)}\n\n")
        body = path.read_text(encoding="utf-8")
        first, separator, rest = body.partition("\n")
        path.write_text(first + separator + "\n" + header + rest, encoding="utf-8")
    return {"method": "PageRank + configured-entry seeds; saved references and unique-name mentions",
            "damping": 0.85, "seed_weight": 5, "documents": records}
