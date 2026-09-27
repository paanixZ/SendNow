"""Human-readable conversion report (Markdown) generated from an AssetDocument."""

from __future__ import annotations

from collections import Counter

STATE_LABEL = {
    "preserved": "erhalten",
    "converted": "umgerechnet",
    "approximated": "angenähert",
    "estimated": "geschätzt",
    "generated": "neu erzeugt",
    "lost": "nicht übertragen",
    "error": "Fehler",
}


def render_markdown(doc: dict) -> str:
    L: list[str] = []
    st = doc.get("status", {})
    L.append(f"# SourceBridge-Bericht: `{doc['source_path']}`")
    L.append("")
    L.append(f"- Asset-ID: `{doc['id']}`")
    L.append(f"- Art: **{doc.get('kind', 'unbekannt')}**" + _cls(doc))
    L.append(f"- Fortschritt: **{st.get('progress')}**")
    L.append(f"- Qualität: **{st.get('quality')}**")
    L.append(
        f"- Veröffentlichung: **{st.get('publication')}** (Rechte: {doc['provenance'].get('redistribution')})"
    )
    L.append("- Werkzeuge: " + ", ".join(f"{k} {v}" for k, v in doc.get("tools", {}).items()))
    L.append("")
    L.append("## Quellen (Mount-Reihenfolge)")
    for i, s in enumerate(doc.get("mount", [])):
        L.append(f"{i + 1}. `{s['id']}` ({s['kind']}) {s['location']}")
    L.append("")
    L.append("## Abhängigkeiten")
    L.append("| Art | Pfad | Status | Quelle | Überschattet in |")
    L.append("|---|---|---|---|---|")
    for d in doc.get("dependencies", []):
        note = f" ({d['note']})" if d.get("note") else ""
        L.append(
            f"| {d['kind']} | `{d['path']}` | {d['status']}{note} | {d.get('source') or '-'} | "
            f"{', '.join(d.get('shadowed_in') or []) or '-'} |"
        )
    if doc.get("problems"):
        L.append("")
        L.append("## Probleme")
        for p in doc["problems"]:
            L.append(f"- {p}")
    if doc.get("checks"):
        L.append("")
        L.append("## Prüfungen")
        for c in doc["checks"]:
            mark = {"passed": "bestanden", "failed": "FEHLGESCHLAGEN", "not-run": "nicht ausgeführt"}[
                c["state"]
            ]
            L.append(f"- **{mark}**: {c['name']}")
            for d in c.get("detail", [])[:20]:
                L.append(f"  - {d}")
    j = doc.get("journal", [])
    if j:
        L.append("")
        L.append("## Änderungsjournal")
        counts = Counter(e["state"] for e in j)
        L.append(", ".join(f"{STATE_LABEL[k]}: {v}" for k, v in counts.items()))
        L.append("")
        L.append("| Objekt | Eigenschaft | Zustand | Detail |")
        L.append("|---|---|---|---|")
        for e in j:
            L.append(f"| `{e['subject']}` | {e['field']} | {STATE_LABEL[e['state']]} | {e['detail']} |")
    if doc.get("outputs"):
        L.append("")
        L.append("## Ausgabe")
        L.append(f"- ModelDoc: `{doc['outputs']['vmdl']}`")
        if doc["outputs"].get("prefab"):
            L.append(f"- Prefab: `{doc['outputs']['prefab']}`")
        L.append(f"- Dateien: {len(doc['outputs']['files'])} unter `{doc['outputs']['assets_root']}`")
    L.append("")
    L.append(f"Originale archiviert: {len(doc.get('originals', []))} Dateien (SHA-256, unverändert).")
    return "\n".join(L) + "\n"


def _cls(doc: dict) -> str:
    c = doc.get("classification")
    if not c:
        return ""
    return f" (Heuristik {c['confidence']}: {'; '.join(c['evidence'])})"
