# Capability-Matrix

Stufen: **erkannt** (Format/Variante wird identifiziert) · **gelesen** (Daten vollständig
dekodiert) · **übertragen** (in s&box-Quellassets geschrieben) · **zielgeprüft** (in s&box
bestanden). Import-Unterstützung heißt nicht Export-Unterstützung.
„–" = nicht vorhanden, „teilweise" = siehe Einschränkungen.

Getestet mit: eigene Fixtures (mdlc-Commit in `fixtures/build/manifest.json`). Keine echten
Valve-/Workshop-Modelle in CI. Zielgeprüft: **noch nichts** (s&box-Lauf ausstehend).

## Container und Quellen

| Quelle | erkannt | gelesen | Einschränkungen |
|---|---|---|---|
| Ordner (Addon) | ja | ja | Symlinks werden ignoriert |
| GMA v1–3 | ja | ja | eigener Reader, CRC je Datei; unsichere Pfade werden gemeldet und übersprungen |
| VPK v1/v2 (`_dir.vpk`) | ja | ja | via sourcepp |
| BSP-Pakete (Pakfile) | – | – | Etappe 4 |

## Modelle

| Merkmal | gelesen | übertragen | zielgeprüft | Einschränkungen |
|---|---|---|---|---|
| MDL v44–49 Header, Flags, Surfaceprop | ja | ja | ausstehend | |
| VVD v4 inkl. Fixups | ja | ja | ausstehend | LOD>0 nur mit Fixture ohne Fixups getestet |
| VTX v7 (klassisch/erweitert) | ja | ja | ausstehend | Layout wird erkannt; erweitert noch ohne echtes Beispiel |
| Geometrie, Normalen, UVs | ja | ja (SMD) | ausstehend | Tangenten nicht übertragen (ModelDoc berechnet neu) |
| Skins (Texture Groups) | ja | ja (MaterialGroups) | ausstehend | |
| Bodygroups | ja | ja (BodyGroupList) | ausstehend | noch keine Fixture mit mehreren Choices |
| LODs | ja | ja (LODGroupList) | ausstehend | Schwellen aus VTX übernommen, Skala ungeprüft |
| Skelett (Bind-Pose) | ja | ja (SMD) | ausstehend | Etappe 2: Charakter-Fixture |
| Gewichte (≤3 je Vertex) | ja | ja (SMD) | ausstehend | Etappe 2 |
| Attachments, Hitboxen | ja | – | – | Etappe 2 |
| Sequenzen/Animationen | Metadaten | – | – | Keyframe-Dekodierung Etappe 2 |
| Flexes | Metadaten | – | – | DMX-Ausgabe Etappe 2 |
| Include-Modelle, .ani | aufgelöst | – | – | Etappe 2 |
| Modell-KeyValues (prop_data) | ja | – | – | im AssetDocument erhalten |

## Physik

| Merkmal | gelesen | übertragen | zielgeprüft | Einschränkungen |
|---|---|---|---|---|
| PHY (VPHY), Konvex-Hüllen | ja | ja (PhysicsHullFile je Hülle) | ausstehend | |
| PHY Legacy (ohne VPHY) | erkannt | ja | – | ohne Beispiel |
| Masse, Surfaceprop je Solid | ja | Masse → Prefab | ausstehend | Surface-Namen werden durchgereicht |
| Ragdoll-Constraints | Text | – | – | Etappe 2 |

## Materialien

| Merkmal | gelesen | übertragen | zielgeprüft | Einschränkungen |
|---|---|---|---|---|
| VMT inkl. `patch` | ja | ja | ausstehend | |
| VTF → PNG (Mip 0) | ja | ja | ausstehend | nur Frame 0/Face 0, Rest gemeldet |
| `$basetexture`, `$bumpmap` | ja | ja | ausstehend | Grünkanal-Konvention ungeprüft |
| `$translucent`, `$alphatest`, `$nocull`, `$selfillum`, `$color2` | ja | ja | ausstehend | angenähert, siehe Journal |
| Envmap, Phong, Detail, Lightwarp | ja | – | – | als „nicht übertragen" gemeldet |

## Weitere Inhalte

| Inhalt | Stand |
|---|---|
| Charaktere mit Animation | Etappe 2 |
| Fahrzeuge (Scripts, fahrbar) | Etappe 3 |
| Sounds, Soundscripts | Etappe 3/4 |
| Maps (BSP/VMF) | Etappe 4 |
| Lua-Addons (Inventar) | Etappe 4 |

## Zielprüfungen

| Nachweis | Status | s&box-Version | Datum |
|---|---|---|---|
| 1 Prop (`models/sourcebridge/crate.mdl`) | nicht ausgeführt | – | – |
| 2 Charakter | nicht vorhanden | – | – |
| 3 Auto | nicht vorhanden | – | – |
