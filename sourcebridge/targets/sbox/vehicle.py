"""s&box output for vehicles: prefab with physics body, wheels, seat, camera anchor and sounds.

GameObject, component and .sound layouts are cloned from Facepunch's shipped files
(templates/prefab_templates.json). The SourceBridge.Vehicles components live in sbox/Code and are
compiled against the real engine by tools/check_sbox_code.sh.
"""

from __future__ import annotations

import copy
import json

from ...journal import Journal
from .model import ASSET_ROOT, _guid, _templates, component, prefab_json

ESTIMATED = {
    "suspension_travel": (
        8.0,
        "in",
        "Source derives travel from vehicle_wheel_*_height pose parameters; none decoded",
    ),
    "tire_grip": (1.0, "friction coefficient", "Source uses surfaceprop friction of the tire material"),
    "brake_deceleration": (0.8, "g", "Source brakes through vphysics with brake materials"),
    "suspension_damping_ratio": (0.7, "ratio", "vphysics springDamping has no documented unit"),
}


def _vec(v) -> str:
    return ",".join(f"{x:.4f}".rstrip("0").rstrip(".") if abs(x) >= 1e-9 else "0" for x in v)


def game_object(
    name: str, seed: str, position, components: list[dict], children: list[dict] | None = None
) -> dict:
    go = copy.deepcopy(_templates()["child"])
    go["__guid"] = _guid(seed + "go")
    go["Name"] = name
    go["Position"] = _vec(position)
    go["Rotation"] = "0,0,0,1"
    go["Scale"] = "1,1,1"
    go["Components"] = components
    go["Children"] = children or []
    return go


def custom(type_name: str, seed: str, **props) -> dict:
    return {"__type": type_name, "__guid": _guid(seed + type_name), "__enabled": True, "Flags": 0, **props}


def sound_event(files: list[str], volume: float | None, level: float | None) -> str:
    ev = copy.deepcopy(_templates()["sound"])
    ev["UI"] = False
    ev["Sounds"] = files
    if volume is not None:
        ev["Volume"] = f"{volume:g}"
    if level is not None:
        ev["Decibels"] = int(level)
    ev["__references"] = []
    return json.dumps(ev, indent=2) + "\n"


def _val(d: dict | None, default=None):
    if not d:
        return default
    v = d.get("value")
    return default if v is None else v


def build_vehicle_prefab(
    vdoc: dict,
    vmdl_path: str,
    name: str,
    mass: float | None,
    wheel_bones: dict[str, str],
    sound_path: str | None,
    journal: Journal,
    subject: str,
) -> tuple[str, str]:
    seed = vmdl_path + "vehicle"
    body = vdoc["body"]
    eng = vdoc["engine"]
    st = vdoc["steering"]
    mass_center = _val(body.get("mass_center_offset"))
    rb_props = {"MassOverride": float(mass or 0)}
    if mass_center:
        rb_props.update({"OverrideMassCenter": True, "MassCenterOverride": _vec(mass_center)})
        journal.approximated(
            subject, "mass centre", "Source massCenterOverride used as model-space mass centre"
        )
    renderer = component("Sandbox.SkinnedModelRenderer", seed, Model=vmdl_path, UseAnimGraph=False)
    comps = [
        renderer,
        component("Sandbox.ModelCollider", seed, Model=vmdl_path),
        component("Sandbox.Rigidbody", seed, **rb_props),
    ]
    est = {k: v[0] for k, v in ESTIMATED.items()}
    for key, (value, unit, why) in ESTIMATED.items():
        journal.estimated(subject, f"vehicle {key}", f"{value:g} {unit}: not in the vehicle script ({why})")
    comps.append(
        custom(
            "SourceBridge.Vehicles.SourceBridgeVehicle",
            seed,
            Horsepower=float(_val(eng.get("horsepower"), 100.0)),
            MaxSpeed=float(_val(eng.get("max_speed"), 528.0)),
            MaxReverseSpeed=float(_val(eng.get("max_reverse_speed"), 176.0)),
            DegreesSlow=float(_val(st.get("degrees_slow"), 40.0)),
            DegreesFast=float(_val(st.get("degrees_fast"), 20.0)),
            SlowSpeed=float(_val(st.get("slow_speed"), 176.0)),
            FastSpeed=float(_val(st.get("fast_speed"), 440.0)),
            SteerRateSlow=float(_val(st.get("rate_slow"), 3.0)),
            SteerRateFast=float(_val(st.get("rate_fast"), 1.5)),
            SteerRestRateSlow=float(_val(st.get("rest_rate_slow"), 3.0)),
            SteerRestRateFast=float(_val(st.get("rest_rate_fast"), 1.5)),
            SteerExponent=float(_val(st.get("exponent"), 1.0)),
            TireGrip=est["tire_grip"],
            BrakeDeceleration=est["brake_deceleration"],
            SuspensionDampingRatio=est["suspension_damping_ratio"],
            ForwardAxis=_vec(_val(vdoc.get("forward_axis"), [1.0, 0.0, 0.0])),
            EngineSound=sound_path or "",
            AcceptPlayerInput=True,
        )
    )
    children = []
    axles = vdoc["axles"]
    for w in vdoc["wheels"]:
        ax = axles[w["axle"]]
        per_axle = sum(1 for x in vdoc["wheels"] if x["axle"] == w["axle"])
        wheel = custom(
            "SourceBridge.Vehicles.SourceBridgeWheel",
            seed + w["name"],
            Radius=float(_val(ax.get("radius"), 14.0)),
            SuspensionTravel=est["suspension_travel"],
            Steers=bool(_val(w.get("steers"), False)),
            DriveShare=float(_val(ax.get("torque_factor"), 0.5)) / per_axle,
            BrakeShare=float(_val(ax.get("brake_factor"), 0.5)) / per_axle,
            BoneName=wheel_bones.get(w["name"], ""),
        )
        children.append(game_object(w["name"], seed + w["name"], w["position"]["value"], [wheel]))
    feet = _val(vdoc["seat"].get("feet"))
    eyes = _val(vdoc["seat"].get("eyes"))
    if feet:
        eyes_rel = [eyes[k] - feet[k] for k in range(3)] if eyes else [0.0, 0.0, 28.0]
        eyes_go = game_object("Eyes", seed + "eyes", eyes_rel, [])
        seat = custom("SourceBridge.Vehicles.VehicleSeat", seed + "seat", ExitDistance=48.0, DriveCamera=True)
        children.append(game_object("Seat", seed + "seat", feet, [seat], [eyes_go]))
    prefab_rel = f"{ASSET_ROOT}/prefabs/{vmdl_path[len(ASSET_ROOT) + 1 : -5]}_vehicle.prefab"
    journal.converted(
        subject,
        "vehicle",
        f"drivable prefab: {len(children) - (1 if feet else 0)} wheels from attachments, seat, camera anchor, "
        "engine/steering values from the vehicle script (driving physics recreated)",
    )
    return prefab_rel, prefab_json(name + "_vehicle", seed, comps, children)
