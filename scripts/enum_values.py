"""Typed enum-array rendering with exact spans; raw caches keep saved names/numbers.

Only generated spans are resolved. Ordinary numbers and text are never searched/replaced.
"""
from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict


def reference_from_tag(tag):
    tree = getattr(tag, "type_name", None)
    children = getattr(tree, "children", None) or []
    if tree is None or tree.name != "ArrayProperty" or not children:
        return None  # legacy byte arrays without an enum identity stay numeric
    inner = children[0]
    enum = (getattr(inner, "children", None) or [None])[0]
    if inner.name not in ("ByteProperty", "EnumProperty") or enum is None or enum.name in ("", "None"):
        return None
    packages = [child.name for child in (getattr(enum, "children", None) or []) if child.name.startswith("/")]
    return {"name": str(enum.name), "path": packages[0].split(".", 1)[0] if len(packages) == 1 else "",
            **({"ambiguous": True} if len(packages) > 1 else {})}


def fallback(reference, value):
    if isinstance(value, str):
        if value.startswith(reference["name"] + "::"):
            return value.replace("|", "\\|") + "(value unresolved)"
        return f"{reference['name']}(name={json.dumps(value, ensure_ascii=False)}; unresolved)"
    return f"{reference['name']}({value}; unresolved)"


class EnumScalar:
    def __init__(self, value, reference, collector):
        self.value, self.reference, self.collector = value, reference, collector

    def token(self):
        return self.collector.token(self.reference, self.value)


class EnumArray(list):
    """Keep raw names/numbers; allocate typed scalars only for elements actually rendered."""
    def __init__(self, values, reference, collector):
        super().__init__(values)
        self.reference, self.collector = reference, collector

    def __iter__(self):
        return (EnumScalar(value, self.reference, self.collector) for value in list.__iter__(self))

    def __getitem__(self, index):
        value = list.__getitem__(self, index)
        return EnumArray(value, self.reference, self.collector) if isinstance(index, slice) else EnumScalar(value, self.reference, self.collector)


class EnumSpans:
    def __init__(self):
        self.prefix = "\x1e" + uuid.uuid4().hex + ":"
        self.values = []

    def token(self, reference, value):
        token = self.prefix + str(len(self.values)) + "\x1f"
        self.values.append((reference, value))
        return token

    def finish(self, markdown):
        """Remove private render tokens; publish readable unresolved values + exact offsets."""
        chunks, spans, end, length = [], [], 0, 0
        for match in re.finditer(re.escape(self.prefix) + r"(\d+)\x1f", markdown):
            before = markdown[end:match.start()]
            chunks.append(before)
            length += len(before)
            reference, value = self.values[int(match[1])]
            text = fallback(reference, value)
            spans.append({"start": length, "end": length + len(text), "reference": reference, "value": value})
            chunks.append(text)
            length += len(text)
            end = match.end()
        chunks.append(markdown[end:])
        return "".join(chunks), spans


class EnumCatalog:
    def __init__(self, datas):
        self.paths, self.names = {}, defaultdict(list)
        for path, result in sorted(datas.items()):
            summary = result["summary"]
            if (summary.get("class") != "UserDefinedEnum" or summary.get("parse_status") != "ok" or
                    summary.get("issues") or summary.get("newer_format") or not summary.get("enum_values")):
                continue
            self.paths[path] = summary["enum_values"]
            self.names[path.rsplit("/", 1)[-1]].append(path)

    def label(self, reference, value):
        if reference.get("ambiguous"):
            return None
        path = reference.get("path")
        if not path:
            candidates = self.names.get(reference["name"], [])
            if len(candidates) != 1:
                return None
            path = candidates[0]
        values = self.paths.get(path) or {}
        if isinstance(value, str):
            matches = [(number, entry) for number, entries in values.items() for entry in entries if entry["name"] == value]
        else:
            matches = [(str(value), entry) for entry in values.get(str(value), [])]
        if len(matches) != 1 or path.rsplit("/", 1)[-1] != reference["name"]:
            return None  # no guessed aliases, package paths or duplicate short names
        number, entry = matches[0]
        name = entry["name"].replace("|", "\\|").replace("\n", "\\n")
        display = entry.get("display")
        detail = ", display=" + json.dumps(display, ensure_ascii=False).replace("|", "\\|") if display else ""
        return f"{name}({number}{detail})"


def resolve_asset_enums(result, catalog):
    """Enrich a fresh/cache-loaded result once, after every enum asset has been decoded."""
    spans = result.get("enum_spans") or []
    if not spans:
        return
    source, chunks, end, resolved = result["markdown"], [], 0, 0
    for span in spans:
        start, stop, reference, value = span["start"], span["end"], span["reference"], span["value"]
        if not (end <= start <= stop <= len(source)) or source[start:stop] != fallback(reference, value):
            raise ValueError("enum span does not match raw decoded Markdown")
        label = catalog.label(reference, value)
        chunks += [source[end:start], label or source[start:stop]]
        resolved += label is not None
        end = stop
    chunks.append(source[end:])
    unresolved = len(spans) - resolved
    result["summary"]["enum_resolution"] = {"resolved": resolved, "unresolved": unresolved}
    result["markdown"] = "".join(chunks)
    if unresolved:
        result["markdown"] += (f"\n_⚠ Enum labels unresolved for {unresolved} rendered values "
                               "(missing/ambiguous enum or unknown value); saved names/numbers are retained._\n")
