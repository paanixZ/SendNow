import hashlib
import json
import shutil

from conftest import REFERENCE

from sourcebridge.pipeline import import_model
from sourcebridge.sources import FolderSource, GmaSource, Mount, open_source
from sourcebridge.targets.sbox.kv3 import dumps_modeldoc, parse_kv3

CRATE = "models/sourcebridge/crate.mdl"


def run(tmp_path, *sources):
    return import_model(Mount([open_source(s) for s in sources]), CRATE, tmp_path / "proj")


def test_prop_import_end_to_end(tmp_path, gma_path):
    doc = run(tmp_path, gma_path)
    assert doc["status"]["progress"] == "converted"
    assert doc["status"]["quality"] == "internal checks passed; target test not run"
    assert doc["kind"] == "prop"
    states = {c["name"]: c["state"] for c in doc["checks"]}
    assert states["mesh round-trip (srctools SMD parser)"] == "passed"
    assert states["collision hulls vs render bounds"] == "passed"
    assert states["references resolve inside the output"] == "passed"
    assert states["s&box ModelDoc compile"] == "not-run"
    roles = sorted(f["role"] for f in doc["outputs"]["files"])
    assert roles.count("render-mesh") == 1
    assert roles.count("collision-hull") == 1
    assert roles.count("material") == 2
    assert roles.count("texture") == 2
    assert roles.count("prefab") == 1
    prefab = json.loads((tmp_path / "proj/sbox/Assets" / doc["outputs"]["prefab"]).read_text())
    rb = next(c for c in prefab["RootObject"]["Components"] if c["__type"] == "Sandbox.Rigidbody")
    assert rb["MassOverride"] == 40.0


def test_originals_archived_byte_identical(tmp_path, gma_path, addon_dir):
    doc = run(tmp_path, gma_path)
    assert {o["path"] for o in doc["originals"]} >= {
        "models/sourcebridge/crate.mdl",
        "models/sourcebridge/crate.vvd",
        "models/sourcebridge/crate.dx90.vtx",
        "models/sourcebridge/crate.phy",
        "materials/models/sourcebridge/crate.vmt",
        "materials/models/sourcebridge/crate.vtf",
    }
    for o in doc["originals"]:
        stored = (tmp_path / "proj" / o["stored_as"]).read_bytes()
        assert hashlib.sha256(stored).hexdigest() == o["sha256"]
        assert stored == (addon_dir / o["path"]).read_bytes()


def test_all_source_kinds_give_identical_output(tmp_path, addon_dir, gma_path, vpk_path):
    hashes = []
    for i, src in enumerate((addon_dir, gma_path, vpk_path)):
        doc = import_model(Mount([open_source(src)]), CRATE, tmp_path / f"p{i}")
        hashes.append(sorted((f["path"], f["sha256"]) for f in doc["outputs"]["files"]))
    assert hashes[0] == hashes[1] == hashes[2]


def test_missing_vertex_data_is_reported_not_guessed(tmp_path, addon_dir):
    broken = tmp_path / "broken"
    shutil.copytree(addon_dir, broken)
    (broken / "models/sourcebridge/crate.vvd").unlink()
    doc = import_model(Mount([FolderSource(broken)]), CRATE, tmp_path / "proj")
    assert doc["status"]["progress"] == "archived-only"
    dep = next(d for d in doc["dependencies"] if d["path"].endswith(".vvd"))
    assert dep["status"] == "missing"
    assert "outputs" not in doc
    assert any(o["path"] == CRATE for o in doc["originals"])  # what exists is still archived
    report = (tmp_path / "proj/reports" / f"{doc['id']}.md").read_text()
    assert "missing" in report


def test_missing_texture_is_lossy_and_reported(tmp_path, addon_dir):
    broken = tmp_path / "broken"
    shutil.copytree(addon_dir, broken)
    (broken / "materials/models/sourcebridge/crate_dark.vtf").unlink()
    doc = import_model(Mount([FolderSource(broken)]), CRATE, tmp_path / "proj")
    assert doc["status"]["progress"] == "converted"
    assert doc["status"]["quality"] == "incomplete input"
    errors = [e for e in doc["journal"] if e["state"] == "error"]
    assert any("crate_dark.vtf" in e["subject"] + e["detail"] for e in errors)


