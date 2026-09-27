"""Import pipeline: resolve -> archive originals -> analyse -> write s&box assets -> verify -> report.

Project folder layout (created by `sourcebridge import`):
    <project>/originals/<sha256[:2]>/<sha256>    every original file, byte-identical, content-addressed
    <project>/assets/<id>.json                    AssetDocument (versioned JSON)
    <project>/reports/<id>.md|.json               conversion report
    <project>/sbox/Assets/s1/...                  editable s&box source assets (or --sbox-assets)
"""

from __future__ import annotations

import hashlib
import io
import json
import platform
import time
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .analyze import classify
from .journal import Journal
from .resolve import ResolvedModel, Resolver
from .safety import safe_join
from .sources import Mount
from .targets.sbox.kv3 import parse_kv3
from .targets.sbox.model import SboxModelOutput, build_sbox_model
from .transform import TRANSFORMS

SCHEMA = "sourcebridge.asset"
SCHEMA_VERSION = 1


def asset_id(path: str) -> str:
    stem = path.rsplit(".", 1)[0].replace("/", "__")
    return f"{stem}-{hashlib.sha1(path.encode()).hexdigest()[:8]}"


def tool_versions() -> dict:
    from importlib.metadata import PackageNotFoundError, version

    def ver(pkg: str) -> str:
        try:
            return version(pkg)
        except PackageNotFoundError:
            return "unknown"

    return {
        "sourcebridge": __version__,
        "python": platform.python_version(),
        "sourcepp": ver("sourcepp"),
        "srctools": ver("srctools"),
    }


def archive_originals(res: ResolvedModel, project: Path) -> list[dict]:
    out = []
    for path, data in sorted(res.files.items()):
        digest = hashlib.sha256(data).hexdigest()
        dest = project / "originals" / digest[:2] / digest
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(data)
        elif dest.stat().st_size != len(data):
            raise RuntimeError(f"archive corruption: {dest} exists with different size")
        dep = next((d for d in res.deps if d.path == path), None)
        out.append(
            {
                "path": path,
                "original_name": dep.original_name if dep else path,
                "sha256": digest,
                "size": len(data),
                "source": dep.source if dep else None,
                "stored_as": dest.relative_to(project).as_posix(),
            }
        )
    return out


def model_summary(res: ResolvedModel) -> dict:
    m = res.mdl
    d = {
        "format": "mdl",
        "version": m.version,
        "checksum": m.checksum,
        "internal_name": m.name,
        "flags": m.flags,
        "flag_names": m.flag_names,
        "eye_position": m.eye_position,
        "hull": [m.hull_min, m.hull_max],
        "view_bbox": [m.view_bbmin, m.view_bbmax],
        "mass": m.mass,
        "contents": m.contents,
        "surface_prop": m.surface_prop,
        "keyvalues": m.keyvalues,
        "textures": m.textures,
        "cd_materials": m.cd_textures,
        "skin_families": m.skin_families,
        "bones": [
            {"index": b.index, "name": b.name, "parent": b.parent, "pos": b.pos, "quat": b.quat,
             "flags": b.flags, "surface_prop": b.surface_prop}
            for b in m.bones
        ],
        "attachments": [asdict(a) for a in m.attachments],
        "hitbox_sets": [asdict(h) for h in m.hitbox_sets],
        "body_parts": [
            {"name": bp.name, "models": [
                {"name": sm.name, "vertices": sm.num_vertices,
                 "meshes": [{"material": me.material, "vertices": me.num_vertices, "flexes": len(me.flexes)}
                            for me in sm.meshes]}
                for sm in bp.models]}
            for bp in m.body_parts
        ],
        "flex_descs": m.flex_descs,
        "flex_controllers": [asdict(f) for f in m.flex_controllers],
        "pose_parameters": [asdict(p) for p in m.pose_parameters],
        "include_models": m.include_models,
        "animations": [
            {"name": a.name, "fps": a.fps, "frames": a.num_frames, "flags": a.flags} for a in m.anim_descs
        ],
        "sequences": [
            {"label": s.label, "activity": s.activity, "flags": s.flags, "anims": s.anim_indices,
             "fade_in": s.fade_in, "fade_out": s.fade_out}
            for s in m.sequences
        ],
        "not_decoded": m.unsupported,
    }  # fmt: skip
    if res.vvd:
        d["vvd"] = {
            "lods": res.vvd.num_lods,
            "lod_vertices": res.vvd.lod_vertex_counts,
            "fixups": len(res.vvd.fixups),
        }
    if res.vtx:
        d["vtx"] = {
            "lods": res.vtx.num_lods,
            "layout": res.vtx.layout,
            "max_bones_per_vertex": res.vtx.max_bones_per_vert,
        }
    return d


