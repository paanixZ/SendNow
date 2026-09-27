# Offener Umfang

Nichts aus dem Auftrag verschwindet; was nicht erledigt ist, steht hier.

## Etappe 1 – Prop (läuft)
- [x] Quellen Ordner/GMA/VPK, Mount-Reihenfolge, Schatten, Limits
- [x] Resolver, Archiv, AssetDocument, Journal, Bericht
- [x] MDL/VVD/VTX/PHY lesen, SMD + Hülle + .vmdl + .vmat + PNG + Prefab schreiben
- [x] s&box-Testprojekt mit Prop-Zieltest; Code kompiliert gegen echte Engine und besteht Whitelist
- [ ] **Zieltest in s&box ausführen** (wartet auf Windows-Lauf, `docs/target-tests.md`)
- [x] Fixture mit LODs und Bodygroups, damit diese Pfade den Vorlagen-Schutztest durchlaufen
- [ ] Vergleichsbild Original vs. Ziel für Materialien
- [ ] Erste echte GMod-/HL2-Props lokal beim Nutzer

## Etappe 2 – Charakter (Pipeline fertig, Zieltest ausstehend)
- [x] Charakter-Fixture (ValveBiped-Skelett, Gewichte, Bodygroups, Attachments, Hitboxen, Sequenzen, .phy-Ragdoll)
- [x] Animationsdekodierung (mstudioanim_t, RLE, Quaternion48/64, Vector48, Sektionen, .ani-Blöcke), Animations-SMD
- [x] AnimationList/AnimFile, AttachmentList, HitboxSetList, PhysicsJointList in .vmdl
- [x] Zieltest: Sequenzen abspielen, Endeffektor-Positionen, Ragdoll (Prefab mit ModelPhysics)
- [x] Deformationstest (CPU-Skinning Original vs. Export)
- [x] Rig-Analyse (Namenskonventionen ValveBiped/Citizen/Mixamo + Strukturprüfungen), Modus „erhalten"
- [ ] **Zieltest in s&box ausführen**
- [ ] Sequenz-Events → AnimEvent, Pose-Parameter → PoseParamList, Blend-Sequenzen → 1D/2DBlend
- [ ] Modi reparieren/retarget (Citizen, mit Funktionstest)/neu riggen
- [ ] Include-Modelle zusammenführen
- [ ] Flexes → DMX (Fixture mit VTA)
- [ ] AnimGraph-Anbindung für PlayerController (Citizen-Parameter)

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
