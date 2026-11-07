# P5 Windows UE 5.8 Native validation

Date: 2026-11-07

Branch: `codex/p5-windows-native-validation`

Base: `codex/p4-unified-analysis` at `ad854085e818878876f298804ef67d66a815d529`

## Result status

**Blocked before the native build.** The executor attached to this task is Debian 13 Linux, not the Windows PC
described by the validation request. It has no Windows filesystem mount, PowerShell, `cmd.exe`, MSVC `cl.exe`,
MSBuild, Unreal Engine installation, or Unreal Editor executable. The Cloud environment reports no VPN/Tailscale
connection to another machine. Repository-runner discovery through the GitHub API was denied with HTTP 403, and
the repository contains no workflow that identifies an available self-hosted Windows runner.

UE 5.8 was not installed or downloaded. No engine path or project path was guessed. Consequently there is no
honest UE 5.8 compile result, Native Oracle JSON, semantic comparison result, or new independently verified field
count from this run. Completion conditions 1–4 remain blocked on access to a Windows UE 5.8 executor.

## Environment observations

| Check | Observed result |
|---|---|
| Executor OS | Debian 13, Linux x86-64, kernel 6.18.57 |
| Windows access | no `/mnt/c`; `powershell.exe`, `pwsh`, `cmd.exe` absent |
| C++/VS tools | `cl.exe`, `msbuild.exe` absent |
| Unreal Engine | no `UnrealEditor.exe`, `Build.bat`, or mounted UE installation found under the workspace |
| Python | 3.12.14 |
| Git | 2.52.0 |
| Reader checkout | clean `codex/p4-unified-analysis` at `ad854085` before the P5 branch was created |
| P5 branch | `codex/p5-windows-native-validation` |
| P2 code | present in `tools/RepoReaderOracle`, exporter, and `semantic-references` comparator profile |

`tests/editor_native_smoke.py` was inspected. It creates a disposable host, copies the editor-only plugin,
builds with the engine's bundled UBT, captures a fixed pin fixture, verifies dirty-state refusal and unchanged
package bytes, and compares the graph/all profiles. It does not currently run the semantic-reference profile on
an asset containing function/variable/event/delegate/macro references. The P2 producer source uses reflection to
read loaded `FMemberReference` fields and calls no Blueprint save, compile, reconstruction, or node mutation API.
Actual UE API compatibility remains unproved until the plugin compiles on UE 5.8.

## Fixed validation project and asset

The Linux reader selected an existing fixed external project already used by the regression suite:

- repository: `https://github.com/tomlooman/ActionRoguelike`
- commit: `31bd38491d9dcec99460d85f3084c79441c5ce8b`
- declared engine: 5.8
- editor target from source: `ActionRoguelikeEditor`
- asset: `/Game/ActionRoguelike/UI/PlayerHealth_Widget`
- package: `Content/ActionRoguelike/UI/PlayerHealth_Widget.uasset`
- Git blob: `6f328ced64ef4f03748cf98695a43832f264e0d4`
- size: 128,600 bytes
- SHA-256 from both the working file and `git show <commit>:<path>`:
  `2687fa1435cf25e493bf05c2d1e4ddff79cb991dc9c4d43411e6beea4e2cb37e`

The saved reader reports `parse_status=ok`, graph IR `complete`, 32/32 nodes, and 23 semantic-reference records.
It covers function, variable, event, delegate, selected delegate function, macro graph, and custom event records.
This is only the binary-reader baseline; it is not Native verification.

The local regression clone intentionally omits unrelated heavy blobs and appears dirty because the partial-clone
test materializes those omissions as deleted paths. It must not be used as the Windows editor project. Use a fresh,
full validation clone at the exact commit in a new directory and preserve the source clone unchanged.

## Commands actually executed in this task

The following checks ran successfully on Linux:

```text
uname -a
python --version
git --version
git status --short --branch
git rev-parse HEAD
python tests/regress.py --repo eg=... --repo ar=... --repo ves=... --repo bt=...
python tools/compare_editor_oracle.py tests/editor_oracles/eg-bfl-util.json \
  --project-root tests/.cache/eg --profile semantic-references \
  --out /tmp/p5-old-oracle-semantic.json
```

