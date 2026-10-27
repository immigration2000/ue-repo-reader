"""Portable skill packaging checks in disposable roots, never the user's home."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import install_skill as I


def _scratch():
    cache = ROOT / "tests/.cache"
    cache.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="skill-", dir=cache)


def test_skill_install_layouts_and_execution():
    with _scratch() as tmp:
        base = Path(tmp).resolve()
        cwd = base / "다른 작업 [ ],"
        cwd.mkdir()
        expected = {False: {"codex": ".agents", "claude": ".claude", "copilot": ".github"},
                    True: {"codex": ".agents", "claude": ".claude", "copilot": ".agents"}}
        for personal, clients in expected.items():
            for client, folder in clients.items():
                root = base / f"설치 [공백], {client}-{personal}"
                root.mkdir()
                # Exercise --user routing while patching only the home resolver.
                if personal:
                    with patch.object(I.Path, "home", return_value=root):
                        assert I.main(["--client", client, "--user"]) == 0
                    installed = root / folder / "skills/ue-repo-reader"
                else:
                    installed = I.install(client, root)
                assert installed == root / folder / "skills/ue-repo-reader"
                assert (installed / "SKILL.md").read_bytes() == (ROOT / "SKILL.md").read_bytes()
                assert not any((installed / name).exists() for name in (".git", "tests", "server", "AGENTS.md", "chatgpt-plugin"))
                # All local imports must resolve inside the installed skill, from
                # a different cwd, without importing from the source checkout.
                code = ("import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                        "import ue_repo_digest,bp_reader,data_reader,map_reader; "
                        "assert all(Path(m.__file__).parent==Path(sys.argv[1]) for m in "
                        "(ue_repo_digest,bp_reader,data_reader,map_reader))")
                result = subprocess.run([sys.executable, "-c", code, str(installed / "scripts")], cwd=cwd,
                                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
                assert result.returncode == 0, result.stderr
                help_result = subprocess.run([sys.executable, str(installed / "scripts/ue_repo_digest.py"), "--help"],
                                             cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
                assert help_result.returncode == 0, help_result.stderr


def test_skill_install_preserves_existing_paths():
    with _scratch() as tmp:
        root = Path(tmp).resolve()
        installed = I.install("codex", root)
        marker = installed / "personal.txt"
        marker.write_text("keep my files", encoding="utf-8")
        before = {p.relative_to(installed): p.read_bytes() for p in installed.rglob("*") if p.is_file()}
        try:
            I.install("codex", root)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing installation overwritten")
        after = {p.relative_to(installed): p.read_bytes() for p in installed.rglob("*") if p.is_file()}
        assert before == after, "existing skill/user files changed"
        missing = root / "missing project"
        try:
            I.install("copilot", missing)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("nonexistent project accepted")
        assert not missing.exists()
        # Linked discovery folders must be rejected before creating children.
        project = root / "linked-project"
        project.mkdir()
        external = root / "external"
        external.mkdir()
        link = project / ".claude"
        if os.name == "nt":
            subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/c", "mklink", "/J", str(link), str(external)],
                           check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        else:
            link.symlink_to(external, target_is_directory=True)
        try:
            I.install("claude", project)
        except ValueError:
            pass
        else:
            raise AssertionError("linked discovery folder accepted")
        assert list(external.iterdir()) == [], "installer wrote through a link/junction"
