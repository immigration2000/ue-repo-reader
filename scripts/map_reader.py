"""Maps (.umap) -> AI-readable Markdown, without the Unreal Editor.

For each level: world settings (game mode override, world partition, streaming sub-levels), the Level
Blueprint (rendered with bp_reader), every placed gameplay actor with its label, class, location and
per-instance property overrides, and a summary of environment actors (meshes, lights, fog, foliage…).
World Partition maps keep actors in separate packages under Content/__ExternalActors__/<map>/ —
pass those files in `external_actor_files` and they are merged into the same listing.

Sub-objects (components) are only unique within their owning actor, so everything here is resolved
by export index / outer index, never by name alone.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from pathlib import Path

import bp_reader as B
import data_reader as D

ENVIRONMENT = {
    "StaticMeshActor", "Brush", "InstancedFoliageActor", "DirectionalLight", "PointLight", "SpotLight", "RectLight",
    "SkyLight", "SkyAtmosphere", "VolumetricCloud", "ExponentialHeightFog", "AtmosphericFog", "SphereReflectionCapture",
    "BoxReflectionCapture", "PlaneReflectionCapture", "PlanarReflection", "DecalActor", "LightmassImportanceVolume",
    "Landscape", "LandscapeProxy", "LandscapeStreamingProxy", "WorldDataLayers", "WorldPartitionMiniMap",
    "WorldPartitionHLOD", "LODActor", "Note", "PrecomputedVisibilityVolume", "LightmassCharacterIndirectDetailVolume",
    "SkeletalMeshActor", "TextRenderActor", "CameraActor", "LevelBounds", "AbstractNavData", "RecastNavMesh",
    "NavigationData", "HLODActor", "WaterBodyOcean", "WaterZone", "PackedLevelActor",
}
NOT_ACTORS = {"LevelScriptBlueprint", "Model", "Polys", "WorldSettings", "BookMark", "BookMark2D", "Level",
              "World", "NavigationSystemConfig", "NavigationSystemModuleConfig"}
_ACTOR_META = {
    "RootComponent", "ActorGuid", "ActorLabel", "FolderPath", "Brush", "BrushComponent", "BrushBuilder",
    "SavedSelections", "BlueprintCreatedComponents", "InstanceComponents", "ActorInstanceGuid", "ContentBundleGuid",
    "bActorLabelEditable", "SpriteComponent", "ArrowComponent", "GoodSprite", "BadSprite", "HLODLayer",
    "bHidden", "UberGraphFrame", "NavigationSystemConfig", "BookmarkArray", "LastBookmarkIndex", "ActorFolder",
    "bIsEditorOnlyActor", "ExternalDataLayerAsset", "ParentComponent", "BrushType", "PolyFlags", "FolderGuid",
    "ActorInstanceGuid", "LandscapeGuid", "LandscapeActor",
}


def _num(v) -> str:
    return B._fmt_num(round(float(v), 1)) if isinstance(v, (int, float)) else str(v)


def _vec(v) -> str | None:
    f = D._fields_of(v)
    if {"X", "Y", "Z"} <= set(f):
        return f"({_num(f['X'])}, {_num(f['Y'])}, {_num(f['Z'])})"
    if hasattr(v, "x"):
        return f"({_num(v.x)}, {_num(v.y)}, {_num(v.z)})"
    return None


def _rot(v) -> str | None:
    f = D._fields_of(v)
    if {"Pitch", "Yaw", "Roll"} <= set(f):
        p, y, r = (float(f[k] or 0) for k in ("Pitch", "Yaw", "Roll"))
    elif hasattr(v, "yaw"):
        p, y, r = float(v.pitch or 0), float(v.yaw or 0), float(v.roll or 0)
    else:
        return None
    if abs(p) < 0.05 and abs(r) < 0.05:
        return None if abs(y) < 0.05 else f"yaw {_num(y)}"
    return f"(P {_num(p)}, Y {_num(y)}, R {_num(r)})"


class PackageActors:
    """Actors of one package (a .umap or an external-actor .uasset), resolved by export index."""

    def __init__(self, path: str):
        from uasset_read.parse_uasset import parse_uasset_with_linker
        self.path = path
        self.r = parse_uasset_with_linker(path, force_full_parse=True, preload_all=True)
        self.ctx = B.Ctx(self.r)
        self.reader = D.TaggedReader(path, self.r, self.ctx)
        self._props = {}
        self.children = defaultdict(list)  # outer export index (1-based) -> [export index (1-based)]
        for i, e in enumerate(self.r.export_map):
            oi = getattr(e, "outer_index", 0)
            oi = getattr(oi, "index", oi)
            if isinstance(oi, int) and oi > 0:
                self.children[oi].append(i + 1)

    def close(self):
        self.reader.close()

    def props(self, idx: int) -> dict:
        if idx not in self._props:
            try:
                items, _ = self.reader.export_stream(self.r.export_map[idx - 1])
                self._props[idx] = dict(items)
            except Exception:
                self._props[idx] = {}
        return self._props[idx]

    def cls(self, idx: int) -> str:
        o = self.ctx.obj(idx)
        return self.ctx.class_of(o) if o is not None else ""

    def name(self, idx: int) -> str:
        return self.r.export_map[idx - 1].object_name

    def child(self, owner: int, name) -> int | None:
        if not isinstance(name, str):
            return None
        for c in self.children.get(owner, []):
            if self.name(c) == name:
                return c
        return None

    def level_exports(self):
        """Export indices whose outer is a Level (exported or imported, e.g. for external actors)."""
        for i in range(1, len(self.r.export_map) + 1):
            o = self.ctx.obj(i)
            outer = getattr(o, "outer", None) if o is not None else None
            if outer is not None and self.ctx.class_of(outer) == "Level":
                yield i

    def actors(self, level_script_class: str | None = None):
        out = []
        for i in self.level_exports():
            cls = self.cls(i)
            if cls in NOT_ACTORS or (level_script_class and cls == level_script_class):
                continue
            p = self.props(i)
            if not ({"ActorGuid", "RootComponent", "ActorLabel"} & set(p)) and cls not in ENVIRONMENT:
                continue
            out.append(self.describe(i, cls, p))
        return out

    def describe(self, idx, cls, p) -> dict:
        name = self.name(idx)
        root = self.child(idx, p.get("RootComponent"))
        rp = self.props(root) if root else {}
        loc = _vec(rp.get("RelativeLocation")) if rp else None
        rot = _rot(rp.get("RelativeRotation")) if rp else None
        scale = _vec(rp.get("RelativeScale3D")) if rp else None
        mesh = None
        if cls == "StaticMeshActor" or "StaticMesh" in rp:
            mesh = D._val(rp.get("StaticMesh")) if rp.get("StaticMesh") is not None else None
        for key in ("SkeletalMeshAsset", "SkeletalMesh"):
            if rp.get(key) not in (None, "None"):
                mesh = D._val(rp[key])
                anim = rp.get("AnimClass") or rp.get("AnimBlueprintGeneratedClass")
                if anim not in (None, "None"):
                    mesh += f" (anim {D._val(anim)})"
                break
        subobjects = {self.name(c) for c in self.children.get(idx, [])}
        overrides = []
        for k, v in p.items():
            if k in _ACTOR_META or k.startswith("bOverride"):
                continue
            if isinstance(v, str) and v in subobjects:
                continue  # component reference, not a tunable value
            s = D._val(v)
            if s.startswith("<") and s.endswith(">"):
                continue
            overrides.append(f"{k}={s if len(s) <= 120 else s[:117] + '…'}")
        folder = p.get("FolderPath")
        return {"name": name, "label": p.get("ActorLabel") or name, "class": cls, "loc": loc, "rot": rot,
                "scale": scale if scale and scale != "(1, 1, 1)" else None, "mesh": mesh,
                "folder": B.fmt_value(folder) if folder not in (None, "None", "") else "",
                "overrides": overrides, "hidden": p.get("bHidden") is True}


def _world_info(pkg: PackageActors) -> dict:
    info = {"game_mode": None, "world_partition": False, "streaming": [], "settings": []}
    for i in range(1, len(pkg.r.export_map) + 1):
        cls = pkg.cls(i)
        if cls == "WorldSettings":
            p = pkg.props(i)
            gm = p.get("DefaultGameMode")
            info["game_mode"] = D._val(gm) if gm not in (None, "None") else None
            if p.get("WorldPartition") not in (None, "None"):
                info["world_partition"] = True
            for k, v in p.items():
                if k in _ACTOR_META or k in ("DefaultGameMode", "WorldPartition", "HierarchicalLODSetup",
                                             "DefaultReverbSettings", "BookmarkArray") or k.startswith("Bookmark"):
                    continue
                s = D._val(v)
                if isinstance(v, str) and pkg.child(i, v):
                    continue
                if not (s.startswith("<") and s.endswith(">")):
                    info["settings"].append(f"{k}={s if len(s) <= 100 else s[:97] + '…'}")
        elif cls == "WorldPartition":
            info["world_partition"] = True
        elif cls.startswith("LevelStreaming"):
            p = pkg.props(i)
            asset = p.get("WorldAsset")
            path = getattr(asset, "asset_path", None) or D._val(asset)
            flags = [k for k in ("bInitiallyLoaded", "bInitiallyVisible", "bShouldBeVisibleInEditor") if p.get(k)]
            info["streaming"].append(f"{str(path).split('.')[0]} ({cls.replace('LevelStreaming', '')}"
                                     + (", " + ", ".join(flags) if flags else "") + ")")
    return info


def read_map(path: str, game_path: str, external_actor_files: list[str] | None = None,
             max_external: int = 5000) -> dict:
    B.ensure_uasset_read()
    logging.disable(logging.CRITICAL)
    B._install_patches()
    if not Path(path).is_file():
        raise FileNotFoundError(path)
    stem = Path(path).stem
    pkg = PackageActors(path)
    ext_errors = 0
    try:
        ev = getattr(pkg.r.summary, "saved_by_engine_version", None)
        saved = f"{ev.major}.{ev.minor}.{ev.patch}" if ev and getattr(ev, "major", 0) else "?"
        info = _world_info(pkg)
        actors = pkg.actors(level_script_class=f"{stem}_C")
    finally:
        pkg.close()
    ext = list(external_actor_files or [])
    truncated = max(0, len(ext) - max_external)
    for f in ext[:max_external]:
        try:
            ep = PackageActors(f)
            try:
                actors.extend(ep.actors())
            finally:
                ep.close()
        except Exception:
            ext_errors += 1

    # Level Blueprint
    lb_md, lb_summary = None, None
    try:
        lb = B.read_blueprint(path, game_path)
        text = lb["markdown"]
        lb_summary = lb["summary"]
        if "## Graphs" in text:
            body = text.split("## Graphs", 1)[1].strip()
            head = text.split("## Graphs", 1)[0]
            extra = [ln for ln in head.splitlines() if ln.startswith("|") or ln.startswith("- ")]
            lb_md = (("\n".join(extra) + "\n\n") if extra else "") + body
    except Exception as e:  # noqa: BLE001
        lb_md = f"(level blueprint could not be read: {type(e).__name__}: {e})"

    gameplay = [a for a in actors if a["class"] not in ENVIRONMENT]
    env = [a for a in actors if a["class"] in ENVIRONMENT]
    md = [f"# {stem}", "", f"`{game_path}` · **Map** · saved with UE {saved}", ""]
    md.append(f"- Game mode override: **{info['game_mode']}**" if info["game_mode"]
              else "- Game mode override: none (uses the project default from DefaultEngine.ini)")
    if info["world_partition"]:
        md.append(f"- World Partition: yes — {len(ext)} external actor packages"
                  + (f" ({truncated} not read, over the limit)" if truncated else "")
                  + (f", {ext_errors} unreadable" if ext_errors else ""))
    if info["streaming"]:
        md.append("- Streaming sub-levels: " + "; ".join(info["streaming"]))
    if info["settings"]:
        md.append("- World settings: " + ", ".join(info["settings"][:15]))
    md.append("")

    md += ["## Level Blueprint", ""]
    if lb_md and lb_md.strip() and "(no graphs)" not in lb_md:
        md += [lb_md, ""]
    else:
        md += ["(empty)", ""]

    md += [f"## Gameplay actors ({len(gameplay)})", "",
           "_Location is the root component's relative location (world location unless the actor is attached)._",
           "_Overrides are the values changed on this placed instance — for Blueprint actors, typically instance-editable variables._", "",
           "| Actor | Class | Location | Rotation | Overrides |", "|---|---|---|---|---|"]
    for a in sorted(gameplay, key=lambda a: (a["folder"], a["class"], a["label"])):
        label = f"{a['folder']}/{a['label']}" if a["folder"] else a["label"]
        if a["name"] != a["label"]:
            label += f" (`{a['name']}`)"
        ov = "; ".join(a["overrides"][:8]) + (" …" if len(a["overrides"]) > 8 else "")
        if a["hidden"]:
            ov = "hidden; " + ov
        md.append(f"| {label} | {a['class']} | {a['loc'] or ''} | {a['rot'] or ''} | {ov.replace('|', '/')} |")
    md.append("")

    if env:
        counts = Counter(a["class"] for a in env)
        md += [f"## Environment ({len(env)} actors, summarized)", ""]
        md.append(", ".join(f"{c} ×{n}" for c, n in counts.most_common()))
        for kind, label in (("StaticMeshActor", "Static meshes placed"), ("SkeletalMeshActor", "Skeletal meshes placed")):
            meshes = Counter(a["mesh"] for a in env if a["class"] == kind and a["mesh"])
            if meshes:
                md += ["", f"{label}: " + ", ".join(f"{m} ×{n}" for m, n in meshes.most_common(30))
                       + (" …" if len(meshes) > 30 else "")]
        md.append("")

    placed = Counter(a["class"] for a in actors)
    summary = {"path": game_path, "saved_with": saved, "game_mode": info["game_mode"],
               "world_partition": info["world_partition"], "external_actors": len(ext),
               "actor_count": len(actors), "gameplay_count": len(gameplay), "placed_classes": dict(placed),
               "level_bp_entries": (lb_summary or {}).get("entries", []),
               "level_bp_nodes": ((lb_summary or {}).get("nodes_ok", 0), (lb_summary or {}).get("nodes_total", 0))}
    return {"markdown": "\n".join(md) + "\n", "summary": summary}


def external_actor_map(rel_path: str) -> str | None:
    """'__ExternalActors__/Maps/L_Main/A/B/X.uasset' -> 'Maps/L_Main' (map path inside its content root)."""
    parts = Path(rel_path).as_posix().split("/")
    if "__ExternalActors__" not in parts:
        return None
    parts = parts[parts.index("__ExternalActors__") + 1:-1]
    # strip the hashed bucket folders (1-2 chars each) that UE appends under the map path
    while parts and re.fullmatch(r"[0-9A-Z]{1,2}", parts[-1]):
        parts.pop()
    return "/".join(parts) if parts else None


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="Render one map (.umap) to Markdown")
    ap.add_argument("umap")
    ap.add_argument("--game-path", default=None)
    a = ap.parse_args()
    out = read_map(a.umap, a.game_path or Path(a.umap).stem)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(out["markdown"])
