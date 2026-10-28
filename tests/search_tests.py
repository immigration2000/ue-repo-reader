"""MCP literal search, durable index generations, containment and response budgets."""
from __future__ import annotations

import os
import json
import re
import sqlite3
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from server_tests import server_fixture, _cache_job, _support_record
import search_index as S


def test_search_literal_unicode_and_index_reuse():
    with server_fixture() as server:
        job = _cache_job(server)
        document = job.dir / "digest/INDEX.md"
        lines = ["BeginPlay player.Move", '100%_done a"b [x] AND x OR y', "한글 값 AßÄ"]
        document.write_text("\n".join(lines), encoding="utf-8")
        source = job.dir / "repo/Source/Player.cpp"
        source.parent.mkdir(parents=True)
        source.write_text("only_source BeginPlay", encoding="utf-8")
        private = job.dir / "repo/.git/config"
        private.parent.mkdir()
        private.write_text("only_private", encoding="utf-8")
        server.publish_cache(job)
        for query in ("begin", "bEGinPlay", "player.mo", "100%_done", 'a"b', "[x]", "AND", "x OR y", "한", "한글", "한글 값", "ßä"):
            expected = [i for i, line in enumerate(lines, 1) if query.lower() in line.lower()]
            result = server.search_digest(job.key, query)
            actual = [int(n) for n in re.findall(r"INDEX.md:(\d+):", result)]
            assert actual == expected, (query, result)
        assert "repo:Source/Player.cpp:1:" in server.search_digest(job.key, "only_source", True)
        assert "no matches" in server.search_digest(job.key, "only_source", False)
        assert "no matches" in server.search_digest(job.key, "only_private", True)
        assert "error:" in server.search_digest(job.key, " ")
        assert "error:" in server.search_digest(job.key, "x" * 257)
        assert "error:" in server.search_digest(job.key, "a\0b")
        database = job.dir / "search.sqlite"
        with closing(sqlite3.connect(database)) as connection:
            assert "VIRTUAL TABLE" in connection.execute("SELECT sql FROM sqlite_master WHERE name='lines'").fetchone()[0]
        timestamp = database.stat().st_mtime_ns
        # Warm and concurrent calls must not walk/re-read documents or rebuild.
        with patch.object(S, "text_files", side_effect=AssertionError("warm search rescanned files")):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: server.search_digest(job.key, "BeginPlay"), range(8)))
            assert all("INDEX.md:1:" in text for text in results)
        assert database.stat().st_mtime_ns == timestamp
        # Same key, new completed generation: old results must disappear.
        document.write_text("NewGeneration", encoding="utf-8")
        marker = job.dir / "cache.json"
        os.utime(marker, ns=(marker.stat().st_atime_ns, marker.stat().st_mtime_ns + 1_000_000))
        assert "no matches" in server.search_digest(job.key, "BeginPlay")
        assert "INDEX.md:1:" in server.search_digest(job.key, "NewGeneration")
        database.write_bytes(b"broken sqlite")
        assert "INDEX.md:1:" in server.search_digest(job.key, "NewGeneration"), "corrupt index not rebuilt"


def test_search_fallback_and_coverage_limits():
    with server_fixture() as server:
        job = _cache_job(server)
        (job.dir / "digest/INDEX.md").write_text("plain fallback", encoding="utf-8")
        huge = job.dir / "digest/oversized.md"
        huge.write_bytes(b"x" * (S.MAX_FILE_BYTES + 1))
        server.publish_cache(job)
        original = S._table

        class WithoutFTS:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, sql):
                if "VIRTUAL TABLE" in sql:
                    raise sqlite3.OperationalError("no such module: fts5")
                return self.connection.execute(sql)

        with patch.object(S, "_table", side_effect=lambda c: original(WithoutFTS(c))):
            result = server.search_digest(job.key, "fallback")
        assert "INDEX.md:1:" in result and "acceleration unavailable" in result
        assert "omitted 1" in result, result
        page = server.read_digest_file(job.key, "oversized.md")
        assert len(page) <= server.PAGE and "offset=" in page, "large files must still support bounded reading"
        # The coverage warning must survive even when there are no matches.
        assert "omitted 1" in server.search_digest(job.key, "unfindable")
        with patch.object(S, "VERSION", 2), patch.object(S, "MAX_INDEX_BYTES", 1):
            assert "Search coverage" in server.search_digest(job.key, "fallback")
        with patch.object(S, "VERSION", 3), patch.object(S, "MAX_INDEX_FILES", 1):
            assert "limited to 1 files" in server.search_digest(job.key, "fallback")
        (job.dir / "digest/INDEX.md").write_text("one\ntwo\nthree", encoding="utf-8")
        with patch.object(S, "VERSION", 4), patch.object(S, "MAX_INDEX_LINES", 1):
            result = server.search_digest(job.key, "one")
            assert "1 lines" in result and "INDEX.md:1:" in result
        # Bound short literal scans as well as FTS queries, without a real 5s wait.
        (job.dir / "digest/INDEX.md").write_text("many rows\n" * 5000, encoding="utf-8")
        marker = job.dir / "cache.json"
        os.utime(marker, ns=(marker.stat().st_atime_ns, marker.stat().st_mtime_ns + 1_000_000))
        S.ensure_index(job.dir, server.SOURCE_EXT)
        with patch.object(S.time, "monotonic", side_effect=[0] + [6] * 10):
            assert "exceeded 5s" in server.search_digest(job.key, "z")


