#!/usr/bin/env python3
"""ue_repo_digest — turn an Unreal Engine git repo (URL or local path) into an AI-readable digest.

No Unreal Editor or engine install needed. Blueprints are decoded straight from the
binary .uasset files and rendered as pseudo-code; C++, config and content are indexed.

    python ue_repo_digest.py https://github.com/owner/Project [--ref main] [--out ./Project_digest]
    python ue_repo_digest.py D:/Work/MyProject

Output (in --out):
    INDEX.md                 start here: bounded reading map, entry points, coverage and priority links
    CATALOG.md               complete catalogs, C++<->BP map, notation and parse report
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
import stat
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from project_support import assess_project, declaration_text, parse_descriptor, support_notice

VERSION = "1.16.0"
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


CLONE_BLOB_LIMIT_MB = 2  # blobs above this are left out of the clone (largest Blueprint seen in tests: 1.2 MB)
# Big .uasset files left out by the filter are still fetched unless their name marks them as heavy art.
_HEAVY_PREFIXES = ("T_", "TX_", "Tex_", "SM_", "SK_", "SKM_", "M_", "MI_", "MF_", "HDR", "S_", "SW_", "A_", "AS_",
                   "Anim_", "MM_", "PA_")


def clone(url: str, dest: Path, ref: str | None, asset_max_mb: float = 8.0, map_max_mb: float = 64.0) -> dict:
    """Partial clone with a blob size filter (CLONE_BLOB_LIMIT_MB): sources, config and small assets come with the
    clone. Bigger blobs stored directly in git are fetched on checkout only if they can matter — maps, and .uasset
    files whose name does not mark them as heavy art (T_, SM_, SK_, M_ …). LFS objects are pulled later."""
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1", GIT_TERMINAL_PROMPT="0")

    def git(*args, check=True, input=None):
        if input is None:
            return run(["git", "-C", str(dest), *args], env=env, check=check)
        # Binary stdin preserves NUL path records and LF refspecs on Windows;
        # TextIOWrapper would turn LF into CRLF and corrupt fetch --stdin.
        result = subprocess.run(["git", "-C", str(dest), *args], env=env,
                                input=input.encode("utf-8"), capture_output=True)
        result.stdout = result.stdout.decode("utf-8", errors="replace")
        result.stderr = result.stderr.decode("utf-8", errors="replace")
        if check:
            result.check_returncode()
        return result

    def fail(msg):
        raise SystemExit(f"error: {msg}")

    skipped: list[str] = []
    blob_limit_mb = CLONE_BLOB_LIMIT_MB

    def tree(commit: str) -> dict:
        entries = {}
        for entry in git("ls-tree", "-r", "-z", commit).stdout.split("\0"):
            meta, sep, path = entry.partition("\t")
            parts = meta.split()
            if sep and len(parts) == 3 and parts[1] == "blob":
                entries[path] = (parts[0], parts[2])
        return entries

    reused = dest.exists() and (dest / ".git").exists()

    def materialize(commit: str):
        """Point HEAD at `commit` and check out only the wanted paths. Blobs above the clone's size filter are
        missing locally; of those only maps are fetched (in one batch by checkout), the rest is skipped."""
        missing = {ln[1:].strip() for ln in git("rev-list", "--objects", "--missing=print", commit).stdout.splitlines()
                   if ln.startswith("?")}
        target = tree(commit)
        wanted = {}
        for path, item in target.items():
            name = path.rsplit("/", 1)[-1]
            heavy = not path.lower().endswith((".uasset", ".umap")) or (
                path.lower().endswith(".uasset") and name.startswith(_HEAVY_PREFIXES))
            if item[1] in missing and heavy:
                skipped.append(path)
            else:
                wanted[path] = item
        listfile = dest / ".git" / "ue-repo-reader-paths"
        indexed = {}
        for entry in git("ls-files", "--stage", "-z").stdout.split("\0"):
            meta, sep, path = entry.partition("\t")
            if sep:
                mode, oid, stage = meta.split()
                if stage != "0":
                    fail("clone has unresolved index entries; use a clean --workdir")
                indexed[path] = (mode, oid)
        if reused:
            previous = tree("HEAD")
            recorded = set(filter(None, listfile.read_text(encoding="utf-8").split("\0"))) if listfile.is_file() else set(previous)
            if (set(indexed) not in (set(previous), recorded) or
                    any(previous.get(path) != item for path, item in indexed.items()) or
                    git("diff", "--quiet", "--ignore-submodules", "--no-ext-diff", "--no-textconv", check=False).returncode != 0):
                fail("clone has local or staged changes; use a clean --workdir")
        stale = set(indexed) - set(wanted)
        changed = [path for path, item in wanted.items() if indexed.get(path) != item]
        base = dest.resolve()
        # Preflight before touching HEAD, index or files. Preserve untracked files
        # that would otherwise be overwritten by path checkout.
        for path in stale | set(changed):
            location = dest / path
            if base not in location.resolve().parents:
                fail(f"clone path escapes --workdir: {path}")
            if path not in indexed and os.path.lexists(location):
                fail(f"untracked file would be overwritten: {path}; use a clean --workdir")
        needed = sorted({oid for _, oid in wanted.values() if oid in missing})
        if needed:
            # Fetch only selected missing blobs in one request. A path checkout
            # from a new commit need not auto-fetch them on every Git version.
            # Same form git uses for its own promisor (lazy) fetches. Without --no-write-fetch-head and the no-op
            # negotiation, git 2.43 against GitHub reports "did not send all necessary objects" for blob ids.
            git("-c", "fetch.negotiationAlgorithm=noop", "fetch", "-q", "--no-tags", "--no-write-fetch-head",
                "--recurse-submodules=no", "--filter=blob:none", "origin", "--stdin", input="\n".join(needed) + "\n")
        if stale:
            git("update-index", "--force-remove", "-z", "--stdin", input="\0".join(sorted(stale)) + "\0")
            for path in stale:
                (dest / path).unlink()
        log(f"[fetch] checking out {len(wanted)} files; skipping {len(skipped)} files over {blob_limit_mb} MB stored in git")
        if changed:
            paths = dest / ".git" / "ue-repo-reader-checkout-paths"
            paths.write_text("\0".join(changed), encoding="utf-8")
            git("--literal-pathspecs", "checkout", "-q", commit,
                f"--pathspec-from-file={paths}", "--pathspec-file-nul")
        git("update-ref", "--no-deref", "HEAD", commit)
        listfile.write_text("\0".join(wanted), encoding="utf-8")

    full_sha = bool(ref and re.fullmatch(r"[0-9a-fA-F]{40}", ref))
    short_hex = bool(ref and not full_sha and re.fullmatch(r"[0-9a-fA-F]{4,39}", ref))
    partial = [f"--filter=blob:limit={blob_limit_mb}m", "--no-checkout", "--no-tags"]
    if reused:
        log(f"[fetch] reusing existing clone at {dest}")
        if not (dest / ".git").is_dir():
            fail("--workdir must be a regular clone, not a linked Git worktree")
        resolved = git("rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref or 'HEAD'}^{{commit}}", check=False)
        if resolved.returncode != 0:
            if git("fetch", "-q", "--depth", "1", f"--filter=blob:limit={blob_limit_mb}m", "origin", ref,
                   check=False).returncode != 0:
                fail(f"ref {ref!r} not found in {url}" + (" (use the full 40-character SHA)" if short_hex else ""))
            resolved = git("rev-parse", "FETCH_HEAD")
        materialize(resolved.stdout.strip())
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        log(f"[fetch] cloning {re.sub(r'//[^/@]*@', '//', url)} (partial: trees first, then only the files that are read) ...")
        if full_sha:
            # fetch exactly that commit; no need to download the default branch first
            dest.mkdir(parents=True, exist_ok=True)
            git("init", "-q")
            git("remote", "add", "origin", url)
            git("config", "remote.origin.promisor", "true")
            git("config", "remote.origin.partialclonefilter", f"blob:limit={blob_limit_mb}m")
            if git("fetch", "-q", "--depth", "1", f"--filter=blob:limit={blob_limit_mb}m", "origin", ref,
                   check=False).returncode != 0:
                fail(f"commit {ref} not found in {url}")
            materialize(git("rev-parse", "FETCH_HEAD").stdout.strip())
        elif ref:
            r = run(["git", "clone", "--depth", "1", *partial, "--branch", ref, url, str(dest)], env=env, check=False)
            if r.returncode == 0:
                materialize(git("rev-parse", "HEAD").stdout.strip())
            else:
                if not short_hex:
                    fail(f"branch or tag {ref!r} not found in {url}: {r.stderr.strip()[-300:]}")
                # abbreviated SHA: servers refuse to fetch those, so take the history without file contents
                shutil.rmtree(dest, ignore_errors=True)
                log(f"[fetch] {ref} looks like a short commit SHA; fetching history to resolve it")
                run(["git", "clone", *partial, url, str(dest)], env=env)
                r = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
                if r.returncode != 0 or not r.stdout.strip():
                    fail(f"commit {ref!r} not found in {url} (use the full 40-character SHA)")
                materialize(r.stdout.strip())
        else:
            run(["git", "clone", "--depth", "1", *partial, url, str(dest)], env=env)
            materialize(git("rev-parse", "HEAD").stdout.strip())
    info = {"url": re.sub(r"//[^/@]*@", "//", url), "ref": ref}  # never keep credentials from the URL
    if skipped:
        info["skipped_large_files"] = {"count": len(skipped), "limit_mb": blob_limit_mb, "assets": sorted(
            pth for pth in skipped if pth.lower().endswith(".uasset"))[:200]}
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


def _lfs_endpoint(repo: Path) -> tuple[str, dict]:
    """(batch API URL, headers) for the repo's origin. Basic auth is taken from credentials in the URL
    (how the MCP server passes GITHUB_TOKEN); repos with a custom lfs.url are left to git-lfs."""
    import base64
    from urllib.parse import urlsplit, urlunsplit
    if (repo / ".lfsconfig").is_file():
        raise RuntimeError("custom .lfsconfig")
    url = run(["git", "-C", str(repo), "remote", "get-url", "origin"]).stdout.strip()
    u = urlsplit(url)
    if u.scheme != "https":
        raise RuntimeError("origin is not https")
    headers = {"Accept": "application/vnd.git-lfs+json", "Content-Type": "application/vnd.git-lfs+json"}
    if u.username or u.password:
        cred = f"{u.username or ''}:{u.password or ''}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(cred).decode()
    host = u.hostname + (f":{u.port}" if u.port else "")
    path = u.path.rstrip("/")
    if not path.endswith(".git"):
        path += ".git"
    return urlunsplit(("https", host, path + "/info/lfs/objects/batch", "", "")), headers


def lfs_batch_download(repo: Path, rel_paths: list[str]) -> int:
    """Download LFS objects through the Git LFS batch API and replace the pointer files.
    Unlike `git lfs pull` this never scans the whole tree (which, in a partial clone, makes git fetch every
    skipped blob). Returns how many files were replaced; anything left is handled by git lfs pull."""
    import hashlib
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor
    endpoint, headers = _lfs_endpoint(repo)
    objs = {}
    for rp in rel_paths:
        data = (repo / rp).read_bytes()
        m_oid = re.search(rb"oid sha256:([0-9a-f]{64})", data)
        m_size = re.search(rb"size (\d+)", data)
        if m_oid and m_size:
            objs.setdefault(m_oid.group(1).decode(), (int(m_size.group(1)), []))[1].append(rp)
    targets = {}
    items = list(objs.items())
    for i in range(0, len(items), 100):
        body = json.dumps({"operation": "download", "transfers": ["basic"],
                           "objects": [{"oid": oid, "size": sz} for oid, (sz, _) in items[i:i + 100]]}).encode()
        req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            for o in json.loads(resp.read().decode("utf-8")).get("objects", []):
                dl = (o.get("actions") or {}).get("download")
                if dl and dl.get("href"):
                    targets[o["oid"]] = dl

    def fetch(oid):
        dl = targets[oid]
        req = urllib.request.Request(dl["href"], headers=dl.get("header") or {})
        with urllib.request.urlopen(req, timeout=300) as resp:
            blob = resp.read()
        if hashlib.sha256(blob).hexdigest() != oid:
            return 0
        for rp in objs[oid][1]:
            (repo / rp).write_bytes(blob)
        return len(objs[oid][1])

    with ThreadPoolExecutor(max_workers=8) as ex:
        return sum(ex.map(lambda o: _safe(fetch, o), list(targets)))


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001 - a failed object stays a pointer and goes to git lfs pull
        return 0


def lfs_include_pattern(path: str) -> str:
    """A git-lfs --include pattern matching this literal path on every OS. Glob metacharacters and commas
    (the list separator) become `?` (any one character): backslash escapes do not survive on Windows, where
    git-lfs treats `\\` as a path separator. At worst a same-length sibling is downloaded too."""
    return re.sub(r"[\[\]*?,\\]", "?", path)


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
    try:
        done = lfs_batch_download(repo, wanted)
    except Exception as e:  # noqa: BLE001 - fall back to git-lfs below
        log(f"[lfs] direct download unavailable ({type(e).__name__}: {str(e)[:120]}); using git lfs pull")
        done = 0
    wanted = [w for w in wanted if lfs_pointer_size(repo / w) is not None]  # still pointers
    if not wanted:
        report["failed"] = 0
        return report
    if done:
        log(f"[lfs] {done} downloaded directly; {len(wanted)} left for git lfs pull")
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
        pats = ",".join(lfs_include_pattern(x) for x in b)
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


def _clean_class(cls):
    """Drop class names that are really a mis-resolved name-table index (e.g. `/Script/CoreUObject.Vector_1476395008`)."""
    if not cls or "/" in cls or re.search(r"_\d{6,}$", cls):
        return None
    return cls


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
                cls = _clean_class(get_asset_class(e, r.import_map, r.export_map))
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
    if not paths:
        return {}
    # Classification reads only headers. Hashing entire art packages costs more
    # than re-reading those headers; cache the expensive decoded bodies below.
    out = {}
    import bp_reader
    bp_reader.ensure_uasset_read()  # finish installation in the parent, before spawning any workers
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=workers, initializer=_worker_init) as pool:
        for i, (p, cls) in enumerate(pool.imap_unordered(_classify, paths, chunksize=16), 1):
            out[p] = cls
            if i % 500 == 0:
                log(f"[scan] classified {i}/{len(paths)}")
    return out


DATA_CLASSES = {
    "DataTable", "CompositeDataTable", "UserDefinedStruct", "UserDefinedEnum", "InputAction", "InputMappingContext",
    "BehaviorTree", "BlackboardData", "StateTree", "CurveTable", "CurveFloat", "CurveVector", "CurveLinearColor",
    "PrimaryDataAsset", "DataAsset", "StringTable", "EnvQuery", "PlayerMappableInputConfig", "AnimMontage",
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


def process_blueprints(items, workers: int, timeout: int, worker=None, label="bp", cache=None):
    results, failures = {}, {}
    if not items:
        return results, failures
    keys, todo = {}, []
    for item in items:
        key = cache.key(label, item) if cache else None
        value = cache.load(key) if cache else None
        if value is None:
            todo.append(item)
            keys[item[1]] = key
        else:
            results[item[1]] = value
    if not todo:
        return results, failures
    import bp_reader
    bp_reader.ensure_uasset_read()
    worker = worker or _worker
    ctx = mp.get_context("spawn")
    pool = ctx.Pool(processes=workers, initializer=_worker_init, maxtasksperchild=200)
    try:
        pending = {it[1]: pool.apply_async(worker, (it,)) for it in todo}
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
                if cache:
                    cache.store(keys[gp], res)
            else:
                failures[gp] = err
            done += 1
            if done % 25 == 0 or done == len(pending):
                log(f"[{label}] {done}/{len(pending)}")
    finally:
        pool.terminate()
        pool.join()
    return {item[1]: results[item[1]] for item in items if item[1] in results}, failures


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


MD_PART_CHARS = 60_000  # ~17k tokens: stays under common tool-output limits (e.g. 25k tokens per read)


def split_md_text(text: str, limit: int = MD_PART_CHARS) -> list[str]:
    """Split Markdown at line boundaries (preferring a heading) into chunks of at most `limit` characters.
    A code fence open at a cut is closed in that part and reopened in the next, so every part renders."""
    if len(text) <= limit:
        return [text]
    parts, cur, size, fence = [], [], 0, None
    budget = limit - 200
    for line in text.splitlines(keepends=True):
        if size + len(line) > budget and cur:
            if fence:
                cur.append("```\n")
            parts.append("".join(cur))
            cur, size = ([fence + "\n"] if fence else []), 0
        cur.append(line)
        size += len(line)
        st = line.strip()
        if st.startswith("```"):
            fence = None if fence else (st if len(st) > 3 else "```")
    if cur:
        parts.append("".join(cur))
    return parts


def split_large_markdown(out: Path, limit: int = MD_PART_CHARS) -> int:
    """Any digest file above `limit` becomes X.md (part 1) + X.part2.md … with a pointer at each cut."""
    n = 0
    for f in sorted(out.rglob("*.md")):
        if ".part" in f.stem:
            continue
        text = f.read_text(encoding="utf-8")
        parts = split_md_text(text, limit)
        if len(parts) == 1:
            continue
        n += 1
        names = [f.name] + [f"{f.stem}.part{i}.md" for i in range(2, len(parts) + 1)]
        for i, (name, body) in enumerate(zip(names, parts)):
            head = f"_(part {i + 1} of {len(parts)} of `{f.name}`)_\n\n" if i else ""
            tail = f"\n\n_→ continued in [{names[i + 1]}](<{names[i + 1]}>)_\n" if i + 1 < len(parts) else ""
            (f.parent / name).write_text(head + body + tail, encoding="utf-8")
    return n


_TAG_LIST = re.compile(r'GameplayTagList=\(\s*Tag="([^"]+)"(?:\s*,\s*DevComment="((?:[^"\\]|\\.)*)")?')
_TAG_REDIRECT = re.compile(r'GameplayTagRedirects=\(\s*OldTagName="([^"]+)"\s*,\s*NewTagName="([^"]*)"')
_TAG_DEFINE = re.compile(r'UE_DEFINE_GAMEPLAY_TAG(?:_COMMENT|_STATIC|_TYPED)?\s*\(\s*(\w+)\s*,\s*(?:TEXT\s*\()?\s*"([^"]+)"'
                         r'(?:\s*\)?\s*,\s*(?:TEXT\s*\()?\s*"([^"]*)")?')
_TAG_REQUEST = re.compile(r'(?:RequestGameplayTag|FGameplayTag::RequestGameplayTag)\s*\(\s*(?:FName\s*\(\s*)?(?:TEXT\s*\(\s*)?"([^"]+)"')
_TAG_USE = re.compile(r"TagName=([A-Za-z0-9_][A-Za-z0-9_.]*)")


def gameplay_tags(proj: Path, docs: dict, value_tags: dict | None = None) -> tuple[list[str], str | None]:
    """GameplayTags: definitions (config ini, tag DataTables, native C++ tags), redirects, and which
    Blueprints/data/maps use each tag. Returns (INDEX lines, config/GameplayTags.md text or None)."""
    defined: dict[str, dict] = {}
    redirects = {}
    cfg_dirs = [proj / "Config"] + ([p / "Config" for p in (proj / "Plugins").rglob("*") if (p / "Config").is_dir()
                                     and any(p.glob("*.uplugin"))] if (proj / "Plugins").is_dir() else [])
    for d in cfg_dirs:
        for ini in [d / "DefaultGameplayTags.ini", *sorted((d / "Tags").glob("*.ini"))]:
            if not ini.is_file():
                continue
            t = ini.read_text(encoding="utf-8-sig", errors="replace")
            rel = ini.relative_to(proj).as_posix()
            for tag, comment in _TAG_LIST.findall(t):
                defined.setdefault(tag, {"where": rel, "comment": comment})
            for old, new in _TAG_REDIRECT.findall(t):
                redirects[old] = new
    cpp_vars, cpp_uses, sources = {}, defaultdict(set), []
    roots = [proj / "Source"] + ([q for q in (proj / "Plugins").glob("*/Source")] if (proj / "Plugins").is_dir() else [])
    for root in roots:
        if root.is_dir():
            sources += [f for f in root.rglob("*") if f.suffix in (".h", ".cpp")]
    texts = {}
    for f in sources:
        try:
            texts[f] = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = f.relative_to(proj).as_posix()
        for var, tag, comment in _TAG_DEFINE.findall(texts[f]):
            defined.setdefault(tag, {"where": rel + " (native)", "comment": comment})
            cpp_vars[var] = tag
        for tag in _TAG_REQUEST.findall(texts[f]):
            cpp_uses[tag].add(f.name)
    for var, tag in cpp_vars.items():  # uses of a native tag through its C++ variable
        pat = re.compile(rf"\b{re.escape(var)}\b")
        for f, t in texts.items():
            n = len(pat.findall(t)) - len(re.findall(rf"UE_(?:DE(?:FINE|CLARE))_GAMEPLAY_TAG\w*\s*\(\s*{re.escape(var)}\b", t))
            if n > 0:
                cpp_uses[tag].add(f.name)
    used = defaultdict(set)
    for gp, tags in (value_tags or {}).items():  # from full decoded values (not limited by Markdown truncation)
        for tag in tags:
            used[tag].add(gp.rsplit("/", 1)[-1])
    for gp, md in docs.items():
        name = gp.rsplit("/", 1)[-1]
        for tag in set(_TAG_USE.findall(md)):
            if tag != "None":
                used[tag].add(name)
        if "GameplayTagTableRow" in md:  # tag DataTable: its rows define tags
            for tag in re.findall(r"\bTag=([A-Za-z0-9_][A-Za-z0-9_.]*)", md):
                defined.setdefault(tag, {"where": gp + " (DataTable)", "comment": ""})
    if not defined and not used:
        return [], None
    parents = {".".join(t.split(".")[:i]) for t in defined for i in range(1, t.count(".") + 1)}
    known = set(defined) | parents
    undefined = sorted(t for t in used if t not in known and t not in redirects)
    via_redirect = sorted(t for t in used if t in redirects)
    unused = sorted(t for t in defined if t not in used and t not in cpp_uses
                    and not any(u.startswith(t + ".") for u in used))
    lines = ["# GameplayTags", "",
             f"{len(defined)} tags defined ({sum(1 for v in defined.values() if 'native' in v['where'])} native C++), "
             f"{len(used)} used by Blueprints/data/maps. Usage is what the saved assets literally contain; tags built at "
             "runtime from strings are not seen.", ""]
    if undefined:
        lines += ["## ⚠ Used but not defined anywhere in this repo", "",
                  *[f"- `{t}` ← {', '.join(sorted(used[t])[:8])}" for t in undefined], ""]
    if via_redirect:
        lines += ["## Used through a redirect (old name still saved in assets)", "",
                  *[f"- `{t}` → `{redirects[t]}` ← {', '.join(sorted(used[t])[:8])}" for t in via_redirect], ""]
    lines += ["## Tags", "", "| Tag | Defined in | Comment | Used by |", "|---|---|---|---|"]
    for t in sorted(defined):
        users = sorted(used.get(t, set()) | {f"{c} (C++)" for c in cpp_uses.get(t, set())})
        shown = ", ".join(users[:6]) + (f" … (+{len(users) - 6})" if len(users) > 6 else "")
        lines.append(f"| `{t}` | {defined[t]['where']} | {defined[t]['comment'].replace('|', '/')} | {shown or '—'} |")
    lines.append("")
    if redirects:
        lines += ["## Redirects", "", *[f"- `{o}` → `{n}`" for o, n in sorted(redirects.items())], ""]
    if unused:
        lines += ["## Defined but not used by any asset or C++ reference found", "", ", ".join(f"`{t}`" for t in unused), ""]
    index = [f"## GameplayTags", "",
             f"{len(defined)} tags defined, {len(used)} used — see [config/GameplayTags.md](<config/GameplayTags.md>)."]
    if undefined:
        index.append(f"- ⚠ used but not defined: " + ", ".join(f"`{t}`" for t in undefined[:12])
                     + (" …" if len(undefined) > 12 else ""))
    if via_redirect:
        index.append(f"- used via redirect: " + ", ".join(f"`{t}`" for t in via_redirect[:12]))
    return index + [""], "\n".join(lines) + "\n"


def input_check(bps: dict, datas: dict) -> list[str]:
    """Enhanced Input cross-check: actions a Blueprint handles but no mapping context in the repo maps
    (they can never fire unless C++ adds a mapping), and mapped actions no Blueprint handles."""
    imcs = {gp: s["summary"].get("mapped_actions") or [] for gp, s in datas.items()
            if s["summary"].get("class") == "InputMappingContext"}
    if not imcs:
        return []
    mapped = {a for acts in imcs.values() for a in acts}
    handled = defaultdict(set)
    for gp, r in bps.items():
        for e in r["summary"].get("entries") or []:
            m = re.fullmatch(r"input (\S+)", e)
            if m and not e.startswith(("input action ", "input key ", "input axis ")):
                handled[m.group(1)].add(gp.rsplit("/", 1)[-1])
    unmapped = sorted(a for a in handled if a not in mapped)
    unhandled = sorted(a for a in mapped if a not in handled)
    md = ["## Input check (Enhanced Input)", "",
          f"{len(imcs)} input mapping contexts map {len(mapped)} actions; Blueprints handle {len(handled)} actions."]
    if unmapped:
        md.append("- ⚠ handled in Blueprints but **not mapped in any mapping context in this repo** (never fires unless "
                  "C++ or a runtime-added context maps it):")
        md += [f"  - `{a}` ← {', '.join(f'`{b}`' for b in sorted(handled[a]))}" for a in unmapped]
    if unhandled:
        # an action assigned to a property (e.g. a C++ character's `MoveAction = IA_Move` default) is bound in C++
        assigned = defaultdict(set)
        for gp, r in list(bps.items()) + [(g, d) for g, d in datas.items()
                                          if d["summary"].get("class") not in ("InputMappingContext", "InputAction")]:
            for a in unhandled:
                if re.search(rf"= {re.escape(a)}\b", r.get("markdown", "")):
                    assigned[a].add(gp.rsplit("/", 1)[-1])
        cpp_bound = [a for a in unhandled if a in assigned]
        orphan = [a for a in unhandled if a not in assigned]
        if cpp_bound:
            md.append("- mapped, no Blueprint input event, but assigned to a property (likely bound in C++): "
                      + ", ".join(f"`{a}` (in {', '.join(sorted(assigned[a]))})" for a in cpp_bound))
        if orphan:
            md.append("- mapped but not handled or referenced by any Blueprint (check C++ sources): "
                      + ", ".join(f"`{a}`" for a in orphan))
    if not unmapped and not unhandled:
        md.append("- every mapped action has a Blueprint handler and every handled action is mapped")
    return md + [""]


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
    engine = declaration_text(meta.get("engine") or "?")
    md += [f"# {title} — Unreal repo digest", "",
           f"source: {src}" + (f" @ `{commit}` ({meta.get('branch')}, {meta.get('commit_date', '')[:10]})" if commit else ""),
           f"engine (EngineAssociation): **{engine}** · generated {_dt.date.today().isoformat()} by ue-repo-reader {VERSION}",
           ""]
    md += support_notice(meta.get("project_support"))
    total_nodes = sum(r["summary"]["nodes_total"] for r in bps.values())
    ok_nodes = sum(r["summary"]["nodes_ok"] for r in bps.values())
    md += ["## How to read this digest", "",
           "- Blueprints were decoded **directly from the binary .uasset files** (no editor). Each one has a file under",
           "  `blueprints/` that mirrors its content path. Graphs are rendered as pseudo-code of the execution flow:",
           "  - `event X(...)`, `custom event`, `input IA_X`, `on Comp.Delegate(...)`, `function F(...) -> Out: T` — entry points",
           "  - `return <value>` / `return (A=.., B=..)` — a function's output values at that exit",
           "  - `[pure, const, private, RunOnServer, Reliable …]` after a function header — its flags; the Variables",
           "    table's Flags column lists InstanceEditable, ExposeOnSpawn, Private, Replicated, Condition=…, SaveGame …",
           "  - `Map<K, V>` shows key and value types; `?` inside a type means unspecified or unreadable, never an inferred type",
           "  - Compact values use `…(+N)` for omitted entries/fields; plain `…` can also mean a string/depth limit.",
           "    Extra CDO defaults show at most 40 values and count further values, opaque/native data and unexpanded subobjects.",
           "    Those omitted values are unknown here, not defaults; a display notice alone is not a parse failure.",
           "  - typed data-asset enum arrays show `Enum::Enumerator(number, display=\"Label\")`; names/numbers match the enum definition.",
           "    Unresolved values keep their saved name/number; ordinary byte arrays stay numeric.",
           "  - `// Function metadata` / `// Function tooltip` are saved entry-node descriptions (Category, CallInEditor, ToolTip),",
           "    not executed statements. Absent metadata is not inferred; explicit CallInEditor=false is kept.",
           "  - one statement per executed node; data inputs are inlined as expressions (`Target.Func(Arg=value)`)",
           "  - `#N = Func(...)` — an impure node whose output is used later as `#N` / `#N.PinName`",
           "  - `$N` — a long pure expression used in several places, spelled out once in the graph's `// where` block",
           "  - `[true]:` / `[cast ok]:` / `[LoopBody]:` / `[then_1]:` — the named exec output a block runs from",
           "  - `→ goto #N` — execution merges into a node already shown; `[#N]` marks such merge targets",
           "  - `// ── text ──` — the comment box the following nodes sit in; `// text` — a node comment",
           "  - `Pin=∅` — object input left unconnected (the call receives None); `⚠ disconnected execution chains` — dead code",
           "  - Anim graphs: pose trees (`← Node`), state machines as `A → B when <rule>`; `when auto (...)` = fires when the",
           "    state's animation finishes; `when never` = rule is constant False; `[blend 0.1s, on start notify X]` =",
           "    non-default transition settings",
           f"- Coverage: {len(bps)} Blueprints rendered, {len(failures)} failed; graph nodes decoded {ok_nodes}/{total_nodes}.",
           "  A Blueprint file says `⚠ N nodes unreadable` when part of a graph could not be decoded.",
           "- `Parse warnings` lists property/graph/actor failures. Node N/N counts nodes with at least one decoded pin;",
           "  it cannot detect a truncated pin list or prove semantic correctness.",
           "  check these warnings too. A failed Level Blueprint is unknown, not an empty graph or 0/0 success.",
           "- Maps are rendered under `maps/`: Level Blueprint, placed actors with per-instance overrides, game mode.",
           "  Map tables are compact previews. Full decoded actor/root-component saved properties are in",
           "  `digest.json` → `maps_detail[map_path].actors` (native fields and opaque bytes retained; missing values stay unknown).",
           "  Check each actor's `properties_status`: partial records are incomplete; absent properties are unknown, not defaults.",
           "  Blueprint files end with `Placed in levels` when instances of them are placed in a map.",
           "- Data assets (DataTables, structs, enums, Behavior Trees, StateTrees, input mappings, montages, DataAssets) are",
           "  rendered under `data/` — see the Data assets table below.",
           "- C++ is summarized in `cpp/CLASSES.md`; read the real sources in the repo for implementation details.",
           "- GameplayTags (definitions, users, undefined tags) are in `config/GameplayTags.md` when the project has any.",
           "- Files longer than ~60k characters are split: `X.md` ends with a link to `X.part2.md`.",
           "- `digest.json` is the same information for scripts — don't read it to understand the project.",
           "  Scripts can inspect `blueprints[path].graph_ir` / `maps_detail[path].level_bp_graph_ir` for versioned",
           "  node/pin identities, decoded types/defaults and saved pin references. Check status and issues;",
           "  complete means projection coverage, not verified gameplay semantics. Node properties/CDOs are outside this IR.",
           "  `blueprints[path].declaration_ir` contains saved variable types/flags/authored defaults, parent/function references",
           "  and widget bindings. Check saved_fields, status and unknown reasons; absent tags do not establish defaults.",
           "- `INDEX.md` is a bounded reading map; this full catalog preserves every listed asset and warning.",
           "  Asset context headers link nearby documents ranked by static references/name mentions, not runtime behavior.",
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
            ok, tot = s.get("level_bp_nodes") or (0, 0)
            lbp = ", ".join(dict.fromkeys(e.replace("custom event ", "ce ").replace("event ", "") for e in s["level_bp_entries"])) or ("—" if not tot else "")
            if s.get("level_bp_status") == "error":
                lbp = "⚠ unreadable"
            elif s.get("level_bp_status") == "partial":
                lbp = "⚠ partial: " + lbp
            wp = " · World Partition" if s.get("world_partition") else ""
            gm = (s['game_mode'] or '(project default)') if s.get("game_mode_known", True) else "⚠ unknown"
            md.append(f"| `{gp}`{wp} | {gm} | {s['gameplay_count']} of {s['actor_count']} | "
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
        warn = " ⚠" if s["nodes_ok"] < s["nodes_total"] or s.get("issues") else ""
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
    guessed = Counter()
    for gp, name, cls in other_assets:
        top = "/".join(gp.split("/")[:3])
        folders[top] += 1
        if cls != "?":
            kinds[cls] += 1
        else:
            guessed[asset_kind(name)] += 1
    for kind, v in guessed.items():  # header unreadable: fold name-based guesses into the real class when it exists
        as_class = kind.replace(" ", "")
        if as_class in kinds:
            kinds[as_class] += v
        else:
            kinds["unknown class" if kind == "other" else f"{kind} (guessed from name)"] += v
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
            if s.get("issues"):
                headline += " ⚠ partial"
            if s.get("row_struct") and s["row_struct"] in cpp_names:
                headline += " (row struct in C++)"
            doc = "data" + gp + ".md"
            md.append(f"| `{gp}` | {s['class']} | {headline} | {used} | [md](<{doc}>) |")
        md.append("")

    md += input_check(bps, datas)
    docs = {gp: r["markdown"] for gp, r in list(bps.items()) + list(datas.items()) + list((levels or {}).items())}
    value_tags = {gp: r["summary"].get("gameplay_tags") or []
                  for gp, r in list(bps.items()) + list(datas.items()) + list((levels or {}).items())}
    tag_index, tag_doc = gameplay_tags(proj, docs, value_tags)
    if tag_doc:
        (out / "config").mkdir(exist_ok=True)
        (out / "config" / "GameplayTags.md").write_text(tag_doc, encoding="utf-8")
        md += tag_index

    # parse report
    md += ["## Parse report", ""]
    if lfs and lfs.get("pointers"):
        md.append(f"- Git LFS: {lfs['pointers']} LFS assets; downloaded {lfs['requested'] - lfs['failed']} .uasset/.umap files, "
                  f"skipped {lfs['skipped_large']} large/non-uasset files" + (f"; ⚠ {lfs['failed']} could not be downloaded" if lfs["failed"] else ""))
        if lfs.get("error"):
            md.append(f"  - LFS error: `{lfs['error'][:300]}`")
    big = meta.get("skipped_large_files")
    if big:
        assets_big = big.get("assets") or []
        md.append(f"- not downloaded (stored in git, over {big.get('limit_mb', '?')} MB and named like art — T_, SM_, SK_, M_ …): "
                  f"{big['count']} files" + (f" — including {len(assets_big)} .uasset: "
                  + ", ".join(f"`{x}`" for x in assets_big[:8]) + (" …" if len(assets_big) > 8 else "")
                  if assets_big else ""))
    partial = [(gp, r["summary"]) for gp, r in bps.items() if r["summary"]["nodes_ok"] < r["summary"]["nodes_total"]]
    if partial:
        md.append(f"- partially decoded Blueprints ({len(partial)}):")
        for gp, s in sorted(partial):
            md.append(f"  - `{gp}` {s['nodes_ok']}/{s['nodes_total']} nodes (saved with UE {s['saved_with']})")
    groups = [("Blueprint", bps), ("data asset", datas), ("map", levels)]
    warned = [(kind, gp, r["summary"]["issues"]) for kind, assets in groups for gp, r in assets.items()
              if r["summary"].get("issues")]
    if warned:
        md.append(f"- ⚠ partially read/rendered assets ({len(warned)}); see each document's Parse warnings:")
        for kind, gp, issues in sorted(warned):
            md.append(f"  - {kind} `{gp}` — {len(issues)} issues")
            for issue in issues:
                detail = f"{issue['stage']} · {issue['context']}: {issue['message']}".replace("\n", " ")
                md.append(f"    - {detail[:240]}")
    newer = sorted(f"{kind} {gp}" for kind, assets in groups for gp, r in assets.items()
                   if r["summary"].get("newer_format"))
    if newer:
        md.append(f"- ⚠ {len(newer)} assets use a newer package format than this tool was verified with "
                  f"(decoded best-effort): " + ", ".join(f"`{g}`" for g in newer[:10]) + (" …" if len(newer) > 10 else ""))
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
    unresolved_enums = [(gp, r["summary"].get("enum_resolution", {}).get("unresolved", 0)) for gp, r in datas.items()]
    unresolved_enums = [(gp, count) for gp, count in unresolved_enums if count]
    if unresolved_enums:
        md.append("- ⚠ enum labels unresolved (saved names/numbers retained; missing/ambiguous enum or unknown value):")
        md.extend(f"  - `{gp}` — {count} rendered values" for gp, count in sorted(unresolved_enums))
    if not partial and not warned and not newer and not failures and not data_failures and not map_failures and not unresolved_enums and not (lfs and lfs.get("failed")):
        support = meta.get("project_support")
        if isinstance(support, dict) and support.get("classification") == "target":
            md.append("- everything decoded cleanly")
        else:
            md.append("- No decode failures reported in rendered assets; project support remains outside the normal target or unconfirmed.")
    md.append("")
    (out / "INDEX.md").write_text("\n".join(md) + "\n", encoding="utf-8")


# =========================================================================== main

def validate_output_dir(output: Path, repo: Path, project: Path | None = None) -> Path:
    """Only replace a dedicated digest directory, never the source or a directory containing it."""
    # lstat's reparse attribute also covers junctions on Python 3.10/3.11 (before Path.is_junction).
    reparse = False
    if os.name == "nt":
        try:
            reparse = bool(output.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        except FileNotFoundError:
            pass
    if output.is_symlink() or reparse:
        raise ValueError(f"output directory must not be a symlink or junction: {output}")
    out = output.resolve()
    for source in (repo, project):
        if source is not None:
            source = source.resolve()
            if out == source or out in source.parents:
                raise ValueError(f"output directory would delete an input repository/project: {out}; choose a separate --out")
    if not out.exists():
        return out
    if not out.is_dir():
        raise ValueError(f"output path is not a directory: {out}")
    entries = list(out.iterdir())
    if not entries:
        return out
    try:
        manifest = json.loads((out / "digest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = None
    if not isinstance(manifest, dict) or not str(manifest.get("tool", "")).startswith("ue-repo-reader "):
        raise ValueError(f"output directory is not a recognized ue-repo-reader digest: {out}; choose a new --out")
    dirs = {"blueprints", "cpp", "data", "maps", "config"}
    files = {"INDEX.md", "CATALOG.md", "digest.json"}
    for entry in entries:
        if entry.name in dirs and entry.is_dir():
            continue
        if (entry.name in files or re.fullmatch(r"(?:INDEX|CATALOG)\.part(?:[2-9]|[1-9][0-9]+)\.md", entry.name)) and entry.is_file():
            continue
        raise ValueError(f"output directory contains an unrelated entry: {entry}; choose a new --out")
    return out


def main(argv=None):
    # Windows pipes default to the ANSI code page (cp949 on Korean systems): force UTF-8 so logs with
    # asset names or symbols never crash, here and in the spawned worker processes.
    os.environ.setdefault("PYTHONIOENCODING", "utf-8:replace")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="git URL (https/ssh) or a local project directory")
    ap.add_argument("--ref", help="branch, tag or commit SHA to read (default: remote HEAD)")
    ap.add_argument("--out", help="output directory (default: ./<name>_digest)")
    ap.add_argument("--source-label", help="what to show as the source in INDEX.md (e.g. a URL without credentials)")
    ap.add_argument("--project", help="which .uproject to read when the repo holds several (name or relative path)")
    ap.add_argument("--best-effort", action="store_true",
                    help="explicit exploratory opt-in for legacy, unconfirmed or newer-than-tested project declarations")
    ap.add_argument("--workdir", help="where to clone (default: ./.ue-repo-reader/<name>)")
    ap.add_argument("--lfs-max-mb", type=float, default=8.0, help="only download LFS .uasset files up to this size (default 8)")
    ap.add_argument("--lfs-map-max-mb", type=float, default=64.0, help="only download LFS .umap files up to this size (default 64)")
    ap.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--timeout", type=int, default=90, help="seconds allowed per Blueprint (default 90)")
    ap.add_argument("--no-asset-cache", action="store_true", help="decode every asset without reading/writing the asset cache")
    ap.add_argument("--asset-cache-dir", type=Path, help="parent folder of the persistent asset cache (default: parser cache folder)")
    ap.add_argument("--max-bp-mb", type=float, default=64.0, help="skip Blueprint candidates larger than this")
    a = ap.parse_args(argv)

    remote = looks_like_url(a.source)
    if remote:
        name = re.sub(r"\.git$", "", a.source.rstrip("/").split("/")[-1].split(":")[-1]) or "repo"
        repo = Path(a.workdir or Path.cwd() / ".ue-repo-reader" / name).resolve()
    else:
        repo = Path(a.source).resolve()
        if not repo.is_dir():
            ap.error(f"not a directory: {repo}")
        name = repo.name
    output = Path(a.out or Path.cwd() / f"{name}_digest")
    try:
        out = validate_output_dir(output, repo)
    except ValueError as e:
        ap.error(str(e))

    meta: dict = {}
    if remote:
        meta.update(clone(a.source, repo, a.ref, a.lfs_max_mb, a.lfs_map_max_mb))
    else:
        try:
            meta["commit"] = run(["git", "-C", str(repo), "rev-parse", "HEAD"]).stdout.strip()
            meta["branch"] = run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
            meta["commit_date"] = run(["git", "-C", str(repo), "log", "-1", "--format=%cI"]).stdout.strip()
        except Exception:
            pass
    if a.source_label:
        meta["url"] = a.source_label

    # Select the project before replacing previous results. A clone/checkout may also have
    # populated a requested output directory inside the source tree, so validate it again.
    uproject, all_projects = pick_uproject(repo, a.project)
    proj = uproject.parent if uproject else repo
    try:
        out = validate_output_dir(output, repo, proj)
    except ValueError as e:
        ap.error(str(e))
    # This gate must precede output replacement, LFS downloads and decoder setup.
    # Read the selected descriptor exactly once; never infer its engine from assets.
    up, metadata_error = {}, None
    if uproject:
        try:
            up = parse_descriptor(uproject.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, UnicodeError, RecursionError) as e:
            up, metadata_error = {}, f"{type(e).__name__}: {e}"
    support = assess_project(up.get("EngineAssociation"), best_effort=a.best_effort,
                             project_found=uproject is not None, metadata_error=metadata_error)
    support["project_file"] = uproject.relative_to(repo).as_posix() if uproject else None
    meta["project_support"] = support
    meta["engine"] = support["engine_association"] if isinstance(support["engine_association"], str) else "?"
    if metadata_error:
        meta["project_metadata_error"] = metadata_error[:400]
    if not support["allowed"]:
        log(f"[project-support-refused] {support['classification']}")
        ap.error(support["reason"] + " Normal analysis requires a numeric 5.7/5.8 project declaration. "
                 "Use --best-effort only for explicitly exploratory analysis; its support status stays outside target or unconfirmed.")
    if support["best_effort_used"]:
        log(f"[warn] explicit best-effort: {support['classification']}. {support['reason']}")
    cache = None
    if not a.no_asset_cache:
        from asset_cache import AssetCache
        cache_dir = a.asset_cache_dir or Path(os.environ.get("UE_REPO_READER_CACHE") or Path.home() / ".cache/ue-repo-reader")
        cache_root = cache_dir.expanduser().resolve() / "asset-results-v1"
        if cache_root == out or out in cache_root.parents or cache_root in out.parents:
            ap.error("asset cache and --out must be separate folders; use --asset-cache-dir or --no-asset-cache")
        cache = AssetCache(cache_dir, repo, VERSION, log=log)
    if out.exists():
        shutil.rmtree(out)
    (out / "blueprints").mkdir(parents=True)
    (out / "cpp").mkdir(parents=True)
    (out / "data").mkdir(parents=True)
    (out / "maps").mkdir(parents=True)

    if len(all_projects) > 1:
        meta["other_projects"] = [p.relative_to(repo).as_posix() for p in all_projects if p != uproject]
        log(f"[warn] {len(all_projects)} .uproject files in repo; reading {uproject.relative_to(repo).as_posix()} "
            f"(choose another with --project)")
    if uproject:
        try:
            meta["modules"] = up.get("Modules") or []
            meta["plugins"] = [p.get("Name") for p in up.get("Plugins") or [] if p.get("Enabled")]
        except Exception as e:  # noqa: BLE001
            log(f"[warn] could not read {uproject.name}: {e}")
        if metadata_error:
            log(f"[warn] could not read {uproject.name}: {metadata_error}")
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
    # instances of this project's Blueprint classes saved as assets (e.g. a DataAsset made from PDA_PlayerData)
    bp_class_names = {Path(str(q)).stem + "_C" for q in local if is_blueprint_class(classes.get(str(q), "?"))}
    data_items = []
    for p in local:
        gp = game_path(p, mounts)
        cls = classes.get(str(p), "?")
        if is_blueprint_class(cls) and p.stat().st_size <= a.max_bp_mb * 1024 * 1024:
            candidates.append((str(p), gp))
        else:
            others.append((gp, p.stem, cls))
            if (is_data_class(cls, project_types) or cls in bp_class_names) and p.stat().st_size <= a.max_bp_mb * 1024 * 1024:
                data_items.append((str(p), gp, cls))
    log(f"[scan] {len(candidates)} Blueprints, {len(data_items)} data assets, {len(maps)} maps, {len(others)} other assets")

    t0 = time.time()
    bps, failures = process_blueprints(candidates, a.workers, a.timeout, cache=cache)
    log(f"[bp] rendered {len(bps)} in {time.time() - t0:.1f}s, {len(failures)} failed")
    for gp, r in bps.items():
        dest = out / "blueprints" / (gp.lstrip("/") + ".md")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(r["markdown"], encoding="utf-8")

    t0 = time.time()
    datas, data_failures = process_blueprints(data_items, a.workers, a.timeout, worker=_data_worker, label="data", cache=cache)
    log(f"[data] rendered {len(datas)} in {time.time() - t0:.1f}s, {len(data_failures)} failed")
    from enum_values import EnumCatalog, resolve_asset_enums
    enum_catalog = EnumCatalog(datas)
    for result in datas.values():
        resolve_asset_enums(result, enum_catalog)
    # who uses each data asset: Blueprints mentioning it + data assets referencing it
    used_by = defaultdict(set)
    names = {gp.rsplit("/", 1)[-1]: gp for gp in datas}
    word = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    for gp, r in bps.items():
        me = gp.rsplit("/", 1)[-1]
        for w in set(word.findall(r["markdown"])):
            if w in names and names[w] != gp and w != me:
                used_by[names[w]].add(me)
    for gp, r in datas.items():
        me = gp.rsplit("/", 1)[-1]
        for w in set(r["summary"].get("references", [])) | set(word.findall(r["markdown"])):
            if w in names and names[w] != gp and w != me:  # same-named asset elsewhere is not a user
                used_by[names[w]].add(me)
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
    level_results, map_failures = process_blueprints(map_items, a.workers, a.timeout * 4, worker=_map_worker, label="map", cache=cache)
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
            import bp_reader
            bp_reader.record_issue(s["issues"], "external_actors", gp, f"{missing} packages not downloaded (Git LFS)")
            s["parse_status"] = "partial"
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
    from navigation import build_navigation, repair_catalog_links
    navigation = build_navigation(meta, cpp, bps, failures, datas, data_failures, level_results, map_failures, lfs, out)
    digest = {"tool": f"ue-repo-reader {VERSION}", "source": meta, "lfs": lfs,
              "blueprints": {gp: r["summary"] for gp, r in bps.items()}, "failures": failures,
              "data_assets": {gp: r["summary"] for gp, r in datas.items()}, "data_failures": data_failures,
              "maps_detail": {gp: r["summary"] for gp, r in level_results.items()}, "map_failures": map_failures,
              "maps": sorted(maps), "cpp": cpp, "navigation": navigation}
    # compact: this file is for scripts, not for reading (it repeats what the Markdown says)
    (out / "digest.json").write_text(json.dumps(digest, ensure_ascii=False, default=list, separators=(",", ":")),
                                     encoding="utf-8")
    n_split = split_large_markdown(out)
    repair_catalog_links(out)
    if n_split:
        log(f"[out] split {n_split} large Markdown files into parts of <= {MD_PART_CHARS} characters")
    log(f"[done] {out / 'INDEX.md'}")
    if cache:
        cache.prune()
        log("[cache] " + " ".join(f"{key}={value}" for key, value in cache.stats.items()))
    print(str(out / "INDEX.md"))
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
