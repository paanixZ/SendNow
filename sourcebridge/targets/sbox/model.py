"""Write a resolved Source 1 model as editable s&box source assets.

Output (all paths relative to the s&box project's Assets folder, below ``s1/``):
    s1/<model dir>/<name>/<name>_<bodypart>_<model>_lod<N>.smd   render meshes
    s1/<model dir>/<name>/<name>_hull<N>.smd                     collision hulls
    s1/<model dir>/<name>.vmdl                                   ModelDoc file
    s1/materials/<...>.vmat + PNG textures
    s1/prefabs/<model path>.prefab                               ready-to-place object

Node classes, key names and file headers are taken from Facepunch's shipped files
(templates/sbox/reference). ModelDoc compiles the .vmdl; SourceBridge never writes compiled
Source 2 resources.
"""

from __future__ import annotations

import copy
import json
import math
import posixpath
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ...formats.anim import decode_animation
from ...formats.binary import FormatError
from ...formats.mdl import StudioModel
from ...geometry import ModelGeometry, bake_pose, extract
from ...journal import Journal
from ...materials import alpha_as_gray, build_vmat, decode_vtf, encode_png, has_meaningful_alpha
from ...resolve import ResolvedModel
from ...safety import normalize_game_path
from ...transform import bone_world_matrices, mat34_apply, pose_world, quat_to_radian_euler
from .character import angle_between, attachment_nodes, build_animations, hitbox_nodes, joint_nodes
from .kv3 import dumps_modeldoc

ASSET_ROOT = "s1"


@dataclass
class OutputFile:
    path: str  # relative to Assets/
    data: bytes
    role: str


@dataclass
class SboxModelOutput:
    vmdl_path: str
    prefab_path: str | None
    files: list[OutputFile] = field(default_factory=list)
    mesh_names: list[str] = field(default_factory=list)
    mesh_files: dict[tuple[int, int, int], str] = field(default_factory=dict)  # (bodypart, model, lod)
    ragdoll_prefab_path: str | None = None
    geometry: dict[tuple[int, int, int], ModelGeometry] = field(default_factory=dict)  # what was written
    rest_pose: list | None = None  # engine rest pose baked into the bind pose, if any
    skeleton: list | None = None  # (pos, RadianEuler) per bone written as SMD bind pose
    extra: dict = field(default_factory=dict)  # outputs added by extensions (vehicle prefab, sounds)
    sequences: list[dict] = field(default_factory=list)
    sequence_checks: list = field(default_factory=list)  # character.SequenceCheck
    animated: bool = False
    hull_count: int = 0

    def add(self, path: str, data: bytes | str, role: str) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.files.append(OutputFile(path, data, role))


def _safe_name(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]+", "_", posixpath.splitext(posixpath.basename(s.replace("\\", "/")))[0])
    return s.strip("_").lower() or "part"


def _material_key(tex: str) -> str:
    return tex.replace("\\", "/").lstrip("/").lower()


def _skeleton_lines(mdl: StudioModel, skeleton=None) -> list[str]:
    out = ["version 1", "nodes"]
    for b in mdl.bones:
        out.append(f'{b.index} "{b.name}" {b.parent}')
    out += ["end", "skeleton", "time 0"]
    for b in mdl.bones:
        pos, rot = skeleton[b.index] if skeleton else (b.pos, b.rot)
        out.append(f"{b.index} {_f(pos[0])} {_f(pos[1])} {_f(pos[2])} {_f(rot[0])} {_f(rot[1])} {_f(rot[2])}")
    out += ["end", "triangles"]
    return out


def write_smd_mesh(mdl: StudioModel, geo: ModelGeometry, material_names: list[str], skeleton=None) -> str:
    out = _skeleton_lines(mdl, skeleton)
    for mesh in geo.meshes:
        mat = material_names[mesh.material_index] if mesh.material_index < len(material_names) else "missing"
        for tri in mesh.triangles:
            out.append(mat)
            for vi in tri:
                v = geo.vertices[vi]
                links = " ".join(f"{b} {_f(w)}" for b, w in zip(v.bones, v.weights, strict=True))
                out.append(
                    f"{v.bones[0]} {_f(v.position[0])} {_f(v.position[1])} {_f(v.position[2])} "
                    f"{_f(v.normal[0])} {_f(v.normal[1])} {_f(v.normal[2])} "
                    f"{_f(v.uv[0])} {_f(1.0 - v.uv[1])} {len(v.bones)} {links}"
                )
    out.append("end")
    return "\n".join(out) + "\n"


