#!/usr/bin/env python3
"""ue_repo_digest — turn an Unreal Engine git repo (URL or local path) into an AI-readable digest.

No Unreal Editor or engine install needed. Blueprints are decoded straight from the
binary .uasset files and rendered as pseudo-code; C++, config and content are indexed.

    python ue_repo_digest.py https://github.com/owner/Project [--ref main] [--out ./Project_digest]
    python ue_repo_digest.py D:/Work/MyProject

Output (in --out):
    INDEX.md                 start here: project overview, Blueprint catalog, C++<->BP map, parse report
    blueprints/<path>.md     one file per Blueprint (components, variables, defaults, graphs as pseudo-code)
    cpp/CLASSES.md           C++ UCLASS/USTRUCT/UENUM index with Blueprint-exposed API
    digest.json              machine-readable summary of everything above
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import multiprocessing as mp
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

VERSION = "1.3.0"
LFS_MAGIC = b"version https://git-lfs"
BP_MARKERS = re.compile(rb"(WidgetBlueprintGeneratedClass|AnimBlueprintGeneratedClass|BlueprintGeneratedClass)")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run(cmd, cwd=None, env=None, check=True):
    return subprocess.run(cmd, cwd=cwd, env=env, check=check, text=True, capture_output=True,
                          encoding="utf-8", errors="replace")


# =========================================================================== fetch

def looks_like_url(s: str) -> bool:
    return bool(re.match(r"^(https?://|git@|ssh://|file://)", s)) or s.endswith(".git")


def clone(url: str, dest: Path, ref: str | None) -> dict:
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1", GIT_TERMINAL_PROMPT="0")
    if dest.exists() and (dest / ".git").exists():
        log(f"[fetch] reusing existing clone at {dest}")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        is_sha = bool(ref and re.fullmatch(r"[0-9a-f]{7,40}", ref))
        cmd = ["git", "clone", "--depth", "1", "--no-tags"]
        if ref and not is_sha:
            cmd += ["--branch", ref]
        log(f"[fetch] cloning {url} ...")
        run(cmd + [url, str(dest)], env=env)
        if is_sha:
            run(["git", "-C", str(dest), "fetch", "--depth", "1", "origin", ref], env=env)
            run(["git", "-C", str(dest), "checkout", "-q", "FETCH_HEAD"], env=env)
    info = {"url": url, "ref": ref}
    try:
        info["commit"] = run(["git", "-C", str(dest), "rev-parse", "HEAD"]).stdout.strip()
        info["branch"] = run(["git", "-C", str(dest), "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        info["commit_date"] = run(["git", "-C", str(dest), "log", "-1", "--format=%cI"]).stdout.strip()
    except Exception:
        pass
    return info


def lfs_pointer_size(p: Path) -> int | None:
    try:
        if p.stat().st_size > 1024:
            return None
        data = p.read_bytes()
    except OSError:
        return None
    if not data.startswith(LFS_MAGIC):
        return None
    m = re.search(rb"size (\d+)", data)
    return int(m.group(1)) if m else 0


def pull_lfs(repo: Path, paths: list[Path], max_mb: float, map_max_mb: float = 64.0) -> dict:
    """Download LFS objects for small .uasset files and for maps (Blueprints/data are small; textures/meshes are not)."""
    report = {"pointers": 0, "requested": 0, "skipped_large": 0, "failed": 0, "error": None, "bytes": 0}
    wanted = []
    for p in paths:
        size = lfs_pointer_size(p)
        if size is None:
            continue
        report["pointers"] += 1
        ext = p.suffix.lower()
        limit = map_max_mb if ext == ".umap" else max_mb
        if ext not in (".uasset", ".umap") or size > limit * 1024 * 1024:
            report["skipped_large"] += 1
            continue
        wanted.append(p.relative_to(repo).as_posix())
        report["bytes"] += size
    report["requested"] = len(wanted)
    if not wanted:
        return report
    if shutil.which("git-lfs") is None and run(["git", "lfs", "version"], check=False).returncode != 0:
        report["error"] = "git-lfs is not installed — LFS-stored assets could not be downloaded"
        report["failed"] = len(wanted)
        return report
    log(f"[lfs] downloading {len(wanted)} .uasset/.umap files ({report['bytes'] / 1e6:.1f} MB) ...")
    batch, length = [], 0
    batches = []
    for w in wanted:
        if batch and length + len(w) > 6000:
            batches.append(batch)
            batch, length = [], 0
        batch.append(w)
        length += len(w) + 1
    if batch:
        batches.append(batch)
    for b in batches:
        # LFS include patterns are globs; escape glob metacharacters in literal paths
        pats = ",".join(re.sub(r"([\[\]\*\?])", r"\\\1", x) for x in b)
        r = run(["git", "-C", str(repo), "lfs", "pull", "--include", pats], check=False)
        if r.returncode != 0:
            report["error"] = (r.stderr or r.stdout).strip()[-400:]
    report["failed"] = sum(1 for w in wanted if lfs_pointer_size(repo / w) is not None)
    return report


# =========================================================================== project inventory

def find_uprojects(root: Path) -> list[Path]:
    found = []
    for p in root.rglob("*.uproject"):
        rel = p.relative_to(root).parts
        if any(part.startswith(".") or part in ("Intermediate", "Saved", "Binaries") for part in rel):
            continue
        found.append(p)
    return sorted(found, key=lambda p: (len(p.relative_to(root).parts), str(p)))


def pick_uproject(root: Path, want: str | None) -> tuple[Path | None, list[Path]]:
    all_ = find_uprojects(root)
    if want:
        for p in all_:
            if want in (p.stem, p.name) or Path(want).as_posix() in p.relative_to(root).as_posix():
                return p, all_
        raise SystemExit(f"--project {want!r} not found. Projects in repo: " +
                         ", ".join(p.relative_to(root).as_posix() for p in all_))
    return (all_[0] if all_ else None), all_


def read_ini_values(path: Path, keys: list[str]) -> dict:
    out = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        for k in keys:
            if line.startswith(k + "="):
                out.setdefault(k, line.split("=", 1)[1].strip())
    return out


def mount_points(proj: Path) -> list[tuple[Path, str]]:
    """(Content dir, mount prefix) pairs: project Content -> /Game, plugin Content -> /<Plugin>."""
    mounts = []
    if (proj / "Content").is_dir():
        mounts.append((proj / "Content", "/Game"))
    for up in sorted((proj / "Plugins").rglob("*.uplugin")) if (proj / "Plugins").is_dir() else []:
        c = up.parent / "Content"
        if c.is_dir():
            mounts.append((c, "/" + up.stem))
    return mounts


def game_path(asset: Path, mounts) -> str:
    for content, prefix in mounts:
        try:
            rel = asset.relative_to(content)
        except ValueError:
            continue
        return prefix + "/" + rel.with_suffix("").as_posix()
    return asset.stem


_UCLASS = re.compile(r"^[ \t]*(UCLASS|USTRUCT|UENUM|UINTERFACE)\s*\(((?:[^()]|\((?:[^()]|\([^()]*\))*\))*)\)\s*(?:\n|\s)*"
                     r"(?:class|struct|enum(?:\s+class)?)\s+(?:\w+_API\s+)?(\w+)(?:\s*(?:final)?\s*:\s*(?:public\s+)?(\w+))?", re.M)
_UFUNC = re.compile(r"^[ \t]*UFUNCTION\s*\(((?:[^()]|\([^()]*\))*)\)\s*\n?\s*(?:static\s+|virtual\s+|FORCEINLINE\s+|const\s+)*"
                    r"([\w:<>,\s\*&]+?)\s+(\w+)\s*\(", re.M)
_UPROP = re.compile(r"^[ \t]*UPROPERTY\s*\(((?:[^()]|\([^()]*\))*)\)\s*\n?\s*([\w:<>,\s\*&]+?)\s+(\w+)\s*(?:[=;{\[]|:\s*1)", re.M)


def scan_cpp(proj: Path) -> dict:
    roots = [proj / "Source"] + ([p for p in (proj / "Plugins").glob("*/Source")] if (proj / "Plugins").is_dir() else [])
    modules, classes = [], []
    for root in roots:
        if not root.is_dir():
            continue
        for bc in root.rglob("*.Build.cs"):
            try:
                t = bc.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            deps = sorted(set(re.findall(r'"(\w+)"', " ".join(re.findall(r"DependencyModuleNames\.AddRange\([^;]*;", t, re.S)))))
            modules.append({"name": bc.name[: -len(".Build.cs")], "path": bc.parent.relative_to(proj).as_posix(), "deps": deps})
        for h in root.rglob("*.h"):
            try:
                text = h.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "UCLASS" not in text and "USTRUCT" not in text and "UENUM" not in text and "UINTERFACE" not in text:
                continue
            matches = list(_UCLASS.finditer(text))
            for i, m in enumerate(matches):
                kind, spec, name, parent = m.group(1), m.group(2), m.group(3), m.group(4)
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                body = text[start:end]
                funcs, props = [], []
                for f in _UFUNC.finditer(body):
                    sp = re.sub(r"\s+", " ", f.group(1)).strip()
                    if re.search(r"Blueprint|Server|Client|NetMulticast|Exec", sp):
                        funcs.append({"name": f.group(3), "ret": re.sub(r"\s+", " ", f.group(2)).strip(), "spec": sp})
                for pm in _UPROP.finditer(body):
                    sp = re.sub(r"\s+", " ", pm.group(1)).strip()
                    if re.search(r"Blueprint|Edit|Visible|Replicated|Config", sp):
                        props.append({"name": pm.group(3), "type": re.sub(r"\s+", " ", pm.group(2)).strip(), "spec": sp})
                if kind == "UENUM":
                    vals = re.findall(r"^\s*(\w+)\s*(?:=\s*[^,\n]+)?\s*(?:UMETA\([^)]*\))?\s*,?\s*$", body.split("}")[0], re.M)
                    props = [{"name": v, "type": "", "spec": ""} for v in vals if v not in ("enum", "class")][:40]
                classes.append({"kind": kind, "name": name, "parent": parent or "", "spec": re.sub(r"\s+", " ", spec).strip(),
                                "file": h.relative_to(proj).as_posix(), "functions": funcs, "properties": props})
    return {"modules": modules, "classes": classes}


def cpp_markdown(cpp: dict) -> str:
    out = ["# C++ index", "", "Blueprint-relevant surface of the project's C++ (UFUNCTION/UPROPERTY with Blueprint, Edit,",
           "Replicated or RPC specifiers). Parsed with regexes from headers — open the file for the exact code.", ""]
    if cpp["modules"]:
        out += ["## Modules", ""]
        for m in cpp["modules"]:
            out.append(f"- **{m['name']}** (`{m['path']}`) deps: {', '.join(m['deps']) or '—'}")
        out.append("")
    for kind, title in (("UCLASS", "Classes"), ("UINTERFACE", "Interfaces"), ("USTRUCT", "Structs"), ("UENUM", "Enums")):
        items = [c for c in cpp["classes"] if c["kind"] == kind]
        if not items:
            continue
        out += [f"## {title} ({len(items)})", ""]
        for c in sorted(items, key=lambda c: c["name"]):
            head = f"### {c['name']}" + (f" : {c['parent']}" if c["parent"] else "")
            out += [head, f"`{c['file']}`" + (f" · {kind}({c['spec']})" if c["spec"] else "")]
            if kind == "UENUM":
                if c["properties"]:
                    out.append("values: " + ", ".join(p["name"] for p in c["properties"]))
            else:
                for f in c["functions"]:
                    out.append(f"- fn `{f['ret']} {f['name']}()` — {f['spec']}")
                for p in c["properties"]:
                    out.append(f"- prop `{p['type']} {p['name']}` — {p['spec']}")
            out.append("")
    return "\n".join(out) + "\n"


# =========================================================================== blueprint workers

def _worker_init():
    # Never raise here: a failing Pool initializer makes multiprocessing respawn workers forever.
    import logging
    logging.disable(logging.CRITICAL)
    try:
        import bp_reader
        bp_reader.ensure_uasset_read()
        bp_reader._install_patches()
    except Exception as e:  # noqa: BLE001 - surfaced per task instead
        print(f"[worker] setup failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)


def _classify(path):
    """Main asset class from header + export table only (bodies are not read)."""
    import importlib
    try:
        P = importlib.import_module("uasset_read.parse_uasset")
        from uasset_read.serializers.object_resources import get_asset_class
        r = P.parse_package_lazy(path)
        stem = Path(path).stem
        best = None
        for e in r.export_map or []:
            if getattr(e, "b_is_asset", False) or e.object_name == stem:
                cls = get_asset_class(e, r.import_map, r.export_map)
                if e.object_name == stem:
                    return path, cls or "?"
                best = best or cls
        return path, best or "?"
    except Exception:  # noqa: BLE001
        try:
            data = Path(path).read_bytes()
        except OSError:
            return path, "?"
        if BP_MARKERS.search(data) and b"K2Node" in data:
            return path, "Blueprint"
        return path, "?"


def classify_assets(paths, workers):
    ctx = mp.get_context("spawn")
    out = {}
    with ctx.Pool(processes=workers, initializer=_worker_init) as pool:
        for i, (p, cls) in enumerate(pool.imap_unordered(_classify, paths, chunksize=16), 1):
            out[p] = cls
            if i % 500 == 0:
                log(f"[scan] classified {i}/{len(paths)}")
    return out


DATA_CLASSES = {
    "DataTable", "CompositeDataTable", "UserDefinedStruct", "UserDefinedEnum", "InputAction", "InputMappingContext",
    "BehaviorTree", "BlackboardData", "StateTree", "CurveTable", "CurveFloat", "CurveVector", "CurveLinearColor",
    "PrimaryDataAsset", "DataAsset", "StringTable", "EnvQuery", "PlayerMappableInputConfig",
}


def is_data_class(cls: str, project_types: set) -> bool:
    return cls in DATA_CLASSES or cls in project_types or cls.endswith("DataAsset")


def _data_worker(args):
    path, gpath, cls = args
    import data_reader
    t = time.time()
    try:
        r = data_reader.read_data_asset(path, gpath, cls)
        r["seconds"] = round(time.time() - t, 2)
        return gpath, r, None
    except Exception as e:  # noqa: BLE001
        return gpath, None, f"{type(e).__name__}: {e}"


def _map_worker(args):
    path, gpath, externals = args
    import map_reader
    t = time.time()
    try:
        r = map_reader.read_map(path, gpath, externals)
        r["seconds"] = round(time.time() - t, 2)
        return gpath, r, None
    except Exception as e:  # noqa: BLE001
        return gpath, None, f"{type(e).__name__}: {e}"


def is_blueprint_class(cls: str) -> bool:
    return cls.endswith("Blueprint") and cls not in ("BlueprintGeneratedClass",)


def _worker(args):
    path, gpath = args
    import bp_reader
    t = time.time()
    try:
        r = bp_reader.read_blueprint(path, gpath)
        r["seconds"] = round(time.time() - t, 2)
        return gpath, r, None
    except Exception as e:  # noqa: BLE001
        return gpath, None, f"{type(e).__name__}: {e}"


def process_blueprints(items, workers: int, timeout: int, worker=None, label="bp"):
    results, failures = {}, {}
    if not items:
        return results, failures
    worker = worker or _worker
    ctx = mp.get_context("spawn")
    pool = ctx.Pool(processes=workers, initializer=_worker_init, maxtasksperchild=200)
    try:
        pending = {it[1]: pool.apply_async(worker, (it,)) for it in items}
        done = 0
        for gp, job in pending.items():
            try:
                _, res, err = job.get(timeout=timeout)
            except mp.TimeoutError:
                res, err = None, f"timed out after {timeout}s"
            except Exception as e:  # noqa: BLE001
                res, err = None, f"{type(e).__name__}: {e}"
            if res is not None:
                results[gp] = res
            else:
                failures[gp] = err
            done += 1
            if done % 25 == 0 or done == len(pending):
                log(f"[{label}] {done}/{len(pending)}")
    finally:
        pool.terminate()
        pool.join()
    return results, failures


# =========================================================================== index

_PREFIX_KINDS = [
    ("SM_", "Static Mesh"), ("SK_", "Skeletal Mesh"), ("T_", "Texture"), ("MI_", "Material Instance"),
    ("MF_", "Material Function"), ("M_", "Material"), ("NS_", "Niagara System"), ("NE_", "Niagara Emitter"),
    ("P_", "Particle System"), ("AM_", "Anim Montage"), ("BS_", "Blend Space"), ("A_", "Anim / Audio"),
    ("S_", "Sound / Struct"), ("SC_", "Sound Cue"), ("MSS_", "MetaSound"), ("DT_", "Data Table"),
    ("DA_", "Data Asset"), ("E_", "Enum"), ("F_", "Struct"), ("IA_", "Input Action"),
    ("IMC_", "Input Mapping Context"), ("PA_", "Physics Asset"), ("SKEL_", "Skeleton"), ("W_", "Widget"),
    ("WBP_", "Widget"), ("C_", "Curve"), ("Curve_", "Curve"), ("ST_", "State Tree"), ("BT_", "Behavior Tree"),
    ("BB_", "Blackboard"), ("EQS_", "EQS Query"), ("GE_", "Gameplay Effect"), ("GA_", "Gameplay Ability"),
    ("LS_", "Level Sequence"), ("PM_", "Physical Material"),
]


def asset_kind(name: str) -> str:
    for p, k in _PREFIX_KINDS:
        if name.startswith(p):
            return k
    return "other"


def build_index(meta, proj, cpp, bps, failures, other_assets, maps, lfs, out: Path, uproject, datas=None, data_failures=None,
                levels=None, map_failures=None, placed_in=None):
    datas = datas or {}
    data_failures = data_failures or {}
    levels = levels or {}
    map_failures = map_failures or {}
    placed_in = placed_in or {}
    md = []
    title = uproject.stem if uproject else Path(meta.get("url") or proj).stem
    src = meta.get("url") or str(proj)
    commit = (meta.get("commit") or "")[:10]
    engine = meta.get("engine") or "?"
    md += [f"# {title} — Unreal repo digest", "",
           f"source: {src}" + (f" @ `{commit}` ({meta.get('branch')}, {meta.get('commit_date', '')[:10]})" if commit else ""),
           f"engine (EngineAssociation): **{engine}** · generated {_dt.date.today().isoformat()} by ue-repo-reader {VERSION}",
           ""]
    total_nodes = sum(r["summary"]["nodes_total"] for r in bps.values())
    ok_nodes = sum(r["summary"]["nodes_ok"] for r in bps.values())
    md += ["## How to read this digest", "",
           "- Blueprints were decoded **directly from the binary .uasset files** (no editor). Each one has a file under",
           "  `blueprints/` that mirrors its content path. Graphs are rendered as pseudo-code of the execution flow:",
           "  - `event X(...)`, `custom event`, `input IA_X`, `on Comp.Delegate(...)`, `function F(...)` — entry points",
           "  - one statement per executed node; data inputs are inlined as expressions (`Target.Func(Arg=value)`)",
           "  - `#N = Func(...)` — an impure node whose output is used later as `#N` / `#N.PinName`",
           "  - `[true]:` / `[cast ok]:` / `[LoopBody]:` / `[then_1]:` — the named exec output a block runs from",
           "  - `→ goto #N` — execution merges into a node already shown; `[#N]` marks such merge targets",
           "  - `// ── text ──` — the comment box the following nodes sit in; `// text` — a node comment",
           "  - `∅` — input left unset; `⚠ disconnected execution chains` — nodes nothing can execute (dead code)",
           "  - Anim graphs: pose trees (`← Node`), state machines as `A → B when <rule>`",
           f"- Coverage: {len(bps)} Blueprints rendered, {len(failures)} failed; graph nodes decoded {ok_nodes}/{total_nodes}.",
           "  A Blueprint file says `⚠ N nodes unreadable` when part of a graph could not be decoded.",
           "- Maps are rendered under `maps/`: Level Blueprint, placed actors with per-instance overrides, game mode.",
           "  Blueprint files end with `Placed in levels` when instances of them are placed in a map.",
           "- Data assets (DataTables, structs, enums, Behavior Trees, StateTrees, input mappings, DataAssets) are",
           "  rendered under `data/` — see the Data assets table below.",
           "- C++ is summarized in `cpp/CLASSES.md`; read the real sources in the repo for implementation details.",
           "- This is a static read of saved assets: it cannot show runtime values, and names are the internal",
           "  node/function names (e.g. `K2_GetActorLocation`), not always the editor display titles.",
           ""]

    # project
    md += ["## Project", ""]
    if uproject:
        md.append(f"- uproject: `{uproject.name}`" + (f" (in `{proj.relative_to(proj.parents[len(proj.parents)-1]).as_posix()}`)" if False else ""))
    if meta.get("other_projects"):
        md.append(f"- ⚠ this repo holds {len(meta['other_projects']) + 1} projects; this digest covers only the one above. "
                  f"Others (re-run with `--project <path>`): " + ", ".join(f"`{x}`" for x in meta["other_projects"][:20])
                  + (" …" if len(meta["other_projects"]) > 20 else ""))
    if meta.get("modules"):
        md.append("- modules: " + ", ".join(f"{m.get('Name')} ({m.get('Type')})" for m in meta["modules"]))
    if meta.get("plugins"):
        md.append("- plugins enabled in .uproject: " + ", ".join(meta["plugins"]))
    if meta.get("local_plugins"):
        md.append("- plugins in repo: " + ", ".join(meta["local_plugins"]))
    for k, v in (meta.get("config") or {}).items():
        md.append(f"- {k} = `{v}`")

    md.append("")

    # maps
    if levels or map_failures:
        md += [f"## Maps ({len(levels)})", "",
               "Each map file under `maps/` has its game mode override, Level Blueprint, every placed gameplay actor",
               "(label, class, location, per-instance overrides) and an environment summary.", "",
               "| Map | Game mode override | Gameplay actors | Level Blueprint | Doc |", "|---|---|---|---|---|"]
        for gp in sorted(levels):
            s = levels[gp]["summary"]
            ok, tot = s.get("level_bp_nodes", (0, 0))
            lbp = ", ".join(dict.fromkeys(e.replace("custom event ", "ce ").replace("event ", "") for e in s["level_bp_entries"])) or ("—" if not tot else "")
            wp = " · World Partition" if s.get("world_partition") else ""
            md.append(f"| `{gp}`{wp} | {s['game_mode'] or '(project default)'} | {s['gameplay_count']} of {s['actor_count']} | "
                      f"{lbp.replace('|', '/')} | [md](<maps{gp}.md>) |")
        for gp, err in sorted(map_failures.items()):
            md.append(f"| `{gp}` | ⚠ not read: {err[:80]} |  |  |  |")
        md.append("")

    # blueprint catalog
    md += [f"## Blueprints ({len(bps)})", "", "| Blueprint | Kind | Parent | Entry points | Doc |", "|---|---|---|---|---|"]
    for gp in sorted(bps):
        s = bps[gp]["summary"]
        entries = ", ".join(dict.fromkeys(e.replace("custom event ", "ce ").replace("event ", "") for e in s["entries"]))
        if len(entries) > 90:
            entries = entries[:87] + "…"
        warn = " ⚠" if s["nodes_ok"] < s["nodes_total"] else ""
        doc = "blueprints" + gp + ".md"
        md.append(f"| `{gp}` | {s['kind']} | {s['parent']} | {entries.replace('|', '/')} | [md](<{doc}>){warn} |")
    md.append("")

    # C++ <-> BP
    cpp_names = {c["name"] for c in cpp["classes"]}
    cpp_names_stripped = {re.sub(r"^[AUFIE](?=[A-Z])", "", n): n for n in cpp_names}
    sub = defaultdict(list)
    calls = defaultdict(set)
    for gp, r in bps.items():
        s = r["summary"]
        par = s["parent"]
        if par in cpp_names_stripped or par in cpp_names:
            sub[cpp_names_stripped.get(par, par)].append(gp)
        for c in s["calls"]:
            cls, _, fn = c.partition("::")
            if cls in cpp_names_stripped:
                calls[f"{cpp_names_stripped[cls]}::{fn}"].add(gp.rsplit("/", 1)[-1])
    direct = {}
    for cls, where in placed_in.items():
        if cls in cpp_names_stripped:
            direct[cpp_names_stripped[cls]] = where
    if sub or calls or direct:
        md += ["## C++ ↔ Blueprint", ""]
        if direct:
            md.append("**Project C++ classes placed directly in maps**")
            md.append("")
            for k in sorted(direct):
                md.append(f"- `{k}` in " + ", ".join(f"{m} ×{n}" for m, n in sorted(direct[k].items())))
            md.append("")
        if sub:
            md.append("**Project C++ classes that Blueprints subclass**")
            md.append("")
            for k in sorted(sub):
                md.append(f"- `{k}` ← " + ", ".join(sorted(x.rsplit('/', 1)[-1] for x in sub[k])))
            md.append("")
        if calls:
            md.append("**Project C++ functions called from Blueprints**")
            md.append("")
            for k in sorted(calls):
                md.append(f"- `{k}` ← " + ", ".join(sorted(calls[k])))
            md.append("")

    # content overview
    folders = Counter()
    kinds = Counter()
    for gp, name, cls in other_assets:
        top = "/".join(gp.split("/")[:3])
        folders[top] += 1
        kinds[cls if cls != "?" else asset_kind(name) + " (by name)"] += 1
    md += ["## Content overview", "",
           f"{len(other_assets) + len(bps) + len(failures)} .uasset files · {len(maps)} maps · Blueprints {len(bps) + len(failures)}", ""]
    if kinds:
        md.append("non-Blueprint assets by class: " + ", ".join(f"{k} {v}" for k, v in kinds.most_common(40)))
        md.append("")
    if folders:
        md.append("largest folders: " + ", ".join(f"`{k}` {v}" for k, v in folders.most_common(15)))
        md.append("")

    # data assets
    if datas:
        md += [f"## Data assets ({len(datas)})", "",
               "DataTables (rows), structs (fields), enums (values), Behavior Trees (tree), StateTrees (state hierarchy),",
               "input mappings and DataAssets of project C++ types (saved properties) — each has a file under `data/`.", "",
               "| Asset | Class | Summary | Used by | Doc |", "|---|---|---|---|---|"]
        cpp_names = {re.sub(r"^[AUF](?=[A-Z])", "", c["name"]) for c in cpp["classes"]}
        order = {"DataTable": 0, "CompositeDataTable": 0, "UserDefinedStruct": 1, "UserDefinedEnum": 2}
        for gp in sorted(datas, key=lambda g: (order.get(datas[g]["summary"]["class"], 3 if datas[g]["summary"]["class"] in cpp_names else 4),
                                                datas[g]["summary"]["class"], g)):
            s = datas[gp]["summary"]
            used = ", ".join(s.get("used_by", [])[:6]) + (" …" if len(s.get("used_by", [])) > 6 else "")
            headline = s["headline"]
            if s.get("row_struct") and s["row_struct"] in cpp_names:
                headline += " (row struct in C++)"
            doc = "data" + gp + ".md"
            md.append(f"| `{gp}` | {s['class']} | {headline} | {used} | [md](<{doc}>) |")
        md.append("")

    # parse report
    md += ["## Parse report", ""]
    if lfs and lfs.get("pointers"):
        md.append(f"- Git LFS: {lfs['pointers']} LFS assets; downloaded {lfs['requested'] - lfs['failed']} .uasset/.umap files, "
                  f"skipped {lfs['skipped_large']} large/non-uasset files" + (f"; ⚠ {lfs['failed']} could not be downloaded" if lfs["failed"] else ""))
        if lfs.get("error"):
            md.append(f"  - LFS error: `{lfs['error'][:300]}`")
    partial = [(gp, r["summary"]) for gp, r in bps.items() if r["summary"]["nodes_ok"] < r["summary"]["nodes_total"]]
    if partial:
        md.append(f"- partially decoded Blueprints ({len(partial)}):")
        for gp, s in sorted(partial):
            md.append(f"  - `{gp}` {s['nodes_ok']}/{s['nodes_total']} nodes (saved with UE {s['saved_with']})")
    if map_failures:
        md.append(f"- maps that could not be read ({len(map_failures)}):")
        for gp, err in sorted(map_failures.items()):
            md.append(f"  - `{gp}` — {err[:200]}")
    if data_failures:
        md.append(f"- data assets that could not be read ({len(data_failures)}):")
        for gp, err in sorted(data_failures.items()):
            md.append(f"  - `{gp}` — {err[:200]}")
    if failures:
        md.append(f"- failed Blueprints ({len(failures)}):")
        for gp, err in sorted(failures.items()):
            md.append(f"  - `{gp}` — {err[:200]}")
    if not partial and not failures and not data_failures and not map_failures and not (lfs and lfs.get("failed")):
        md.append("- everything decoded cleanly")
    md.append("")
    (out / "INDEX.md").write_text("\n".join(md) + "\n", encoding="utf-8")


# =========================================================================== main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="git URL (https/ssh) or a local project directory")
    ap.add_argument("--ref", help="branch, tag or commit SHA to read (default: remote HEAD)")
    ap.add_argument("--out", help="output directory (default: ./<name>_digest)")
    ap.add_argument("--source-label", help="what to show as the source in INDEX.md (e.g. a URL without credentials)")
    ap.add_argument("--project", help="which .uproject to read when the repo holds several (name or relative path)")
    ap.add_argument("--workdir", help="where to clone (default: ./.ue-repo-reader/<name>)")
    ap.add_argument("--lfs-max-mb", type=float, default=8.0, help="only download LFS .uasset files up to this size (default 8)")
    ap.add_argument("--lfs-map-max-mb", type=float, default=64.0, help="only download LFS .umap files up to this size (default 64)")
    ap.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--timeout", type=int, default=90, help="seconds allowed per Blueprint (default 90)")
    ap.add_argument("--max-bp-mb", type=float, default=64.0, help="skip Blueprint candidates larger than this")
    a = ap.parse_args(argv)

    meta: dict = {}
    if looks_like_url(a.source):
        name = re.sub(r"\.git$", "", a.source.rstrip("/").split("/")[-1].split(":")[-1]) or "repo"
        repo = Path(a.workdir or Path.cwd() / ".ue-repo-reader" / name)
        meta.update(clone(a.source, repo, a.ref))
    else:
        repo = Path(a.source).resolve()
        if not repo.is_dir():
            ap.error(f"not a directory: {repo}")
        name = repo.name
        try:
            meta["commit"] = run(["git", "-C", str(repo), "rev-parse", "HEAD"]).stdout.strip()
            meta["branch"] = run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
            meta["commit_date"] = run(["git", "-C", str(repo), "log", "-1", "--format=%cI"]).stdout.strip()
        except Exception:
            pass
    if a.source_label:
        meta["url"] = a.source_label
    out = Path(a.out or Path.cwd() / f"{name}_digest").resolve()
    if out.exists():
        shutil.rmtree(out)
    (out / "blueprints").mkdir(parents=True)
    (out / "cpp").mkdir(parents=True)
    (out / "data").mkdir(parents=True)
    (out / "maps").mkdir(parents=True)

    uproject, all_projects = pick_uproject(repo, a.project)
    proj = uproject.parent if uproject else repo
    if len(all_projects) > 1:
        meta["other_projects"] = [p.relative_to(repo).as_posix() for p in all_projects if p != uproject]
        log(f"[warn] {len(all_projects)} .uproject files in repo; reading {uproject.relative_to(repo).as_posix()} "
            f"(choose another with --project)")
    if uproject:
        try:
            up = json.loads(uproject.read_text(encoding="utf-8-sig", errors="replace"))
            meta["engine"] = up.get("EngineAssociation") or "?"
            meta["modules"] = up.get("Modules") or []
            meta["plugins"] = [p.get("Name") for p in up.get("Plugins") or [] if p.get("Enabled")]
        except Exception as e:  # noqa: BLE001
            log(f"[warn] could not read {uproject.name}: {e}")
    else:
        log("[warn] no .uproject found — treating the repo root as the project")
    if (proj / "Plugins").is_dir():
        meta["local_plugins"] = sorted({p.stem for p in (proj / "Plugins").rglob("*.uplugin")})
    cfg = {}
    cfg.update(read_ini_values(proj / "Config" / "DefaultEngine.ini",
                               ["GameDefaultMap", "EditorStartupMap", "GlobalDefaultGameMode", "GameInstanceClass",
                                "GlobalDefaultServerGameMode"]))
    cfg.update(read_ini_values(proj / "Config" / "DefaultInput.ini", ["DefaultPlayerInputClass", "DefaultInputComponentClass"]))
    meta["config"] = cfg

    mounts = mount_points(proj)
    assets = [p for c, _ in mounts for p in c.rglob("*") if p.suffix.lower() in (".uasset", ".umap")]
    log(f"[scan] {len(assets)} assets under {len(mounts)} content roots")
    lfs = pull_lfs(repo, assets, a.lfs_max_mb, a.lfs_map_max_mb)

    maps, candidates, others = [], [], []
    local = []
    map_files = {}
    external = defaultdict(list)   # map path inside its content root -> external actor files
    external_pointer = defaultdict(int)
    n_external_objects = 0
    import map_reader
    for p in assets:
        gp = game_path(p, mounts)
        parts = p.as_posix().split("/")
        if "__ExternalActors__" in parts:
            key = None
            for content, prefix in mounts:
                try:
                    rel = p.relative_to(content).as_posix()
                except ValueError:
                    continue
                inner = map_reader.external_actor_map(rel)
                key = prefix + "/" + inner if inner else None
                break
            if key:
                if lfs_pointer_size(p) is not None:
                    external_pointer[key] += 1
                else:
                    external[key].append(str(p))
            continue
        if "__ExternalObjects__" in parts:
            n_external_objects += 1
            continue
        if p.suffix.lower() == ".umap":
            maps.append(gp)
            map_files[gp] = p
        elif lfs_pointer_size(p) is not None:
            others.append((gp, p.stem, "(not downloaded: Git LFS)"))
        else:
            local.append(p)
    cpp = scan_cpp(proj)
    (out / "cpp" / "CLASSES.md").write_text(cpp_markdown(cpp), encoding="utf-8")
    log(f"[cpp] {len(cpp['classes'])} reflected types in {len(cpp['modules'])} modules")
    project_types = {re.sub(r"^[AUF](?=[A-Z])", "", c["name"]) for c in cpp["classes"]}

    classes = classify_assets([str(p) for p in local], a.workers)
    data_items = []
    for p in local:
        gp = game_path(p, mounts)
        cls = classes.get(str(p), "?")
        if is_blueprint_class(cls) and p.stat().st_size <= a.max_bp_mb * 1024 * 1024:
            candidates.append((str(p), gp))
        else:
            others.append((gp, p.stem, cls))
            if is_data_class(cls, project_types) and p.stat().st_size <= a.max_bp_mb * 1024 * 1024:
                data_items.append((str(p), gp, cls))
    log(f"[scan] {len(candidates)} Blueprints, {len(data_items)} data assets, {len(maps)} maps, {len(others)} other assets")

    t0 = time.time()
    bps, failures = process_blueprints(candidates, a.workers, a.timeout)
    log(f"[bp] rendered {len(bps)} in {time.time() - t0:.1f}s, {len(failures)} failed")
    for gp, r in bps.items():
        dest = out / "blueprints" / (gp.lstrip("/") + ".md")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(r["markdown"], encoding="utf-8")

    t0 = time.time()
    datas, data_failures = process_blueprints(data_items, a.workers, a.timeout, worker=_data_worker, label="data")
    log(f"[data] rendered {len(datas)} in {time.time() - t0:.1f}s, {len(data_failures)} failed")
    # who uses each data asset: Blueprints mentioning it + data assets referencing it
    used_by = defaultdict(set)
    names = {gp.rsplit("/", 1)[-1]: gp for gp in datas}
    word = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    for gp, r in bps.items():
        for w in set(word.findall(r["markdown"])):
            if w in names and names[w] != gp:
                used_by[names[w]].add(gp.rsplit("/", 1)[-1])
    for gp, r in datas.items():
        for w in set(r["summary"].get("references", [])) | set(word.findall(r["markdown"])):
            if w in names and names[w] != gp:
                used_by[names[w]].add(gp.rsplit("/", 1)[-1])
    for gp, r in datas.items():
        r["summary"]["used_by"] = sorted(used_by.get(gp, []))
        md = r["markdown"]
        if r["summary"]["used_by"]:
            md += "\n## Used by\n" + ", ".join(f"`{u}`" for u in r["summary"]["used_by"]) + "\n"
        dest = out / "data" / (gp.lstrip("/") + ".md")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(md, encoding="utf-8")

    # maps: level blueprint, placed actors, world settings (+ World Partition external actors)
    def ext_for(gp):
        # external actor folders are keyed by the map path; match the longest map path prefix
        files = []
        for key, fl in external.items():
            if key == gp or key.startswith(gp + "/"):
                files.extend(fl)
        return files
    map_items = [(str(p), gp, ext_for(gp)) for gp, p in map_files.items() if lfs_pointer_size(p) is None]
    t0 = time.time()
    level_results, map_failures = process_blueprints(map_items, a.workers, a.timeout * 4, worker=_map_worker, label="map")
    for gp, p in map_files.items():
        if lfs_pointer_size(p) is not None:
            map_failures[gp] = "not downloaded (Git LFS: over --lfs-map-max-mb or LFS not accessible)"
    log(f"[map] rendered {len(level_results)} in {time.time() - t0:.1f}s, {len(map_failures)} failed")
    placed_in = defaultdict(Counter)  # class -> map -> count
    for gp, r in level_results.items():
        s = r["summary"]
        missing = sum(v for k, v in external_pointer.items() if k == gp or k.startswith(gp + "/"))
        if missing:
            s["external_actors_not_downloaded"] = missing
        for cls, n in s["placed_classes"].items():
            placed_in[cls][gp.rsplit("/", 1)[-1]] += n
        dest = out / "maps" / (gp.lstrip("/") + ".md")
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = r["markdown"]
        if missing:
            text += f"\n_⚠ {missing} external actor packages of this map were not downloaded (Git LFS) and are missing above._\n"
        dest.write_text(text, encoding="utf-8")
    for gp, r in bps.items():
        cls = gp.rsplit("/", 1)[-1] + "_C"
        if cls in placed_in:
            r["summary"]["placed_in"] = dict(placed_in[cls])
            dest = out / "blueprints" / (gp.lstrip("/") + ".md")
            with open(dest, "a", encoding="utf-8") as fh:
                fh.write("\n## Placed in levels\n" + ", ".join(f"`{m}` ×{n}" for m, n in sorted(placed_in[cls].items())) + "\n")
    meta["external_objects"] = n_external_objects

    build_index(meta, proj, cpp, bps, failures, others, maps, lfs, out, uproject, datas, data_failures,
                level_results, map_failures, placed_in)
    digest = {"tool": f"ue-repo-reader {VERSION}", "source": meta, "lfs": lfs,
              "blueprints": {gp: r["summary"] for gp, r in bps.items()}, "failures": failures,
              "data_assets": {gp: r["summary"] for gp, r in datas.items()}, "data_failures": data_failures,
              "maps_detail": {gp: r["summary"] for gp, r in level_results.items()}, "map_failures": map_failures,
              "maps": sorted(maps), "cpp": cpp}
    (out / "digest.json").write_text(json.dumps(digest, indent=1, ensure_ascii=False, default=list), encoding="utf-8")
    log(f"[done] {out / 'INDEX.md'}")
    print(str(out / "INDEX.md"))
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
