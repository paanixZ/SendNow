import io
import json
import re
import shutil
import sys

import pytest
from conftest import FIXTURES, ROOT

from sourcebridge.pipeline import import_vehicle
from sourcebridge.sources import FolderSource, GmaSource, Mount
from sourcebridge.vehicles import (
    MPH_TO_INCHES_PER_SECOND,
    Dynamic,
    LuaParseError,
    find_sounds,
    find_soundscripts,
    find_vehicle_definitions,
    scan_addon,
)

sys.path.insert(0, str(ROOT / "fixtures"))
import gen_vehicle as authored  # noqa: E402

GMA = FIXTURES / "sourcebridge_fixtures.gma"


def rz90(p):
    """studiomdl's default root rotation for non-static models: (x, y, z) -> (-y, x, z)."""
    return (-p[1], p[0], p[2])


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    proj = tmp_path_factory.mktemp("veh") / "proj"
    doc = import_vehicle(Mount([GmaSource(GMA)]), "sb_buggy", proj)
    return doc, proj / "sbox/Assets"


# ------------------------------------------------------------------ Lua (static, never executed)


def test_lua_definition_direct():
    src = (FIXTURES / "addon/lua/autorun/sb_buggy.lua").read_text()
    (d,) = find_vehicle_definitions("lua/autorun/sb_buggy.lua", src)
    assert d.id == "sb_buggy"
    assert d.model == "models/sourcebridge/sb_buggy.mdl"
    assert d.script == "scripts/vehicles/sb_buggy.txt"
    assert d.get("Class") == "prop_vehicle_jeep"
    assert d.dynamic == []


def test_lua_definition_through_local_helper_and_dynamic_values():
    src = """
local Category = "Cars"
local function AddVehicle( t, class )
    list.Set( "Vehicles", class, t )
end
AddVehicle( {
    Name = "Car " .. "One",
    Model = "models/car.mdl",
    Class = "prop_vehicle_jeep",
    Category = Category,
    KeyValues = { vehiclescript = "scripts/vehicles/car.txt" },
    Members = { HandleAnimation = function( v, p ) return 1 end },
}, "car_one" )
"""
    (d,) = find_vehicle_definitions("lua/autorun/cars.lua", src)
    assert d.id == "car_one" and d.model == "models/car.mdl" and d.script == "scripts/vehicles/car.txt"
    assert isinstance(d.table["Name"], Dynamic) and isinstance(d.table["Category"], Dynamic)
    assert any(x.startswith("Members.HandleAnimation") for x in d.dynamic)


def test_hostile_lua_is_only_read():
    src = 'os.execute( "rm -rf /" )\nlist.Set( "Vehicles", "x", { Model = file.Read( "secret.txt" ), Class = "prop_vehicle_jeep" } )\n'
    (d,) = find_vehicle_definitions("lua/autorun/x.lua", src)
    assert isinstance(d.table["Model"], Dynamic)
    assert d.model is None


def test_lua_syntax_error_is_reported_not_raised(tmp_path):
    addon = tmp_path / "addon"
    (addon / "lua/autorun").mkdir(parents=True)
    (addon / "lua/autorun/broken.lua").write_text('list.Set( "Vehicles", "x", { Model = "a" ')
    scan = scan_addon(Mount([FolderSource(addon)]))
    assert scan["vehicles"] == []
    assert scan["errors"] and "broken.lua" in scan["errors"][0]
    with pytest.raises(LuaParseError):
        find_vehicle_definitions("x.lua", 'list.Set( "Vehicles", "x", { Model = "a" ')


def test_sound_definitions():
    snd = find_sounds("x.lua", (FIXTURES / "addon/lua/autorun/sb_buggy.lua").read_text())
    s = snd["SB_Buggy.EngineIdle"]
    assert s["files"] == ["vehicles/sb_buggy/engine_idle.wav"]
    assert s["pitch"] == [95.0, 105.0] and s["level"] == 80.0 and s["channel"] == "CHAN_STATIC"
    kv = find_soundscripts(
        "scripts/game_sounds_x.txt",
        '"Car.Horn"\n{\n "channel" "CHAN_ITEM"\n "wave" ")vehicles/horn.wav"\n}\n',
    )
    assert kv["Car.Horn"]["files"] == ["vehicles/horn.wav"]


def test_framework_addons_are_detected_not_converted(tmp_path):
    addon = tmp_path / "addon"
    shutil.copytree(FIXTURES / "addon", addon)
    (addon / "lua/autorun/other.lua").write_text("if simfphys then simfphys.RegisterEquipment() end\n")
    scan = scan_addon(Mount([FolderSource(addon)]))
    assert "simfphys" in scan["frameworks"]
    doc = import_vehicle(Mount([FolderSource(addon)]), "sb_buggy", tmp_path / "proj")
    assert any("simfphys" in p for p in doc["vehicle"]["problems"])


def test_unknown_vehicle_lists_available(tmp_path):
    with pytest.raises(ValueError, match="sb_buggy"):
        import_vehicle(Mount([GmaSource(GMA)]), "nope", tmp_path / "p")


# ------------------------------------------------------------------ VehicleDoc