The complete P2/P3/P4 regression passed: 173 unit tests, six external assets, eight existing Native Oracle
groups, two saved/loaded evidence checks, and four fixed projects. The semantic comparison against the older
`eg-bfl-util` capture exited 1 with `status=incomplete`, `checked=0`, one unavailable asset. That is the expected
fail-closed result because the old capture lacks P2's loaded semantic-reference capability; it is not a P5 pass.

The GitHub self-hosted-runner list request returned HTTP 403 (`Resource not accessible by integration`). This
does not prove that no runner exists; it proves this credential cannot discover or use one.

## Windows commands prepared but not executed

Run these only on an attached Windows machine after explicitly setting existing paths. The commands deliberately
contain no guessed engine or project location.

```powershell
$Reader = (Resolve-Path $env:UE_REPO_READER_ROOT).Path
$Engine = (Resolve-Path $env:UE58_ROOT).Path
$Checks = (Resolve-Path $env:P5_CHECK_ROOT).Path
$ProjectRoot = Join-Path $Checks "ActionRoguelike-31bd384"
$Project = Join-Path $ProjectRoot "ActionRoguelike.uproject"
$AssetFile = Join-Path $ProjectRoot "Content/ActionRoguelike/UI/PlayerHealth_Widget.uasset"

Get-Content (Join-Path $Engine "Engine/Build/Build.version")
py --version
git --version
git -C $Reader status --short --branch
git -C $Reader rev-parse HEAD

git clone https://github.com/tomlooman/ActionRoguelike $ProjectRoot
git -C $ProjectRoot checkout 31bd38491d9dcec99460d85f3084c79441c5ce8b
git -C $ProjectRoot submodule update --init --recursive
git -C $ProjectRoot lfs pull
git -C $ProjectRoot status --short
Get-FileHash -Algorithm SHA256 $AssetFile
```

The hash must equal the pinned value above before continuing. Copy `tools/RepoReaderOracle` to the validation
clone's `Plugins/RepoReaderOracle`, enable RepoReaderOracle and PythonScriptPlugin in that clone only, and build
the declared target:

```powershell
& (Join-Path $Engine "Engine/Build/BatchFiles/Build.bat") `
  ActionRoguelikeEditor Win64 Development "-Project=$Project" `
  -WaitMutex -NoHotReloadFromIDE *> (Join-Path $Checks "build.log")
```

Capture into a new path outside `Content` using `tools/export_editor_oracle.py` and exactly this package path:

```python
import importlib.util
spec = importlib.util.spec_from_file_location(
    "oracle_export", r"<UE_REPO_READER_ROOT>\tools\export_editor_oracle.py")
oracle_export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle_export)
oracle_export.export_oracle(
    r"<P5_CHECK_ROOT>\semantic-native.json",
    [r"/Game/ActionRoguelike/UI/PlayerHealth_Widget"])
```

Then close the editor and compare the unchanged bytes:

```powershell
Get-FileHash -Algorithm SHA256 $AssetFile
py (Join-Path $Reader "tools/compare_editor_oracle.py") `
  (Join-Path $Checks "semantic-native.json") `
  --project-root $ProjectRoot `
  --profile semantic-references `
  --out (Join-Path $Checks "semantic-compare.json")
git -C $ProjectRoot status --short
```

Preserve `Build.version`, VS/MSVC discovery output, `build.log`, editor log, the pre/post hashes, native JSON,
comparison JSON, exact source commit, and final status. Do not overwrite any existing Oracle JSON.

## Required continuation evidence

P5 can be completed only after the Windows run supplies:

1. the exact UE 5.8 version/build and successful/failed plugin compiler log;
2. a clean native JSON with `package_dirty=false`, same pre/post/package hash, and no capture issues;
3. native graph/node/reference counts and exact member/macro observations;
4. the new semantic comparison JSON with match, mismatch, unavailable, and saved/loaded difference counts;
5. post-run project status showing no source package change.

GridInventorySystem is not ready for a claim of independently verified semantic references until that evidence
exists. Its later validation must use its own pinned commit and package hashes rather than reusing the
ActionRoguelike result as a universal guarantee.
