import io
import json
import math
import sys

import pytest
from conftest import ROOT, read

from sourcebridge.formats.anim import decode_animation
from sourcebridge.formats.binary import FormatError
from sourcebridge.formats.mdl import read_mdl
from sourcebridge.formats.vtx import read_vtx
from sourcebridge.formats.vvd import read_vvd
from sourcebridge.geometry import extract
from sourcebridge.pipeline import import_model
from sourcebridge.sources import Mount, open_source
from sourcebridge.targets.sbox.kv3 import parse_kv3
from sourcebridge.transform import (
    bone_world_matrices,
    euler_to_quat,
    mat34_apply,
    mat34_inverse,
    mat34_mul,
    pose_world,
    quat_mul,
)

sys.path.insert(0, str(ROOT / "fixtures"))
import generate_sources as authored  # noqa: E402

MAN = "models/sourcebridge/mannequin"
RZ90 = euler_to_quat((0.0, 0.0, math.pi / 2))


def _smd_euler(bf):
    """srctools names the SMD rotation columns x, y, z as pitch, yaw, roll (degrees)."""
    return (bf.rotation.pitch, bf.rotation.yaw, bf.rotation.roll)


def _angle(a, b):
    return 2 * math.acos(min(1.0, abs(sum(x * y for x, y in zip(a, b, strict=True)))))


@pytest.fixture(scope="module")
def mdl_data():
    return read(MAN + ".mdl")


@pytest.fixture(scope="module")
def mdl(mdl_data):
    return read_mdl(mdl_data)


