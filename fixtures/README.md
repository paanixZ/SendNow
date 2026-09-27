# Test fixtures

Own work, MIT licensed. `generate_sources.py` writes the QC/SMD/VMT/PNG sources in `src/`;
`build.py --mdlc <path>` compiles them to real Source 1 files with
[mdlc](https://github.com/MoRanYue/mdlc) (GPL-3.0, an independent studiomdl reimplementation,
used only as an external program) and packs them as GMA and VPK. `build/manifest.json` records
the compiler commit and SHA-256 of every file. The compiled files are committed so tests run
without the compiler.