def test_mcp_response_limits_and_lossless_pagination():
    with server_fixture() as server:
        job = _cache_job(server)
        text = "012345한글🙂\n" * 8000
        (job.dir / "digest/INDEX.md").write_text(text, encoding="utf-8")
        for i in range(250):
            name = "BP_" + "x" * 50 + f"_{i:03}.md"
            (job.dir / "digest" / name).write_text("needle\n" * 3, encoding="utf-8")
        server.publish_cache(job)
        offset, chunks = 0, []
        while True:
            response = server.read_digest_file(job.key, "INDEX.md", offset)
            assert len(response) <= server.PAGE
            chunks.append(response.split("\n\n[", 1)[0])
            next_offset = re.search(r"offset=(\d+)", response)
            if not next_offset:
                break
            assert int(next_offset[1]) > offset
            offset = int(next_offset[1])
        assert "".join(chunks) == text, "paged text lost or duplicated characters"
        offset, names = 0, []
        while True:
            response = server.list_digest_files(job.key, offset=offset)
            assert len(response) <= server.PAGE
            names += [line.split("  (")[0] for line in response.splitlines() if "  (" in line]
            next_offset = re.search(r"offset=(\d+)", response)
            if not next_offset:
                break
            offset = int(next_offset[1])
        assert len(names) == len(set(names)) == 251, "file pagination lost or repeated entries"
        assert len(server.search_digest(job.key, "needle", max_results=100000)) <= server.PAGE
        result = server.search_digest(job.key, "needle", max_results=-1)
        assert len([line for line in result.splitlines() if ".md:" in line]) == 1
        job.status = "done"
        server.JOBS[job.id] = job
        with patch.object(server, "resolve_commit", return_value=job.commit):
            assert len(server.analyze_repo("owner/repo")) <= server.PAGE
        assert len(server.wait_for_analysis(job.id)) <= server.PAGE
        assert len(server.read_source_file(job.key, "x" * 30000)) <= server.PAGE


def test_search_and_source_globs_contain_links():
    with server_fixture() as server:
        job = _cache_job(server)
        repo = job.dir / "repo"
        repo.mkdir()
        outside = Path(server.DATA) / "outside"
        outside.mkdir()
        (outside / "Secret.cpp").write_text("OUTSIDE_SECRET", encoding="utf-8")
        alias = repo / "escape"
        if os.name == "nt":
            subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/c", "mklink", "/J", str(alias), str(outside)],
                           check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        else:
            alias.symlink_to(outside, target_is_directory=True)
        for i in range(220):
            (repo / f"File{i:03}.cpp").write_text("source", encoding="utf-8")
        server.publish_cache(job)
        assert "Secret" not in server.read_source_file(job.key, "**/*.cpp")
        assert "error:" in server.read_source_file(job.key, "../outside/*.cpp")
        assert "error:" in server.read_source_file(job.key, "escape/Secret.cpp")
        assert "no matches" in server.search_digest(job.key, "OUTSIDE_SECRET", include_source=True)
        first = server.read_source_file(job.key, "*.cpp")
        assert "offset=200" in first
        second = server.read_source_file(job.key, "*.cpp", offset=200)
        assert "File200.cpp" in second and "File000.cpp" not in second


def test_cache_refresh_waits_for_open_readers():
    with server_fixture() as server:
        job = _cache_job(server)
        server.publish_cache(job)
        entered, release, mutating = threading.Event(), threading.Event(), threading.Event()
        original_reader, original_remove = server.file_page, server.shutil.rmtree
        results = []

        def slow_read(path, *args, **kwargs):
            with path.open(encoding="utf-8") as handle:
                entered.set()
                assert release.wait(5), "reader not released"
                assert handle.read() == "# cached"
            return original_reader(path, *args, **kwargs)

        def remove(*args, **kwargs):
            mutating.set()
            return original_remove(*args, **kwargs)

        script = Path(server.DATA) / "digest.py"
        payload = json.dumps({"tool": f"ue-repo-reader {server.DIGEST_VERSION}",
                              "source": {"commit": job.commit, "project_support": _support_record()}})
        script.write_text("import sys; from pathlib import Path; "
                          "out=Path(sys.argv[sys.argv.index('--out')+1]); out.mkdir(); "
                          "(out/'INDEX.md').write_text('# refreshed',encoding='utf-8'); "
                          f"(out/'digest.json').write_text({payload!r},encoding='utf-8')", encoding="utf-8")
        server.DIGEST_SCRIPT, server.JOB_TIMEOUT = script, 5
        reader = threading.Thread(target=lambda: results.append(server.read_digest_file(job.key, "INDEX.md")))
        refresh = threading.Thread(target=server.run_job, args=(job,))
        with patch.object(server, "file_page", side_effect=slow_read), \
                patch.object(server.shutil, "rmtree", side_effect=remove):
            reader.start()
            assert entered.wait(2)
            refresh.start()
            try:
                assert not mutating.wait(.2), "refresh deleted a cache with an active reader"
            finally:
                release.set()
                reader.join(10)
                refresh.join(10)
        assert not reader.is_alive() and not refresh.is_alive()
        assert results == ["# cached"] and job.status == "done", job.error
        assert (job.dir / "digest/INDEX.md").read_text(encoding="utf-8") == "# refreshed"
