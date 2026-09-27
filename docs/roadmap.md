# Offener Umfang

Nichts aus dem Auftrag verschwindet; was nicht erledigt ist, steht hier.

## Etappe 1 – Prop (läuft)
- [x] Quellen Ordner/GMA/VPK, Mount-Reihenfolge, Schatten, Limits
- [x] Resolver, Archiv, AssetDocument, Journal, Bericht
- [x] MDL/VVD/VTX/PHY lesen, SMD + Hülle + .vmdl + .vmat + PNG + Prefab schreiben
- [x] s&box-Testprojekt mit Prop-Zieltest; Code kompiliert gegen echte Engine und besteht Whitelist
- [ ] **Zieltest in s&box ausführen** (wartet auf Windows-Lauf, `docs/target-tests.md`)
- [ ] Fixture mit LODs und Bodygroups, damit diese Pfade den Vorlagen-Schutztest durchlaufen
- [ ] Vergleichsbild Original vs. Ziel für Materialien
- [ ] Erste echte GMod-/HL2-Props lokal beim Nutzer

## Etappe 2 – Charakter
- [ ] Charakter-Fixture (ValveBiped-Skelett, Gewichte, Bodygroups, Attachments, Hitboxen, Sequenzen, .phy-Ragdoll)
- [ ] Animationsdekodierung (mstudioanim_t, Sektionen, Delta/Autolayer), Ausgabe als Animations-SMD
- [ ] AnimationList/AnimFile in .vmdl, Attachments, Hitboxen, Ragdoll-Joints
- [ ] AnimGraph-Anbindung + Zieltest (Sequenz abspielen, Deformation prüfen)
- [ ] Modi erhalten/reparieren/retarget/neu riggen; Namenswörterbücher, Struktur-Analyse
- [ ] Flexes → DMX

## Etappe 3 – Auto
- [ ] Fahrzeug-Fixture (Karosserie, 4 Rad-Bones, Sitz-Attachment, Collision) + Standard-Vehicle-Script
- [ ] KeyValues-Parser für Vehicle-Scripts, VehicleDoc mit Einheiten und Herkunft
- [ ] s&box-Fahrzeug auf libwheel: fahren, lenken, bremsen, rückwärts, Sitz/Kamera, Motorsound
- [ ] Zieltest mit messbaren Kriterien

## Etappe 4 – Erweiterbar
- [ ] Batch-Jobs abbrechbar mit Fortschritt (Grundgerüst in `batch` vorhanden)
- [ ] Fahrzeug-Framework-Adapter (simfphys, LVS …) nach Untersuchung
- [ ] Sounds, Soundscripts
- [ ] Maps (BSP/VMF) begrenzt
- [ ] Lua-Addon-Inventar, erster Entity-Adapter
- [ ] Source-1-Game-Mount als Engine-Beitrag
- [ ] optionale KI-Stufe (Opt-in)

## Etappe 5 – Bearbeitung und Creator
- [ ] Oberfläche, Auto-Rig, Charakter-Creator, weitere Austauschformate

## Umgebung
- [ ] `artifacts.sbox.game` ist in der Cloud-Umgebung gesperrt; mit Zugriff könnte `./Setup.sh`
      die komplette Engine inkl. nativer Teile bauen (für Tests weiterhin Windows nötig)
