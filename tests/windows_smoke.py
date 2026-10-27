#!/usr/bin/env python3
"""Native Windows PowerShell 5.1 setup/LFS checks in disposable paths and isolated Git config.

Uses the existing Python and Git; installs no software and changes no user-wide settings.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ue_repo_digest as D
import install_skill as I


def quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def doc_blocks() -> dict[int, list[str]]:
    text = (ROOT / "docs" / "CODEX_SETUP.ko.md").read_text(encoding="utf-8")
    sections = re.split(r"^## (\d+)\. .*\n", text, flags=re.M)
    blocks = {int(sections[i]): re.findall(r"```powershell\n(.*?)```", sections[i + 1], re.S)
              for i in range(1, len(sections), 2)}
    assert {key: len(blocks[key]) for key in (1, 2, 3, 4, 5)} == {1: 2, 2: 2, 3: 1, 4: 1, 5: 1}
    return blocks


def powershell(script: str, env: dict, cwd: Path, name: str, logs: Path) -> dict:
    executable = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run([str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                            cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    (logs / (name + ".stdout.log")).write_text(result.stdout, encoding="utf-8")
    (logs / (name + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
    assert result.returncode == 0, f"{name}: PowerShell exit {result.returncode}; see {logs}"
    line = next((line[len("UE_SMOKE:"):] for line in result.stdout.splitlines() if line.startswith("UE_SMOKE:")), None)
    assert line is not None, f"{name}: missing proof record; see {logs}"
    return json.loads(line)


def setup_smoke(base: Path, env: dict, logs: Path) -> dict:
    blocks = doc_blocks()
    skill, work = base / "skill", base / "공백[검증], 폴더"
    fixture = json.loads((ROOT / "tests" / "fixtures.json").read_text(encoding="utf-8"))["eg"]
    portable = I.install("codex", base)
    install = blocks[4][0].replace('$skill = "$env:USERPROFILE\\.agents\\skills\\ue-repo-reader"', "$skill = " + quote(skill))
    assert "$env:USERPROFILE" not in install
    analyze = blocks[5][0].replace('$work = "C:\\UEReview"', "$work = " + quote(work))
    assert "C:\\UEReview" not in analyze
    analyze = analyze.replace(" --workdir ", f" --ref {fixture['sha']} --workdir ")
    all_blocks = "\n".join(quote(block) + "," for items in blocks.values() for block in items).rstrip(",")
    script = f"""
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$ErrorActionPreference = 'Continue'
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {{ throw 'requires native 5.1' }}
$snippets = @({all_blocks})
foreach ($snippet in $snippets) {{
    $tokens = $null; $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseInput($snippet, [ref]$tokens, [ref]$parseErrors) | Out-Null
    if ($parseErrors.Count) {{ throw 'setup guide syntax error' }}
}}
{blocks[1][0]}
{blocks[1][1]}
if (-not $global:UePy) {{ throw 'existing Python was not selected' }}
# Dependencies already exist. The install step is intentionally unnecessary.
{blocks[3][0]}
if ((git config --global --get core.longpaths) -ne 'true') {{ throw 'isolated longpaths config missing' }}
if ((git config --global --get filter.lfs.process) -ne 'git-lfs filter-process') {{ throw 'LFS config missing' }}
{install}
if (-not (Test-Path "$skill\\scripts\\ue_repo_digest.py")) {{ throw 'skill clone failed' }}
# Exercise the same guide against the minimal installed snapshot, without the
# source checkout or any repository-level instructions in that skill folder.
$skill = {quote(portable)}
if (-not (Test-Path "$skill\\SKILL.md")) {{ throw 'portable skill missing' }}
# Keep native stderr at Continue as the guide instructs; preserve the actual child exit code.
$guideOutput = @(. {{
{analyze}
}})
$analysisExit = $LASTEXITCODE
$guideOutput | Write-Output
if ($analysisExit -ne 0) {{ throw "digest exit $analysisExit" }}
if (-not ($guideOutput | Where-Object {{ "$_" -like '*Coverage:*' }})) {{ throw 'guide did not print coverage for literal path' }}
$digestPath = Join-Path $work 'ExtractionGame_Fin_digest'
$digest = Get-Content -LiteralPath (Join-Path $digestPath 'digest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$index = Get-Content -LiteralPath (Join-Path $digestPath 'INDEX.md') -Raw -Encoding UTF8
if ($index -notmatch 'Coverage: (\\d+) Blueprints rendered, 0 failed; graph nodes decoded (\\d+)/(\\d+)') {{ throw 'coverage missing' }}
if ($Matches[2] -ne $Matches[3]) {{ throw 'partial nodes' }}
$coverage = $Matches[0]
if ($index -notmatch 'everything decoded cleanly') {{ throw 'partial digest' }}
Invoke-UePython -c "import sys; print('native progress', file=sys.stderr); sys.exit(7)"
$failureExit = $LASTEXITCODE
if ($failureExit -ne 7) {{ throw 'native failure exit code was lost' }}
$proof = [ordered]@{{ powershell=$PSVersionTable.PSVersion.ToString(); snippets=$snippets.Count; analysis_exit=$analysisExit;
    native_failure_exit=$failureExit; coverage=$coverage; displayed_coverage=$true;
    selected_python=($global:UePy -join ' '); commit=$digest.source.commit; portable_skill_analyzed=$true }}
Write-Output ('UE_SMOKE:' + ($proof | ConvertTo-Json -Compress))
exit 0
"""
    return powershell(script, env, base, "setup", logs)


def picker_smoke(base: Path, env: dict, logs: Path) -> dict:
    picker = doc_blocks()[1][1]
    script = f"""
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
function python {{ $global:LASTEXITCODE=9009; 'store stub' }}
function py {{ & {quote(sys.executable)} @($args | Select-Object -Skip 1) }}
function python3 {{ $global:LASTEXITCODE=1 }}
{picker}
if (($global:UePy -join ' ') -ne 'py -3') {{ throw 'store stub was accepted or launcher fallback failed' }}
function py {{ $global:LASTEXITCODE=1 }}
{picker}
if ($global:UePy) {{ throw 'missing Python was accepted' }}
Write-Output 'UE_SMOKE:{{"store_stub_rejected":true,"launcher_selected":true,"missing_python_rejected":true}}'
exit 0
"""
    return powershell(script, env, base, "picker", logs)


def lfs_smoke(base: Path, env: dict) -> dict:
    def git(*args, cwd=base):
        return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=60).stdout

    origin, checkout = base / "lfs-origin", base / "lfs-checkout"
    git("init", "-q", str(origin))
    git("-C", str(origin), "lfs", "track", "*.uasset", "*.umap")
    contents = {"Content/한글 공백/테스트[1],A.uasset": b"asset-one\0" * 40,
                "Content/한글 공백/맵[2],B.umap": b"map-two\0" * 40}
    for name, data in contents.items():
        path = origin / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    git("-C", str(origin), "add", ".")
    git("-C", str(origin), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "LFS fixture")
    clone_env = dict(env, GIT_LFS_SKIP_SMUDGE="1")
    subprocess.run(["git", "clone", "-q", "--no-local", str(origin), str(checkout)], cwd=base, env=clone_env,
                   check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    paths = [checkout / name for name in contents]
    assert all(D.lfs_pointer_size(path) is not None for path in paths), "clone did not preserve pointers"
    # File origins deliberately take the real git-lfs fallback path, including its Go glob handling.
    saved = dict(os.environ)
    try:
        os.environ.update(env)
        report = D.pull_lfs(checkout, paths, 8)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    assert report["requested"] == 2 and report["failed"] == 0, report
    assert all((checkout / name).read_bytes() == data for name, data in contents.items())
    return {"literal_paths_downloaded": 2, "failed": report["failed"]}


def main() -> int:
    if os.name != "nt":
        print("Windows PowerShell 5.1 is required")
        return 2
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    cache = ROOT / "tests" / ".cache"
    logs = cache / "windows-smoke"
    logs.mkdir(parents=True, exist_ok=True)
    real_config = Path.home() / ".gitconfig"
    before = hashlib.sha256(real_config.read_bytes()).hexdigest() if real_config.exists() else None
    with tempfile.TemporaryDirectory(prefix="ps51-", dir=cache) as tmp:
        base = Path(tmp).resolve()
        assert base.parent == cache.resolve()
        env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
                   GIT_CONFIG_GLOBAL=str(base / "gitconfig"), GIT_CONFIG_NOSYSTEM="1",
                   GIT_CEILING_DIRECTORIES=str(cache.resolve()), GIT_TERMINAL_PROMPT="0", PYTHONIOENCODING="cp949")
        result = {"setup": setup_smoke(base, env, logs), "picker": picker_smoke(base, env, logs),
                  "lfs": lfs_smoke(base, env)}
    after = hashlib.sha256(real_config.read_bytes()).hexdigest() if real_config.exists() else None
    assert before == after, "user Git config changed"
    result["user_git_config_unchanged"] = True
    (logs / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
