# Architektur

```
Quellen (Ordner/GMA/VPK)  ─┐
                           ├─ Mount (Reihenfolge, Schatten, Limits)
                           │
Resolver ──────────────────┤  MDL → VVD/VTX/PHY/ANI/Includes → VMT (patch) → VTF
                           │  jede Datei: Quelle, Hash, überschattete Kopien, Status
Archiv  ───────────────────┤  originals/<sha256>  (unverändert, content-addressed)
Analyse ───────────────────┤  Klassifizierung mit Belegen (prop/character/vehicle/unknown)
AssetDocument ─────────────┤  versioniertes JSON: Modell, Physik, Materialien, Transformationen,
                           │  Journal (erhalten/umgerechnet/angenähert/geschätzt/neu/verloren/Fehler)
s&box-Ziel ────────────────┤  SMD, Hull-SMD, .vmdl, .vmat, PNG, Prefab  →  <Assets>/s1/...
Prüfungen ─────────────────┤  Round-Trip (srctools), Hüllen vs. Mesh, Referenzen; Zieltests: nicht ausgeführt
Bericht ───────────────────┘  reports/<id>.md
```

## Pakete

| Modul | Aufgabe |
|---|---|
| `sourcebridge/formats/` | Binär-Reader: `mdl`, `vvd`, `vtx`, `phy`, `gma` (alle bounds-geprüft, `FormatError` mit Offset) |
| `sourcebridge/sources.py` | `FolderSource`, `GmaSource`, `VpkSource`, `Mount` |
| `sourcebridge/safety.py` | Pfad-Normalisierung, Traversal-Schutz, Größen-/Anzahl-Limits, Lese-Budget |
| `sourcebridge/resolve.py` | Abhängigkeitsgraph, Checksummen-Abgleich MDL↔VVD/VTX/PHY |
| `sourcebridge/geometry.py` | Dreiecke aus MDL+VVD+VTX je Bodypart/Modell/LOD |
| `sourcebridge/materials.py` | VMT laden (inkl. `patch`), VTF → PNG, Mapping auf `complex.shader` |
| `sourcebridge/transform.py` | Koordinatenräume (dokumentiert), Bone-Matrizen |
| `sourcebridge/analyze.py` | erklärbare Klassifizierung |
| `sourcebridge/journal.py` | Änderungsjournal mit festen Zuständen |
| `sourcebridge/targets/sbox/` | KV3-Emitter/Parser, ModelDoc-/Material-/Prefab-Writer |
| `sourcebridge/pipeline.py` | Orchestrierung, Archiv, AssetDocument, Prüfungen |
| `sourcebridge/report.py`, `cli.py` | Bericht, CLI (`inspect`, `import`, `batch`) |
| `sbox/` | s&box-Testprojekt (C#): Zieltests in einer Szene |
| `tools/` | Fixture-/Projekt-Vorbereitung, Compile- und Whitelist-Check gegen die echte Engine |

## Projektordner eines Imports

```
<project>/originals/ab/ab12…      Originaldateien, byte-identisch
<project>/assets/<id>.json        AssetDocument (schema sourcebridge.asset, Version 1)
<project>/reports/<id>.md         Bericht
<project>/sbox/Assets/s1/…         Zielassets (oder --sbox-assets <Projekt>/Assets)
<project>/batch-state.json        Fortschritt von `batch` (fortsetzbar)
```

## Drei Produktwege

1. **Lokal benutzen** – Source-1-Game-Mount für s&box (C#, Engine-Beitrag). Noch nicht begonnen;
   s&box hat laut `engine/Mounting` Mounts für GoldSrc, Quake, NS2, SE3, aber keinen für Source 1.
2. **Dauerhaft erhalten und bearbeiten** – diese Pipeline.
3. **Funktion wiederherstellen** – s&box-Komponenten (Physik-Prop jetzt; Charakter-Animation und
   Fahrzeug in Etappe 2/3).
