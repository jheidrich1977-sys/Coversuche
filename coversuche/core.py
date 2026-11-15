"""
Die eigentliche Arbeit von Coversuche – ganz ohne Oberfläche.

Hier steht alles, was mit MP3-Dateien, Covern und dem Internet zu tun hat:
  * MP3-Dateien in einem Ordner finden
  * prüfen, ob im ID3-Tag schon ein Cover steckt
  * aus dem Dateinamen einen Suchbegriff machen
  * online nach einem Cover suchen (iTunes, ersatzweise Deezer)
  * das gefundene Cover in die MP3-Datei schreiben
  * eine Log-Datei schreiben

Die Oberfläche (gui.py) ruft nur diese Funktionen auf. Dadurch kann man
die Logik auch ohne Fenster testen.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests
from mutagen.id3 import APIC, ID3, ID3NoHeaderError
from PIL import Image

# Wie sich das Programm bei den Online-Diensten vorstellt.
USER_AGENT = "Coversuche/1.0 (MP3-Cover-Werkzeug)"
TIMEOUT = 15  # Sekunden, die wir maximal auf eine Antwort warten

# Mögliche Ergebnisse pro Datei (stehen so auch im Log).
STATUS_VORHANDEN = "Cover schon vorhanden"
STATUS_FEHLT = "Kein Cover"
STATUS_ERGAENZT = "Cover ergänzt"
STATUS_NICHT_GEFUNDEN = "Kein Cover gefunden"
STATUS_FEHLER = "Fehler"


# ---------------------------------------------------------------------------
# 1. MP3-Dateien finden
# ---------------------------------------------------------------------------

def finde_mp3_dateien(ordner: str | Path, mit_unterordnern: bool) -> list[Path]:
    """Liefert alle MP3-Dateien im Ordner, alphabetisch sortiert."""
    ordner = Path(ordner)
    muster = ordner.rglob("*") if mit_unterordnern else ordner.glob("*")
    dateien = [p for p in muster if p.is_file() and p.suffix.lower() == ".mp3"]
    return sorted(dateien, key=lambda p: str(p).lower())


# ---------------------------------------------------------------------------
# 2. Cover im ID3-Tag lesen und schreiben
# ---------------------------------------------------------------------------

def lade_tags(datei: Path) -> ID3 | None:
    """Liest den ID3-Tag. Gibt None zurück, wenn die Datei noch keinen hat."""
    try:
        return ID3(datei)
    except ID3NoHeaderError:
        return None


def lese_cover(datei: Path) -> bytes | None:
    """Gibt die Bilddaten des Covers zurück – oder None, wenn keins da ist."""
    tags = lade_tags(datei)
    if tags is None:
        return None
    bilder = tags.getall("APIC")
    if not bilder:
        return None
    # Bevorzugt das "Front Cover" (Typ 3), sonst irgendein Bild.
    for bild in bilder:
        if bild.type == 3:
            return bild.data
    return bilder[0].data


def hat_cover(datei: Path) -> bool:
    return lese_cover(datei) is not None


def lese_kuenstler_titel(datei: Path) -> tuple[str, str]:
    """Künstler und Titel aus dem ID3-Tag (leer, falls nicht vorhanden)."""
    tags = lade_tags(datei)
    if tags is None:
        return "", ""
    kuenstler = str(tags.get("TPE1", "") or "").strip()
    titel = str(tags.get("TIT2", "") or "").strip()
    return kuenstler, titel


def schreibe_cover(datei: Path, bilddaten: bytes) -> None:
    """Schreibt das Bild als Front-Cover in den ID3-Tag der Datei."""
    tags = lade_tags(datei) or ID3()
    tags.delall("APIC")
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3,
                  desc="Cover", data=bilddaten))
    # ID3 Version 2.3 versteht auch der Windows-Explorer.
    tags.save(datei, v2_version=3)


def als_jpeg(bilddaten: bytes, max_groesse: int = 1000) -> bytes:
    """Prüft, ob es wirklich ein Bild ist, und speichert es als JPEG."""
    bild = Image.open(io.BytesIO(bilddaten))
    bild = bild.convert("RGB")
    bild.thumbnail((max_groesse, max_groesse))
    puffer = io.BytesIO()
    bild.save(puffer, format="JPEG", quality=90)
    return puffer.getvalue()


# ---------------------------------------------------------------------------
# 3. Suchbegriff aus dem Dateinamen bauen
# ---------------------------------------------------------------------------

# Dinge, die in Dateinamen oft vorkommen, aber die Suche stören.
_STOERWOERTER = re.compile(
    r"\b(official|video|audio|lyrics?|hq|hd|320 ?kbps|128 ?kbps|remastered"
    r"|explicit|mp3|clip)\b",
    re.IGNORECASE,
)


def suchbegriff_aus_dateiname(datei: Path) -> str:
    """
    Macht aus z. B. "03 - Queen - Bohemian Rhapsody (Official Video).mp3"
    den Suchbegriff "Queen Bohemian Rhapsody".
    """
    name = datei.stem
    name = name.replace("_", " ")
    name = re.sub(r"[\(\[\{].*?[\)\]\}]", " ", name)      # (…) [ … ] { … }
    name = re.sub(r"^\s*(cd\s*)?\d{1,3}\s*[-._)]*\s+", "", name,
                  flags=re.IGNORECASE)                       # Tracknummer vorne
    name = _STOERWOERTER.sub(" ", name)
    name = re.sub(r"\s+-\s+|\s+–\s+", " ", name)             # Trennstriche
    name = re.sub(r"\s+", " ", name)
    return name.strip(" -.")


def _woerter(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _passt(suchbegriff: str, gefunden: str) -> bool:
    """
    Grobe Prüfung, ob ein Suchergebnis zum Suchbegriff passt:
    Mindestens 60 % der Wörter aus dem Suchbegriff müssen vorkommen.
    So verhindern wir, dass völlig falsche Cover eingetragen werden.
    """
    such = _woerter(suchbegriff)
    if not such:
        return False
    treffer = len(such & _woerter(gefunden))
    return treffer / len(such) >= 0.6


# ---------------------------------------------------------------------------
# 4. Online nach einem Cover suchen
# ---------------------------------------------------------------------------

@dataclass
class Treffer:
    quelle: str        # z. B. "iTunes"
    beschreibung: str  # z. B. "Queen – Bohemian Rhapsody"
    bild_url: str


def _suche_itunes(suchbegriff: str, sitzung: requests.Session) -> Treffer | None:
    antwort = sitzung.get(
        "https://itunes.apple.com/search",
        params={"term": suchbegriff, "media": "music", "entity": "song",
                "limit": 10},
        timeout=TIMEOUT,
    )
    antwort.raise_for_status()
    for eintrag in antwort.json().get("results", []):
        beschreibung = (f"{eintrag.get('artistName', '')} – "
                        f"{eintrag.get('trackName', '')}")
        url = eintrag.get("artworkUrl100")
        if url and _passt(suchbegriff, beschreibung):
            # iTunes liefert kleine Bilder; über die URL bekommt man größere.
            url = url.replace("100x100bb", "600x600bb")
            return Treffer("iTunes", beschreibung, url)
    return None


def _suche_deezer(suchbegriff: str, sitzung: requests.Session) -> Treffer | None:
    antwort = sitzung.get(
        "https://api.deezer.com/search",
        params={"q": suchbegriff, "limit": 10},
        timeout=TIMEOUT,
    )
    antwort.raise_for_status()
    for eintrag in antwort.json().get("data", []):
        kuenstler = (eintrag.get("artist") or {}).get("name", "")
        beschreibung = f"{kuenstler} – {eintrag.get('title', '')}"
        album = eintrag.get("album") or {}
        url = album.get("cover_xl") or album.get("cover_big")
        if url and _passt(suchbegriff, beschreibung):
            return Treffer("Deezer", beschreibung, url)
    return None


def suche_cover_online(suchbegriff: str,
                       sitzung: requests.Session | None = None
                       ) -> tuple[Treffer, bytes] | None:
    """Sucht nacheinander bei iTunes und Deezer. Gibt Treffer + Bild zurück."""
    if not suchbegriff:
        return None
    sitzung = sitzung or neue_sitzung()
    for suche in (_suche_itunes, _suche_deezer):
        try:
            treffer = suche(suchbegriff, sitzung)
            if treffer is None:
                continue
            bild = sitzung.get(treffer.bild_url, timeout=TIMEOUT)
            bild.raise_for_status()
            return treffer, als_jpeg(bild.content)
        except (requests.RequestException, ValueError, OSError):
            # Dienst nicht erreichbar oder kaputte Antwort → nächsten probieren
            continue
    return None


def neue_sitzung() -> requests.Session:
    sitzung = requests.Session()
    sitzung.headers["User-Agent"] = USER_AGENT
    return sitzung


# ---------------------------------------------------------------------------
# 5. Eine Datei komplett bearbeiten
# ---------------------------------------------------------------------------

def bearbeite_datei(datei: Path,
                    sitzung: requests.Session | None = None
                    ) -> tuple[str, str]:
    """
    Prüft eine Datei und ergänzt bei Bedarf das Cover.
    Gibt (Status, Details) zurück, z. B. ("Cover ergänzt", "iTunes: …").
    """
    try:
        if hat_cover(datei):
            return STATUS_VORHANDEN, ""

        # Erst mit dem Dateinamen suchen …
        suchbegriffe = [suchbegriff_aus_dateiname(datei)]
        # … und falls das nichts bringt, mit Künstler/Titel aus dem Tag.
        kuenstler, titel = lese_kuenstler_titel(datei)
        if kuenstler and titel:
            suchbegriffe.append(f"{kuenstler} {titel}")

        for begriff in dict.fromkeys(b for b in suchbegriffe if b):
            ergebnis = suche_cover_online(begriff, sitzung)
            if ergebnis:
                treffer, bild = ergebnis
                schreibe_cover(datei, bild)
                return (STATUS_ERGAENZT,
                        f"{treffer.quelle}: {treffer.beschreibung} "
                        f"(Suche: \"{begriff}\")")

        return STATUS_NICHT_GEFUNDEN, f"Suche: \"{suchbegriffe[0]}\""
    except Exception as fehler:  # z. B. Datei schreibgeschützt oder kaputt
        return STATUS_FEHLER, f"{type(fehler).__name__}: {fehler}"


# ---------------------------------------------------------------------------
# 6. Log-Datei
# ---------------------------------------------------------------------------

class Logbuch:
    """Schreibt jede Aktion sofort in eine Textdatei."""

    def __init__(self, ordner: str | Path):
        zeit = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.pfad = Path(ordner) / f"Coversuche_Log_{zeit}.txt"
        self._datei = open(self.pfad, "w", encoding="utf-8-sig")
        self._datei.write(f"Coversuche – Protokoll vom "
                          f"{datetime.now():%d.%m.%Y %H:%M:%S}\n")
        self._datei.write(f"Ordner: {ordner}\n\n")
        self._zaehler: dict[str, int] = {}

    def eintrag(self, datei: Path, status: str, details: str = "") -> None:
        zeile = f"{datetime.now():%H:%M:%S} | {status:<22} | {datei}"
        if details:
            zeile += f" | {details}"
        self._datei.write(zeile + "\n")
        self._datei.flush()
        self._zaehler[status] = self._zaehler.get(status, 0) + 1

    def schliessen(self, abgebrochen: bool = False) -> None:
        self._datei.write("\nZusammenfassung:\n")
        for status, anzahl in sorted(self._zaehler.items()):
            self._datei.write(f"  {status}: {anzahl}\n")
        if abgebrochen:
            self._datei.write("  (Vorgang wurde vorzeitig abgebrochen)\n")
        self._datei.close()
