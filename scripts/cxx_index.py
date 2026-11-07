#!/usr/bin/env python3
"""Source-faithful C++ syntax index with deliberately conservative resolution.

tree-sitter observes syntax.  It does not run the preprocessor or perform C++
name lookup, overload resolution, template instantiation, or UnrealHeaderTool.
Consequently no record produced here is marked ``semantic_resolved``.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
PARSER_NAME = "tree-sitter-cpp"
SOURCE_SUFFIXES = {".h", ".hh", ".hpp", ".hxx", ".c", ".cc", ".cpp", ".cxx", ".inl"}
UE_MACROS = {"UCLASS", "USTRUCT", "UENUM", "UINTERFACE", "UFUNCTION", "UPROPERTY", "GENERATED_BODY",
             "GENERATED_UCLASS_BODY", "GENERATED_USTRUCT_BODY", "GENERATED_IINTERFACE_BODY",
             "GENERATED_UINTERFACE_BODY", "ENUM_CLASS_FLAGS", "IMPLEMENT_MODULE", "IMPLEMENT_GAME_MODULE",
             "IMPLEMENT_PRIMARY_GAME_MODULE", "DEFINE_LOG_CATEGORY", "DEFINE_LOG_CATEGORY_STATIC"}
CONTROL_TYPES = {
    "if_statement": "if", "switch_statement": "switch", "for_statement": "for",
    "for_range_loop": "for_range", "while_statement": "while", "do_statement": "do_while",
    "return_statement": "return", "break_statement": "break", "continue_statement": "continue",
    "goto_statement": "goto", "try_statement": "try", "throw_statement": "throw",
}


def _load_parser():
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_cpp
    except (ImportError, OSError) as exc:
        return None, f"tree-sitter dependency unavailable: {type(exc).__name__}: {exc}"
    try:
        return Parser(Language(tree_sitter_cpp.language())), None
    except Exception as exc:  # binary/API incompatibility must be visible in the index
        return None, f"tree-sitter initialization failed: {type(exc).__name__}: {exc}"


def _versions() -> dict[str, str | None]:
    out: dict[str, str | None] = {"tree_sitter": None, "tree_sitter_cpp": None}
    for package, key in (("tree-sitter", "tree_sitter"), ("tree-sitter-cpp", "tree_sitter_cpp")):
        try:
            out[key] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    return out


def _walk(node) -> Iterable[Any]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _desc(node, types: set[str]):
    for item in _walk(node):
        if item.type in types:
            return item
    return None


def _text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _span(node) -> dict[str, Any]:
    return {
        "byte_start": node.start_byte, "byte_end": node.end_byte,
        "line_start": node.start_point.row + 1, "column_start": node.start_point.column + 1,
        "line_end": node.end_point.row + 1, "column_end": node.end_point.column + 1,
    }


def _base(path: str, node, symbol: str, qualified: str | None, issues: list[str] | None = None) -> dict[str, Any]:
    span = _span(node)
    return {
        "source_file": path, "line_start": span["line_start"], "line_end": span["line_end"],
        "symbol_name": symbol, "qualified_name": qualified, "parser": PARSER_NAME,
        "resolution_status": "syntax_observed", "source_span": span, "issues": list(issues or []),
    }


def _balanced_macros(source: bytes) -> list[dict[str, Any]]:
    """Find UE macro calls without interpreting their arguments."""
    text = source.decode("utf-8", errors="surrogateescape")
    char_to_byte = [0]
    for char in text:
        char_to_byte.append(char_to_byte[-1] + len(char.encode("utf-8", errors="surrogateescape")))
    found = []
    names = "|".join(re.escape(x) for x in sorted(UE_MACROS, key=len, reverse=True))
    pattern = re.compile(r"\b(" + names + r"|DECLARE_[A-Za-z0-9_]*DELEGATE[A-Za-z0-9_]*)\s*\(")
    for match in pattern.finditer(text):
        i, depth, quote, escape = match.end() - 1, 0, None, False
        while i < len(text):
            char = text[i]
            if quote:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        complete = depth == 0
        end_char = i if complete else len(text)
        start, end = char_to_byte[match.start()], char_to_byte[end_char]
        raw = source[start:end].decode("utf-8", errors="replace")
        open_at = raw.find("(")
        found.append({
            "name": match.group(1), "raw": raw, "arguments_raw": raw[open_at + 1:-1] if complete else None,
            "byte_start": start, "byte_end": end, "line_start": text.count("\n", 0, match.start()) + 1,
            "line_end": text.count("\n", 0, end_char) + 1, "complete": complete,
        })
    return found


def _masked_source(source: bytes, macros: list[dict[str, Any]]) -> bytes:
    masked = bytearray(source)
    for macro in macros:
        for i in range(macro["byte_start"], macro["byte_end"]):
            if masked[i] not in (10, 13):
                masked[i] = 32
    # Export macros between class/struct and the type name are not C++ grammar.
    for match in re.finditer(rb"\b[A-Z][A-Z0-9_]*_API\b", bytes(masked)):
        masked[match.start():match.end()] = b" " * (match.end() - match.start())
    return bytes(masked)


def _annotation(macros: list[dict[str, Any]], node, allowed: set[str], source: bytes):
    candidates = [m for m in macros if m["name"] in allowed and m["byte_end"] <= node.start_byte]
    if not candidates:
        return None
    macro = max(candidates, key=lambda m: m["byte_end"])
    if node.start_point.row + 1 - macro["line_end"] > 3:
        return None
    between = source[macro["byte_end"]:node.start_byte].decode("utf-8", errors="replace")
    between = re.sub(r"/\*.*?\*/|//[^\n]*", "", between, flags=re.S)
    return dict(macro) if not between.strip() else None


def _namespace(node, source: bytes) -> list[str]:
    names = []
    parent = node.parent
    while parent:
        if parent.type == "namespace_definition":
            name = parent.child_by_field_name("name") or _desc(parent, {"namespace_identifier", "identifier"})
            if name:
                names.append(_text(source, name))
        parent = parent.parent
    return list(reversed(names))


def _type_ancestor(node, type_nodes: dict[int, dict[str, Any]]):
    parent = node.parent
    while parent:
        record = type_nodes.get(parent.id)
        if record:
            return record
        parent = parent.parent
    return None


def _name_from_declarator(node, source: bytes):
    current = node
    while current:
        for field in ("declarator", "name"):
            child = current.child_by_field_name(field)
            if child and child.type != "parameter_list":
                if child.type in {"identifier", "field_identifier", "qualified_identifier", "operator_name", "destructor_name"}:
                    return _text(source, child), child
                current = child
                break
        else:
            break
    candidate = _desc(node, {"qualified_identifier", "destructor_name", "operator_name", "field_identifier", "identifier"})
    return (_text(source, candidate), candidate) if candidate else ("<unknown>", node)


def _access_for(node, owning: dict[str, Any] | None, source: bytes) -> str | None:
    if not owning:
        return None
    default = "private" if owning["kind"] in {"class", "UCLASS", "UINTERFACE"} else "public"
    body = node.parent
    while body and body.type != "field_declaration_list":
        body = body.parent
    if not body:
        return default
    access = default
    for child in body.children:
        if child.start_byte >= node.start_byte:
            break
        if child.type == "access_specifier":
            access = _text(source, child).rstrip(":").strip()
    return access


def _preprocessor_context(node, source: bytes) -> list[str]:
    context = []
    parent = node.parent
    while parent:
        if parent.type.startswith("preproc_if"):
            first = _text(source, parent).splitlines()[0].strip()
            context.append(first)
        parent = parent.parent
    return list(reversed(context))


def _parse_file(parser, project: Path, path: Path) -> dict[str, Any]:
    rel = path.relative_to(project).as_posix()
    source = path.read_bytes()
    macros = _balanced_macros(source)
    masked = _masked_source(source, macros)
    tree = parser.parse(masked)
    root = tree.root_node
    file_record: dict[str, Any] = {
        "source_file": rel, "sha256": hashlib.sha256(source).hexdigest(), "bytes": len(source),
        "parse_status": "partial" if root.has_error else "ok", "has_error": root.has_error,
        "line_start": 1, "line_end": source.count(b"\n") + 1, "symbol_name": rel, "qualified_name": None,
        "parser": PARSER_NAME, "resolution_status": "unresolved" if root.has_error else "syntax_observed",
        "source_span": {"byte_start": 0, "byte_end": len(source), "line_start": 1, "column_start": 1,
                        "line_end": source.count(b"\n") + 1, "column_end": len(source.rsplit(b"\n", 1)[-1]) + 1},
        "generated_header_includes": [], "preprocessor_directives": [], "issues": [],
    }
    for line_no, line in enumerate(source.decode("utf-8", errors="replace").splitlines(), 1):
        if re.match(r"^\s*#\s*include\s*[<\"].*\.generated\.h[>\"]", line):
            file_record["generated_header_includes"].append({"line": line_no, "raw": line.strip(), "resolution_status": "syntax_observed"})
        if re.match(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b", line):
            file_record["preprocessor_directives"].append({"line": line_no, "raw": line.strip(), "resolution_status": "unresolved",
                                                            "issues": ["preprocessor condition was not evaluated"]})
    errors = [n for n in _walk(root) if n.type in {"ERROR"} or n.is_missing]
    for node in errors[:100]:
        file_record["issues"].append({"kind": "syntax_error" if node.type == "ERROR" else "missing_syntax",
                                      "source_span": _span(node), "raw": _text(source, node)[:240]})
    if len(errors) > 100:
        file_record["issues"].append({"kind": "truncated_error_list", "count": len(errors) - 100})
    if root.has_error and not file_record["issues"]:
        file_record["issues"].append({"kind": "syntax_error", "source_span": _span(root),
                                      "raw": "tree-sitter reported an error without an exposed error child"})

    types, functions, fields, calls, controls, accesses, lambdas = [], [], [], [], [], [], []
    type_nodes: dict[int, dict[str, Any]] = {}
    type_kinds = {"class_specifier": "class", "struct_specifier": "struct", "enum_specifier": "enum"}
    for node in _walk(root):
        if node.type not in type_kinds:
            continue
        name_node = node.child_by_field_name("name") or _desc(node, {"type_identifier", "identifier"})
        if not name_node:
            continue
        name = _text(source, name_node)
        namespace = _namespace(node, source)
        owning = _type_ancestor(node, type_nodes)
        qualified = (owning["qualified_name"] + "::" + name) if owning else ("::".join(namespace + [name]) if namespace else name)
        allowed = {"UCLASS", "UINTERFACE"} if node.type == "class_specifier" else ({"USTRUCT"} if node.type == "struct_specifier" else {"UENUM"})
        annotation = _annotation(macros, node, allowed, source)
        kind = annotation["name"] if annotation else type_kinds[node.type]
        rec = _base(rel, node, name, qualified)
        rec.update({"id": f"type:{rel}:{node.start_byte}", "kind": kind, "syntax_kind": type_kinds[node.type],
                    "namespace": namespace, "owner": owning["qualified_name"] if owning else None,
                    "annotation": annotation, "bases": [], "access": _access_for(node, owning, source),
                    "preprocessor_conditions": _preprocessor_context(node, source)})
        base_clause = node.child_by_field_name("base_class_clause") or _desc(node, {"base_class_clause"})
        if base_clause:
            raw = _text(source, base_clause).lstrip(":").strip()
            for part in raw.split(","):
                token = part.strip()
                access_match = re.match(r"(?:(public|protected|private)\s+)?(?:virtual\s+)?(.+)", token)
                if access_match:
                    rec["bases"].append({"name": access_match.group(2).strip(), "access": access_match.group(1),
                                         "resolution_status": "unresolved", "issues": ["base type lookup was not performed"]})
        types.append(rec)
        type_nodes[node.id] = rec

    function_parents = []
    for node in _walk(root):
        if node.type == "function_definition":
            function_parents.append(node)
        elif node.type in {"declaration", "field_declaration"} and _desc(node, {"function_declarator"}):
            # Ignore declarations nested in function bodies (local prototypes are still retained as local scope).
            function_parents.append(node)
    seen_functions = set()
    function_nodes: dict[int, dict[str, Any]] = {}
    for parent in function_parents:
        declarator = _desc(parent, {"function_declarator"})
        if not declarator or (parent.start_byte, declarator.end_byte) in seen_functions:
            continue
        seen_functions.add((parent.start_byte, declarator.end_byte))
        raw_name, name_node = _name_from_declarator(declarator, source)
        symbol = raw_name.split("::")[-1]
        owning = _type_ancestor(parent, type_nodes)
        namespaces = _namespace(parent, source)
        if "::" in raw_name:
            qualified = "::".join(namespaces + [raw_name]) if namespaces and not raw_name.startswith("::") else raw_name.lstrip(":")
            owner_name = qualified.rsplit("::", 1)[0]
        elif owning:
            qualified = owning["qualified_name"] + "::" + symbol
            owner_name = owning["qualified_name"]
        else:
            qualified = "::".join(namespaces + [symbol]) if namespaces else symbol
            owner_name = None
        params = declarator.child_by_field_name("parameters") or _desc(declarator, {"parameter_list"})
        body = parent.child_by_field_name("body") or (_desc(parent, {"compound_statement", "try_statement"}) if parent.type == "function_definition" else None)
        annotation = _annotation(macros, parent, {"UFUNCTION"}, source)
        prefix = source[parent.start_byte:declarator.start_byte].decode("utf-8", errors="replace").strip()
        rec = _base(rel, parent, symbol, qualified, ["tree-sitter does not resolve overloads or generated declarations"])
        rec.update({
            "id": f"function:{rel}:{parent.start_byte}:{declarator.start_byte}", "declaration_kind": "definition" if body else "declaration",
            "owner": owner_name, "namespace": namespaces, "access": _access_for(parent, owning, source),
            "signature_raw": _text(source, declarator), "return_prefix_raw": prefix or None,
            "parameters_raw": _text(source, params) if params else None, "annotation": annotation,
            "is_static_syntax": bool(re.search(r"\bstatic\b", prefix)), "is_virtual_syntax": bool(re.search(r"\bvirtual\b", prefix)),
            "is_const_syntax": bool(re.search(r"\bconst\s*(?:noexcept[^\{;]*)?$", _text(source, declarator))),
            "body_span": _span(body) if body else None, "preprocessor_conditions": _preprocessor_context(parent, source),
            "unreal_relation": None,
        })
        if symbol.endswith("_Implementation"):
            rec["unreal_relation"] = {"kind": "implementation_candidate", "declared_name": symbol[:-15], "resolution_status": "unresolved"}
        elif symbol.endswith("_Validate"):
            rec["unreal_relation"] = {"kind": "validation_candidate", "declared_name": symbol[:-9], "resolution_status": "unresolved"}
        functions.append(rec)
        function_nodes[parent.id] = rec

        if not body:
            continue
        for item in _walk(body):
            if item.type in CONTROL_TYPES:
                ctl = _base(rel, item, CONTROL_TYPES[item.type], qualified)
                ctl.update({"function_id": rec["id"], "kind": CONTROL_TYPES[item.type], "raw": _text(source, item)[:500]})
                controls.append(ctl)
            elif item.type == "lambda_expression":
                lam = _base(rel, item, "<lambda>", qualified)
                lam.update({"function_id": rec["id"], "capture_raw": _text(source, item.child_by_field_name("captures")) if item.child_by_field_name("captures") else None,
                            "raw": _text(source, item)[:1000]})
                lambdas.append(lam)
            elif item.type == "call_expression":
                callee = item.child_by_field_name("function") or (item.children[0] if item.children else item)
                callee_raw = _text(source, callee)
                symbol_name = re.split(r"::|->|\.", callee_raw)[-1].strip()
                symbol_name = re.sub(r"<.*>$", "", symbol_name).strip()
                call = _base(rel, item, symbol_name or "<expression>", None,
                             ["callee target requires C++ semantic analysis"])
                call.update({"id": f"call:{rel}:{item.start_byte}", "caller_id": rec["id"], "caller": qualified,
                             "callee_expression": callee_raw, "call_kind": "member" if re.search(r"->|\.", callee_raw) else ("qualified" if "::" in callee_raw else "unqualified"),
                             "arguments_raw": _text(source, item.child_by_field_name("arguments")) if item.child_by_field_name("arguments") else None,
                             "observation_status": "syntax_observed", "resolution_status": "unresolved", "candidate_status": "not_evaluated", "candidates": []})
                calls.append(call)
            elif item.type == "assignment_expression":
                left, right = item.child_by_field_name("left"), item.child_by_field_name("right")
                op = next((_text(source, c) for c in item.children if c.type.endswith("=")), "=")
                for side, mode in ((left, "read_write" if op != "=" else "write"), (right, "read")):
                    if side:
                        access = _base(rel, side, _text(source, side), qualified)
                        access.update({"function_id": rec["id"], "access": mode, "expression_raw": _text(source, side)})
                        accesses.append(access)
            elif item.type == "update_expression":
                access = _base(rel, item, _text(source, item), qualified)
                access.update({"function_id": rec["id"], "access": "read_write", "expression_raw": _text(source, item)})
                accesses.append(access)

        # Identifier reads are source observations only. Exclude declaration names,
        # assignment destinations and call callee names, which have dedicated records.
        for item in _walk(body):
            if item.type not in {"identifier", "field_identifier"}:
                continue
            parent = item.parent
            skip = False
            expression = item
            while parent and parent.id != body.id:
                if parent.type == "call_expression":
                    callee = parent.child_by_field_name("function")
                    if callee and callee.start_byte <= item.start_byte < callee.end_byte:
                        skip = True
                        break
                if parent.type in {"function_declarator", "parameter_declaration"}:
                    declarator_name = parent.child_by_field_name("declarator")
                    while declarator_name and declarator_name.type == "init_declarator":
                        declarator_name = declarator_name.child_by_field_name("declarator")
                    if declarator_name and declarator_name.start_byte <= item.start_byte < declarator_name.end_byte:
                        skip = True
                        break
                if parent.type in {"init_declarator", "declaration"}:
                    declarator_name = parent.child_by_field_name("declarator")
                    while declarator_name and declarator_name.type == "init_declarator":
                        declarator_name = declarator_name.child_by_field_name("declarator")
                    if declarator_name and declarator_name.start_byte <= item.start_byte < declarator_name.end_byte:
                        skip = True
                        break
                if parent.type == "assignment_expression":
                    left = parent.child_by_field_name("left")
                    if left and left.start_byte <= item.start_byte < left.end_byte:
                        skip = True
                    break
                if parent.type == "update_expression":
                    skip = True
                    break
                if parent.type in {"field_expression", "subscript_expression"}:
                    expression = parent
                parent = parent.parent
            if skip:
                continue
            read = _base(rel, expression, _text(source, expression), qualified)
            read.update({"function_id": rec["id"], "access": "read", "expression_raw": _text(source, expression)})
            accesses.append(read)

    # Class/struct data members. Function declarations were collected above.
    for node in _walk(root):
        if node.type != "field_declaration" or _desc(node, {"function_declarator"}):
            continue
        owning = _type_ancestor(node, type_nodes)
        if not owning:
            continue
        annotation = _annotation(macros, node, {"UPROPERTY"}, source)
        declarator = node.child_by_field_name("declarator")
        names = []
        if declarator:
            names = [n for n in _walk(declarator) if n.type in {"field_identifier", "identifier"}]
        if not names:
            names = [n for n in node.children if n.type in {"field_identifier", "identifier"}]
        for name_node in names[:1]:
            name = _text(source, name_node)
            rec = _base(rel, node, name, owning["qualified_name"] + "::" + name)
            rec.update({"id": f"field:{rel}:{node.start_byte}:{name_node.start_byte}", "owner": owning["qualified_name"],
                        "access": _access_for(node, owning, source), "declaration_raw": _text(source, node),
                        "annotation": annotation, "preprocessor_conditions": _preprocessor_context(node, source)})
            fields.append(rec)

    for macro in macros:
        macro.update({"source_file": rel, "symbol_name": macro["name"], "qualified_name": None,
                      "parser": "ue-macro-lexical", "resolution_status": "syntax_observed",
                      "source_span": {"byte_start": macro["byte_start"], "byte_end": macro["byte_end"],
                                      "line_start": macro["line_start"], "column_start": 1,
                                      "line_end": macro["line_end"], "column_end": 1},
                      "issues": [] if macro["complete"] else ["macro argument list is incomplete"]})
    # Multiple identifier nodes can belong to the same member/subscript expression.
    unique_accesses = {}
    for access in accesses:
        key = (access["function_id"], access["source_span"]["byte_start"], access["source_span"]["byte_end"], access["access"])
        unique_accesses[key] = access
    return {"file": file_record, "types": types, "functions": functions, "fields": fields, "calls": calls,
            "control_flow": controls, "data_accesses": list(unique_accesses.values()), "lambdas": lambdas, "macros": macros}


def _source_roots(project: Path) -> list[Path]:
    roots = []
    direct = project / "Source"
    if direct.is_dir():
        roots.append(direct)
    plugins = project / "Plugins"
    if plugins.is_dir():
        roots.extend(sorted({p for p in plugins.rglob("Source") if p.is_dir()}))
    return roots


def _build_rules(project: Path, roots: list[Path]) -> list[dict[str, Any]]:
    records = []
    for path in sorted({p for root in roots for p in root.rglob("*.cs")
                        if p.name.endswith((".Build.cs", ".Target.cs"))}):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(project).as_posix()
        kind = "module" if path.name.endswith(".Build.cs") else "target"
        suffix = ".Build.cs" if kind == "module" else ".Target.cs"
        name = path.name[:-len(suffix)]
        deps = sorted(set(re.findall(
            r"(?:Public|Private|DynamicallyLoaded)DependencyModuleNames\s*\.\s*(?:Add|AddRange)\s*\([^;]*?\)",
            text, re.S)))
        dep_names = sorted(set(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"', " ".join(deps))))
        type_match = re.search(r"\bType\s*=\s*TargetType\.([A-Za-z_][A-Za-z0-9_]*)", text)
        records.append({
            "source_file": rel, "line_start": 1, "line_end": text.count("\n") + 1, "symbol_name": name,
            "qualified_name": name, "parser": "csharp-lexical", "resolution_status": "syntax_observed",
            "source_span": {"byte_start": 0, "byte_end": len(text.encode('utf-8')), "line_start": 1,
                            "column_start": 1, "line_end": text.count("\n") + 1,
                            "column_end": len(text.rsplit("\n", 1)[-1].encode("utf-8")) + 1},
            "issues": ["C# rules were lexically observed; UBT was not executed"], "kind": kind,
            "dependencies": dep_names, "target_type": type_match.group(1) if type_match else None,
        })
    return records


def analyze_project(project: Path) -> dict[str, Any]:
    project = project.resolve()
    parser, error = _load_parser()
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "status": "unavailable" if error else "ok",
        "parser": {"name": PARSER_NAME, "versions": _versions(), "semantic_engine": None},
        "accuracy_contract": {
            "syntax_observed": "direct source syntax only", "semantic_resolved": "reserved for a future typed semantic engine",
            "unresolved": "target/type/preprocessor result is not proven", "semantic_resolved_count": 0,
        },
        "source_roots": [], "files": [], "types": [], "functions": [], "fields": [], "calls": [],
        "control_flow": [], "data_accesses": [], "lambdas": [], "unreal_macros": [],
        "declaration_definition_links": [], "unreal_function_links": [], "build_rules": [], "issues": [], "statistics": {},
    }
    roots = _source_roots(project)
    result["source_roots"] = [p.relative_to(project).as_posix() for p in roots]
    result["build_rules"] = _build_rules(project, roots)
    if error:
        result["issues"].append({"kind": "parser_unavailable", "message": error,
                                 "resolution_status": "unresolved"})
        return result
    paths = sorted({p for root in roots for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES})
    for path in paths:
        try:
            parsed = _parse_file(parser, project, path)
        except (OSError, UnicodeError) as exc:
            result["status"] = "partial"
            result["issues"].append({"kind": "source_read_failed", "source_file": path.relative_to(project).as_posix(),
                                     "message": f"{type(exc).__name__}: {exc}", "resolution_status": "unresolved"})
            continue
        result["files"].append(parsed.pop("file"))
        for key, target in (("types", "types"), ("functions", "functions"), ("fields", "fields"), ("calls", "calls"),
                            ("control_flow", "control_flow"), ("data_accesses", "data_accesses"), ("lambdas", "lambdas"),
                            ("macros", "unreal_macros")):
            result[target].extend(parsed[key])
    if any(f["parse_status"] == "partial" for f in result["files"]):
        result["status"] = "partial"

    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for function in result["functions"]:
        by_symbol[function["symbol_name"]].append(function)
    for call in result["calls"]:
        candidates = by_symbol.get(call["symbol_name"], [])
        # Qualified syntax can safely narrow spelling candidates, but still cannot prove a C++ target.
        expression = call["callee_expression"].replace("->", "::").replace(".", "::")
        if "::" in expression:
            narrowed = [f for f in candidates if f["qualified_name"] and f["qualified_name"].endswith(expression)]
            if narrowed:
                candidates = narrowed
        call["candidates"] = [f["id"] for f in candidates]
        candidate_keys = {(f["qualified_name"], re.sub(r"\s+", "", f["parameters_raw"] or "")) for f in candidates}
        duplicate_kind = any(sum(1 for f in candidates if (f["qualified_name"], re.sub(r"\s+", "", f["parameters_raw"] or "")) == key
                                 and f["declaration_kind"] == kind) > 1
                             for key in candidate_keys for kind in ("declaration", "definition"))
        unique = len(candidate_keys) == 1 and not duplicate_kind
        call["candidate_status"] = "none" if not candidates else ("unique_syntax_candidate" if unique else "ambiguous_syntax_candidates")
        if not unique:
            call["issues"].append("no unique source-spelling candidate" if not candidates else "multiple source-spelling candidates")

    signature_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for function in result["functions"]:
        normalized = re.sub(r"\s+", "", function["parameters_raw"] or "")
        signature_groups[(function["qualified_name"] or function["symbol_name"], normalized)].append(function)
    for (_, _), group in signature_groups.items():
        declarations = [f for f in group if f["declaration_kind"] == "declaration"]
        definitions = [f for f in group if f["declaration_kind"] == "definition"]
        for declaration in declarations:
            result["declaration_definition_links"].append({
                "declaration_id": declaration["id"], "definition_candidates": [f["id"] for f in definitions],
                "resolution_status": "syntax_observed" if len(definitions) == 1 else "unresolved",
                "issues": ["matched by qualified spelling and parameter syntax; type equivalence was not checked"] +
                          ([] if len(definitions) == 1 else ["definition candidate count is not one"]),
            })
    for function in result["functions"]:
        relation = function.get("unreal_relation")
        if not relation:
            continue
        owner = function.get("owner")
        candidates = [f for f in result["functions"] if f["symbol_name"] == relation["declared_name"] and f.get("owner") == owner]
        result["unreal_function_links"].append({
            "implementation_id": function["id"], "kind": relation["kind"], "declaration_candidates": [f["id"] for f in candidates],
            "resolution_status": "syntax_observed" if len(candidates) == 1 else "unresolved",
            "issues": ["UnrealHeaderTool/generated code was not available; this is a naming and owner candidate only"],
        })
    result["statistics"] = {key: len(result[key]) for key in
                            ("files", "types", "functions", "fields", "calls", "control_flow", "data_accesses", "lambdas")}
    result["statistics"]["files_partial"] = sum(1 for f in result["files"] if f["parse_status"] == "partial")
    result["statistics"]["calls_ambiguous"] = sum(1 for c in result["calls"] if c["candidate_status"] == "ambiguous_syntax_candidates")
    result["statistics"]["calls_unmatched"] = sum(1 for c in result["calls"] if c["candidate_status"] == "none")
    return result


def functions_markdown(index: dict[str, Any]) -> str:
    out = ["# C++ functions", "", "Source syntax observed by tree-sitter-cpp. Names and signatures are not typed C++ resolution.", "",
           f"Status: **{index['status']}** · semantic-resolved records: **0**", ""]
    for fn in sorted(index["functions"], key=lambda x: (x["source_file"], x["line_start"], x["id"])):
        out += [f"## `{fn['qualified_name'] or fn['symbol_name']}`", "",
                f"- Source: `{fn['source_file']}:{fn['line_start']}-{fn['line_end']}`",
                f"- Kind: `{fn['declaration_kind']}` · resolution: `{fn['resolution_status']}`",
                f"- Signature: `{fn['signature_raw']}`"]
        if fn.get("annotation"):
            out.append(f"- Unreal annotation (source): `{fn['annotation']['raw']}`")
        if fn.get("preprocessor_conditions"):
            out.append("- Unevaluated preprocessor context: " + ", ".join(f"`{x}`" for x in fn["preprocessor_conditions"]))
        out.append("")
    if not index["functions"]:
        out += ["_No function syntax was indexed._", ""]
    return "\n".join(out) + "\n"


def call_graph_markdown(index: dict[str, Any]) -> str:
    functions = {f["id"]: f for f in index["functions"]}
    out = ["# C++ call graph", "", "Every edge is a syntax observation. tree-sitter does not prove its runtime or overload target.", ""]
    for call in sorted(index["calls"], key=lambda x: (x["source_file"], x["line_start"], x["id"])):
        targets = list(dict.fromkeys(functions[x]["qualified_name"] for x in call["candidates"] if x in functions))
        out += [f"- `{call['caller']}` → `{call['callee_expression']}` at `{call['source_file']}:{call['line_start']}`",
                f"  - target: `{call['resolution_status']}` / `{call['candidate_status']}`" +
                ((" · candidates: " + ", ".join(f"`{x}`" for x in targets)) if targets else "")]
    if not index["calls"]:
        out += ["_No call expressions were indexed._"]
    return "\n".join(out) + "\n"


def unresolved_markdown(index: dict[str, Any]) -> str:
    out = ["# C++ unresolved and partial analysis", "", "These items must not be treated as proven semantic facts.", "",
           f"Index status: **{index['status']}**", ""]
    for issue in index["issues"]:
        out.append(f"- `{issue.get('kind', 'issue')}`: {issue.get('message', issue)}")
    for file in index["files"]:
        if file["parse_status"] != "ok":
            out.append(f"- Partial parse: `{file['source_file']}` ({len(file['issues'])} recorded syntax issues)")
        for directive in file["preprocessor_directives"]:
            out.append(f"- Unevaluated `{file['source_file']}:{directive['line']}`: `{directive['raw']}`")
    for call in index["calls"]:
        out.append(f"- Call target `{call['callee_expression']}` at `{call['source_file']}:{call['line_start']}`: {call['candidate_status']}")
    if len(out) == 5:
        out.append("_No unresolved items were recorded._")
    return "\n".join(out) + "\n"
