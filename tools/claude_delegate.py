#!/usr/bin/env python3
"""Run the real Claude Code CLI as a file-editing worker; Codex reviews and integrates."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = "Read,Glob,Grep,Edit,Write"


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def save(job: Path, state: dict):
    temp = job / "state.tmp"
    temp.write_text(json.dumps(state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    temp.replace(job / "state.json")


def load(job: Path):
    return json.loads((job / "state.json").read_text(encoding="utf-8"))


def executable(value=None):
    found = value or shutil.which("claude")
    if not found:
        raise ValueError("Claude Code is not installed; supply --claude with its executable path")
    path = Path(found).resolve()
    if path.suffix.lower() in (".cmd", ".bat", ".ps1"):
        # npm on Windows installs a native binary alongside its shell shim.
        path = path.parent / "node_modules/@anthropic-ai/claude-code/bin/claude.exe"
    if not path.is_file():
        raise ValueError("Claude executable not found; supply --claude (shell shims are not executed)")
    return str(path)


def command(claude: str, session: str, resume: bool, read_only=False):
    tools = "Read,Glob,Grep" if read_only else TOOLS
    return [claude, "--print", "--verbose", "--output-format", "stream-json",
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--tools", tools, "--allowedTools", tools, "--disable-slash-commands", "--no-chrome",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--resume" if resume else "--session-id", session]


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, encoding="utf-8", check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.kill()
        process.wait(timeout=5)


def summarize(path: Path):
    session, result, tools = None, None, []
    if path.is_file():
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("session_id"):
                    session = event["session_id"]
                if event.get("type") == "result":
                    result = event
                for content in (event.get("message") or {}).get("content", []):
                    if isinstance(content, dict) and content.get("type") == "tool_use":
                        tools.append(content.get("name", "?"))
    return session, result, tools[-8:]


def run(job: Path, prompt: str, argv: list[str], timeout: float):
    """Keep an independent deadline even if the CLI never writes stdout."""
    lock = job / "running.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    state = load(job)
    process = None
    state.update(phase="running", started_at=timestamp(), manager_pid=os.getpid())
    attempt = state.get("attempt", 0) + 1
    state.update(attempt=attempt, stdout=f"attempt-{attempt}.jsonl", stderr=f"attempt-{attempt}.stderr.txt")
    (job / f"attempt-{attempt}.prompt.txt").write_text(prompt, encoding="utf-8")
    save(job, state)
    started = time.monotonic()
    try:
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        with (job / state["stdout"]).open("w", encoding="utf-8") as stdout, \
                (job / state["stderr"]).open("w", encoding="utf-8") as stderr:
            process = subprocess.Popen(argv, cwd=state["workdir"], stdin=subprocess.PIPE,
                                       stdout=stdout, stderr=stderr, encoding="utf-8", errors="replace",
                                       env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}, **options)
            state["worker_pid"] = process.pid
            save(job, state)
            first = True
            while True:
                if (job / "stop.request").exists():
                    state["phase"] = "stopped"
                    stop_process(process)
                    break
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    state["phase"] = "timed_out"
                    stop_process(process)
                    break
                try:
                    process.communicate(input=prompt if first else None, timeout=min(1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    first = False
            state["exit_code"] = process.returncode
        session, result, _ = summarize(job / state["stdout"])
        if session:
            state["session_id"] = session
        if state["phase"] == "running":
            state["phase"] = "awaiting_review" if process.returncode == 0 and result and not result.get("is_error") else "needs_attention"
            if result and result.get("permission_denials"):
                state["phase"] = "needs_attention"
        state["result"] = str((result or {}).get("result", ""))[:16000]
    except KeyboardInterrupt:
        state["phase"] = "stopped"
        if process:
            stop_process(process)
    except Exception as error:
        state.update(phase="needs_attention", error=f"{type(error).__name__}: {error}")
        if process:
            stop_process(process)
    finally:
        state.update(finished_at=timestamp(), elapsed_seconds=round(time.monotonic() - started, 2))
        try:
            save(job, state)
        finally:
            lock.unlink()
    return state


def worktree(path: Path, read_only=False):
    if not read_only and not (path / ".git").is_file():
        raise ValueError("Editing workers require a separate git worktree, not the primary checkout")
    result = subprocess.run(["git", "branch", "--show-current"], cwd=path, capture_output=True,
                            encoding="utf-8", check=True)
    branch = result.stdout.strip()
    if not read_only and not branch.startswith(("claude/", "codex/")):
        raise ValueError("Use an isolated claude/* or codex/* branch; main/master/detached workspaces are refused")
    return branch


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    start = subs.add_parser("start")
    start.add_argument("task")
    start.add_argument("--workdir", type=Path, required=True)
    start.add_argument("--state-dir", type=Path, default=ROOT / ".ue-repo-reader/claude-jobs")
    again = subs.add_parser("continue")
    again.add_argument("job", type=Path)
    for sub in (start, again):
        sub.add_argument("--prompt-file", type=Path, required=True)
        sub.add_argument("--claude")
        sub.add_argument("--timeout", type=float, default=1800)
        sub.add_argument("--read-only", action="store_true", help="Review with Read/Glob/Grep only")
    for name in ("status", "stop", "review"):
        sub = subs.add_parser(name)
        sub.add_argument("job", type=Path)
        if name == "review":
            sub.add_argument("--outcome", choices=("accepted", "rework", "rejected"), required=True)
            sub.add_argument("--note", required=True)
    args = parser.parse_args(argv)
    if args.action in ("status", "stop", "review"):
        job = args.job.resolve()
        state = load(job)
        if args.action == "stop":
            if state["phase"] != "running":
                raise ValueError("The job is not running")
            (job / "stop.request").write_text(timestamp(), encoding="utf-8")
        elif args.action == "review":
            if (job / "running.lock").exists():
                raise ValueError("Wait for the worker to exit before recording review")
            if args.outcome == "accepted" and state["phase"] != "awaiting_review":
                raise ValueError("Only a successful, completed worker run can be accepted")
            state.update(phase=args.outcome, review_note=args.note, reviewed_at=timestamp())
            save(job, state)
        _, _, tools = summarize(job / state.get("stdout", "missing.jsonl"))
        print(json.dumps({**state, "recent_tools": tools, "job": str(job)}, ensure_ascii=False, indent=2))
        return 0
    if not 0 < args.timeout <= 43200:
        raise ValueError("timeout must be greater than zero and at most 43200 seconds")
    prompt = args.prompt_file.read_text(encoding="utf-8")
    if not prompt.strip() or len(prompt.encode("utf-8")) > 1_000_000:
        raise ValueError("prompt must contain text and fit in 1MB")
    claude = executable(args.claude)
    if args.action == "start":
        if not re.fullmatch(r"[A-Z][A-Z0-9-]{0,39}", args.task):
            raise ValueError("task must be a short uppercase task ID")
        cwd = args.workdir.resolve()
        branch = worktree(cwd, args.read_only)
        job = args.state_dir.resolve() / (args.task + "-" + uuid.uuid4().hex[:8])
        job.mkdir(parents=True)
        session = str(uuid.uuid4())
        save(job, {"task": args.task, "workdir": str(cwd), "branch": branch, "created_at": timestamp(),
                   "session_id": session, "phase": "prepared", "claude": claude, "read_only": args.read_only})
        resume = False
    else:
        job = args.job.resolve()
        state = load(job)
        if state["phase"] in ("accepted", "rejected"):
            raise ValueError("This job is closed; start a new task")
        if (job / "running.lock").exists():
            raise ValueError("The job is already running")
        args.read_only = args.read_only or state.get("read_only", False)
        if worktree(Path(state["workdir"]), args.read_only) != state["branch"]:
            raise ValueError("The worker branch changed since assignment")
        session = state["session_id"]
        resume = True
        (job / "stop.request").unlink(missing_ok=True)
        state["read_only"] = args.read_only
        save(job, state)
    print(f"Claude Code job: {job}", flush=True)
    state = run(job, prompt, command(claude, session, resume, args.read_only), args.timeout)
    print(json.dumps({"phase": state["phase"], "job": str(job), "session_id": state["session_id"]}, ensure_ascii=False))
    return 0 if state["phase"] == "awaiting_review" else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
