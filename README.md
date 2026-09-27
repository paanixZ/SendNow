# SourceBridge

Source-1- und Garry's-Mod-Inhalte erhalten und in **s&box** (Source 2) wieder benutzbar machen:
Originale unverändert archivieren, Abhängigkeiten nachvollziehbar auflösen, Inhalte analysieren,
als bearbeitbare s&box-Quellassets ausgeben und in s&box prüfen. Kein Viewer, kein reiner
Konverter: Ziel ist, dass der Inhalt in s&box **funktioniert** (Prop kollidiert, Charakter
animiert, Auto fährt). VRChat ist kein Ziel.

> Arbeitsname „SourceBridge". Stand: Props, Charaktere und Fahrzeuge konvertierbar; die Zieltests in s&box stehen aus. Was belegt ist und was nicht, steht in
> [`docs/capabilities.md`](docs/capabilities.md); offener Umfang in [`docs/roadmap.md`](docs/roadmap.md).

## Schnellstart

```
pip install -e ".[dev]"
sourcebridge inspect --source mein_addon.gma
sourcebridge import --source mein_addon.gma --model models/foo/bar.mdl --project out
```

Ergebnis:

- `out/originals/` – alle gelesenen Originaldateien, byte-identisch (SHA-256)
- `out/assets/<id>.json` – AssetDocument (Modell, Physik, Materialien, Journal, Prüfungen)
- `out/reports/<id>.md` – Bericht: Quellen, Abhängigkeiten, was erhalten/umgerechnet/angenähert/verloren ist
- `out/sbox/Assets/s1/…` – .vmdl, SMD, .vmat, PNG, Prefab (oder direkt ins s&box-Projekt mit `--sbox-assets`)

Mehrere `--source` sind erlaubt (Ordner, `.gma`, `_dir.vpk`); die erste gewinnt, verdeckte Kopien
werden im Bericht genannt. Es wird nie in anderen, nicht angegebenen Installationen gesucht.
`sourcebridge batch --source … --project out` verarbeitet alle Modelle und ist fortsetzbar.
`sourcebridge vehicle --source … --id <id> --project out` konvertiert ein GMod-Fahrzeug fahrbar
(Definition aus Lua, Vehicle-Script, Modell, Motorsound → Prefab mit Rädern, Sitz, Kamera).

## Prüfen

```
pytest                       # Parser, Resolver, Pipeline, Sicherheit, Vorlagen-Treue
tools/check_sbox_code.sh     # sbox/Code gegen die echte s&box-Engine kompilieren + Whitelist
```

Die Zieltests in s&box selbst (Windows) beschreibt [`docs/target-tests.md`](docs/target-tests.md).

## Dokumentation

- [Architektur](docs/architecture.md) · [Entscheidungen](docs/decisions.md) · [Capability-Matrix](docs/capabilities.md)
- [Zieltests](docs/target-tests.md) · [Lizenzen und Rechte](docs/licensing.md) · [Referenzen](docs/references.md) · [Roadmap](docs/roadmap.md)

## Lizenz

Code: MIT. Rechte an importierten Inhalten klärt das Werkzeug nicht; siehe [`docs/licensing.md`](docs/licensing.md).
