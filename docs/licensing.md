# Lizenzen, Herkunft, Rechte

Drei getrennte Ebenen:

1. **Werkzeug (dieses Repository):** MIT, siehe `LICENSE`.
2. **Engine/SDK-Bedingungen:** s&box-Engine-Quellcode (`Facepunch/sbox-public`) MIT; native
   Binaries unter der s&box-EULA. Source SDK 2013 unter Valves eigener, nicht-kommerzieller
   SDK-Lizenz – hier wird **kein** SDK-Code übernommen; die öffentlichen Header wurden nur als
   Formatbeschreibung gelesen.
3. **Importierte Inhalte:** SourceBridge klärt keine Rechte. Jedes AssetDocument hat
   `provenance.redistribution = "unknown"`, bis jemand eine Erlaubnis dokumentiert. Lokaler
   Besitz oder ein Workshop-Eintrag ist keine Weitergabeerlaubnis. Ergebnisse aus fremden Inhalten
   werden nie automatisch veröffentlicht.

## Abhängigkeiten

| Komponente | Lizenz | Verwendung |
|---|---|---|
| sourcepp (craftablescience) | MIT | Python-Paket: VPK lesen, VTF dekodieren, PNG schreiben |
| srctools (TeamSpen210) | MIT | Python-Paket: VMT/KeyValues, SMD-Gegenprüfung, MDL-Gegenprüfung |
| Facepunch sbox-public | MIT | Referenzdateien in `templates/sbox/reference`, Compile-/Whitelist-Checks |
| Facepunch sbox-libwheel | MIT | geplant: Radkollision (Etappe 3) |
| mdlc (MoRanYue) | GPL-3.0 | nur externes Programm zum Bauen der Fixtures, nicht eingebunden oder verteilt |
| System.Speech (NuGet, Microsoft) | MIT | nur für den lokalen Compile-Check der Engine |

## Fixtures

Alle Testinhalte in `fixtures/` sind eigene Arbeit (MIT). Öffentliche Demos verwenden nur diese.