def write_smd_hull(mdl: StudioModel, bone: int, points, triangles, skeleton=None) -> str:
    out = _skeleton_lines(mdl, skeleton)
    for tri in triangles:
        pa, pb, pc = (points[i] for i in tri)
        n = _normal(pa, pb, pc)
        out.append("phy")
        for p in (pa, pb, pc):
            out.append(
                f"{bone} {_f(p[0])} {_f(p[1])} {_f(p[2])} {_f(n[0])} {_f(n[1])} {_f(n[2])} 0 0 1 {bone} 1"
            )
    out.append("end")
    return "\n".join(out) + "\n"


def _normal(a, b, c):
    u = [b[k] - a[k] for k in range(3)]
    w = [c[k] - a[k] for k in range(3)]
    n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
    ln = sum(x * x for x in n) ** 0.5 or 1.0
    return tuple(x / ln for x in n)


def _f(x: float) -> str:
    s = f"{x:.6f}"
    return "0.000000" if s == "-0.000000" else s


def engine_rest_pose(res: ResolvedModel, journal: Journal):
    """The pose the Source engine shows for a model that is not really animated.

    Non-static models always play a sequence; for a model whose sequences all have a single frame
    that frame (including studiomdl's root default rotation) is what players see, so it becomes the
    exported bind pose. Returns None when the bind pose already is that pose, for $staticprop
    models (geometry rotated at compile time) and for animated models (animations are exported).
    """
    mdl = res.mdl
    if mdl.is_static_prop or not mdl.sequences or not mdl.anim_descs:
        return None
    if any(a.num_frames > 1 for a in mdl.anim_descs):
        return None
    seq = mdl.sequences[0]
    if not seq.anim_indices or seq.anim_indices[0] >= len(mdl.anim_descs):
        return None
    try:
        anim = decode_animation(mdl, res.files[res.path], mdl.anim_descs[seq.anim_indices[0]])
    except FormatError as exc:
        journal.error(res.path, "rest pose", f"default sequence could not be decoded: {exc}")
        return None
    pose = anim.frames[0]
    moved = [
        mdl.bones[i].name
        for i, (p, q) in enumerate(pose)
        if max(abs(a - b) for a, b in zip(p, mdl.bones[i].pos, strict=True)) > 1e-3
        or angle_between(q, mdl.bones[i].quat) > 1e-4
    ]
    if not moved:
        return None
    journal.converted(
        res.path,
        "rest pose",
        f"the engine shows sequence '{seq.label}' frame 0, not the bind pose (bones differing: "
        f"{', '.join(moved[:6])}); baked into the exported bind pose so the model looks as in Source",
    )
    return pose