def physics_summary(res: ResolvedModel) -> dict | None:
    if res.phy is None:
        return None
    return {
        "solids": [
            {
                "index": s.index,
                "hulls": len(s.hulls),
                "points": sum(len(h.points) for h in s.hulls),
                "legacy_format": s.legacy,
                "info": res.phy.solid_info(s.index),
            }
            for s in res.phy.solids
        ],
        "total_mass": res.phy.total_mass,
        "text_blocks": [asdict(b) for b in res.phy.blocks],
    }


# ---------------------------------------------------------------- verification


def verify_outputs(res: ResolvedModel, out: SboxModelOutput) -> list[dict]:
    """Checks that can run without s&box. None of them replaces the target test."""
    import srctools.smd as smd

    checks = []
    files = {f.path: f for f in out.files}

    # 1. every render SMD re-parses with an independent SMD reader and matches the source mesh
    from .geometry import extract

    ok = True
    detail = []
    for lod in range(max(1, res.vtx.num_lods)):
        for geo in extract(res.mdl, res.vvd, res.vtx, lod):
            if not geo.meshes:
                continue
            name = out.mesh_files.get((geo.body_part_index, geo.model_index, lod))
            f = files.get(name) if name else None
            if f is None:
                ok = False
                detail.append(f"no SMD for {geo.body_part}/{geo.model_name} lod{lod}")
                continue
            mesh = smd.Mesh.parse_smd(io.BytesIO(f.data))
            if len(mesh.triangles) != geo.triangle_count:
                ok = False
                detail.append(f"{name}: {len(mesh.triangles)} triangles, source has {geo.triangle_count}")
            src_bounds = geo.bounds()
            pts = [v.pos for t in mesh.triangles for v in (t.point1, t.point2, t.point3)]
            got = (
                tuple(min(p[k] for p in pts) for k in range(3)),
                tuple(max(p[k] for p in pts) for k in range(3)),
            )
            if any(
                abs(a - b) > 1e-3
                for x, y in zip(src_bounds, got, strict=True)
                for a, b in zip(x, y, strict=True)
            ):
                ok = False
                detail.append(f"{name}: bounds {got} differ from source {src_bounds}")
            detail.append(f"{name}: {len(mesh.triangles)} triangles, bounds match")
    checks.append(
        {
            "name": "mesh round-trip (srctools SMD parser)",
            "state": "passed" if ok else "failed",
            "detail": detail,
        }
    )

    # 2. collision hulls re-parse and stay inside the render bounds (+1 inch tolerance)
    if res.phy is not None:
        hull_files = [f for f in out.files if f.role == "collision-hull"]
        geo0 = [g for g in extract(res.mdl, res.vvd, res.vtx, 0) if g.meshes]
        lo = [min(g.bounds()[0][k] for g in geo0) for k in range(3)]
        hi = [max(g.bounds()[1][k] for g in geo0) for k in range(3)]
        ok = bool(hull_files)
        detail = []
        for f in hull_files:
            mesh = smd.Mesh.parse_smd(io.BytesIO(f.data))
            pts = [v.pos for t in mesh.triangles for v in (t.point1, t.point2, t.point3)]
            hlo = [min(p[k] for p in pts) for k in range(3)]
            hhi = [max(p[k] for p in pts) for k in range(3)]
            inside = all(hlo[k] >= lo[k] - 1 and hhi[k] <= hi[k] + 1 for k in range(3))
            ok &= inside
            detail.append(
                f"{f.path}: {len(mesh.triangles)} triangles, bounds {hlo}..{hhi} {'inside' if inside else 'OUTSIDE'} render bounds"
            )
        checks.append(
            {
                "name": "collision hulls vs render bounds",
                "state": "passed" if ok else "failed",
                "detail": detail,
            }
        )

    # 3. every file referenced from .vmdl/.vmat exists in the output
    missing = []
    vmdl = files[out.vmdl_path].data.decode()
    try:
        tree = parse_kv3(vmdl)
        kv_ok = True
    except ValueError as exc:
        kv_ok = False
        tree = {}
        missing.append(f"vmdl does not parse as KV3: {exc}")
    for key, ref in _kv3_refs(tree):
        if ref and ref not in files:
            missing.append(f"vmdl {key} -> {ref}")
    for f in out.files:
        if f.role == "material":
            for ref in _vmat_refs(f.data.decode()):
                if ref not in files:
                    missing.append(f"{f.path} -> {ref}")
    checks.append(
        {
            "name": "references resolve inside the output",
            "state": "passed" if kv_ok and not missing else "failed",
            "detail": missing,
        }
    )
    checks.append(
        {
            "name": "s&box ModelDoc compile",
            "state": "not-run",
            "detail": ["needs s&box (Windows); see docs/target-tests.md"],
        }
    )
    checks.append(
        {
            "name": "s&box runtime (render, collide, fall)",
            "state": "not-run",
            "detail": ["needs s&box; see docs/target-tests.md"],
        }
    )
    return checks


