"""The committed s&box target-test project must match what the pipeline produces today."""

import json
import sys
from pathlib import Path

from conftest import FIXTURES, ROOT

from sourcebridge.pipeline import import_model
from sourcebridge.sources import GmaSource, Mount

sys.path.insert(0, str(ROOT / "tools"))
import prepare_sbox_project as prep  # noqa: E402

SBOX = ROOT / "sbox"


def test_committed_assets_are_up_to_date(tmp_path):
    assets = tmp_path / "Assets"
    docs = []
    for model in prep.MODELS:
        docs.append(
            import_model(
                Mount([GmaSource(FIXTURES / "sourcebridge_fixtures.gma")]), model, tmp_path / "p", assets
            )
        )
    for d in docs:
        for f in d["outputs"]["files"]:
            fresh = (assets / f["path"]).read_bytes()
            committed = SBOX / "Assets" / f["path"]
            assert committed.exists(), f"{f['path']} missing: run tools/prepare_sbox_project.py"
            assert committed.read_bytes() == fresh, f"{f['path']} stale: run tools/prepare_sbox_project.py"
    assert (SBOX / "Code/SourceBridge/GeneratedCases.cs").read_text() == prep.cases_cs(docs)
    assert (SBOX / "Assets/scenes/sourcebridge_tests.scene").read_text() == prep.scene()


def test_scene_is_the_facepunch_template_plus_runner():
    tpl = json.loads((ROOT / "templates/sbox/reference/minimal.scene").read_text())
    ours = json.loads((SBOX / "Assets/scenes/sourcebridge_tests.scene").read_text())
    names = [g["Name"] for g in ours["GameObjects"]]
    assert "SourceBridge Tests" in names
    assert not any(n.startswith("Cube") for n in names)
    kept = [g for g in tpl["GameObjects"] if not g["Name"].startswith("Cube")]
    assert ours["GameObjects"][: len(kept)] == kept  # sun, sky, ground plane, camera unchanged
    assert set(ours) == set(tpl)


def test_sbproj_points_at_the_test_scene():
    proj = json.loads((SBOX / "sourcebridge_tests.sbproj").read_text())
    assert proj["Type"] == "game"
    scene = proj["Metadata"]["StartupScene"]
    assert (SBOX / "Assets" / scene).exists()


def test_generated_cases_reference_existing_prefabs():
    text = (SBOX / "Code/SourceBridge/GeneratedCases.cs").read_text()
    for line in text.splitlines():
        if line.strip().startswith('new( "'):
            prefab = line.split('"')[1]
            if not prefab.endswith(".prefab"):
                continue
            assert (SBOX / "Assets" / prefab).exists(), prefab
            assert Path(prefab).suffix == ".prefab"