def build_sbox_model(res: ResolvedModel, journal: Journal) -> SboxModelOutput:
    mdl, vvd, vtx = res.mdl, res.vvd, res.vtx
    if mdl is None or vvd is None or vtx is None:
        raise ValueError("model is incomplete (need .mdl, .vvd and .vtx)")
    stem = res.path[:-4]  # models/foo/bar
    name = _safe_name(stem)
    model_dir = f"{ASSET_ROOT}/{stem}"
    vmdl_path = f"{ASSET_ROOT}/{stem}.vmdl"
    subj = res.path
    out = SboxModelOutput(vmdl_path, None)
    out.rest_pose = engine_rest_pose(res, journal)
    bind = bone_world_matrices(mdl.bones)
    pose_w = pose_world(mdl.bones, out.rest_pose) if out.rest_pose else None
    if out.rest_pose:
        out.skeleton = [(p, quat_to_radian_euler(q)) for p, q in out.rest_pose]

    # ---- materials ----
    mat_names = [_safe_name(t) for t in mdl.textures]
    vmat_for_texture: dict[int, str] = {}
    written_textures: dict[str, dict[str, str]] = {}
    for ti, tex in enumerate(mdl.textures):
        info = res.materials.get(ti)
        if info is None or info.error:
            journal.error(
                subj, f"material {tex}", "missing or unreadable; ModelDoc will show an error material"
            )
            continue
        vmat_rel = f"{ASSET_ROOT}/{info.path[:-4]}.vmat"
        roles: dict[str, str] = {}
        base = info.textures.get("$basetexture")
        if base and base in res.textures:
            roles.update(_texture_outputs(res, base, out, journal, info.path, written_textures))
        elif base:
            journal.error(info.path, "$basetexture", f"{base} missing")
        bump = info.textures.get("$bumpmap") or info.textures.get("$normalmap")
        if bump and bump in res.textures:
            roles["normal"] = _texture_outputs(
                res, bump, out, journal, info.path, written_textures, normal=True
            )["color"]
        for param in info.textures:
            if param not in ("$basetexture", "$bumpmap", "$normalmap"):
                journal.lost(info.path, param, "texture parameter without s&box mapping (original archived)")
        vmat = build_vmat(info, roles, journal, info.path)
        out.add(vmat_rel, vmat, "material")
        vmat_for_texture[ti] = vmat_rel

    # ---- render meshes (all LODs present in the VTX) ----
    render_nodes = []
    lod_groups: dict[int, list[str]] = {}
    bodygroup_meshes: dict[tuple[int, int], list[str]] = {}
    num_lods = max(1, vtx.num_lods)
    switch_points: dict[int, float] = {}
    for lod in range(num_lods):
        geos = extract(mdl, vvd, vtx, lod)
        for geo in geos:
            if geo.error:
                journal.error(subj, f"{geo.body_part}/{geo.model_name} lod{lod}", geo.error)
            if not geo.meshes:
                continue
            if pose_w is not None:
                geo = bake_pose(geo, bind, pose_w)
            out.geometry[(geo.body_part_index, geo.model_index, lod)] = geo
            mesh_name = f"{name}_{_safe_name(geo.body_part)}_{_safe_name(geo.model_name)}_lod{lod}"
            smd_rel = f"{model_dir}/{mesh_name}.smd"
            out.add(smd_rel, write_smd_mesh(mdl, geo, mat_names, out.skeleton), "render-mesh")
            out.mesh_names.append(mesh_name)
            out.mesh_files[(geo.body_part_index, geo.model_index, lod)] = smd_rel
            render_nodes.append(
                {
                    "_class": "RenderMeshFile",
                    "name": mesh_name,
                    "filename": smd_rel,
                    "import_translation": [0.0, 0.0, 0.0],
                    "import_rotation": [0.0, 0.0, 0.0],
                    "import_scale": 1.0,
                    "align_origin_x_type": "None",
                    "align_origin_y_type": "None",
                    "align_origin_z_type": "None",
                    "parent_bone": "",
                    "import_filter": {"exclude_by_default": False, "exception_list": []},
                }
            )
            lod_groups.setdefault(lod, []).append(mesh_name)
            bodygroup_meshes.setdefault((geo.body_part_index, geo.model_index), []).append(mesh_name)
            try:
                switch_points[lod] = vtx.body_parts[geo.body_part_index][geo.model_index][lod].switch_point
            except IndexError:
                pass
    journal.preserved(subj, "geometry LOD0", "vertices, normals, UVs, weights and triangles written to SMD")
    if num_lods > 1:
        journal.converted(subj, "LODs", f"{num_lods} LODs as LODGroups; switch points copied from VTX")
    if vvd.tangents:
        journal.lost(subj, "tangents", "VVD tangents not written (SMD has none); ModelDoc recomputes them")

    children: list[dict] = [{"_class": "RenderMeshList", "children": render_nodes}]
    if num_lods > 1:
        children.append(
            {
                "_class": "LODGroupList",
                "children": [
                    {
                        "_class": "LODGroup",
                        "name": f"LOD{lod}",
                        "switch_threshold": float(max(0.0, switch_points.get(lod, 0.0))),
                        "meshes": meshes,
                    }
                    for lod, meshes in sorted(lod_groups.items())
                ],
            }
        )

    # ---- body groups ----
    groups = []
    for bpi, bp in enumerate(mdl.body_parts):
        if len(bp.models) < 2:
            continue
        choices = []
        for mi, sub in enumerate(bp.models):
            choices.append(
                {
                    "_class": "BodyGroupChoice",
                    "name": sub.name or f"choice{mi}",
                    "meshes": bodygroup_meshes.get((bpi, mi), []),
                }
            )
        groups.append({"_class": "BodyGroup", "name": bp.name, "children": choices, "hidden_in_tools": False})
    if groups:
        children.append({"_class": "BodyGroupList", "children": groups})
        journal.converted(subj, "bodygroups", f"{len(groups)} body groups with their choices")

    # ---- material groups (skins) ----
    def remaps(family: list[int]) -> list[dict]:
        out_r = []
        for slot, ti in enumerate(family):
            if slot >= len(mdl.textures) or ti not in vmat_for_texture:
                continue
            out_r.append({"from": f"{mat_names[slot]}.vmat", "to": vmat_for_texture[ti]})
        return out_r

    families = mdl.skin_families or [list(range(len(mdl.textures)))]
    mg_children = [
        {
            "_class": "DefaultMaterialGroup",
            "remaps": remaps(families[0]),
            "use_global_default": False,
            "global_default_material": "",
        }
    ]
    for fi, fam in enumerate(families[1:], start=1):
        mg_children.append({"_class": "MaterialGroup", "name": f"skin{fi}", "remaps": remaps(fam)})
    children.append({"_class": "MaterialGroupList", "children": mg_children})
    journal.converted(
        subj,
        "skins",
        f"{len(families)} skin families -> DefaultMaterialGroup + {len(families) - 1} MaterialGroup",
    )

    # ---- skeleton features: animations, attachments, hitboxes ----
    trivial = all(a.num_frames <= 1 for a in mdl.anim_descs)
    if mdl.anim_descs and not trivial:
        ani_path = normalize_game_path(mdl.anim_block_name) if mdl.anim_block_name else None
        cres = build_animations(
            mdl,
            res.files[res.path],
            res.files.get(ani_path) if ani_path else None,
            model_dir,
            name,
            out,
            journal,
            subj,
        )
        children += cres.nodes
        out.sequences = cres.sequences
        out.sequence_checks = cres.checks
        out.animated = bool(cres.nodes)
    elif mdl.anim_descs:
        journal.preserved(
            subj,
            "sequences",
            "only single-frame sequences: the pose they show is the exported rest pose"
            + (" (baked, see 'rest pose')" if out.rest_pose else ""),
        )
    children += attachment_nodes(mdl, journal, subj)
    children += hitbox_nodes(mdl, journal, subj)

    # ---- physics ----
    if res.phy is not None:
        hull_nodes = _physics(res, model_dir, name, out, journal)
        if hull_nodes:
            children.append({"_class": "PhysicsShapeList", "children": hull_nodes})
        if len(res.phy.solids) > 1:
            children += joint_nodes(mdl, res.phy, journal, subj)
    else:
        journal.preserved(subj, "collision", "source model has no .phy; none generated")

    for u in mdl.unsupported:
        journal.lost(subj, "mdl", u)
    if mdl.keyvalues:
        journal.lost(
            subj, "model keyvalues", "not mapped yet; kept in AssetDocument extras and original .mdl"
        )

    ragdoll = res.phy is not None and len(res.phy.solids) > 1
    prop_physics = res.phy is not None and not ragdoll
    root = {
        "_class": "RootNode",
        "children": children,
        "model_archetype": "physics_prop_model" if prop_physics else "",
        "primary_associated_entity": "prop_physics" if prop_physics else "",
        "anim_graph_name": "",
        "base_model_name": "",
    }
    out.add(vmdl_path, dumps_modeldoc(root), "modeldoc")
    out.prefab_path = f"{ASSET_ROOT}/prefabs/{stem}.prefab"
    if out.animated or ragdoll:
        first = out.sequences[0]["name"] if out.sequences else None
        out.add(out.prefab_path, _skinned_prefab(vmdl_path, name, first), "prefab")
        if ragdoll:
            out.ragdoll_prefab_path = f"{ASSET_ROOT}/prefabs/{stem}_ragdoll.prefab"
            out.add(out.ragdoll_prefab_path, _ragdoll_prefab(vmdl_path, name), "prefab")
    else:
        out.add(out.prefab_path, _prefab(res, vmdl_path, name), "prefab")
    return out