FILE_KEYS = ("filename", "to", "global_default_material")


def _kv3_refs(node, key=""):
    """(key, path) for every KV3 value that names a file ModelDoc must find."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in FILE_KEYS and isinstance(v, str):
                yield k, v
            else:
                yield from _kv3_refs(v, k)
    elif isinstance(node, list):
        for v in node:
            yield from _kv3_refs(v, key)


def _vmat_refs(text: str) -> list[str]:
    import re

    return [m for m in re.findall(r'"Texture[A-Za-z]*"\s+"([^"\[]+)"', text)]


# ---------------------------------------------------------------- main entry


def import_model(
    mount: Mount,
    model_path: str,
    project: Path,
    sbox_assets: Path | None = None,
    provenance: dict | None = None,
) -> dict:
    started = time.time()
    project = Path(project)
    journal = Journal()
    res = Resolver(mount).resolve_model(model_path)
    aid = asset_id(res.path)
    doc: dict = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "id": aid,
        "source_path": res.path,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tools": tool_versions(),
        "mount": [s.describe() for s in mount.sources],
        "provenance": {
            "author": None,
            "license": None,
            "redistribution": "unknown",
            "notes": "Rights to imported content are not determined by SourceBridge. Unknown means not cleared.",
            **(provenance or {}),
        },
        "dependencies": [asdict(d) for d in res.deps],
        "problems": list(res.problems),
        "transforms": TRANSFORMS,
    }
    for s in mount.sources:
        desc = s.describe()
        if desc.get("kind") == "gma" and doc["provenance"]["author"] is None:
            doc["provenance"]["author"] = desc.get("author") or None
            doc["provenance"]["gma"] = {k: desc.get(k) for k in ("title", "steam_id", "metadata", "crc_ok")}
    doc["originals"] = archive_originals(res, project)

    status = {"progress": "failed", "quality": "unknown", "publication": "not cleared"}
    if res.mdl is None:
        doc["status"] = status
        doc["journal"] = journal.to_list()
        return _finish(project, doc, started)

    cls = classify(res.mdl)
    doc["classification"] = asdict(cls)
    doc["kind"] = cls.kind
    doc["model"] = model_summary(res)
    doc["physics"] = physics_summary(res)
    if cls.kind == "character" or len(res.mdl.bones) > 1:
        from .analyze import analyze_rig

        doc["rig"] = analyze_rig(res.mdl)
    doc["materials"] = [
        {
            "path": m.path,
            "shader": m.shader,
            "params": m.params,
            "textures": m.textures,
            "includes": m.includes,
            "error": m.error,
        }
        for m in res.skin_materials.values()
    ]
    missing = [d for d in res.deps if d.status in ("missing", "invalid")]
    for d in missing:
        journal.error(d.path, d.kind, f"{d.status}{': ' + d.note if d.note else ''}")

    if res.vvd is None or res.vtx is None:
        status["progress"] = "archived-only"
        status["quality"] = "incomplete input"
        doc["status"] = status
        doc["journal"] = journal.to_list()
        return _finish(project, doc, started)

    out = build_sbox_model(res, journal)
    target_root = Path(sbox_assets) if sbox_assets else project / "sbox" / "Assets"
    written = []
    for f in out.files:
        dest = safe_join(target_root, f.path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(f.data)
        written.append(
            {
                "path": f.path,
                "role": f.role,
                "sha256": hashlib.sha256(f.data).hexdigest(),
                "size": len(f.data),
            }
        )
    checks = verify_outputs(res, out)
    doc["outputs"] = {
        "target": "sbox",
        "assets_root": str(target_root),
        "vmdl": out.vmdl_path,
        "prefab": out.prefab_path,
        "ragdoll_prefab": out.ragdoll_prefab_path,
        "sequences": out.sequences,
        "sequence_checks": [asdict(c) for c in out.sequence_checks],
        "files": written,
    }
    doc["checks"] = checks
    doc["journal"] = journal.to_list()
    failed = [c for c in checks if c["state"] == "failed"]
    status["progress"] = "converted"
    status["quality"] = (
        "failed internal checks"
        if failed
        else ("incomplete input" if missing else "internal checks passed; target test not run")
    )
    doc["status"] = status
    return _finish(project, doc, started)


def _finish(project: Path, doc: dict, started: float) -> dict:
    from .report import render_markdown

    doc["duration_s"] = round(time.time() - started, 3)
    (project / "assets").mkdir(parents=True, exist_ok=True)
    (project / "reports").mkdir(parents=True, exist_ok=True)
    (project / "assets" / f"{doc['id']}.json").write_text(json.dumps(doc, indent=2, default=list) + "\n")
    (project / "reports" / f"{doc['id']}.md").write_text(render_markdown(doc))
    return doc
