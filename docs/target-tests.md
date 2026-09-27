# Zieltests in s&box

Diese Tests laufen **nur in s&box** (Windows, Steam). In der Entwicklungsumgebung von SourceBridge
gibt es kein s&box; dort sind sie deshalb als **nicht ausgeführt** markiert. Nicht ausgeführt heißt
nicht bestanden. Erst dein Lauf macht aus einem Nachweis einen bestandenen Nachweis.

Was vorher schon automatisch geprüft ist (CI bzw. `pytest`, `tools/check_sbox_code.sh`):

- Parser, Resolver, Archiv, Round-Trip der Meshes und Collision, Referenzen der Ausgabe
- jede erzeugte ModelDoc-Klasse/Taste, jede Material-Taste und jedes Prefab-Feld kommt in echten
  Facepunch-Dateien vor (Vorlagen aus `Facepunch/sbox-public`, siehe `templates/sbox/reference`)
- `sbox/Code` kompiliert gegen die echte verwaltete s&box-Engine (gleicher Commit) und besteht
  s&box' eigene API-Whitelist-Prüfung (`Sandbox.AccessControl`)

Was nur s&box selbst beweisen kann: dass ModelDoc die SMD-Dateien so importiert wie erwartet,
dass das Modell rendert, kollidiert, fällt und richtig liegt.

## Nachweis 1: Prop (Kiste mit 2 Skins, Collision, 40 kg)

1. s&box über Steam installieren und einmal starten. Die s&box-Version aus dem Hauptmenü notieren.
2. Dieses Repository klonen.
3. Im s&box-Editor **Open Project** und `sbox/sourcebridge_tests.sbproj` öffnen.
4. Der Editor kompiliert die Assets. In der Konsole darf für `s1/models/sourcebridge/crate.vmdl`
   kein Fehler erscheinen. Optional das Modell im Model Editor öffnen: Kiste sichtbar,
   Physik-Hülle als Box, zwei Material Groups (`default`, `skin1`).
5. Szene `scenes/sourcebridge_tests.scene` ist Startszene. **Play** drücken.
6. In der Konsole erscheinen Zeilen `SOURCEBRIDGE-TEST PASS|FAIL [...]`:

   | Test | bestanden, wenn |
   |---|---|
   | `prop.model` | Modell geladen, kein Fehlermodell |
   | `prop.skins` | 2 Material Groups |
   | `prop.collision` | mindestens 1 Physik-Teil |
   | `prop.mass` | Rigidbody-Masse 40 kg (aus der .phy) |
   | `prop.fall` | Kiste fällt aus 96 Einheiten, kommt zur Ruhe, unterste Physikkante bei z = 0 ± 1,5 |

7. Die Zeilen (oder `sourcebridge_results.json` aus dem Datenordner des Projekts) zurückmelden.
   Ich trage das Ergebnis mit s&box-Version in `docs/capabilities.md` ein. Schlägt etwas fehl,
   brauche ich zusätzlich die Konsolenausgabe beim Kompilieren von `crate.vmdl`.

Bekanntes Risiko: Facepunchs eigene Modelle nutzen FBX/DMX. SMD als ModelDoc-Eingabe ist
dokumentiert, aber nicht durch ein Facepunch-Beispiel belegt. Falls ModelDoc SMD anders
interpretiert (Einheiten, Achsen, V-Koordinate), zeigt das genau dieser Test; die Umstellung
auf DMX ist dann der nächste Schritt (siehe `docs/decisions.md`, E4).

## Eigene GMod-/HL2-Inhalte testen

```
pip install -e .
sourcebridge inspect --source "C:\Pfad\zu\addon.gma"
sourcebridge import --source "C:\Pfad\zu\addon.gma" --source "C:\Pfad\zu\garrysmod\garrysmod_dir.vpk" ^
    --model models/props_c17/oildrum001.mdl --project out --sbox-assets sbox\Assets
```

Nur ausdrücklich angegebene Quellen werden durchsucht, die erste gewinnt. Der Bericht liegt in
`out/reports/`. Solche Dateien niemals committen oder veröffentlichen: Rechte an Valve- und
Workshop-Inhalten sind nicht geklärt (siehe `docs/licensing.md`).

## Nachweis 2: Charakter (Mannequin mit ValveBiped-Skelett)

Gleiche Szene, gleicher Play-Lauf. Neben den Prop-Zeilen erscheinen:

| Test | bestanden, wenn |
|---|---|
| `character.model`, `character.bones` | Modell geladen, 17 Bones |
| `character.sequences` | `idle` und `walk` vorhanden |
| `character.attachments` | `eyes`, `anim_attachment_RH` vorhanden |
| `character.bodygroups` | 1 Bodygroup (`head`: Kopf/Helm) |
| `character.physics` | 11 Physik-Teile, 10 Gelenke |
| `character.animation` (6×) | Sequenz bei Frame 0, n/3, 2n/3 eingefroren; Kopf, Hände, Füße liegen höchstens 1 Einheit von den Positionen entfernt, die aus den Original-Animationsdaten berechnet wurden |
| `character.ragdoll.bodies` | Ragdoll-Prefab baut 11 Körper und 10 Gelenke |
| `character.ragdoll.fall` | Ragdoll fällt, kommt zur Ruhe, kein Körper unter dem Boden |

Wenn `character.animation` um ungefähr eine Vierteldrehung abweicht (Hände vertauschen x/y), dreht
ModelDoc Wurzelknochen beim SMD-Import selbst; dann bitte die Zeilen schicken (E11).

## Nachweis 3 (Auto)

Folgt in Etappe 3 mit eigenem Testfall in derselben Szene.