def _texture_outputs(res, vtf_path, out, journal, subject, cache, normal=False) -> dict[str, str]:
    if vtf_path in cache:
        return cache[vtf_path]
    roles: dict[str, str] = {}
    try:
        w, h, rgba, info = decode_vtf(res.textures[vtf_path])
    except Exception as exc:
        journal.error(subject, vtf_path, f"VTF could not be decoded: {exc}")
        cache[vtf_path] = roles
        return roles
    base = f"{ASSET_ROOT}/{vtf_path[:-4]}"
    color_rel = f"{base}{'_normal' if normal else '_color'}.png"
    out.add(color_rel, encode_png(w, h, rgba), "texture")
    roles["color"] = color_rel
    if info["frames"] > 1 or info["faces"] > 1:
        journal.lost(
            subject,
            vtf_path,
            f"only frame 0/face 0 of {info['frames']} frames, {info['faces']} faces exported",
        )
    if not normal and has_meaningful_alpha(rgba):
        trans_rel = f"{base}_trans.png"
        out.add(trans_rel, encode_png(w, h, alpha_as_gray(rgba)), "texture")
        roles["translucency"] = trans_rel
        roles["selfillum"] = trans_rel
    cache[vtf_path] = roles
    return roles


def _bone_render_boxes(out: SboxModelOutput) -> dict[int, tuple[list[float], list[float]]]:
    """Model-space AABB of the written LOD0 vertices per strongest bone; key -1 is the whole model."""
    boxes: dict[int, tuple[list[float], list[float]]] = {}
    for (_bp, _m, lod), geo in out.geometry.items():
        if lod != 0:
            continue
        used = {i for m in geo.meshes for t in m.triangles for i in t}
        for i in used:
            v = geo.vertices[i]
            b = v.bones[max(range(len(v.weights)), key=lambda k: v.weights[k])]
            for key in (b, -1):
                lo, hi = boxes.setdefault(key, ([math.inf] * 3, [-math.inf] * 3))
                for k in range(3):
                    lo[k] = min(lo[k], v.position[k])
                    hi[k] = max(hi[k], v.position[k])
    return boxes


