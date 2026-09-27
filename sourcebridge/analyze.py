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
