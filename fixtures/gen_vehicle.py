"""Source files for the vehicle fixture: a small buggy as a standard Source vehicle (MIT, own work).

Model authored with forward = +X, left = +Y, up = +Z. For non-static models studiomdl turns the
root by Rz(90) in every sequence, so in the engine the buggy faces +Y like Valve's vehicles.
Addon side (copied, not compiled): Lua vehicle definition, sound.Add, vehicle script, engine WAV.
"""

from __future__ import annotations

import array
import math
import struct
from pathlib import Path

WHEELS = {
    "wheel_fl": (38.0, 30.0, 14.0),
    "wheel_fr": (38.0, -30.0, 14.0),
    "wheel_rl": (-36.0, 30.0, 14.0),
    "wheel_rr": (-36.0, -30.0, 14.0),
}
WHEEL_RADIUS = 14.0
WHEEL_WIDTH = 8.0
DRIVER_EYES = (-4.0, 12.0, 44.0)
DRIVER_FEET = (-4.0, 12.0, 16.0)
MASS = 800.0


def wheel_tris(mat, bone, center, radius, width, segments=12):
    tris = []
    cx, cy, cz = center
    ring = [
        (
            cx + radius * math.cos(2 * math.pi * i / segments),
            cz + radius * math.sin(2 * math.pi * i / segments),
        )
        for i in range(segments)
    ]
    y0, y1 = cy - width / 2, cy + width / 2
    links = [(bone, 1.0)]
    for i in range(segments):
        (x_a, z_a), (x_b, z_b) = ring[i], ring[(i + 1) % segments]
        n = ((x_a + x_b) / 2 - cx, 0.0, (z_a + z_b) / 2 - cz)
        ln = math.hypot(n[0], n[2])
        n = (n[0] / ln, 0.0, n[2] / ln)
        u0, u1 = i / segments, (i + 1) / segments
        a, b, c, d = (x_a, y0, z_a), (x_b, y0, z_b), (x_b, y1, z_b), (x_a, y1, z_a)
        # outward faces, counter-clockwise seen from outside
        tris.append((mat, [(links, a, n, (u0, 0)), (links, d, n, (u0, 1)), (links, c, n, (u1, 1))]))
        tris.append((mat, [(links, a, n, (u0, 0)), (links, c, n, (u1, 1)), (links, b, n, (u1, 0))]))
        for y, ny in ((y0, -1.0), (y1, 1.0)):
            cap = (
                [(cx, y, cz), (x_a, y, z_a), (x_b, y, z_b)]
                if ny < 0
                else [(cx, y, cz), (x_b, y, z_b), (x_a, y, z_a)]
            )
            tris.append((mat, [(links, p, (0.0, ny, 0.0), (0.5, 0.5)) for p in cap]))
    return tris


def engine_wav(path: Path, seconds: float = 1.0, rate: int = 22050) -> None:
    samples = array.array("h")
    for i in range(int(seconds * rate)):
        t = i / rate
        v = (
            0.45 * math.sin(2 * math.pi * 55 * t)
            + 0.25 * math.sin(2 * math.pi * 110 * t)
            + 0.1 * math.sin(2 * math.pi * 165 * t)
        )
        samples.append(int(max(-1.0, min(1.0, v)) * 20000))
    data = samples.tobytes()
    fmt = struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVEfmt "
        + fmt
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )


LUA = """-- SourceBridge test vehicle (MIT). Standard Source vehicle, no framework.
sound.Add( {
\tname = "SB_Buggy.EngineIdle",
\tchannel = CHAN_STATIC,
\tvolume = 0.8,
\tlevel = 80,
\tpitch = { 95, 105 },
\tsound = "vehicles/sb_buggy/engine_idle.wav"
} )

list.Set( "Vehicles", "sb_buggy", {
\tName = "SourceBridge Buggy",
\tModel = "models/sourcebridge/sb_buggy.mdl",
\tClass = "prop_vehicle_jeep",
\tCategory = "SourceBridge",
\tAuthor = "SourceBridge",
\tInformation = "Test vehicle for SourceBridge",
\tKeyValues = {
\t\tvehiclescript = "scripts/vehicles/sb_buggy.txt"
\t}
} )
"""

AXLE = """\t"axle"
\t{{
\t\t"wheel"
\t\t{{
\t\t\t"radius"\t"{radius}"
\t\t\t"mass"\t\t"60"
\t\t\t"inertia"\t"0.5"
\t\t\t"damping"\t"0"
\t\t\t"rotdamping"\t"0.0"
\t\t\t"material"\t"jeeptire"
\t\t\t"skidmaterial"\t"slidingrubbertire"
\t\t\t"brakematerial"\t"brakingrubbertire"
\t\t}}
\t\t"suspension"
\t\t{{
\t\t\t"springConstant"\t\t"80"
\t\t\t"springDamping"\t\t\t"0.7"
\t\t\t"stabilizerConstant"\t\t"50"
\t\t\t"springDampingCompression"\t"4"
\t\t\t"maxBodyForce"\t\t\t"12"
\t\t}}
\t\t"torquefactor"\t"{torque}"
\t\t"brakefactor"\t"{brake}"
\t}}
"""

