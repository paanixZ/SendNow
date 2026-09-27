# Test fixtures

Own work, MIT licensed. `generate_sources.py` writes the QC/SMD/VMT/PNG sources in `src/`;
`build.py --mdlc <path>` compiles them to real Source 1 files with
[mdlc](https://github.com/MoRanYue/mdlc) (GPL-3.0, an independent studiomdl reimplementation,
used only as an external program) and packs them as GMA and VPK. `build/manifest.json` records
the compiler commit and SHA-256 of every file. The compiled files are committed so tests run
without the compiler.

## mdlc patch

mdlc (commit in `build/manifest.json`) writes `numLODs = 0` for every model after the first in a
body part (`vtx_writer.rs`, `model_abs` computed once outside the model loop), so bodygroup
choices lose their triangles. `mdlc-multimodel-bodypart.patch` fixes that one line; `build.py`
refuses to run without it. SourceBridge reports such files as an error instead of reading them
as empty (see `sourcebridge/geometry.py`). The fix should go upstream.

Other mdlc limits met while authoring: no `blank` bodygroup choices; `$lod` on models with several
body parts fails, so LODs are exercised by the crate.

## Charakter-Fixture (`mannequin`)

Eigener Mannequin mit ValveBiped-Knochennamen: 17 Bones (Arme mit 90°-Ruhegierung), gemischte
Gewichte an Gelenken, Bodygroup `head` (Kopf/Helm), Alphatest-Visier, 2 Attachments, 5 Hitboxen,
Sequenzen `idle` (20 Frames) und `walk` (30 Frames, loop), Ragdoll mit 11 Solids und
Gelenkgrenzen. Beobachtet an mdlc: Ragdoll-Hüllen stehen im gedrehten Modellraum statt
bone-lokal; ob studiomdl das ebenso macht, ist offen (siehe `docs/decisions.md`, E12).