def test_vehicle_doc_units_and_origins(result):
    doc, _ = result
    v = doc["vehicle"]
    assert doc["kind"] == "vehicle"
    assert v["engine"]["max_speed"]["value"] == pytest.approx(30 * MPH_TO_INCHES_PER_SECOND)
    assert v["engine"]["max_speed"]["unit"] == "in/s" and v["engine"]["max_speed"]["origin"] == "derived"
    assert v["engine"]["horsepower"]["value"] == 180 and v["engine"]["horsepower"]["origin"] == "original"
    assert v["engine"]["gears"]["value"] == [3.0, 1.8, 1.1]
    assert v["body"]["mass"]["value"] == authored.MASS and v["body"]["mass"]["unit"] == "kg"
    assert [a["torque_factor"]["value"] for a in v["axles"]] == [0.4, 0.6]
    assert v["script"]["raw"][0][0] == "vehicle"  # full script kept, order and duplicates preserved
    assert v["problems"] == []
    assert v["status"]["multiplayer"].startswith("not implemented")
    estimated = [e for e in doc["journal"] if e["state"] == "estimated" and e["field"].startswith("vehicle ")]
    assert {e["field"] for e in estimated} == {
        "vehicle suspension_travel",
        "vehicle tire_grip",
        "vehicle brake_deceleration",
        "vehicle suspension_damping_ratio",
    }


def test_wheels_seat_and_direction_match_the_engine_view(result):
    doc, _ = result
    v = doc["vehicle"]
    for w in v["wheels"]:
        expected = rz90(authored.WHEELS[w["name"]])
        assert w["position"]["value"] == pytest.approx(expected, abs=0.01), w["name"]
    assert [w["steers"]["value"] for w in v["wheels"]] == [True, True, False, False]
    assert v["forward_axis"]["value"] == pytest.approx([0, 1, 0], abs=1e-4)
    assert v["seat"]["feet"]["value"] == pytest.approx(rz90(authored.DRIVER_FEET), abs=0.01)
    assert v["seat"]["eyes"]["value"] == pytest.approx(rz90(authored.DRIVER_EYES), abs=0.01)
    assert v["wheelbase"]["value"] == pytest.approx(74.0, abs=0.01)


def test_rest_pose_is_baked_into_the_exported_mesh(result):
    import srctools.smd as smd

    doc, assets = result
    f = next(x for x in doc["outputs"]["files"] if x["role"] == "render-mesh")
    mesh = smd.Mesh.parse_smd(io.BytesIO((assets / f["path"]).read_bytes()))
    pts = [v.pos for t in mesh.triangles for v in (t.point1, t.point2, t.point3)]
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    # authored: x -50..52, y -34..34, z 0..46 -> engine view (Rz90): x -34..34, y -50..52
    assert lo == pytest.approx([-34, -50, 0], abs=0.05)
    assert hi == pytest.approx([34, 52, 46], abs=0.05)
    assert any(e["field"] == "rest pose" and e["state"] == "converted" for e in doc["journal"])


# ------------------------------------------------------------------ s&box output fidelity


def _cs_properties(cls: str) -> set[str]:
    for f in (ROOT / "sbox/Code").rglob("*.cs"):
        text = f.read_text()
        if re.search(rf"class {cls}\b", text):
            return set(re.findall(r"\[Property[^\]]*\]\s*public\s+\S+\s+(\w+)", text))
    raise AssertionError(cls)


def test_vehicle_prefab_uses_real_fields_and_our_properties(result):
    doc, assets = result
    ref = json.loads((ROOT / "sourcebridge/targets/sbox/templates/prefab_templates.json").read_text())
    prefab = json.loads((assets / doc["outputs"]["extra"]["vehicle_prefab"]).read_text())

    def check(go, root=False):
        if not root:
            assert set(go) == set(ref["child"]), go["Name"]
        for c in go["Components"]:
            if c["__type"].startswith("Sandbox."):
                assert set(c) == set(ref["components"][c["__type"]])
            else:
                props = set(c) - {"__type", "__guid", "__enabled", "Flags"}
                cls = c["__type"].rsplit(".", 1)[1]
                assert props <= _cs_properties(cls), (cls, props - _cs_properties(cls))
        for ch in go["Children"]:
            check(ch)

    check(prefab["RootObject"], root=True)
    wheels = [
        c["Components"][0]
        for c in prefab["RootObject"]["Children"]
        if c["Components"][0]["__type"].endswith("Wheel")
    ]
    assert len(wheels) == 4
    assert sum(w["DriveShare"] for w in wheels) == pytest.approx(1.0)
    assert sum(w["BrakeShare"] for w in wheels) == pytest.approx(1.0)
    assert {w["BoneName"] for w in wheels} == set(authored.WHEELS)
    rb = next(c for c in prefab["RootObject"]["Components"] if c["__type"] == "Sandbox.Rigidbody")
    assert rb["MassOverride"] == authored.MASS


def test_engine_sound_event(result):
    doc, assets = result
    ref = json.loads((ROOT / "sourcebridge/targets/sbox/templates/prefab_templates.json").read_text())[
        "sound"
    ]
    ev_path = doc["outputs"]["extra"]["vehicle_sound"]
    ev = json.loads((assets / ev_path).read_text())
    assert set(ev) == set(ref)
    (vsnd,) = ev["Sounds"]
    wav = assets / (vsnd[: -len(".vsnd")] + ".wav")
    assert wav.read_bytes()[:4] == b"RIFF"
    assert wav.read_bytes() == (FIXTURES / "addon/sound/vehicles/sb_buggy/engine_idle.wav").read_bytes()
