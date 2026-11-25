"""
Start über das Kontextmenü des Windows-Explorers.

Der Explorer ruft das Programm so auf:
    Coversuche.exe --cover      "C:\\Musik\\Lied.mp3"
    Coversuche.exe --tag        "C:\\Musik\\Album"
    Coversuche.exe --umbenennen "C:\\Musik\\Lied.mp3"
Ohne Zusatz startet ganz normal das Hauptfenster.

Problem: Markiert man im Explorer 20 Dateien und klickt auf einen Eintrag,
startet Windows das Programm 20-mal – mit je EINER Datei. Damit dann nicht
20 Fenster aufgehen, sammelt der erste gestartete Prozess die Dateien der
anderen ein (über eine kleine Verbindung nur auf diesem Computer) und
zeigt alles in EINEM Fenster.
"""

from __future__ import annotations

import json
import socket
import sys
import time

AKTIONEN = {"--cover": "cover", "--tag": "tag", "--umbenennen": "umbenennen"}

# Fester Anschluss (Port) nur auf diesem Rechner (127.0.0.1) für das Einsammeln
PORT = 47815
WARTEZEIT = 0.8      # so lange nach der letzten Datei auf weitere warten (s)
MAX_WARTEZEIT = 5.0  # höchstens so lange insgesamt einsammeln (s)


def lese_argumente(argumente: list[str]) -> tuple[str | None, list[str]]:
    """Trennt die Aktion (z. B. "cover") von den Pfaden."""
    aktion = None
    pfade = []
    for arg in argumente:
        if arg in AKTIONEN:
            aktion = AKTIONEN[arg]
        else:
            pfade.append(arg)
    return aktion, pfade


def _als_sammler_starten() -> socket.socket | None:
    """Versucht, der "Sammler" zu werden. None, wenn es schon einen gibt."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # nur unter Windows vorhanden
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(("127.0.0.1", PORT))
        sock.listen(50)
        return sock
    except OSError:
        sock.close()
        return None


def _an_sammler_senden(aktion: str, pfade: list[str]) -> bool:
    """Schickt die eigenen Pfade an den Sammler. True, wenn es geklappt hat."""
    nachricht = json.dumps({"aktion": aktion, "pfade": pfade}).encode("utf-8")
    for _ in range(10):  # der Sammler startet evtl. gerade erst
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1) as s:
                s.sendall(nachricht)
            return True
        except OSError:
            time.sleep(0.1)
    return False


def _einsammeln(sock: socket.socket, aktion: str, pfade: list[str]) -> list[str]:
    """Nimmt eine kurze Zeit lang Pfade von anderen Prozessen entgegen."""
    gesammelt = list(pfade)
    start = time.monotonic()
    letzte = start
    sock.settimeout(0.1)
    while (time.monotonic() - letzte < WARTEZEIT and
           time.monotonic() - start < MAX_WARTEZEIT):
        try:
            verbindung, _ = sock.accept()
        except socket.timeout:
            continue
        with verbindung:
            verbindung.settimeout(1)
            daten = b""
            try:
                while block := verbindung.recv(65536):
                    daten += block
                nachricht = json.loads(daten.decode("utf-8"))
            except (OSError, ValueError):
                continue
        if nachricht.get("aktion") == aktion:
            gesammelt.extend(nachricht.get("pfade", []))
            letzte = time.monotonic()
    sock.close()
    return gesammelt


def sammle_pfade(aktion: str, pfade: list[str]) -> list[str] | None:
    """
    Gibt alle eingesammelten Pfade zurück, wenn DIESER Prozess das Fenster
    zeigen soll – oder None, wenn ein anderer Prozess übernimmt.
    """
    sock = _als_sammler_starten()
    if sock is None:
        if _an_sammler_senden(aktion, pfade):
            return None  # erledigt, der andere Prozess zeigt alles an
        return pfade      # Notfall: selbst anzeigen
    return _einsammeln(sock, aktion, pfade)


def main(argumente: list[str] | None = None) -> None:
    argumente = sys.argv[1:] if argumente is None else argumente
    aktion, pfade = lese_argumente(argumente)

    if aktion is None:
        from .gui import main as hauptfenster
        hauptfenster(pfade)  # evtl. mit Pfaden, z. B. per Drag & Drop auf die .exe
        return

    pfade = sammle_pfade(aktion, pfade)
    if pfade is None:
        return

    # Erst jetzt die (langsamere) Oberfläche laden
    from . import gui
    gui.starte_aus_explorer(aktion, pfade)


if __name__ == "__main__":
    main()
