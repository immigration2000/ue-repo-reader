#!/usr/bin/env python3
"""Optional real MCP/HTTP smoke; reuses a pinned local eg clone, no new clone.

Install server/requirements.txt into a venv, or pass --deps for a pip --target
directory. Temporary server data stays in tests/.cache; bind only to loopback.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import site
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deps", type=Path, help="optional isolated pip --target SDK directory")
    parser.add_argument("--repo", type=Path, default=ROOT / "tests/.cache/eg")
    args = parser.parse_args()
    if args.deps:
        args.deps = args.deps.resolve()
        site.addsitedir(str(args.deps))  # process .pth too (pywin32 on Windows)
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    repo = args.repo.resolve()
    fixture = json.loads((ROOT / "tests/fixtures.json").read_text(encoding="utf-8"))["eg"]
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                            capture_output=True, text=True, encoding="utf-8").stdout.strip()
    assert commit == fixture["sha"], "use the pinned eg fixture from tests/regress.py"
    cache = ROOT / "tests/.cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="server-smoke-", dir=cache) as tmp:
        work = Path(tmp)
        count = work / "runs.txt"
        # Exercise the real CLI and spawn workers using the existing local clone.
        # Only remote resolution/clone are replaced; no external service is needed.
        shim = work / "local_digest.py"
        shim.write_text("import shutil,subprocess,sys; from pathlib import Path\n"
                        "if __name__ == '__main__':\n"
                        f" p=Path({str(count)!r}); p.write_text(p.read_text(encoding='utf-8')+'1' if p.exists() else '1',encoding='utf-8')\n"
                        " args=sys.argv[2:]; i=args.index('--workdir'); dest=Path(args[i+1]); del args[i:i+2]\n"
                        f" source=Path({str(repo)!r})\n"
                        " for src in source.rglob('*.uproject'):\n"
                        "  target=dest/src.relative_to(source); target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,target)\n"
                        f" sys.exit(subprocess.call([sys.executable,{str(ROOT / 'scripts/ue_repo_digest.py')!r},{str(repo)!r},*args]))\n",
                        encoding="utf-8")
        bootstrap = work / "serve.py"
        bootstrap.write_text("import sys,site\n" +
                             (f"site.addsitedir({str(args.deps)!r})\n" if args.deps else "") +
                             f"sys.path.insert(0,{str(ROOT / 'server')!r})\n"
                             "import server as S\nfrom pathlib import Path\n"
                             f"S.resolve_commit=lambda repo: {commit!r}\nS.DIGEST_SCRIPT=Path({str(shim)!r})\n"
                             "S.main()\n", encoding="utf-8")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, HOST="127.0.0.1", PORT=str(port), UE_READER_DATA=str(work / "data"),
                   UE_READER_SECRET="smoke", UE_READER_WAIT="1", UE_READER_TIMEOUT="90",
                   UE_READER_ALLOWED_HOSTS="", UE_READER_ALLOWED_OWNERS="", GITHUB_TOKEN="",
                   PYTHONIOENCODING="utf-8:replace")
        url = f"http://127.0.0.1:{port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        async def check(restarted=False):
            async with streamable_http_client(url + "/smoke/mcp") as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    assert len(tools) == 6 and all(t.annotations.readOnlyHint for t in tools)

                    async def call(name, **arguments):
                        result = await session.call_tool(name, arguments)
                        assert not result.isError, result
                        return "\n".join(c.text for c in result.content if c.type == "text")

                    async def analyze(refresh=False):
                        text = await call("analyze_repo", repo_url="owner/repo", ref=commit, refresh=refresh)

                        async def wait_done(text):
                            while "job_id:" in text and "status: error" not in text:
                                job_id = re.search(r"job_id: (\w+)", text).group(1)
                                text = await call("wait_for_analysis", job_id=job_id)
                            return text

                        text = await asyncio.wait_for(wait_done(text), timeout=90)
                        assert "status: done" in text and "1779/1779" in text, text[:3000]
                        return re.search(r"digest_id: ([\w.-]+)", text).group(1)

                    digest_id = await analyze()
                    assert "INDEX.md" in await call("list_digest_files", digest_id=digest_id)
                    assert "ExtractionGame" in await call("read_digest_file", digest_id=digest_id, path="INDEX.md")
                    assert "BP_" in await call("search_digest", digest_id=digest_id, query="BeginPlay")
                    sources = await call("read_source_file", digest_id=digest_id, path="**/*.uproject")
                    assert ".uproject" in sources, sources
                    source = sources.splitlines()[0]
                    assert "EngineAssociation" in await call("read_source_file", digest_id=digest_id, path=source)
                    assert "error:" in await call("read_source_file", digest_id=digest_id, path="../serve.py")
                    assert await analyze() == digest_id
                    assert count.read_text(encoding="utf-8") == ("11" if restarted else "1"), "cache missed"
                    if not restarted:
                        assert await analyze(refresh=True) == digest_id
                        assert count.read_text(encoding="utf-8") == "11", "refresh did not run"

        for restarted in (False, True):
            with (work / f"server-{int(restarted)}.log").open("w", encoding="utf-8") as log:
                proc = subprocess.Popen([sys.executable, str(bootstrap)], env=env, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 15
                    while True:
                        assert proc.poll() is None, "server exited; inspect smoke bootstrap"
                        try:
                            with opener.open(url, timeout=1) as response:
                                assert b"MCP server is running" in response.read()
                            break
                        except urllib.error.URLError:
                            assert time.monotonic() < deadline, "server did not start"
                            time.sleep(.1)
                    asyncio.run(check(restarted))
                finally:
                    proc.terminate()
                    proc.wait(timeout=10)
        print("PASS MCP HTTP: 6 tools, real eg 49 BP / 1779 nodes, cache reuse, refresh and restart reuse")


if __name__ == "__main__":
    main()
