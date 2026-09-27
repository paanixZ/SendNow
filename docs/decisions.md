# Entscheidungen

Kurz, mit Begründung und dem, was eine Entscheidung wieder kippen würde.

**E1 – Kern in Python, s&box-Seite in C#.** Die belastbaren offenen Source-1-Bibliotheken
(sourcepp, srctools) sind in Python nutzbar und laufen headless unter Linux und Windows. Alles,
was in s&box läuft, ist zwangsläufig C#. Kippt, wenn der Source-1-Mount (Weg „lokal benutzen")
denselben Parser in C# braucht; dann wird der Parser nach C# portiert, das Datenmodell bleibt.

**E2 – Eigene Reader für MDL/VVD/VTX/PHY/GMA.** sourcepp' mdlpp ist unvollständig und ohne
Python-Binding, srctools liest MDL nur als Metadaten, SourceIO hängt an Blender. sourcepp öffnet
eine kaputte GMA stillschweigend als gültig, daher eigener, streng geprüfter GMA-Reader
(Gegenprobe gegen sourcepp im Test). VPK liest sourcepp. Formatwissen aus den öffentlichen
Headern des Source SDK 2013 (nur gelesen, kein Code übernommen) und der Dokumentation von mdlc.

**E3 – Testassets: eigene Quellen, unabhängig kompiliert.** Frei lizenzierte kompilierte
Source-1-Modelle gibt es praktisch nicht. Die Fixtures sind eigene QC/SMD-Quellen, kompiliert mit
`mdlc` (clean-room studiomdl, laut Projekt feldweise gegen studiomdl validiert). Dadurch testet der
Reader nicht gegen seinen eigenen Writer. srctools liest dieselben Dateien unabhängig gegen.
Grenze: Das ist kein Beweis für echte Valve-/Workshop-Modelle. Die müssen lokal beim Nutzer
getestet werden (`docs/target-tests.md`).

**E4 – s&box-Eingabe per SMD.** SMD ist verlustfrei für Skelett, Gewichte und Animationen in
Source-Einheiten und wird von ModelDoc laut Doku gelesen. Facepunchs eigene Dateien nutzen aber nur
FBX (1858×) und DMX (78×), SMD 0×. Unbestätigt bis zum Zieltest. Fallback: DMX-Writer
(Valve-Format, deckt auch Flexes ab). Kein eigener FBX-Writer.

**E5 – Nichts erfinden bei Zielformaten.** .vmdl-Knoten, .vmat-Tasten und Prefab-Felder werden nur
verwendet, wenn sie in echten Facepunch-Dateien vorkommen. Die Statistiken
(`templates/sbox/reference/modeldoc_classes.json`, `complex_shader_keys.json`) und
Prefab-Komponenten-Vorlagen sind eingecheckt; Tests schlagen bei jeder unbelegten Taste fehl.

**E6 – Keine Einheiten- oder Achsenumrechnung für Geometrie.** Source 1 und s&box: Z-oben, Zoll.
Einzige Umrechnung ist IVP-Physik (Meter, vertauschte Achsen) → Modellraum, geprüft an der
Fixture-Kiste (Hülle exakt −16…16, 0…32). V-Koordinate: VVD speichert 1−v, SMD bekommt v zurück.

**E7 – Dreiecksreihenfolge aus VTX unverändert.** An der Fixture stimmen alle Dreiecke mit den
gespeicherten Normalen überein (Test `test_geometry_matches_authored_box`).

**E8 – Materialien auf `shaders/complex.shader`.** Einziger Shader, der in Facepunchs Props
flächendeckend genutzt wird (387 Dateien). Source 1 hat keine PBR-Eingaben: Rauheit 0,7 und
Metall 0 werden als „neu erzeugt" markiert. Normal-Map-Grünkanal-Konvention ungeprüft (Journal:
„angenähert").

**E9 – Masse im Prefab.** .phy-Gesamtmasse → `Rigidbody.MassOverride`. In .vmdl gibt es dafür
nur `PhysicsBodyMarkup.mass_override` mit Body-Namen, deren Benennung für Props nicht belegt ist.

**E10 – s&box-Code gegen die echte Engine prüfen.** `artifacts.sbox.game` (native Binaries) ist
in der Entwicklungsumgebung gesperrt. Für Compile-Checks reichen die verwalteten Assemblies:
Interop-Bindings aus `engine/Definitions` erzeugen, `System.Speech` aus NuGet, `Sandbox.Engine`
bauen (`tools/build_sbox_reference.sh`). Danach s&box' eigene Whitelist-Prüfung.

**E11 – studiomdl-Standarddrehung wird übernommen, nicht „repariert".** studiomdl dreht Wurzelknochen
in Animationen um Rz(90°) (`g_defaultrotation`), bei `$staticprop` stattdessen die Geometrie. Die
Engine zeigt genau diese Daten; SourceBridge exportiert sie unverändert. Der Charakter-Zieltest
prüft Endeffektor-Positionen in s&box gegen diese Werte und deckt so auf, falls ModelDoc beim
SMD-Import selbst noch einmal dreht.

**E12 – Raum der Ragdoll-Hüllen wird gemessen, nicht angenommen.** Bone-lokal (Engine-Semantik
für Ragdoll-Körper) und Modellraum (so schreibt es mdlc) sind beide plausibel; ohne echte
Valve-Ragdolls hier nicht entscheidbar. SourceBridge vergleicht je Modell die Hüllen unter jeder
Hypothese mit den Vertices des jeweiligen Bones und nimmt die beste; die Werte stehen im Journal.

**E13 – Hitboxen als Kapseln.** s&box-ModelDoc kennt in Facepunchs Dateien nur `HitboxCapsule`.
Source-Hitboxen (Quader) werden als umschließende Kapsel entlang der längsten Achse geschrieben,
Trefferzonen als Tags. Im Journal als „angenähert".

**E14 – Ragdoll-Gelenke.** `ragdollconstraint` mit genau einer freien Achse → `PhysicsJointRevolute`
mit Min/Max, sonst `PhysicsJointConical` (Swing = größtes y/z-Limit, Twist = x). Anker am Kind-Bone
im Raum des Eltern-Bones. Bedeutung von `anchor_angles` in s&box nicht belegt → „angenähert",
Zieltest prüft nur Anzahl, Aufbau und Stabilität (fällt, liegt, versinkt nicht).

**E15 – Charaktere standardmäßig „Original erhalten".** Skelett, Gewichte, Sequenzen bleiben wie im
Original. Die Rig-Analyse (Namenskonvention + Strukturprüfungen) wird nur dokumentiert; Retarget
auf Citizen kommt erst mit eigenem Funktionstest.
