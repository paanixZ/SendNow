"""Command line interface.

sourcebridge inspect  --source <dir|gma|vpk> [--source ...]
sourcebridge import   --source ... --model models/x.mdl --project out/ [--sbox-assets <Assets dir>]
sourcebridge batch    --source ... --project out/ [--pattern "models/*.mdl"]
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path

from .formats.binary import FormatError
from .safety import LimitExceeded, UnsafePath
from .sources import Mount, open_source


def _mount(args) -> Mount:
    if not args.source:
        raise SystemExit("at least one --source is required (only explicitly given sources are searched)")
    sources = []
    seen = set()
    for s in args.source:
        src = open_source(Path(s))
        base, n = src.id, 2
        while src.id in seen:
            src.id = f"{base}#{n}"
            n += 1
        seen.add(src.id)
        sources.append(src)
    return Mount(sources)


def cmd_inspect(args) -> int:
    m = _mount(args)
    models = sorted(p for p in m.all_paths() if p.endswith(".mdl"))
    from .vehicles import scan_addon

    scan = scan_addon(m)
    info = {
        "sources": [s.describe() for s in m.sources],
        "models": models,
        "vehicles": [
            {
                "id": v.id,
                "model": v.model,
                "script": v.script,
                "class": v.get("Class"),
                "defined_in": f"{v.source_file}:{v.line}",
            }
            for v in scan["vehicles"]
        ],
        "vehicle_frameworks": scan["frameworks"],
        "lua_parse_errors": scan["errors"],
        "counts": {
            ext: sum(1 for p in m.all_paths() if p.endswith(ext))
            for ext in (".mdl", ".vmt", ".vtf", ".wav", ".mp3", ".lua", ".txt", ".bsp")
        },
    }
    print(json.dumps(info, indent=2))
    return 0


def cmd_import(args) -> int:
    from .pipeline import import_model

    m = _mount(args)
    doc = import_model(
        m, args.model, Path(args.project), Path(args.sbox_assets) if args.sbox_assets else None
    )
    _summary(doc, Path(args.project))
    return 0 if doc["status"]["progress"] == "converted" and "failed" not in doc["status"]["quality"] else 2


def cmd_vehicle(args) -> int:
    from .pipeline import import_vehicle

    m = _mount(args)
    doc = import_vehicle(m, args.id, Path(args.project), Path(args.sbox_assets) if args.sbox_assets else None)
    _summary(doc, Path(args.project))
    if doc.get("outputs", {}).get("extra", {}).get("vehicle_prefab"):
        print(f"vehicle prefab: {doc['outputs']['extra']['vehicle_prefab']}")
    return 0 if doc["status"]["progress"] == "converted" and "failed" not in doc["status"]["quality"] else 2


def cmd_batch(args) -> int:
    from .pipeline import import_model

    m = _mount(args)
    models = sorted(p for p in m.all_paths() if p.endswith(".mdl") and fnmatch.fnmatch(p, args.pattern))
    done_file = Path(args.project) / "batch-state.json"
    done = json.loads(done_file.read_text()) if done_file.exists() and not args.restart else {}
    rc = 0
    try:
        for i, path in enumerate(models, 1):
            if path in done:
                continue
            print(f"[{i}/{len(models)}] {path}", file=sys.stderr)
            try:
                doc = import_model(
                    m, path, Path(args.project), Path(args.sbox_assets) if args.sbox_assets else None
                )
                done[path] = doc["status"]
            except (FormatError, LimitExceeded, UnsafePath, ValueError) as exc:
                done[path] = {"progress": "failed", "quality": str(exc)}
                rc = 2
            done_file.parent.mkdir(parents=True, exist_ok=True)
            done_file.write_text(json.dumps(done, indent=2))
    except KeyboardInterrupt:
        print("interrupted; rerun the same command to continue", file=sys.stderr)
        return 130
    print(json.dumps(done, indent=2))
    return rc


def _summary(doc: dict, project: Path) -> None:
    st = doc["status"]
    print(f"{doc['source_path']}: {st['progress']} / {st['quality']}")
    for c in doc.get("checks", []):
        print(f"  [{c['state']}] {c['name']}")
    print(f"report: {project / 'reports' / (doc['id'] + '.md')}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sourcebridge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("inspect", "import", "batch", "vehicle"):
        p = sub.add_parser(name)
        p.add_argument("--source", action="append", default=[], help="folder, .gma or _dir.vpk; first wins")
        if name != "inspect":
            p.add_argument("--project", required=True)
            p.add_argument("--sbox-assets", help="write into this s&box project's Assets folder")
        if name == "import":
            p.add_argument("--model", required=True, help="game path, e.g. models/props_c17/oildrum001.mdl")
        if name == "vehicle":
            p.add_argument("--id", required=True, help="vehicle id as in list.Set( 'Vehicles', <id>, ... )")
        if name == "batch":
            p.add_argument("--pattern", default="*")
            p.add_argument("--restart", action="store_true")
    args = ap.parse_args(argv)
    try:
        return {"inspect": cmd_inspect, "import": cmd_import, "batch": cmd_batch, "vehicle": cmd_vehicle}[
            args.cmd
        ](args)
    except (FormatError, LimitExceeded, UnsafePath, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
