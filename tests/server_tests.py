"""Server regressions without network, clones or the optional MCP SDK.

Only SDK decorators are stubbed. Jobs, subprocess trees and cache files are real.
The installed SDK/protocol is exercised separately by server_smoke.py.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
from processes import run_process


@contextmanager
def server_fixture():
    class SDK:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self, **kwargs):
            return lambda fn: fn

        def custom_route(self, *args, **kwargs):
            return lambda fn: fn

    names = ("mcp", "mcp.server", "mcp.server.fastmcp", "mcp.server.transport_security", "mcp.types")
    modules = {name: ModuleType(name) for name in names}
    modules["mcp.server.fastmcp"].FastMCP = SDK
    modules["mcp.server.transport_security"].TransportSecuritySettings = SimpleNamespace
    modules["mcp.types"].ToolAnnotations = SimpleNamespace
    with tempfile.TemporaryDirectory(prefix="ue-server-") as tmp, \
            patch.dict(os.environ, {"UE_READER_DATA": tmp, "GITHUB_TOKEN": "test-secret-token"}), \
            patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("_ue_test_server", ROOT / "server/server.py")
        server = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {spec.name: server}):
            spec.loader.exec_module(server)
            yield server


def _run(code, *, timeout=1, lines=None):
    lines = [] if lines is None else lines
    env = dict(os.environ, PYTHONIOENCODING="utf-8:replace")
    return run_process([sys.executable, "-u", "-c", code], env=env, timeout=timeout, on_line=lines.append)


def test_server_deadline_without_output():
    for code in ("import time; time.sleep(120)",
                 "import time; print('unfinished', end='', flush=True); time.sleep(120)",
                 "import os,time; os.close(1); os.close(2); time.sleep(120)",
                 "import os,time\nwhile True: os.write(1, b'x'*4096); time.sleep(.001)"):
        lines = []
        started = time.monotonic()
        try:
            _run(code, timeout=.7, lines=lines)
        except TimeoutError as exc:
            assert "exceeded 0.7s" in str(exc)
        else:
            raise AssertionError("analysis did not time out")
        assert time.monotonic() - started < 6, "deadline blocked on stdout"
        assert all(len(line) <= 4096 for line in lines), "unbounded unterminated line"
    assert not any(t.name == "ue-analysis-output" for t in threading.enumerate()), "pipe reader leaked"


def _is_running(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes as W
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes, api.OpenProcess.restype = [W.DWORD, W.BOOL, W.DWORD], W.HANDLE
        api.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
        api.CloseHandle.argtypes = [W.HANDLE]
        handle = api.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = W.DWORD()
        try:
            assert api.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            api.CloseHandle(handle)
    # A killed orphan may briefly remain a zombie until its OS reaper collects it.
    status = Path(f"/proc/{pid}/stat")
    if status.exists() and status.read_text(encoding="utf-8").split()[2] == "Z":
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_server_deadline_kills_descendants():
    with tempfile.TemporaryDirectory(prefix="ue-tree-") as tmp:
        pidfile = Path(tmp) / "child.json"
        child = "import time; time.sleep(120)"
        prefix = ("import subprocess,sys,json,os,time; from pathlib import Path; "
                  f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
                  f"Path({str(pidfile)!r}).write_text(json.dumps([os.getpid(),p.pid]),encoding='utf-8'); ")
        # Both a live parent and an exited parent whose child holds stdout open.
        for tail in ("time.sleep(120)", "sys.exit(0)"):
            try:
                _run(prefix + tail, timeout=1.2)
            except TimeoutError:
                pass
            else:
                raise AssertionError("inherited stdout bypassed deadline")
            assert pidfile.is_file(), "fixture did not launch before deadline"
            pids = json.loads(pidfile.read_text(encoding="utf-8"))
            until = time.monotonic() + 3
            while any(_is_running(pid) for pid in pids) and time.monotonic() < until:
                time.sleep(.02)
            assert not any(_is_running(pid) for pid in pids), "descendant survived timeout"
            pidfile.unlink()


def test_server_output_and_exit_status():
    lines = []
    code = "import sys; print('한글 출력'); print('stderr', file=sys.stderr); sys.exit(7)"
    assert _run(code, timeout=5, lines=lines) == 7
    assert "한글 출력" in lines and "stderr" in lines, lines
    assert _run("print('ok')", timeout=5) == 0


def test_server_job_timeout_releases_slot():
    with server_fixture() as server:
        script = Path(server.DATA) / "fake_digest.py"
        script.write_text("import time; print('test-secret-token', flush=True); time.sleep(120)", encoding="utf-8")
        server.DIGEST_SCRIPT, server.JOB_TIMEOUT = script, 1
        repo = server.RepoRef("github.com", "owner", "repo", None)
        job = server.Job("test", "test", repo, "a" * 40, None)
        server.run_job(job)
        assert job.status == "error" and job.done_event.is_set()
        assert "exceeded 1s" in job.error and job.finished is not None
        assert "***" in job.log and "test-secret-token" not in str(job.log)
        assert len(job.log) <= 40
        assert server.RUN_SLOT.acquire(blocking=False), "analysis slot leaked"
        server.RUN_SLOT.release()
        # A following job can run, and a failed exit is not marked done.
        script.write_text("import sys; print('failure'); sys.exit(7)", encoding="utf-8")
        next_job = server.Job("next", "next", repo, "b" * 40, None)
        server.run_job(next_job)
        assert next_job.status == "error" and "digest failed" in next_job.error


def test_server_cache_key_collisions_and_version():
    with server_fixture() as server:
        repo = server.RepoRef("github.com", "owner", "repo", "main")
        commit = "a" * 40
        projects = [None, "Chapter/A", "Chapter-A", "한글/A", "../A", "./A",
                    "a" * 45 + "/One", "a" * 45 + "/Two"]
        keys = {server.digest_key(repo, commit, project) for project in projects}
        assert len(keys) == len(projects), "project identity collided"
        key = server.digest_key(repo, commit, None)
        assert key != server.digest_key(repo, "a" * 12 + "b" * 28, None), "commit truncated"
        assert key != server.digest_key(server.RepoRef("gitlab.com", "owner", "repo", None), commit, None)
        assert key != server.digest_key(server.RepoRef("github.com", "other", "repo", None), commit, None)
        assert key == server.digest_key(server.RepoRef("github.com", "owner", "repo", "tag"), commit, "")
        with patch.object(server, "DIGEST_VERSION", "next"):
            assert key != server.digest_key(repo, commit, None), "tool version omitted"
        with patch.object(server, "CACHE_SCHEMA", 2):
            assert key != server.digest_key(repo, commit, None), "cache schema omitted"
        assert "test-secret-token" not in key and len(key) < 120
        with patch.object(server, "git", return_value=""):
            assert server.resolve_commit(server.RepoRef("github.com", "owner", "repo", commit)) == commit
            try:
                server.resolve_commit(server.RepoRef("github.com", "owner", "repo", commit[:12]))
            except ValueError as exc:
                assert "full 40-character" in str(exc)
            else:
                raise AssertionError("unresolved short SHA accepted as immutable cache identity")


def _cache_job(server, project=None):
    repo = server.RepoRef("github.com", "owner", "repo", None)
    commit = "a" * 40
    job = server.Job("cache", server.digest_key(repo, commit, project), repo, commit, project)
    (job.dir / "digest").mkdir(parents=True)
    (job.dir / "digest/INDEX.md").write_text("# cached", encoding="utf-8")
    (job.dir / "digest/digest.json").write_text(json.dumps({"tool": f"ue-repo-reader {server.DIGEST_VERSION}",
                                                          "source": {"commit": commit}}), encoding="utf-8")
    return job


def test_server_cache_requires_completion_and_identity():
    with server_fixture() as server:
        job = _cache_job(server, "한글/A")
        identity = server.cache_identity(job.repo, job.commit, job.project)
        assert not server.completed_cache(job.dir), "partial INDEX reused"
        server.publish_cache(job)
        assert server.completed_cache(job.dir, identity)
        assert server.digest_dir(job.key) == job.dir
        marker = job.dir / "cache.json"
        valid = marker.read_text(encoding="utf-8")
        assert "test-secret-token" not in valid
        for text in ("{", "[]", "null", json.dumps(dict(identity, tool="ue-repo-reader old")),
                     json.dumps(dict(identity, project="한글-A")), json.dumps(dict(identity, schema=0)),
                     json.dumps(dict(identity, commit="b" * 40))):
            marker.write_text(text, encoding="utf-8")
            assert not server.completed_cache(job.dir, identity), text
            try:
                server.digest_dir(job.key)
            except ValueError:
                pass
            else:
                raise AssertionError("stale/partial digest_id served")
        marker.write_text(valid, encoding="utf-8")
        with patch.object(server, "DIGEST_VERSION", "next"):
            assert not server.completed_cache(job.dir), "old producer cache accepted"
        (job.dir / "digest/INDEX.md").unlink()
        assert not server.completed_cache(job.dir)
        job.status = "done"
        assert "status: error" in server.job_report(job, 0), "expired cache reported done"


def test_server_cache_reuse_refresh_and_deduplication():
    with server_fixture() as server:
        original = _cache_job(server)
        server.publish_cache(original)
        with patch.object(server, "resolve_commit", return_value=original.commit), \
                patch.object(server.threading, "Thread") as worker:
            cached = server.start_or_get(original.repo, None, False)
            assert cached.status == "done" and cached.done_event.is_set()
            assert server.start_or_get(original.repo, None, False) is cached
            worker.assert_not_called()
            refresh = server.start_or_get(original.repo, None, True)
            assert refresh is not cached and refresh.status == "queued"
            assert server.start_or_get(original.repo, None, True) is refresh
            assert worker.call_count == 1, "queued refresh was duplicated"
            # A completed failed job must not hide a good on-disk result.
            refresh.status = "error"
            recovered = server.start_or_get(original.repo, None, False)
            assert recovered.status == "done" and recovered is not refresh
            (original.dir / "cache.json").unlink()
            restart = server.start_or_get(original.repo, None, False)
            assert restart.status == "queued" and worker.call_count == 2


def test_server_job_publishes_only_current_success():
    with server_fixture() as server:
        script = Path(server.DATA) / "fake_digest.py"
        server.DIGEST_SCRIPT, server.JOB_TIMEOUT = script, 5
        repo = server.RepoRef("github.com", "owner", "repo", None)
        commit = "a" * 40
        for version, source_commit, exit_code, expected in (
                (server.DIGEST_VERSION, commit, 0, "done"), ("old", commit, 0, "error"),
                (server.DIGEST_VERSION, "b" * 40, 0, "error"), (server.DIGEST_VERSION, commit, 7, "error")):
            payload = {"tool": f"ue-repo-reader {version}", "source": {"commit": source_commit}}
            script.write_text("import sys,json; from pathlib import Path; "
                              "out=Path(sys.argv[sys.argv.index('--out')+1]); out.mkdir(); "
                              "(out/'INDEX.md').write_text('# result',encoding='utf-8'); "
                              f"(out/'digest.json').write_text({json.dumps(payload)!r},encoding='utf-8'); "
                              f"print('line\\n'*60); sys.exit({exit_code})", encoding="utf-8")
            key = server.digest_key(repo, commit, None)
            job = server.Job("run", key, repo, commit, None)
            server.run_job(job)
            assert job.status == expected, job.error
            assert job.done_event.is_set() and len(job.log) == 40
            assert server.completed_cache(job.dir) == (expected == "done")
            assert (job.dir / "cache.json").exists() == (expected == "done")