def _iou(a, b) -> float:
    inter = 1.0
    for k in range(3):
        d = min(a[1][k], b[1][k]) - max(a[0][k], b[0][k])
        if d <= 0:
            return 0.0
        inter *= d
    va = math.prod(max(1e-6, a[1][k] - a[0][k]) for k in range(3))
    vb = math.prod(max(1e-6, b[1][k] - b[0][k]) for k in range(3))
    return inter / (va + vb - inter)


def _aabb(pts):
    return [min(p[k] for p in pts) for k in range(3)], [max(p[k] for p in pts) for k in range(3)]


def _physics(
    res: ResolvedModel, model_dir: str, name: str, out: SboxModelOutput, journal: Journal
) -> list[dict]:
    mdl, phy = res.mdl, res.phy
    world = bone_world_matrices(mdl.bones)
    bone_by_name = {b.name.lower(): b.index for b in mdl.bones}
    ragdoll = len(phy.solids) > 1
    if out.rest_pose:
        world = pose_world(mdl.bones, out.rest_pose)
    detect = ragdoll or not mdl.is_static_prop
    render_boxes = _bone_render_boxes(out) if detect else {}
    spaces = {
        "bone-local": lambda b, p: mat34_apply(world[b], p),
        "model": lambda b, p: p,
        "model rotated by studiomdl default Rz(90)": lambda b, p: (p[1], -p[0], p[2]),
    }
    convert = spaces["model"]
    if detect:
        # One decision for the whole model: every solid of a .phy uses the same convention.
        totals = dict.fromkeys(spaces, 0.0)
        compared = 0
        for solid in phy.solids:
            b = bone_by_name.get(phy.solid_info(solid.index).get("name", "").lower())
            if not ragdoll:
                b = -1 if b is None else b
            if b is None or b not in render_boxes:
                continue
            pts = [p for h in solid.hulls for p in h.points]
            for k, f in spaces.items():
                totals[k] += _iou(_aabb([f(max(b, 0), p) for p in pts]), render_boxes[b])
            compared += 1
        if compared == 0:
            chosen = "bone-local"
            journal.estimated(
                res.path,
                "collision space",
                "no solid could be compared with its bone's mesh; assumed bone-local (Source ragdoll convention)",
            )
        else:
            chosen = max(totals, key=totals.get)
            detail = ", ".join(f"{k}: {v / compared:.2f}" for k, v in totals.items())
            state = journal.converted if totals[chosen] / compared >= 0.5 else journal.approximated
            state(
                res.path,
                "collision space",
                f"detected '{chosen}' from mean overlap of {compared} solids with their bones' mesh ({detail})",
            )
        convert = spaces[chosen]
    nodes = []
    hull_i = 0
    for solid in phy.solids:
        info = phy.solid_info(solid.index)
        bone_name = info.get("name", "")
        bone = bone_by_name.get(bone_name.lower(), 0)
        surface = info.get("surfaceprop", mdl.surface_prop or "default")
        for hull in solid.hulls:
            pts = [convert(bone, p) for p in hull.points]
            hull_name = f"{name}_hull{hull_i}"
            rel = f"{model_dir}/{hull_name}.smd"
            out.add(rel, write_smd_hull(mdl, bone, pts, hull.triangles, out.skeleton), "collision-hull")
            nodes.append(
                {
                    "_class": "PhysicsHullFile",
                    "name": hull_name,
                    "parent_bone": mdl.bones[bone].name if ragdoll else "",
                    "surface_prop": surface,
                    "collision_tags": "solid",
                    "recenter_on_parent_bone": False,
                    "offset_origin": [0.0, 0.0, 0.0],
                    "offset_angles": [0.0, 0.0, 0.0],
                    "align_origin_x_type": "None",
                    "align_origin_y_type": "None",
                    "align_origin_z_type": "None",
                    "filename": rel,
                    "import_scale": 1.0,
                    "faceMergeAngle": 10.0,
                    "maxHullVertices": 0,
                    "import_mode": "SingleHull",
                    "optimization_algorithm": "QEM",
                    "import_filter": {"exclude_by_default": False, "exception_list": []},
                }
            )
            hull_i += 1
    out.hull_count = hull_i
    journal.converted(
        res.path,
        "collision",
        f"{len(phy.solids)} solid(s), {hull_i} convex hull(s) as PhysicsHullFile (one SMD per hull, SingleHull)",
    )
    mass = phy.total_mass
    if mass is not None:
        journal.converted(res.path, "mass", f"{mass:g} kg -> Rigidbody.MassOverride in the prefab")
    for b in phy.blocks:
        if b.kind == "solid":
            for k in ("damping", "rotdamping", "inertia"):
                if k in b.values and float(b.values[k]) not in (0.0, 1.0):
                    journal.lost(res.path, f"solid {b.values.get('index')} {k}", b.values[k])
    return nodes


