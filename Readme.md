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

## Programm herunterladen (ohne Programmierkenntnisse)

GitHub baut die `Coversuche.exe` automatisch bei jeder Änderung:

1. Auf GitHub im Repository oben auf **Actions** klicken.
2. Den obersten Eintrag mit grünem Haken öffnen.
3. Unten unter **Artifacts** auf **Coversuche-Windows** klicken. Du bekommst eine ZIP-Datei.
4. ZIP entpacken und `Coversuche.exe` per Doppelklick starten.

Windows zeigt beim ersten Start eventuell „Der Computer wurde durch Windows
geschützt“. Das liegt daran, dass das Programm nicht digital signiert ist.
Klicke auf **Weitere Informationen** und dann auf **Trotzdem ausführen**.

## Aufbau des Projekts (für Neugierige)

| Datei | Inhalt |
|---|---|
| `coversuche/core.py` | Die Logik: Dateien finden, Cover lesen/schreiben, Online-Suche, Log |
| `coversuche/gui.py` | Das Fenster (Dateiliste links, Vorschau rechts) |
| `start.py` | Startet das Programm |
| `tests/test_core.py` | Automatische Tests der Logik |
| `requirements.txt` | Verwendete Zusatz-Bibliotheken |
| `.github/workflows/windows-build.yml` | Anleitung für GitHub, die `.exe` zu bauen |

Geschrieben in **Python** mit den Bibliotheken *mutagen* (ID3-Tags),
*Pillow* (Bilder), *requests* (Internet) und *tkinter* (Fenster).
