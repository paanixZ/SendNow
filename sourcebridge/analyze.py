"""Explainable asset classification. Every decision carries the evidence that produced it."""

from __future__ import annotations

from dataclasses import dataclass, field

from .formats.mdl import StudioModel

HUMANOID_MARKERS = {
    "valvebiped.bip01_pelvis", "valvebiped.bip01_spine", "valvebiped.bip01_head1",
    "valvebiped.bip01_l_thigh", "valvebiped.bip01_r_thigh", "valvebiped.bip01_l_upperarm",
    "valvebiped.bip01_r_upperarm",
}  # fmt: skip
VEHICLE_ATTACHMENTS = {
    "vehicle_driver_eyes",
    "vehicle_feet_passenger0",
    "vehicle_engine",
    "vehicle_driver_exit",
}


@dataclass
class Classification:
    kind: str  # prop | character | vehicle | unknown
    confidence: float  # heuristic, not proof
    evidence: list[str] = field(default_factory=list)


def classify(mdl: StudioModel, has_vehicle_script: bool = False) -> Classification:
    bones = {b.name.lower() for b in mdl.bones}
    atts = {a.name.lower() for a in mdl.attachments}
    ev: list[str] = []
    wheel_bones = sorted(b for b in bones if "wheel" in b)
    veh_atts = sorted(atts & VEHICLE_ATTACHMENTS)
    if has_vehicle_script or veh_atts or len(wheel_bones) >= 3:
        if has_vehicle_script:
            ev.append("a vehicle script references this model")
        if veh_atts:
            ev.append("vehicle attachments: " + ", ".join(veh_atts))
        if wheel_bones:
            ev.append(f"{len(wheel_bones)} wheel bones: " + ", ".join(wheel_bones[:6]))
        score = min(
            1.0, 0.4 * bool(has_vehicle_script) + 0.3 * bool(veh_atts) + 0.3 * (len(wheel_bones) >= 3)
        )
        return Classification("vehicle", round(score, 2), ev)
    hum = bones & HUMANOID_MARKERS
    if len(hum) >= 4:
        ev.append(f"{len(hum)}/{len(HUMANOID_MARKERS)} ValveBiped marker bones present")
        if mdl.sequences:
            ev.append(f"{len(mdl.sequences)} sequences")
        return Classification("character", round(len(hum) / len(HUMANOID_MARKERS), 2), ev)
    if mdl.is_static_prop or len(mdl.bones) <= 1:
        ev.append("$staticprop flag set" if mdl.is_static_prop else "single bone")
        return Classification("prop", 0.9 if mdl.is_static_prop else 0.6, ev)
    ev.append(f"{len(mdl.bones)} bones, no known humanoid or vehicle markers; not forced into a template")
    return Classification("unknown", 0.0, ev)


# ------------------------------------------------------------------ rig analysis

CANONICAL = [
    "hips", "spine", "chest", "upperChest", "neck", "head",
    "leftShoulder", "leftUpperArm", "leftLowerArm", "leftHand",
    "rightShoulder", "rightUpperArm", "rightLowerArm", "rightHand",
    "leftUpperLeg", "leftLowerLeg", "leftFoot", "leftToes",
    "rightUpperLeg", "rightLowerLeg", "rightFoot", "rightToes",
]  # fmt: skip
REQUIRED = {"hips", "spine", "head", "leftUpperArm", "leftLowerArm", "leftHand", "rightUpperArm",
            "rightLowerArm", "rightHand", "leftUpperLeg", "leftLowerLeg", "leftFoot", "rightUpperLeg",
            "rightLowerLeg", "rightFoot"}  # fmt: skip