def _guid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "sourcebridge:" + seed))


def _templates() -> dict:
    path = Path(__file__).with_name("templates") / "prefab_templates.json"
    return json.loads(path.read_text(encoding="utf-8"))


def component(type_name: str, seed: str, **overrides) -> dict:
    """Clone a component exactly as it appears in a shipped Facepunch file, then override fields."""
    comp = copy.deepcopy(_templates()["components"][type_name])
    for k, v in overrides.items():
        if k not in comp:
            raise KeyError(f"{type_name} template has no field {k!r}")
        comp[k] = v
    comp["__guid"] = _guid(seed + type_name)
    return comp


def prefab_json(name: str, seed: str, components: list[dict], children: list[dict] | None = None) -> str:
    tpl = copy.deepcopy(_templates()["prefab"])
    root = tpl["RootObject"]
    root["__guid"] = _guid(seed + "root")
    root["Name"] = name
    root["Components"] = components
    root["Children"] = children or []
    tpl["ShowInMenu"] = True
    tpl["MenuPath"] = "SourceBridge"
    return json.dumps(tpl, indent=2) + "\n"


def _prefab(res: ResolvedModel, vmdl_path: str, name: str) -> str:
    model = vmdl_path
    comps = [component("Sandbox.ModelRenderer", vmdl_path, Model=model)]
    if res.phy is not None:
        mass = res.phy.total_mass
        comps.append(component("Sandbox.ModelCollider", vmdl_path, Model=model))
        comps.append(component("Sandbox.Rigidbody", vmdl_path, MassOverride=float(mass) if mass else 0))
    return prefab_json(name, vmdl_path, comps)


def _skinned_prefab(vmdl_path: str, name: str, sequence: str | None) -> str:
    renderer = component(
        "Sandbox.SkinnedModelRenderer",
        vmdl_path,
        Model=vmdl_path,
        UseAnimGraph=False,
        Sequence={"Name": sequence, "Looping": True, "Blending": False},
        CreateAttachments=True,
    )
    return prefab_json(name, vmdl_path, [renderer])


def _ragdoll_prefab(vmdl_path: str, name: str) -> str:
    seed = vmdl_path + "ragdoll"
    root_guid = _guid(seed + "root")
    renderer = component("Sandbox.SkinnedModelRenderer", seed, Model=vmdl_path, UseAnimGraph=False)
    physics = component(
        "Sandbox.ModelPhysics",
        seed,
        Model=vmdl_path,
        Renderer={
            "_type": "component",
            "component_id": renderer["__guid"],
            "go": root_guid,
            "component_type": "SkinnedModelRenderer",
        },
        Bodies=[],
        Joints=[],
        PhysicsWereCreated=False,
        Locking={"X": False, "Y": False, "Z": False, "Pitch": False, "Yaw": False, "Roll": False},
        MotionEnabled=True,
    )
    return prefab_json(name + "_ragdoll", seed, [renderer, physics])
