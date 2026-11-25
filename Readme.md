# Coversuche

Ein Windows-Programm, das MP3-Dateien nach fehlenden Covern durchsucht und
diese automatisch aus dem Internet ergänzt.

## Was das Programm macht

1. Du wählst einen Ordner (wahlweise mit Unterordnern).
2. Links erscheinen alle MP3-Dateien mit ihrem Status, rechts die Cover-Vorschau
   der ausgewählten Datei.
3. Mit **„Fehlende Cover suchen und ergänzen“** wird für jede Datei ohne Cover
   anhand des Dateinamens online gesucht (iTunes, ersatzweise Deezer) und das
   Cover in den ID3-Tag geschrieben.
4. Alles wird in einer Log-Datei protokolliert
   (`Coversuche_Log_<Datum>_<Uhrzeit>.txt` im gewählten Ordner):
   *Cover schon vorhanden*, *Cover ergänzt*, *Kein Cover gefunden* oder *Fehler*.

5. **Rechtsklick auf eine Datei** in der Liste öffnet ein Menü:
   * **Cover entfernen** – löscht das Cover aus dem ID3-Tag (mit Rückfrage)
   * **Cover manuell hinzufügen …** – ein eigenes Bild (JPG) auswählen; der Ordner
     des letzten Covers wird gemerkt (auch nach einem Neustart)
   * **ID3-Tag bearbeiten …** – Titel, Interpret, Album, Jahr, Genre usw. ändern
     (ein leer gelassenes Feld wird gelöscht)

**Cover-Größe:** Zu kleine Cover werden auf 600 Pixel vergrößert, sehr große
auf 1000 Pixel verkleinert (Seitenverhältnis bleibt erhalten).

**Tipp:** Die Suche klappt am besten bei Dateinamen wie
`Künstler - Titel.mp3`. Tracknummern, „(Official Video)“, „[HQ]“ und Ähnliches
werden automatisch entfernt. Bringt der Dateiname nichts, wird zusätzlich mit
Künstler und Titel aus dem ID3-Tag gesucht.

**Hinweis:** Das Programm verändert deine MP3-Dateien. Probiere es zuerst an
einem Ordner mit Kopien aus.

## Explorer-Kontextmenü

Wenn beim Installieren das Häkchen „Explorer-Kontextmenü“ gesetzt war, gibt es
nach einem Rechtsklick ein Untermenü **Coversuche**:

| Rechtsklick auf … | Einträge |
|---|---|
| eine oder mehrere MP3-Dateien | Cover suchen · ID3-Tag bearbeiten · Dateinamen aus ID3-Tag erstellen |
| einen Ordner | dasselbe für alle MP3s im Ordner (ohne Unterordner) |

* **Cover suchen** öffnet das Hauptfenster mit diesen Dateien und startet die Suche sofort.
* **ID3-Tag bearbeiten** bei mehreren Dateien: nur Felder, die du änderst, werden
  in alle Dateien geschrieben. Titel und Tracknummer sind dann gesperrt.
* **Dateinamen aus ID3-Tag erstellen** zeigt zuerst eine Vorschau. Schema:
  `Interpret - Album - 01 - Titel.mp3` (Tracknummer immer zweistellig).
  Fehlen Album oder Tracknummer, werden sie weggelassen; ohne Interpret oder
  Titel wird die Datei übersprungen.

**Windows 11:** Das Untermenü steht unter **„Weitere Optionen anzeigen“**
(oder Rechtsklick mit gedrückter **Umschalttaste**). Ins neue, verkürzte Menü
kommen nur Programme mit einer kostenpflichtigen digitalen Signatur.

## Installieren (ohne Programmierkenntnisse)

GitHub baut das Setup automatisch bei jeder Änderung:

1. Auf GitHub im Repository oben auf **Actions** klicken.
2. Den obersten Eintrag mit grünem Haken öffnen.
3. Unten unter **Artifacts** auf **Coversuche-Setup** klicken (ZIP-Datei).
4. ZIP entpacken und `Coversuche-Setup.exe` per Doppelklick starten.

Windows zeigt eventuell „Der Computer wurde durch Windows geschützt“, weil das
Setup nicht digital signiert ist: **Weitere Informationen** → **Trotzdem ausführen**.
Administratorrechte sind nicht nötig. Deinstallieren geht über
**Einstellungen → Apps → Installierte Apps → Coversuche**.

## Aufbau des Projekts (für Neugierige)

| Datei | Inhalt |
|---|---|
| `coversuche/core.py` | Die Logik: Dateien finden, Cover lesen/schreiben, Online-Suche, Log |
| `coversuche/gui.py` | Die Fenster (Hauptfenster, Tag-Bearbeitung, Umbenennen) |
| `coversuche/explorer.py` | Start über das Explorer-Kontextmenü |
| `installer/coversuche.iss` | Bauanleitung für das Setup (Inno Setup) |
| `start.py` | Startet das Programm |
| `tests/test_core.py` | Automatische Tests der Logik |
| `requirements.txt` | Verwendete Zusatz-Bibliotheken |
| `.github/workflows/windows-build.yml` | Anleitung für GitHub, das Setup zu bauen |

Geschrieben in **Python** mit den Bibliotheken *mutagen* (ID3-Tags),
*Pillow* (Bilder), *requests* (Internet) und *tkinter* (Fenster).