@pytest.fixture(scope="module")
def doc(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("man")
    gma = ROOT / "fixtures/build/sourcebridge_fixtures.gma"
    return import_model(Mount([open_source(gma)]), MAN + ".mdl", tmp / "proj"), tmp / "proj/sbox/Assets"


def test_skeleton_matches_compiler_bind_pose(mdl):
    """Our bone math reproduces the compiler's poseToBone matrices."""
    world = bone_world_matrices(mdl.bones)
    for b, w in zip(mdl.bones, world, strict=True):
        for x, y in zip(mat34_inverse(b.pose_to_bone), w, strict=True):
            assert abs(x - y) < 1e-4, b.name
    assert [b.name for b in mdl.bones] == [n for n, *_ in authored.MANNEQUIN_BONES]


@pytest.mark.parametrize("seq,kind,frames", [(0, "idle", 20), (1, "walk", 30)])
def test_animation_decodes_to_authored_keyframes(mdl, mdl_data, seq, kind, frames):
    """Decoded frames equal the authored SMD frames, with two documented compiler rules:
    root bones carry studiomdl's default rotation Rz(90), and on looping sequences the last
    frame's rotation is replaced by the first one."""
    anim = decode_animation(mdl, mdl_data, mdl.anim_descs[seq])
    src = authored._anim_frames(kind, frames)
    assert len(anim.frames) == frames and anim.looping and anim.fps == 30
    for f in range(frames):
        rot_src = src[0] if f == frames - 1 else src[f]
        for bi, pos, _r in src[f]:
            dp, dq = anim.frames[f][bi]
            assert max(abs(a - b) for a, b in zip(pos, dp, strict=True)) < 0.01, (kind, f, bi)
        for bi, _p, rot in rot_src:
            q = euler_to_quat(rot)
            if mdl.bones[bi].parent < 0:
                q = quat_mul(RZ90, q)
            assert _angle(q, anim.frames[f][bi][1]) < math.radians(0.1), (kind, f, mdl.bones[bi].name)


def test_truncated_animation_data_is_reported(mdl, mdl_data):
    desc = mdl.anim_descs[1]
    cut = desc.desc_offset + desc.anim_index + 20
    with pytest.raises(FormatError):
        decode_animation(mdl, mdl_data[:cut], desc)


def test_animation_in_external_block_needs_ani(mdl, mdl_data):
    import dataclasses

    desc = dataclasses.replace(mdl.anim_descs[0], anim_block=1)
    with pytest.raises(FormatError, match=r"\.ani"):
        decode_animation(mdl, mdl_data, desc)


def test_character_import(doc):
    d, _assets = doc
    assert d["kind"] == "character"
    assert d["status"]["quality"] == "internal checks passed; target test not run"
    rig = d["rig"]
    assert rig["mode"] == "preserve" and rig["convention"] == "valvebiped" and rig["humanoid"]
    assert rig["missing_required"] == []
    assert all(c["passed"] for c in rig["structure_checks"])
    assert [s["name"] for s in d["outputs"]["sequences"]] == ["idle", "walk"]
    assert d["outputs"]["ragdoll_prefab"]
    states = {(e["field"], e["state"]) for e in d["journal"]}
    assert ("hitboxes", "approximated") in states
    assert ("ragdoll constraints", "approximated") in states
    assert ("attachments", "converted") in states
    assert not [e for e in d["journal"] if e["state"] == "error"]


def _nodes(tree, cls):
    out = []
    if isinstance(tree, dict):
        if tree.get("_class") == cls:
            out.append(tree)
        for v in tree.values():
            out += _nodes(v, cls)
    elif isinstance(tree, list):
        for v in tree:
            out += _nodes(v, cls)
    return out


def test_character_vmdl_content(doc, mdl):
    d, assets = doc
    tree = parse_kv3((assets / d["outputs"]["vmdl"]).read_text())
    assert [n["name"] for n in _nodes(tree, "AnimFile")] == ["idle", "walk"]
    assert {n["name"]: n["parent_bone"] for n in _nodes(tree, "Attachment")} == {
        "eyes": "ValveBiped.Bip01_Head1",
        "anim_attachment_RH": "ValveBiped.Bip01_R_Hand",
    }
    eyes = next(n for n in _nodes(tree, "Attachment") if n["name"] == "eyes")
    assert eyes["relative_origin"] == pytest.approx([5.0, 0.0, 5.0], abs=1e-3)
    assert len(_nodes(tree, "HitboxCapsule")) == 5
    assert len(_nodes(tree, "PhysicsHullFile")) == 11
    joints = _nodes(tree, "PhysicsJointRevolute") + _nodes(tree, "PhysicsJointConical")
    assert len(joints) == 10
    calf = next(j for j in joints if j["child_body"] == "ValveBiped.Bip01_L_Calf")
    assert calf["_class"] == "PhysicsJointRevolute" and (calf["min_angle"], calf["max_angle"]) == (0.0, 140.0)
    bodygroups = _nodes(tree, "BodyGroup")
    assert [(g["name"], len(g["children"])) for g in bodygroups] == [("head", 2)]


def test_animation_smd_round_trip(doc, mdl, mdl_data):
    """The exported animation SMD, read with srctools, reproduces the decoded poses."""
    import srctools.smd as smd

    d, assets = doc
    anim = decode_animation(mdl, mdl_data, mdl.anim_descs[1])
    f = next(x for x in d["outputs"]["files"] if x["path"].endswith("_anim_walk.smd"))
    mesh = smd.Mesh.parse_smd(io.BytesIO((assets / f["path"]).read_bytes()))
    assert len(mesh.animation) == len(anim.frames)
    for fi, frame in mesh.animation.items():
        for bf in frame:
            p, q = anim.frames[fi][mdl.bones[[b.name for b in mdl.bones].index(bf.bone.name)].index]
            assert max(abs(a - b) for a, b in zip(bf.position, p, strict=True)) < 1e-4
            r = _smd_euler(bf)
            assert _angle(euler_to_quat(tuple(math.radians(x) for x in r)), q) < 1e-3


def _skin(verts, bind, pose):
    """Linear blend skinning: model-space vertex positions for a pose."""
    out = []
    for v in verts:
        acc = [0.0, 0.0, 0.0]
        for b, w in zip(v.bones, v.weights, strict=True):
            m = mat34_mul(pose[b], mat34_inverse(bind[b]))
            p = mat34_apply(m, v.position)
            for k in range(3):
                acc[k] += w * p[k]
        out.append(acc)
    return out


def test_deformation_matches_original_at_every_frame(doc, mdl, mdl_data):
    """Skin the ORIGINAL mesh (VVD/VTX) with the ORIGINAL animation and our EXPORTED mesh + animation
    SMDs (parsed by srctools); every vertex must land in the same place."""
    import srctools.smd as smd

    d, assets = doc
    vvd, vtx = read_vvd(read(MAN + ".vvd")), read_vtx(read(MAN + ".dx90.vtx"))
    body = next(g for g in extract(mdl, vvd, vtx) if g.body_part == "body")
    anim = decode_animation(mdl, mdl_data, mdl.anim_descs[1])
    bind = bone_world_matrices(mdl.bones)

    ref_file = next(f for f in d["outputs"]["files"] if f["path"].endswith("_body_mannequin_ref_lod0.smd"))
    ref = smd.Mesh.parse_smd(io.BytesIO((assets / ref_file["path"]).read_bytes()))
    anim_file = next(f for f in d["outputs"]["files"] if f["path"].endswith("_anim_walk.smd"))
    exported_anim = smd.Mesh.parse_smd(io.BytesIO((assets / anim_file["path"]).read_bytes()))
    names = [b.name for b in mdl.bones]
    exported_verts = []
    for tri in ref.triangles:
        for v in (tri.point1, tri.point2, tri.point3):
            exported_verts.append((tuple(v.pos), [(names.index(b.name), w) for b, w in v.links]))

    for f in (0, 7, 15, 29):
        pose = pose_world(mdl.bones, anim.frames[f])
        original = _skin(body.vertices, bind, pose)
        exp_pose = []
        for b in mdl.bones:
            bf = next(x for x in exported_anim.animation[f] if x.bone.name == b.name)
            q = euler_to_quat(tuple(math.radians(x) for x in _smd_euler(bf)))
            exp_pose.append((tuple(bf.position), q))
        epw = pose_world(mdl.bones, exp_pose)
        orig_set = sorted(tuple(round(c, 2) for c in p) for p in original)
        exp_positions = []
        for pos, links in exported_verts:
            acc = [0.0, 0.0, 0.0]
            for b, w in links:
                p = mat34_apply(mat34_mul(epw[b], mat34_inverse(bind[b])), pos)
                for k in range(3):
                    acc[k] += w * p[k]
            exp_positions.append(tuple(round(c, 2) for c in acc))
        missing = set(exp_positions) - set(orig_set)
        close = all(
            min(max(abs(a - b) for a, b in zip(e, o, strict=True)) for o in orig_set) < 0.05 for e in missing
        )
        assert close, f"frame {f}: exported deformation differs from the original"


def test_prefabs_use_real_component_fields(doc):
    d, assets = doc
    ref = json.loads((ROOT / "sourcebridge/targets/sbox/templates/prefab_templates.json").read_text())
    for key in ("prefab", "ragdoll_prefab"):
        prefab = json.loads((assets / d["outputs"][key]).read_text())
        for comp in prefab["RootObject"]["Components"]:
            assert set(comp) == set(ref["components"][comp["__type"]])
    rag = json.loads((assets / d["outputs"]["ragdoll_prefab"]).read_text())
    comps = {c["__type"]: c for c in rag["RootObject"]["Components"]}
    ref_id = comps["Sandbox.ModelPhysics"]["Renderer"]
    assert ref_id["component_id"] == comps["Sandbox.SkinnedModelRenderer"]["__guid"]
    assert ref_id["go"] == rag["RootObject"]["__guid"]