SCRIPT_HEAD = """// SourceBridge test vehicle script (MIT). Values chosen for this fixture.
"vehicle"
{
\t"wheelsperaxle"\t"2"
\t"body"
\t{
\t\t"countertorquefactor"\t"1"
\t\t"massCenterOverride"\t"0 0 -4"
\t\t"massoverride"\t\t"800"\t\t// kg
\t\t"addgravity"\t\t"0.33"
\t}
\t"engine"
\t{
\t\t"horsepower"\t\t"180"
\t\t"maxrpm"\t\t"4000"
\t\t"maxspeed"\t\t"30"\t\t// mph
\t\t"maxReverseSpeed"\t"10"\t\t// mph
\t\t"autotransmission"\t"1"
\t\t"axleratio"\t\t"4.1"
\t\t"gear"\t\t\t"3.0"
\t\t"gear"\t\t\t"1.8"
\t\t"gear"\t\t\t"1.1"
\t\t"shiftuprpm"\t\t"3200"
\t\t"shiftdownrpm"\t\t"1400"
\t}
\t"steering"
\t{
\t\t"degreesSlow"\t\t"40"
\t\t"degreesFast"\t\t"20"
\t\t"degreesBoost"\t\t"12"
\t\t"steeringExponent"\t"1.2"
\t\t"slowcarspeed"\t\t"10"
\t\t"fastcarspeed"\t\t"25"
\t\t"slowSteeringRate"\t"3.0"
\t\t"fastSteeringRate"\t"1.5"
\t\t"steeringRestRateSlow"\t"3.0"
\t\t"steeringRestRateFast"\t"1.5"
\t\t"turnThrottleReduceSlow" "0.01"
\t\t"turnThrottleReduceFast" "1.0"
\t\t"brakeSteeringRateFactor"\t"4"
\t\t"throttleSteeringRestRateFactor"\t"2"
\t\t"skidallowed"\t\t"1"
\t\t"dustcloud"\t\t"0"
\t}
"""

SCRIPT_SOUNDS = """}

"vehicle_sounds"
{
\t"gear"
\t{
\t\t"max_speed"\t\t"0.4"
\t\t"speed_approach_factor" "1.0"
\t}
\t"gear"
\t{
\t\t"max_speed"\t\t"1.0"
\t\t"speed_approach_factor" "0.05"
\t}
\t"state"
\t{
\t\t"name"\t\t"SS_START_IDLE"
\t\t"sound"\t\t"SB_Buggy.EngineIdle"
\t}
\t"state"
\t{
\t\t"name"\t\t"SS_IDLE"
\t\t"sound"\t\t"SB_Buggy.EngineIdle"
\t}
\t"state"
\t{
\t\t"name"\t\t"SS_GEAR_0"
\t\t"sound"\t\t"SB_Buggy.EngineIdle"
\t}
}
"""


def write_sources(src: Path, write, smd, box_triangles, png) -> None:
    d = src / "sb_buggy"
    nodes = [(0, "body", -1)] + [(i + 1, n, 0) for i, n in enumerate(WHEELS)]
    rest = [[(0, (0, 0, 0), (0, 0, 0))] + [(i + 1, p, (0, 0, 0)) for i, p in enumerate(WHEELS.values())]]
    body = box_triangles("sb_buggy_paint", (-50, -26, 12), (50, 26, 30), 0)
    body += box_triangles("sb_buggy_paint", (-22, -22, 30), (18, 22, 46), 0)
    mesh = list(body)
    for i, center in enumerate(WHEELS.values()):
        mesh += wheel_tris("sb_buggy_tire", i + 1, center, WHEEL_RADIUS, WHEEL_WIDTH)
    write(d / "sb_buggy_ref.smd", smd(nodes, rest, mesh))
    write(d / "sb_buggy_phys.smd", smd(nodes, rest, body))
    write(d / "sb_buggy_idle.smd", smd(nodes, rest, None))
    atts = "\n".join(f'$attachment "{n}" "{n}" 0 0 0 rotate 0 0 0' for n in WHEELS)
    ex, ey, ez = DRIVER_EYES
    fx, fy, fz = DRIVER_FEET
    write(
        d / "sb_buggy.qc",
        f"""$modelname "sourcebridge/sb_buggy.mdl"
$body body "sb_buggy_ref.smd"
$cdmaterials "models/sourcebridge/"
$surfaceprop "metalvehicle"
{atts}
$attachment "vehicle_driver_eyes" "body" {ex} {ey} {ez} rotate 0 0 0
$attachment "vehicle_feet_passenger0" "body" {fx} {fy} {fz} rotate 0 0 0
$attachment "vehicle_engine" "body" 36 0 24 rotate 0 0 0
$sequence idle "sb_buggy_idle.smd" fps 30
$collisionmodel "sb_buggy_phys.smd" {{
	$concave
	$mass {MASS:g}
}}
""",
    )
    mats = d / "materials" / "models" / "sourcebridge"
    png(
        mats / "sb_buggy_paint.png",
        32,
        32,
        lambda x, y: (200, 60, 40, 255) if y > 4 else (240, 240, 240, 255),
    )
    png(
        mats / "sb_buggy_tire.png",
        32,
        32,
        lambda x, y: (30, 30, 30, 255) if (x // 4) % 2 else (45, 45, 45, 255),
    )
    for name, prop in (("sb_buggy_paint", "metalvehicle"), ("sb_buggy_tire", "rubbertire")):
        write(
            mats / f"{name}.vmt",
            f'"VertexLitGeneric"\n{{\n\t"$basetexture" "models/sourcebridge/{name}"\n\t"$surfaceprop" "{prop}"\n}}\n',
        )
    extra = d / "extra"
    write(extra / "lua" / "autorun" / "sb_buggy.lua", LUA)
    engine_wav(extra / "sound" / "vehicles" / "sb_buggy" / "engine_idle.wav")
    script = SCRIPT_HEAD + AXLE.format(radius=WHEEL_RADIUS, torque="0.4", brake="0.6")
    script += AXLE.format(radius=WHEEL_RADIUS, torque="0.6", brake="0.4") + SCRIPT_SOUNDS
    write(extra / "scripts" / "vehicles" / "sb_buggy.txt", script)
