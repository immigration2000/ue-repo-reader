"""Supervised Claude jobs: subprocess outcomes, deadlines and review separation; no API calls."""
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from threading import Timer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import claude_delegate as C


def job(root):
    value = Path(root) / "job"
    value.mkdir()
    C.save(value, {"phase": "prepared", "workdir": root, "session_id": "expected-session"})
    return value


def test_claude_job_success_requires_manager_review():
    with tempfile.TemporaryDirectory() as tmp:
        path = job(tmp)
        code = ("import json,sys; prompt=sys.stdin.read(); "
                "print(json.dumps({'type':'system','session_id':'real-session'})); "
                "print(json.dumps({'type':'assistant','message':{'content':[{'type':'tool_use','name':'Edit'}]}})); "
                "print(json.dumps({'type':'result','is_error':False,'result':prompt}))")
        state = C.run(path, '한글 "task"\nsecond line', [sys.executable, "-c", code], 10)
        assert state["phase"] == "awaiting_review", state
        assert state["session_id"] == "real-session" and state["result"] == '한글 "task"\nsecond line'
        assert not (path / "running.lock").exists()
        assert C.summarize(path / state["stdout"])[2] == ["Edit"]
        with redirect_stdout(io.StringIO()):
            C.main(["review", str(path), "--outcome", "accepted", "--note", "Diff and independent tests passed"])
        assert C.load(path)["phase"] == "accepted"


def test_claude_job_failures_and_denials_never_complete():
    cases = [("print('not JSON')", "needs_attention"),
             ("print('{\"type\":\"result\",\"is_error\":true,\"result\":\"login required\"}')", "needs_attention"),
             ("print('{\"type\":\"result\",\"permission_denials\":[{\"tool_name\":\"Bash\"}]}')", "needs_attention"),
             ("print('{\"type\":\"result\"}'); raise SystemExit(7)", "needs_attention")]
    for code, expected in cases:
        with tempfile.TemporaryDirectory() as tmp:
            path = job(tmp)
            state = C.run(path, "work", [sys.executable, "-c", "import sys; sys.stdin.read(); " + code], 10)
            assert state["phase"] == expected, state
            try:
                C.main(["review", str(path), "--outcome", "accepted", "--note", "must be rejected"])
            except ValueError:
                pass
            else:
                raise AssertionError("failed worker accepted")


def test_claude_job_silent_deadline_and_stop():
    for stop in (False, True):
        with tempfile.TemporaryDirectory() as tmp:
            path = job(tmp)
            timer = Timer(0.25, lambda: (path / "stop.request").write_text("stop", encoding="utf-8")) if stop else None
            if timer:
                timer.start()
            try:
                state = C.run(path, "work", [sys.executable, "-c", "import sys,time; sys.stdin.read(); time.sleep(20)"], 5 if stop else 0.5)
            finally:
                if timer:
                    timer.join()
            assert state["phase"] == ("stopped" if stop else "timed_out"), state
            assert state["elapsed_seconds"] < 8 and not (path / "running.lock").exists()
    # Windows communicate(input=...) can block on stdin before its timeout starts.
    # Fill the pipe of a child that never reads it; stop/timeout must still be enforced.
    with tempfile.TemporaryDirectory() as tmp:
        path = job(tmp)
        state = C.run(path, "큰 지시" * 200000, [sys.executable, "-c", "import time; time.sleep(20)"], 0.5)
        assert state["phase"] == "timed_out" and state["elapsed_seconds"] < 8, state


def test_claude_job_tool_scope_and_overlap_guards():
    for readonly in (False, True):
        argv = C.command("claude.exe", "session", True, readonly)
        assert argv[-2:] == ["--resume", "session"]
        assert "bypassPermissions" not in argv and "--dangerously-skip-permissions" not in argv
        assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
        tools = argv[argv.index("--tools") + 1].split(",")
        assert "Bash" not in tools and "PowerShell" not in tools
        assert ("Write" in tools) != readonly
    with tempfile.TemporaryDirectory() as tmp:
        path = job(tmp)
        (path / "running.lock").write_text("another manager", encoding="utf-8")
        (path / "stop.request").write_text("keep pending stop", encoding="utf-8")
        prompt = Path(tmp) / "prompt.txt"
        prompt.write_text("fix", encoding="utf-8")
        with patch.object(C, "executable", return_value="claude.exe"):
            try:
                C.main(["continue", str(path), "--prompt-file", str(prompt)])
            except ValueError as error:
                assert "already running" in str(error)
            else:
                raise AssertionError("overlapping manager allowed")
        assert (path / "stop.request").read_text(encoding="utf-8") == "keep pending stop"
        try:
            C.worktree(Path(tmp))
        except ValueError as error:
            assert "separate git worktree" in str(error)
        else:
            raise AssertionError("non-worktree edit target allowed")
    with tempfile.TemporaryDirectory() as tmp:
        path = job(tmp)
        with patch.object(C, "save", side_effect=OSError("disk full")):
            try:
                C.run(path, "work", ["not launched"], 1)
            except OSError:
                pass
            else:
                raise AssertionError("initial state write failure ignored")
        assert not (path / "running.lock").exists(), "startup failure left a stale running lock"
