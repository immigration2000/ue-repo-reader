"""ue-repo-reader MCP server — lets ChatGPT, Claude or any MCP client analyze an Unreal Engine git repo.

The client passes a repo URL; the server clones it, builds the digest with scripts/ue_repo_digest.py
(Blueprints, maps, data assets decoded from binary .uasset/.umap files) and exposes the digest and the
repo's text sources through read-only tools.

Environment (all optional):
  PORT / HOST                 listen address (default 0.0.0.0:8000)
  UE_READER_SECRET            secret path segment: the endpoint becomes /<secret>/mcp (use on public hosts)
  GITHUB_TOKEN                token for private repos and their Git LFS content
  UE_READER_ALLOWED_OWNERS    comma-separated GitHub owners allowed (default: any)
  UE_READER_DATA              working directory for clones and digests (default: /tmp/ue-reader)
  UE_READER_KEEP              how many analyzed repos to keep on disk (default 6)
  UE_READER_WAIT              seconds a tool call waits for a running analysis (default 45)
  UE_READER_TIMEOUT           max seconds for one analysis (default 1800)
  UE_READER_ALLOWED_HOSTS     comma-separated Host headers to accept (default: any)
  UE_READER_WORKERS           parallel parser processes per analysis (default 2; lower on small instances)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlparse

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from processes import run_process

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from ue_repo_digest import VERSION as DIGEST_VERSION

DIGEST_SCRIPT = ROOT / "scripts" / "ue_repo_digest.py"
CACHE_SCHEMA = 1  # bump when server-side cache identity/completion semantics change
DATA = Path(os.environ.get("UE_READER_DATA", "/tmp/ue-reader"))
SECRET = os.environ.get("UE_READER_SECRET", "").strip("/")
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
ALLOWED_OWNERS = {o.strip().lower() for o in os.environ.get("UE_READER_ALLOWED_OWNERS", "").split(",") if o.strip()}
KEEP = int(os.environ.get("UE_READER_KEEP", "6"))
WAIT = int(os.environ.get("UE_READER_WAIT", "45"))
JOB_TIMEOUT = int(os.environ.get("UE_READER_TIMEOUT", "1800"))
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("UE_READER_ALLOWED_HOSTS", "").split(",") if h.strip()]
WORKERS = max(1, int(os.environ.get("UE_READER_WORKERS", "2")))
PAGE = 20000
SOURCE_EXT = {".h", ".hpp", ".cpp", ".c", ".inl", ".cs", ".ini", ".uproject", ".uplugin", ".json", ".md", ".txt",
              ".py", ".usf", ".ush", ".hlsl", ".yml", ".yaml", ".xml", ".bat", ".sh", ".gitattributes", ".gitignore",
              ".editorconfig", ".toml", ".cfg"}
HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}

(DATA / "work").mkdir(parents=True, exist_ok=True)
(DATA / "cache").mkdir(parents=True, exist_ok=True)


# =========================================================================== repo URLs

@dataclass
class RepoRef:
    host: str
    owner: str
    name: str
    ref: str | None

    @property
    def public_url(self) -> str:
        return f"https://{self.host}/{self.owner}/{self.name}"

    @property
    def clone_url(self) -> str:
        if TOKEN and self.host == "github.com":
            return f"https://x-access-token:{quote(TOKEN, safe='')}@github.com/{self.owner}/{self.name}.git"
        return self.public_url + ".git"


def parse_repo(text: str, ref: str | None) -> RepoRef:
    t = text.strip()
    m = re.fullmatch(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", t)
    if m:
        return RepoRef("github.com", m.group(1), re.sub(r"\.git$", "", m.group(2)), ref)
    if t.startswith("git@"):
        m = re.fullmatch(r"git@([^:]+):([^/]+)/(.+?)(?:\.git)?", t)
        if not m:
            raise ValueError("unrecognized git URL")
        t = f"https://{m.group(1)}/{m.group(2)}/{m.group(3)}"
    u = urlparse(t if "://" in t else "https://" + t)
    if u.scheme != "https" or (u.hostname or "").lower() not in HOSTS:
        raise ValueError(f"only https URLs on {', '.join(sorted(HOSTS))} are supported")
    parts = [p for p in u.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("URL must include owner and repository")
    owner, name = parts[0], re.sub(r"\.git$", "", parts[1])
    if not ref and len(parts) >= 4 and parts[2] in ("tree", "commit", "-") and parts[3] not in ("tree",):
        ref = "/".join(parts[3:]) if parts[2] == "tree" else parts[3]
    for piece in (owner, name):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", piece) or piece in (".", ".."):
            raise ValueError("invalid owner or repository name")
    return RepoRef(u.hostname.lower(), owner, name, ref)


def scrub(text: str) -> str:
    if TOKEN:
        text = text.replace(TOKEN, "***").replace(quote(TOKEN, safe=""), "***")
    return re.sub(r"x-access-token:[^@\s]+@", "", text)


def git(*args, cwd=None, timeout=600):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(scrub((r.stderr or r.stdout).strip())[-600:])
    return r.stdout


def resolve_commit(repo: RepoRef) -> str:
    out = git("ls-remote", repo.clone_url, repo.ref or "HEAD", timeout=60)
    for line in out.splitlines():
        sha, _, name = line.partition("\t")
        if sha:
            return sha
    if repo.ref and re.fullmatch(r"[0-9a-fA-F]{40}", repo.ref):
        return repo.ref.lower()
    if repo.ref and re.fullmatch(r"[0-9a-fA-F]{7,39}", repo.ref):
        raise ValueError("use the full 40-character commit SHA for an unadvertised commit")
    raise RuntimeError(f"ref '{repo.ref}' not found in {repo.public_url}")


# =========================================================================== jobs

@dataclass
class Job:
    id: str
    key: str
    repo: RepoRef
    commit: str
    project: str | None
    status: str = "queued"  # queued | running | done | error
    started: float = field(default_factory=time.time)
    finished: float | None = None
    log: list = field(default_factory=list)
    error: str | None = None
    done_event: threading.Event = field(default_factory=threading.Event)

    @property
    def dir(self) -> Path:
        return DATA / "work" / self.key


JOBS: dict[str, Job] = {}
BY_KEY: dict[str, Job] = {}
LOCK = threading.Lock()
RUN_SLOT = threading.Semaphore(1)  # one analysis at a time keeps memory predictable


def cache_identity(repo: RepoRef, commit: str, project: str | None) -> dict:
    return {"schema": CACHE_SCHEMA, "tool": f"ue-repo-reader {DIGEST_VERSION}",
            "host": repo.host, "owner": repo.owner, "repo": repo.name,
            "commit": commit.lower(), "project": project or None}


def identity_key(identity: dict) -> str:
    # Hash the complete tuple, never a sanitized/truncated project path or commit.
    # URL-safe base64 keeps all 256 bits in 43 path characters (Windows path budget).
    # Credentials and movable branch names are excluded.
    raw = json.dumps(identity, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest()).decode("ascii").rstrip("=")


def digest_key(repo: RepoRef, commit: str, project: str | None) -> str:
    return identity_key(cache_identity(repo, commit, project))


def completed_cache(directory: Path, expected: dict | None = None) -> bool:
    """A successful process publishes cache.json last; partial INDEX files don't count."""
    try:
        identity = json.loads((directory / "cache.json").read_text(encoding="utf-8"))
        if not isinstance(identity, dict) or (expected is not None and identity != expected):
            return False
        if identity.get("schema") != CACHE_SCHEMA or identity.get("tool") != f"ue-repo-reader {DIGEST_VERSION}":
            return False
        if set(identity) != {"schema", "tool", "host", "owner", "repo", "commit", "project"}:
            return False
        if identity_key(identity) != directory.name:
            return False
        return (directory / "digest" / "INDEX.md").is_file()
    except (OSError, ValueError, TypeError, KeyError):
        return False


