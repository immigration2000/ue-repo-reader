"""Independent assertions for the precision C++ syntax contract."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import cxx_index as C
import ue_repo_digest as D


def _project(files: dict[str, str]):
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return temp, root


def _available(index):
    assert index["status"] != "unavailable", "install requirements-cxx.txt before running C++ precision tests"
    assert index["accuracy_contract"]["semantic_resolved_count"] == 0


def test_cxx_precision_observes_unreal_functions_bodies_and_source_spans():
    temp, root = _project({
        "Source/Game/Public/Thing.h": '''#pragma once
#include "Thing.generated.h"
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnValue, int, Value);
UCLASS(BlueprintType)
class GAME_API AThing : public ABase {
 GENERATED_BODY()
public:
 UFUNCTION(BlueprintNativeEvent, Server, Reliable)
 virtual int Compute(
     const int Value) const;
 UPROPERTY(EditAnywhere) int Count;
};
''',
        "Source/Game/Private/Thing.cpp": '''#include "Thing.h"
int AThing::Compute_Implementation(const int Value) const {
#if WITH_EDITOR
 if (Value > 0) { return Helper(Value); }
#endif
 auto Twice = [this](int X) { return X + Count; };
 Count = Twice(Value);
 return Count;
}
''',
    })
    try:
        index = C.analyze_project(root)
        _available(index)
        thing = next(t for t in index["types"] if t["symbol_name"] == "AThing")
        assert thing["kind"] == "UCLASS" and thing["bases"][0]["name"] == "ABase"
        assert any(m["name"] == "DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam" and m["complete"]
                   for m in index["unreal_macros"])
        declaration = next(f for f in index["functions"] if f["symbol_name"] == "Compute")
        definition = next(f for f in index["functions"] if f["symbol_name"] == "Compute_Implementation")
        assert declaration["annotation"]["arguments_raw"] == "BlueprintNativeEvent, Server, Reliable"
        assert declaration["line_start"] == 9 and declaration["line_end"] == 10
        assert definition["body_span"] and definition["resolution_status"] == "syntax_observed"
        assert any(c["kind"] == "if" for c in index["control_flow"])
        assert len(index["lambdas"]) == 1
        assert any(a["access"] == "write" and a["symbol_name"] == "Count" for a in index["data_accesses"])
        assert any(a["access"] == "read" and a["symbol_name"] == "Value" for a in index["data_accesses"])
        assert any(a["access"] == "read" and a["symbol_name"] == "Count" for a in index["data_accesses"])
        assert any(c["callee_expression"] == "Helper" and c["resolution_status"] == "unresolved" for c in index["calls"])
        assert index["files"][0]["generated_header_includes"] or index["files"][1]["generated_header_includes"]
        assert any(d["raw"] == "#if WITH_EDITOR" for f in index["files"] for d in f["preprocessor_directives"])
        link = index["unreal_function_links"][0]
        assert link["resolution_status"] == "syntax_observed" and len(link["declaration_candidates"]) == 1
    finally:
        temp.cleanup()


def test_cxx_precision_keeps_overloads_duplicates_namespaces_and_ambiguity():
    temp, root = _project({
        "Source/Game/A.cpp": '''namespace One { int Work(int X) { return X; } }
namespace Two { int Work(double X) { return 0; } }
template<typename T> T Apply(T X) { return X; }
int Caller() { return Work(1) + One::Work(2) + Apply<int>(3); }
''',
        "Source/Game/B.cpp": '''class First { public: First(); ~First(); void Tick(); };
class Second { public: void Tick(); };
First::First() {}
First::~First() {}
void First::Tick() {}
void Second::Tick() {}
''',
    })
    try:
        index = C.analyze_project(root)
        _available(index)
        work = [f for f in index["functions"] if f["symbol_name"] == "Work"]
        assert {f["qualified_name"] for f in work} == {"One::Work", "Two::Work"}
        ambiguous = next(c for c in index["calls"] if c["callee_expression"] == "Work")
        qualified = next(c for c in index["calls"] if c["callee_expression"] == "One::Work")
        assert ambiguous["candidate_status"] == "ambiguous_syntax_candidates"
        assert qualified["candidate_status"] == "unique_syntax_candidate"
        assert qualified["resolution_status"] == "unresolved"
        assert len([f for f in index["functions"] if f["symbol_name"] == "Tick"]) == 4
        assert any(f["symbol_name"] == "First" for f in index["functions"])
        assert any(f["symbol_name"] == "~First" for f in index["functions"])
        assert any(f["symbol_name"] == "Apply" for f in index["functions"])
        exact, stripped = D._cpp_name_indexes([
            {"name": "AShared", "file": "One.h"}, {"name": "AShared", "file": "Two.h"},
            {"name": "AUnique", "file": "Only.h"},
        ])
        assert D._unique_cpp_name_candidate("Shared", exact, stripped) is None
        assert D._unique_cpp_name_candidate("Unique", exact, stripped) == "AUnique"
    finally:
        temp.cleanup()


def test_cxx_precision_reports_invalid_source_and_missing_parser_without_false_success():
    temp, root = _project({"Source/Game/Broken.cpp": "int Broken( { if (true) return Missing();\n"})
    try:
        index = C.analyze_project(root)
        _available(index)
        assert index["status"] == "partial"
        assert index["files"][0]["parse_status"] == "partial" and index["files"][0]["issues"]
        with patch.object(C, "_load_parser", return_value=(None, "deliberate missing dependency")):
            unavailable = C.analyze_project(root)
        assert unavailable["status"] == "unavailable"
        assert unavailable["issues"][0]["resolution_status"] == "unresolved"
        assert unavailable["functions"] == []
    finally:
        temp.cleanup()


def test_cxx_precision_build_rules_and_digest_outputs_are_additive():
    temp, root = _project({
        "Source/Game/Game.Build.cs": '''public class Game : ModuleRules { public Game(ReadOnlyTargetRules Target) : base(Target) {
PublicDependencyModuleNames.AddRange(new string[] { "Core", "Engine" }); } }''',
        "Source/Game.Target.cs": '''public class GameTarget : TargetRules { public GameTarget(TargetInfo Target) : base(Target) {
Type = TargetType.Game; } }''',
        "Source/Game/X.h": "USTRUCT() struct FRow { GENERATED_BODY() int Value; };\n",
        "Source/Game/X.cpp": "static int Plain(int X) { while (X) { --X; } return X; }\n",
    })
    try:
        cpp = D.scan_cpp(root)
        _available(cpp["precision"])
        assert set(cpp) == {"modules", "classes", "precision"}
        assert cpp["modules"][0]["deps"] == ["Core", "Engine"]
        rules = {r["kind"]: r for r in cpp["precision"]["build_rules"]}
        assert rules["module"]["dependencies"] == ["Core", "Engine"]
        assert rules["target"]["target_type"] == "Game"
        output = root / "Output" / "cpp"
        output.mkdir(parents=True)
        D.write_cpp_precision(cpp, output)
        names = {p.name for p in output.iterdir()}
        assert names == {"CXX_INDEX.json", "FUNCTIONS.md", "CALL_GRAPH.md", "UNRESOLVED.md"}
        written = json.loads((output / "CXX_INDEX.json").read_text(encoding="utf-8"))
        assert written["schema_version"] == 1 and written["statistics"]["functions"] == 1
        assert "semantic-resolved records: **0**" in (output / "FUNCTIONS.md").read_text(encoding="utf-8")
    finally:
        temp.cleanup()
