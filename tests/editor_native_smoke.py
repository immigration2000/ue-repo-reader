"""Optional Windows native-editor oracle E2E; all project/build output stays in an owned cache.

Requires an installed UE 5.7/5.8 editor and C++ toolchain. Normal regressions use
the captured, pinned JSON oracles and do not require an editor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import compare_editor_oracle as C


def run(command, log, timeout):
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, encoding="utf-8", timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"command exited {result.returncode}; inspect {log}\n" + log.read_text(encoding="utf-8", errors="replace")[-2000:])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True, help="installed UE_5.7 or UE_5.8 folder")
    parser.add_argument("--workdir", type=Path, help="new output directory; must not exist")
    parser.add_argument("--no-pch", action="store_true", help="avoid large generated PCH caches in the disposable host build")
    args = parser.parse_args(argv)
    engine = args.engine.resolve() / "Engine"
    version = json.loads((engine / "Build/Build.version").read_text(encoding="utf-8"))
    minor = f"{version['MajorVersion']}.{version['MinorVersion']}"
    if minor not in ("5.7", "5.8"):
        parser.error("this fixture smoke targets installed 5.7/5.8 engines")
    binaries = list((engine / "Binaries/ThirdParty/DotNet").glob("*/win-x64/dotnet.exe"))
    if len(binaries) != 1:
        parser.error("expected one bundled Windows dotnet runtime")
    cache = ROOT / "tests/.cache"
    cache.mkdir(exist_ok=True)
    if args.workdir:
        base = args.workdir.resolve()
        base.mkdir(parents=True, exist_ok=False)
    else:
        base = Path(tempfile.mkdtemp(prefix="native-", dir=cache))
    project = base / "Oracle.uproject"
    # Only this disposable host project's engine plugin defaults are disabled.
    # No user project, engine plugin setting or global configuration is changed.
    project.write_text(json.dumps({"FileVersion": 3, "EngineAssociation": minor, "DisableEnginePluginsByDefault": True,
                                   "Plugins": [{"Name": "PythonScriptPlugin", "Enabled": True},
                                               {"Name": "EditorScriptingUtilities", "Enabled": True},
                                               {"Name": "RepoReaderOracle", "Enabled": True}]}), encoding="utf-8")
    plugin = base / "Plugins/RepoReaderOracle"
    source = ROOT / "tools/RepoReaderOracle"
    shutil.copytree(source, plugin, ignore=shutil.ignore_patterns("Binaries", "Intermediate"))
    if args.no_pch:
        rules = plugin / "Source/RepoReaderOracle/RepoReaderOracle.Build.cs"
        rules.write_text(rules.read_text(encoding="utf-8").replace("PCHUsageMode.UseExplicitOrSharedPCHs", "PCHUsageMode.NoPCHs"), encoding="utf-8")
    build = [str(binaries[0]), str(engine / "Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll"),
             "UnrealEditor", "Win64", "Development", "-Project=" + str(project),
             "-plugin=" + str(plugin / "RepoReaderOracle.uplugin"), "-NoHotReload", "-NoUBTMakefiles", "-NoUBA", "-MaxParallelActions=2"]
    if args.no_pch:
        build += ["-NoPCH", "-NoSharedPCH"]
    run(build, base / "build.log", 900)
    import asset_regress as A
    manifest = json.loads(A.MANIFEST.read_text(encoding="utf-8"))
    case = next(c for c in manifest["cases"] if c["id"] == "pins-" + minor)
    fixture_cache = cache / "asset-fixtures" / manifest["commit"]
    A.fetch_file(manifest, manifest["license"], fixture_cache)
    fixture = A.fetch_file(manifest, case["asset"], fixture_cache)
    content = base / "Content/KeyRepairs"
    content.mkdir(parents=True)
    package = content / "BP_Keys.uasset"
    shutil.copyfile(fixture, package)
    original = hashlib.sha256(package.read_bytes()).hexdigest()
    exporter = ROOT / "tools/export_editor_oracle.py"
    script = base / "capture.py"
    # The only mutating API in this test modifies the disposable project's
    # in-memory Blueprint to prove dirty state is refused; no asset is saved.
    script.write_text("\n".join([
        "import importlib.util, json, unreal",
        "from pathlib import Path",
        f"base=Path({str(base)!r})",
        f"spec=importlib.util.spec_from_file_location('native_exporter',{str(exporter)!r})",
        "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)",
        "result=module.export_oracle(base/'oracle.json',['/Game/KeyRepairs/BP_Keys'])",
        "bp=unreal.load_asset('/Game/KeyRepairs/BP_Keys')",
        "ok=unreal.BlueprintEditorLibrary.add_member_variable(bp,'OracleUnsavedProbe',unreal.BlueprintEditorLibrary.get_basic_type_by_name('bool'))",
        "assert ok, 'dirty-state test did not create its in-memory variable'",
        "dirty=module.export_oracle(base/'dirty.json',['/Game/KeyRepairs/BP_Keys'])",
        "assert dirty['assets'][0]['snapshot']['package_dirty'] is True, dirty",
        "assert dirty['assets'][0]['issues'], 'unsaved state was silently treated as saved bytes'",
        "print('NATIVE_ORACLE_SMOKE_COMPLETE')", ""]), encoding="utf-8")
    command = [str(engine / "Binaries/Win64/UnrealEditor-Cmd.exe"), str(project), "-run=pythonscript", "-script=" + str(script),
               "-unattended", "-nullrhi", "-nosplash", "-nosound", "-nop4", "-stdout", "-FullStdOutLogOutput"]
    run(command, base / "editor.log", 180)
    assert hashlib.sha256(package.read_bytes()).hexdigest() == original, "editor test changed saved package bytes"
    oracle = C.load_json((base / "oracle.json").read_text(encoding="utf-8"))
    graph = C.compare_oracle(oracle, base, profile="graph")
    full = C.compare_oracle(oracle, base)
    assert graph["status"] == "passed", graph
    dirty = C.compare_oracle(C.load_json((base / "dirty.json").read_text(encoding="utf-8")), base, profile="graph")
    assert dirty["status"] == "incomplete", dirty
    for name, value in (("comparison-graph.json", graph), ("comparison-all.json", full), ("comparison-dirty.json", dirty)):
        (base / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS native {minor}: graph {graph['checked']} observations; all profile={full['status']}; dirty refused; bytes unchanged. Output: {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