def publish_cache(job: Job) -> None:
    identity = cache_identity(job.repo, job.commit, job.project)
    # The digest itself is written by the child. Do not publish a completion
    # marker for a stale producer or a partial/malformed output.
    manifest = json.loads((job.dir / "digest" / "digest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("tool") != identity["tool"]:
        raise RuntimeError("digest producer version does not match this server")
    if manifest.get("source", {}).get("commit") != job.commit:
        raise RuntimeError("digest source commit does not match this analysis")
    marker = job.dir / "cache.json.tmp"
    marker.write_text(json.dumps(identity, sort_keys=True, ensure_ascii=True), encoding="utf-8")
    marker.replace(job.dir / "cache.json")


def run_job(job: Job) -> None:
    with RUN_SLOT:
        job.status = "running"
        job.started = time.time()
        try:
            repo_dir = job.dir / "repo"
            out_dir = job.dir / "digest"
            if job.dir.exists():
                shutil.rmtree(job.dir, ignore_errors=True)
            job.dir.mkdir(parents=True)
            job.log.append(f"cloning {job.repo.public_url} @ {job.commit[:10]}")
            # the digest script does a partial clone of exactly this commit (big art blobs are never downloaded)
            cmd = [sys.executable, str(DIGEST_SCRIPT), job.repo.clone_url, "--ref", job.commit,
                   "--workdir", str(repo_dir), "--out", str(out_dir),
                   "--source-label", f"{job.repo.public_url} ({job.commit})",
                   "--workers", str(WORKERS)]
            if job.project:
                cmd += ["--project", job.project]
            env = dict(os.environ, GIT_TERMINAL_PROMPT="0", PYTHONIOENCODING="utf-8:replace")
            env.setdefault("UE_REPO_READER_CACHE", str(DATA / "cache"))  # keep the parser pre-fetched at image build

            def log_line(line):
                job.log.append(scrub(line))
                del job.log[:-40]

            code = run_process(cmd, env=env, timeout=JOB_TIMEOUT, on_line=log_line)
            if code != 0 or not (out_dir / "INDEX.md").is_file():
                raise RuntimeError("digest failed: " + " | ".join(job.log[-5:]))
            publish_cache(job)
            job.status = "done"
        except Exception as e:  # noqa: BLE001
            job.status = "error"
            job.error = scrub(f"{type(e).__name__}: {e}")
        finally:
            job.finished = time.time()
            job.done_event.set()
            prune()


def prune() -> None:
    dirs = sorted((p for p in (DATA / "work").iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    active = {j.key for j in JOBS.values() if j.status in ("queued", "running")}
    for p in dirs[KEEP:]:
        if p.name not in active:
            shutil.rmtree(p, ignore_errors=True)


def start_or_get(repo: RepoRef, project: str | None, refresh: bool) -> Job:
    commit = resolve_commit(repo)
    key = digest_key(repo, commit, project)
    with LOCK:
        job = BY_KEY.get(key)
        cached = completed_cache(DATA / "work" / key, cache_identity(repo, commit, project))
        if job and job.status in ("queued", "running"):
            return job
        if cached and not refresh:
            if not job or job.status != "done":
                job = Job(uuid.uuid4().hex[:10], key, repo, commit, project, status="done", finished=time.time())
                job.done_event.set()
                JOBS[job.id] = job
                BY_KEY[key] = job
            os.utime(DATA / "work" / key)
            return job
        job = Job(uuid.uuid4().hex[:10], key, repo, commit, project)
        JOBS[job.id] = job
        BY_KEY[key] = job
    threading.Thread(target=run_job, args=(job,), daemon=True).start()
    return job


def job_report(job: Job, wait: int) -> str:
    if job.status in ("queued", "running"):
        job.done_event.wait(timeout=wait)
    if job.status == "done":
        if not completed_cache(job.dir):
            return f"job_id: {job.id}\nstatus: error\nDigest expired or is being refreshed — run analyze_repo again."
        try:
            index = (job.dir / "digest" / "INDEX.md").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return f"job_id: {job.id}\nstatus: error\nDigest expired or is being refreshed — run analyze_repo again."
        head = (f"digest_id: {job.key}\nstatus: done ({job.repo.public_url} @ {job.commit[:10]})\n"
                f"Use read_digest_file / search_digest / read_source_file with this digest_id.\n\n")
        return head + page(index, 0, "INDEX.md")
    if job.status == "error":
        return f"job_id: {job.id}\nstatus: error\n{job.error}"
    elapsed = int(time.time() - job.started)
    last = job.log[-1] if job.log else ""
    return (f"job_id: {job.id}\nstatus: {job.status} ({elapsed}s elapsed; last step: {last})\n"
            f"The analysis is still running. Call wait_for_analysis with job_id '{job.id}' to keep waiting.")


def page(text: str, offset: int, label: str, limit: int = PAGE) -> str:
    offset = max(0, offset)
    chunk = text[offset:offset + limit]
    end = offset + len(chunk)
    tail = (f"\n\n[{label}: characters {offset}-{end} of {len(text)}. More: call again with offset={end}]"
            if end < len(text) else "")
    return chunk + tail


def digest_dir(digest_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", digest_id or ""):
        raise ValueError("invalid digest_id")
    d = DATA / "work" / digest_id
    if not completed_cache(d):
        raise ValueError("unknown or expired digest_id — run analyze_repo again")
    os.utime(d)
    return d


def safe_path(base: Path, rel: str) -> Path:
    p = (base / rel.lstrip("/\\")).resolve()
    if base.resolve() not in (p, *p.parents):
        raise ValueError("path escapes the repository")
    return p


# =========================================================================== MCP server

INSTRUCTIONS = """Reads Unreal Engine projects from a git URL, including Blueprints, maps and data assets decoded
from binary .uasset/.umap files (no editor needed).
Workflow: call analyze_repo with the URL (it waits up to ~45 s; if it reports 'running', call wait_for_analysis
until done). Read the returned INDEX.md fully, then read the files you need: maps/*.md (level Blueprint, placed
actors), blueprints/*.md (components, variables, graphs as execution-flow pseudo-code), data/*.md (DataTables,
structs, enums, behavior trees, input mappings, DataAssets), cpp/CLASSES.md, and real C++ sources through
read_source_file. Quote Blueprint paths and pseudo-code lines, state coverage from the Parse report, and do not
guess the content of nodes marked unreadable."""

security = TransportSecuritySettings(
    enable_dns_rebinding_protection=bool(ALLOWED_HOSTS),
    allowed_hosts=ALLOWED_HOSTS,
    allowed_origins=[],
)
mcp = FastMCP(
    "ue-repo-reader",
    instructions=INSTRUCTIONS,
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "8000")),
    streamable_http_path=f"/{SECRET}/mcp" if SECRET else "/mcp",
    stateless_http=True,
    transport_security=security,
)
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


@mcp.tool(title="Analyze Unreal repo", annotations=READ_ONLY)
def analyze_repo(repo_url: str, ref: str | None = None, project: str | None = None, refresh: bool = False) -> str:
    """Analyze an Unreal Engine git repository and return its digest index (INDEX.md).

    repo_url: https URL of the repo (GitHub/GitLab/Bitbucket) or 'owner/repo' for GitHub.
    ref: optional branch, tag or full 40-character commit SHA (a /tree/<branch> URL also works).
    project: optional .uproject name when the repo contains several projects.
    refresh: re-analyze even if this exact commit was analyzed before.
    Returns the digest_id used by the other tools, or a job_id to pass to wait_for_analysis while it runs."""
    try:
        repo = parse_repo(repo_url, ref)
    except ValueError as e:
        return f"error: {e}"
    if ALLOWED_OWNERS and repo.owner.lower() not in ALLOWED_OWNERS:
        return f"error: this server only analyzes repositories of: {', '.join(sorted(ALLOWED_OWNERS))}"
    try:
        job = start_or_get(repo, project, refresh)
    except Exception as e:  # noqa: BLE001
        return "error: " + scrub(str(e)) + ("\n(Private repo? The server needs GITHUB_TOKEN with access to it.)"
                                             if "not found" in str(e).lower() or "authentication" in str(e).lower() else "")
    return job_report(job, WAIT)


@mcp.tool(title="Wait for analysis", annotations=READ_ONLY)
def wait_for_analysis(job_id: str) -> str:
    """Keep waiting (up to ~45 s per call) for an analysis started by analyze_repo; returns INDEX.md when done."""
    job = JOBS.get(job_id)
    if not job:
        return "error: unknown job_id (the server may have restarted) — call analyze_repo again"
    return job_report(job, WAIT)


@mcp.tool(title="List digest files", annotations=READ_ONLY)
def list_digest_files(digest_id: str, folder: str = "") -> str:
    """List files in a digest (optionally under a folder such as 'blueprints/Game/UI' or 'maps')."""
    try:
        base = digest_dir(digest_id) / "digest"
        root = safe_path(base, folder) if folder else base
    except ValueError as e:
        return f"error: {e}"
    files = sorted(p for p in root.rglob("*.md") if p.is_file())
    lines = [f"{p.relative_to(base).as_posix()}  ({p.stat().st_size // 1024 + 1} KB)" for p in files[:600]]
    more = f"\n… {len(files) - 600} more — narrow with folder=" if len(files) > 600 else ""
    return "\n".join(lines) + more if lines else "(no files)"


@mcp.tool(title="Read digest file", annotations=READ_ONLY)
def read_digest_file(digest_id: str, path: str, offset: int = 0) -> str:
    """Read a digest file, e.g. 'INDEX.md', 'blueprints/Game/BP_Player.md', 'maps/Game/Maps/L_Main.md'.
    Long files are paged: pass the offset given at the end of the previous page."""
    try:
        base = digest_dir(digest_id) / "digest"
        p = safe_path(base, path)
    except ValueError as e:
        return f"error: {e}"
    if not p.is_file():
        return f"error: {path} not found — use list_digest_files or search_digest"
    return page(p.read_text(encoding="utf-8", errors="replace"), offset, path)


@mcp.tool(title="Search digest", annotations=READ_ONLY)
def search_digest(digest_id: str, query: str, include_source: bool = False, max_results: int = 60) -> str:
    """Case-insensitive search across the digest (Blueprints, maps, data, index). With include_source=true it
    also searches the repo's C++/config text files. Returns file:line: text."""
    try:
        d = digest_dir(digest_id)
    except ValueError as e:
        return f"error: {e}"
    q = query.lower()
    hits = []
    roots = [(d / "digest", "*.md", "")]
    if include_source:
        roots.append((d / "repo", "*", "repo:"))
    for base, pattern, prefix in roots:
        for p in sorted(base.rglob(pattern)):
            if not p.is_file() or ".git" in p.parts:
                continue
            if prefix and (p.suffix.lower() not in SOURCE_EXT or p.stat().st_size > 2_000_000):
                continue
            try:
                for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if q in line.lower():
                        hits.append(f"{prefix}{p.relative_to(base).as_posix()}:{i}: {line.strip()[:220]}")
                        if len(hits) >= max_results:
                            return "\n".join(hits) + "\n… more results — refine the query"
            except OSError:
                continue
    return "\n".join(hits) if hits else "(no matches)"


@mcp.tool(title="Read source file", annotations=READ_ONLY)
def read_source_file(digest_id: str, path: str, offset: int = 0) -> str:
    """Read a text file from the analyzed repo (C++ .h/.cpp, .Build.cs, Config/*.ini, .uproject, …).
    A path ending in '/' or a glob such as 'Source/**/*.h' lists matching files instead."""
    try:
        base = digest_dir(digest_id) / "repo"
    except ValueError as e:
        return f"error: {e}"
    if path.endswith("/") or any(ch in path for ch in "*?["):
        pattern = path + "**/*" if path.endswith("/") else path
        try:
            matches = [p for p in base.glob(pattern.lstrip("/")) if p.is_file() and ".git" not in p.parts
                       and p.suffix.lower() in SOURCE_EXT]
        except ValueError as e:
            return f"error: {e}"
        lines = [p.relative_to(base).as_posix() for p in sorted(matches)[:400]]
        return "\n".join(lines) if lines else "(no matching text files)"
    try:
        p = safe_path(base, path)
    except ValueError as e:
        return f"error: {e}"
    if ".git" in p.relative_to(base.resolve()).parts:
        return "error: not allowed"
    if not p.is_file():
        return f"error: {path} not found"
    if p.suffix.lower() not in SOURCE_EXT and p.name not in (".gitattributes", ".gitignore"):
        return "error: binary asset — read its rendering under blueprints/, data/ or maps/ in the digest instead"
    return page(p.read_text(encoding="utf-8", errors="replace"), offset, path)


@mcp.custom_route("/", methods=["GET"])
async def health(_request):
    from starlette.responses import PlainTextResponse
    return PlainTextResponse("ue-repo-reader MCP server is running.\n")


def main():
    print(f"ue-repo-reader MCP: http://{mcp.settings.host}:{mcp.settings.port}{mcp.settings.streamable_http_path}",
          file=sys.stderr, flush=True)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