def test_checksum_mismatch_is_invalid(tmp_path, addon_dir):
    broken = tmp_path / "broken"
    shutil.copytree(addon_dir, broken)
    vvd = bytearray((broken / "models/sourcebridge/crate.vvd").read_bytes())
    vvd[8] ^= 1
    (broken / "models/sourcebridge/crate.vvd").write_bytes(bytes(vvd))
    doc = import_model(Mount([FolderSource(broken)]), CRATE, tmp_path / "proj")
    dep = next(d for d in doc["dependencies"] if d["path"].endswith(".vvd"))
    assert dep["status"] == "invalid"
    assert "checksum" in dep["note"]


def test_override_source_wins_and_is_recorded(tmp_path, addon_dir, gma_path):
    override = tmp_path / "override"
    (override / "materials/models/sourcebridge").mkdir(parents=True)
    shutil.copy(
        addon_dir / "materials/models/sourcebridge/crate.vmt", override / "materials/models/sourcebridge/"
    )
    doc = import_model(Mount([FolderSource(override), GmaSource(gma_path)]), CRATE, tmp_path / "proj")
    dep = next(d for d in doc["dependencies"] if d["path"] == "materials/models/sourcebridge/crate.vmt")
    assert dep["source"] == "folder:override"
    assert dep["shadowed_in"] == ["gma:sourcebridge_fixtures.gma"]


# ------------------------------------------------------------------ fidelity to real s&box files


def _classes(tree, acc):
    if isinstance(tree, dict):
        if "_class" in tree:
            acc.setdefault(tree["_class"], set()).update(k for k in tree if k != "children")
        for v in tree.values():
            _classes(v, acc)
    elif isinstance(tree, list):
        for v in tree:
            _classes(v, acc)
    return acc


def test_kv3_parser_reads_every_reference_vmdl():
    for f in sorted(REFERENCE.glob("*.vmdl*")):
        tree = parse_kv3(f.read_text())
        assert "rootNode" in tree, f


def test_kv3_emitter_round_trips_reference_file():
    tree = parse_kv3((REFERENCE / "crate01.vmdl").read_text())
    again = parse_kv3(dumps_modeldoc(tree["rootNode"]))
    assert again == tree


def test_generated_vmdl_only_uses_classes_and_keys_seen_in_facepunch_files(tmp_path, gma_path):
    survey = json.loads((REFERENCE / "modeldoc_classes.json").read_text())["classes"]
    known = {cls: set(keys) | {"_class"} for cls, keys in survey.items()}
    doc = run(tmp_path, gma_path)
    ours = _classes(parse_kv3((tmp_path / "proj/sbox/Assets" / doc["outputs"]["vmdl"]).read_text()), {})
    for cls, keys in ours.items():
        assert cls in known, f"invented node class {cls}"
        assert keys <= known[cls], f"{cls}: keys not seen in real files: {keys - known[cls]}"


def test_generated_prefab_components_match_real_component_fields(tmp_path, gma_path):
    ref = json.loads(
        (
            REFERENCE.parent.parent.parent / "sourcebridge/targets/sbox/templates/prefab_templates.json"
        ).read_text()
    )
    doc = run(tmp_path, gma_path)
    prefab = json.loads((tmp_path / "proj/sbox/Assets" / doc["outputs"]["prefab"]).read_text())
    assert set(prefab) == set(ref["prefab"])
    assert set(prefab["RootObject"]) == set(ref["prefab"]["RootObject"])
    for comp in prefab["RootObject"]["Components"]:
        assert set(comp) == set(ref["components"][comp["__type"]])


def test_generated_vmat_keys_exist_in_real_complex_shader_materials(tmp_path, gma_path):
    import re

    survey = json.loads((REFERENCE / "complex_shader_keys.json").read_text())["keys"]
    doc = run(tmp_path, gma_path)
    for f in doc["outputs"]["files"]:
        if f["role"] == "material":
            text = (tmp_path / "proj/sbox/Assets" / f["path"]).read_text()
            for key in re.findall(r'^\s*"([A-Za-z_0-9]+)"', text, re.M):
                if key not in ("Layer0",):
                    assert key in survey, f"{key} never appears in Facepunch complex.shader materials"


def test_material_mapping_keys_are_all_surveyed():
    """Every key build_vmat can emit (any branch) exists in real Facepunch materials."""
    import re

    import sourcebridge.materials as m

    survey = json.loads((REFERENCE / "complex_shader_keys.json").read_text())["keys"]
    src = open(m.__file__).read()
    emitted = set(re.findall(r'put\("([A-Za-z_0-9]+)"', src)) | {
        "SystemAttributes",
        "PhysicsSurfaceProperties",
    }
    assert emitted, "no keys found"
    assert emitted <= set(survey), emitted - set(survey)