# Naming conventions, lower-case bone name -> canonical slot. Sources: Valve's ValveBiped
# (HL2/GMod player and NPC models), s&box Citizen (sbox-public citizen.vmdl), Mixamo.
NAMING = {
    "valvebiped": {
        "valvebiped.bip01_pelvis": "hips", "valvebiped.bip01_spine": "spine",
        "valvebiped.bip01_spine1": "chest", "valvebiped.bip01_spine2": "upperChest",
        "valvebiped.bip01_neck1": "neck", "valvebiped.bip01_head1": "head",
        "valvebiped.bip01_l_clavicle": "leftShoulder", "valvebiped.bip01_l_upperarm": "leftUpperArm",
        "valvebiped.bip01_l_forearm": "leftLowerArm", "valvebiped.bip01_l_hand": "leftHand",
        "valvebiped.bip01_r_clavicle": "rightShoulder", "valvebiped.bip01_r_upperarm": "rightUpperArm",
        "valvebiped.bip01_r_forearm": "rightLowerArm", "valvebiped.bip01_r_hand": "rightHand",
        "valvebiped.bip01_l_thigh": "leftUpperLeg", "valvebiped.bip01_l_calf": "leftLowerLeg",
        "valvebiped.bip01_l_foot": "leftFoot", "valvebiped.bip01_l_toe0": "leftToes",
        "valvebiped.bip01_r_thigh": "rightUpperLeg", "valvebiped.bip01_r_calf": "rightLowerLeg",
        "valvebiped.bip01_r_foot": "rightFoot", "valvebiped.bip01_r_toe0": "rightToes",
    },
    "citizen": {
        "pelvis": "hips", "spine_0": "spine", "spine_1": "chest", "spine_2": "upperChest",
        "neck_0": "neck", "head": "head",
        "clavicle_l": "leftShoulder", "arm_upper_l": "leftUpperArm", "arm_lower_l": "leftLowerArm", "hand_l": "leftHand",
        "clavicle_r": "rightShoulder", "arm_upper_r": "rightUpperArm", "arm_lower_r": "rightLowerArm", "hand_r": "rightHand",
        "leg_upper_l": "leftUpperLeg", "leg_lower_l": "leftLowerLeg", "ankle_l": "leftFoot", "ball_l": "leftToes",
        "leg_upper_r": "rightUpperLeg", "leg_lower_r": "rightLowerLeg", "ankle_r": "rightFoot", "ball_r": "rightToes",
    },
    "mixamo": {
        "mixamorig:hips": "hips", "mixamorig:spine": "spine", "mixamorig:spine1": "chest",
        "mixamorig:spine2": "upperChest", "mixamorig:neck": "neck", "mixamorig:head": "head",
        "mixamorig:leftshoulder": "leftShoulder", "mixamorig:leftarm": "leftUpperArm",
        "mixamorig:leftforearm": "leftLowerArm", "mixamorig:lefthand": "leftHand",
        "mixamorig:rightshoulder": "rightShoulder", "mixamorig:rightarm": "rightUpperArm",
        "mixamorig:rightforearm": "rightLowerArm", "mixamorig:righthand": "rightHand",
        "mixamorig:leftupleg": "leftUpperLeg", "mixamorig:leftleg": "leftLowerLeg",
        "mixamorig:leftfoot": "leftFoot", "mixamorig:lefttoebase": "leftToes",
        "mixamorig:rightupleg": "rightUpperLeg", "mixamorig:rightleg": "rightLowerLeg",
        "mixamorig:rightfoot": "rightFoot", "mixamorig:righttoebase": "rightToes",
    },
}  # fmt: skip


def analyze_rig(mdl: StudioModel) -> dict:
    """Map bones to canonical humanoid slots with evidence; never modifies the rig.

    The default processing mode is "preserve": the original skeleton, weights and animations
    are exported unchanged. The mapping is information for later retarget/repair modes and is
    only offered when the structural checks agree with the names.
    """
    names = {b.name.lower(): b for b in mdl.bones}
    best, best_hits = None, 0
    for convention, table in NAMING.items():
        hits = sum(1 for n in table if n in names)
        if hits > best_hits:
            best, best_hits = convention, hits
    mapping: dict[str, dict] = {}
    if best:
        for n, slot in NAMING[best].items():
            if n in names:
                mapping[slot] = {"bone": names[n].name, "reason": f"name matches {best} convention"}
    world = None
    checks = []
    if mapping:
        from .transform import bone_world_matrices

        world = bone_world_matrices(mdl.bones)
        idx = {b.name: b.index for b in mdl.bones}

        def pos(slot):
            return (
                world[idx[mapping[slot]["bone"]]][3],
                world[idx[mapping[slot]["bone"]]][7],
                world[idx[mapping[slot]["bone"]]][11],
            )

        def is_ancestor(a: str, b: str) -> bool:
            i = mdl.bones[idx[mapping[b]["bone"]]].parent
            target = idx[mapping[a]["bone"]]
            while i >= 0:
                if i == target:
                    return True
                i = mdl.bones[i].parent
            return False

        for a, b in [("hips", "spine"), ("spine", "head"), ("leftUpperArm", "leftHand"), ("rightUpperArm", "rightHand"),
                     ("leftUpperLeg", "leftFoot"), ("rightUpperLeg", "rightFoot")]:  # fmt: skip
            if a in mapping and b in mapping:
                checks.append({"check": f"{a} is an ancestor of {b}", "passed": is_ancestor(a, b)})
        if "head" in mapping and "hips" in mapping:
            checks.append({"check": "head above hips", "passed": pos("head")[2] > pos("hips")[2]})
        for side, other in (("left", "right"),):
            for part in ("UpperArm", "UpperLeg"):
                if f"{side}{part}" in mapping and f"{other}{part}" in mapping:
                    ly, ry = pos(f"{side}{part}")[1], pos(f"{other}{part}")[1]
                    checks.append(
                        {
                            "check": f"{side}{part} and {other}{part} on opposite sides (y)",
                            "passed": ly * ry < 0,
                        }
                    )
    missing = sorted(REQUIRED - set(mapping))
    unmapped = [b.name for b in mdl.bones if b.name not in {m["bone"] for m in mapping.values()}]
    consistent = bool(mapping) and all(c["passed"] for c in checks)
    humanoid = consistent and not missing
    confidence = round(len(set(mapping) & REQUIRED) / len(REQUIRED) * (1.0 if consistent else 0.5), 2)
    return {
        "mode": "preserve",
        "convention": best,
        "humanoid": humanoid,
        "confidence": confidence,
        "confidence_note": "heuristic from names and structure checks, not proof",
        "mapping": mapping,
        "structure_checks": checks,
        "missing_required": missing,
        "extra_bones": unmapped,
        "available_modes": ["preserve"]
        + (["retarget (not implemented yet, see docs/roadmap.md)"] if humanoid else []),
    }
