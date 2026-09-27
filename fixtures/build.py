"""Compile the fixture sources into real Source 1 files.

    python fixtures/build.py --mdlc /path/to/mdlc

Outputs (committed, so tests do not need the compiler):
    fixtures/build/addon/          loose GMod-style addon folder (models/, materials/)
    fixtures/build/sourcebridge_fixtures.gma
    fixtures/build/sourcebridge_fixtures_dir.vpk
    fixtures/build/manifest.json   tool versions and SHA-256 of every produced file

mdlc (https://github.com/MoRanYue/mdlc, GPL-3.0) is only run as an external program; it is
not part of SourceBridge. It is an independent studiomdl reimplementation, so the parser is not
tested against output of its own writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import time
import zlib
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "src"
OUT = HERE / "build"
ADDON = OUT / "addon"

MODELS = {"crate": "crate.qc", "mannequin": "mannequin.qc", "sb_buggy": "sb_buggy.qc"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_model(mdlc: str, name: str, qc: str) -> list[str]:
    work = OUT / "_work" / name
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(SRC / name, work, ignore=shutil.ignore_patterns("materials", "extra"))
    proc = subprocess.run(
        [mdlc, "build-qc", qc, "--out", str(work / "out")],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"mdlc failed for {name}:\n{proc.stdout}\n{proc.stderr}")
    produced = []
    for f in sorted((work / "out").rglob("*")):
        if f.is_file():
            rel = Path("models") / f.relative_to(work / "out")
            dest = ADDON / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            produced.append(rel.as_posix())
    return produced


def convert_materials(name: str) -> list[str]:
    from sourcepp import vtfpp

    produced = []
    mat_root = SRC / name / "materials"
    if not mat_root.exists():
        return []
    for f in sorted(mat_root.rglob("*")):
        if not f.is_file():
            continue
        rel = Path("materials") / f.relative_to(mat_root)
        if f.suffix == ".vmt":
            dest = ADDON / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            produced.append(rel.as_posix())
        elif f.suffix == ".png":
            opts = vtfpp.VTF.CreationOptions()
            opts.output_format = vtfpp.ImageFormat.DXT1
            opts.compute_mips = True
            vtf = vtfpp.VTF.create_from_file(str(f), opts)
            dest = (ADDON / rel).with_suffix(".vtf")
            dest.parent.mkdir(parents=True, exist_ok=True)
            vtf.bake_to_file(str(dest))
            produced.append(dest.relative_to(ADDON).as_posix())
    return produced


def copy_extra(name: str) -> list[str]:
    """Addon files that are not compiled (Lua, scripts, sounds) are copied unchanged."""
    root = SRC / name / "extra"
    out = []
    if root.exists():
        for f in sorted(root.rglob("*")):
            if f.is_file():
                rel = f.relative_to(root)
                dest = ADDON / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                out.append(rel.as_posix())
    return out


def write_gma(path: Path, files: list[str], title: str) -> None:
    """Minimal GMA v3 writer (layout of Facepunch's open-source gmad)."""
    body = bytearray(b"GMAD")
    body += bytes([3])
    body += struct.pack("<QQ", 0, 0)  # steamid, timestamp (0 = reproducible)
    body += b"\0"  # required content list (empty)
    body += title.encode() + b"\0"
    body += b'{"description":"SourceBridge test fixtures","type":"model","tags":["build"]}\0'
    body += b"SourceBridge\0"
    body += struct.pack("<i", 1)
    blobs = []
    for i, rel in enumerate(files, start=1):
        data = (ADDON / rel).read_bytes()
        blobs.append(data)
        body += struct.pack("<I", i) + rel.lower().encode() + b"\0"
        body += struct.pack("<qI", len(data), zlib.crc32(data))
    body += struct.pack("<I", 0)
    for data in blobs:
        body += data
    body += struct.pack("<I", zlib.crc32(bytes(body)))
    path.write_bytes(bytes(body))


def write_vpk(path: Path, files: list[str]) -> None:
    from sourcepp import vpkpp

    if path.exists():
        path.unlink()
    vpk = vpkpp.VPK.create(str(path), 2)
    for rel in files:
        vpk.add_entry_from_file(rel, str(ADDON / rel))
    vpk.bake()


def tool_version(mdlc: str) -> dict:
    repo = Path(mdlc).resolve().parents[2]
    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "-C", str(repo), "diff"], capture_output=True, text=True, check=False
    ).stdout
    patch = (HERE / "mdlc-multimodel-bodypart.patch").read_text()
    if diff and diff != patch:
        raise SystemExit("mdlc checkout has local changes other than fixtures/mdlc-multimodel-bodypart.patch")
    if not diff:
        raise SystemExit(
            "apply fixtures/mdlc-multimodel-bodypart.patch to mdlc first (see fixtures/README.md)"
        )
    import sourcepp

    return {
        "mdlc": {
            "url": "https://github.com/MoRanYue/mdlc",
            "commit": commit or "unknown",
            "patch": "fixtures/mdlc-multimodel-bodypart.patch",
            "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
        },
        "sourcepp": sourcepp.__version__,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mdlc", required=True)
    args = ap.parse_args()
    if ADDON.exists():
        shutil.rmtree(ADDON)
    files: list[str] = []
    for name, qc in MODELS.items():
        files += compile_model(args.mdlc, name, qc)
        files += convert_materials(name)
        files += copy_extra(name)
    shutil.rmtree(OUT / "_work", ignore_errors=True)
    files.sort()
    write_gma(OUT / "sourcebridge_fixtures.gma", files, "SourceBridge Fixtures")
    write_vpk(OUT / "sourcebridge_fixtures_dir.vpk", files)
    manifest = {
        "generated": time.strftime("%Y-%m-%d"),
        "license": "MIT (own work, see fixtures/README.md)",
        "tools": tool_version(args.mdlc),
        "files": {rel: sha256(ADDON / rel) for rel in files},
        "packages": {p.name: sha256(p) for p in sorted(OUT.glob("*.gma")) + sorted(OUT.glob("*.vpk"))},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
