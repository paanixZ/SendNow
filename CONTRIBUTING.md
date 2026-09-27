# Mitmachen

- `pip install -e ".[dev]"`, dann `ruff check . && ruff format --check . && pytest`.
- Neue Zielformate (ModelDoc-Knoten, Material-Tasten, Prefab-Felder) nur, wenn sie in echten
  Facepunch-Dateien vorkommen. Referenz-Statistiken in `templates/sbox/reference` bei neuer
  s&box-Version neu erzeugen (siehe dortige `SOURCE.md`).
- Jede Umwandlung schreibt einen Journal-Eintrag (`preserved`, `converted`, `approximated`,
  `estimated`, `generated`, `lost`, `error`). Nichts wird still verworfen.
- Fixtures sind eigene Arbeit: Quellen in `fixtures/generate_sources.py`, Build mit
  `python fixtures/build.py --mdlc <mdlc>`. Keine Valve- oder Workshop-Inhalte committen.
- Nach Änderungen an Ausgabe oder Fixtures: `python tools/prepare_sbox_project.py`.
- s&box-Code in `sbox/Code` muss `tools/check_sbox_code.sh` bestehen.
- Neue Fähigkeiten in `docs/capabilities.md` eintragen, offene Punkte in `docs/roadmap.md`.
