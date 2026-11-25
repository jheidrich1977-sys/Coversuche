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
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests
from mutagen.id3 import APIC, COMM, ID3, Frames, ID3NoHeaderError
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


# Cover-Größe in Pixeln (längere Seite): kleinere Bilder werden auf
# MIN_GROESSE vergrößert, größere auf MAX_GROESSE verkleinert.
MIN_GROESSE = 600
MAX_GROESSE = 1000


def als_jpeg(bilddaten: bytes, min_groesse: int = MIN_GROESSE,
             max_groesse: int = MAX_GROESSE) -> bytes:
    """
    Prüft, ob es wirklich ein Bild ist, bringt es auf eine passende Größe
    und speichert es als JPEG. Das Seitenverhältnis bleibt immer erhalten.
    """
    bild = Image.open(io.BytesIO(bilddaten))
    bild = bild.convert("RGB")
    laengste_seite = max(bild.size)
    if laengste_seite < min_groesse:
        # Zu klein → hochskalieren (LANCZOS ergibt das schärfste Ergebnis)
        faktor = min_groesse / laengste_seite
        neue_groesse = (max(1, round(bild.width * faktor)),
                        max(1, round(bild.height * faktor)))
        bild = bild.resize(neue_groesse, Image.Resampling.LANCZOS)
    else:
        # Zu groß → verkleinern (macht nichts, wenn es schon passt)
        bild.thumbnail((max_groesse, max_groesse), Image.Resampling.LANCZOS)
    puffer = io.BytesIO()
    bild.save(puffer, format="JPEG", quality=90)
    return puffer.getvalue()


def entferne_cover(datei: Path) -> bool:
    """Löscht alle Bilder aus dem ID3-Tag. True, wenn etwas gelöscht wurde."""
    tags = lade_tags(datei)
    if tags is None or not tags.getall("APIC"):
        return False
    tags.delall("APIC")
    tags.save(datei, v2_version=3)
    return True


def cover_aus_bilddatei(datei: Path, bildpfad: str | Path) -> None:
    """Liest ein Bild von der Festplatte und schreibt es als Cover in die MP3."""
    bilddaten = Path(bildpfad).read_bytes()
    schreibe_cover(datei, als_jpeg(bilddaten))


# --- ID3-Tag bearbeiten ----------------------------------------------------

# Die Felder, die man im Bearbeiten-Fenster sieht: (Anzeigename, ID3-Kennung)
TAG_FELDER = [
    ("Titel", "TIT2"),
    ("Interpret", "TPE1"),
    ("Album", "TALB"),
    ("Album-Interpret", "TPE2"),
    ("Jahr", "TDRC"),
    ("Titelnummer", "TRCK"),
    ("CD-Nummer", "TPOS"),
    ("Genre", "TCON"),
    ("Komponist", "TCOM"),
    ("Kommentar", "COMM"),
]


def _kommentar_schluessel(tags: ID3) -> list[str]:
    """Die "normalen" Kommentare (ohne Beschreibung), nicht die von iTunes & Co."""
    return [k for k in tags.keys()
            if k.startswith("COMM") and tags[k].desc == ""]


def lese_tag_felder(datei: Path) -> dict[str, str]:
    """Liest alle Felder aus TAG_FELDER. Fehlende Felder sind leer."""
    tags = lade_tags(datei)
    werte = {kennung: "" for _, kennung in TAG_FELDER}
    if tags is None:
        return werte
    for _, kennung in TAG_FELDER:
        if kennung == "COMM":
            schluessel = _kommentar_schluessel(tags)
            if schluessel:
                werte["COMM"] = str(tags[schluessel[0]])
        elif kennung in tags:
            werte[kennung] = str(tags[kennung])
    return werte


def schreibe_tag_felder(datei: Path, werte: dict[str, str]) -> None:
    """
    Schreibt die Felder in den ID3-Tag. Ein leeres Feld wird gelöscht.
    Alles andere im Tag (z. B. das Cover) bleibt unverändert.
    """
    tags = lade_tags(datei) or ID3()
    for kennung, wert in werte.items():
        wert = wert.strip()
        if kennung == "COMM":
            sprache = "eng"
            for schluessel in _kommentar_schluessel(tags):
                sprache = tags[schluessel].lang or sprache
                del tags[schluessel]
            if wert:
                tags.add(COMM(encoding=3, lang=sprache, desc="", text=wert))
            continue
        tags.delall(kennung)
        if wert:
            tags.add(Frames[kennung](encoding=3, text=wert))
    tags.save(datei, v2_version=3)


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
# 6. Einstellungen merken (z. B. den zuletzt benutzten Cover-Ordner)
# ---------------------------------------------------------------------------

def einstellungs_datei() -> Path:
    """Unter Windows: C:\\Users\\<Name>\\AppData\\Roaming\\Coversuche\\einstellungen.json"""
    basis = os.environ.get("APPDATA") or Path.home()
    return Path(basis) / "Coversuche" / "einstellungen.json"


def lade_einstellungen() -> dict:
    try:
        return json.loads(einstellungs_datei().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # noch keine Datei oder kaputt → mit leeren Werten starten


def speichere_einstellung(schluessel: str, wert) -> None:
    einstellungen = lade_einstellungen()
    einstellungen[schluessel] = wert
    try:
        pfad = einstellungs_datei()
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(json.dumps(einstellungen, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    except OSError:
        pass  # Merken ist nur Komfort – wenn es nicht klappt, ist das kein Drama


# ---------------------------------------------------------------------------
# 7. Log-Datei
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


# ---------------------------------------------------------------------------
# 8. Dateien und Ordner aus dem Explorer in eine MP3-Liste verwandeln
# ---------------------------------------------------------------------------

def sammle_mp3(pfade: list[str | Path], mit_unterordnern: bool = False) -> list[Path]:
    """
    Aus einer Mischung von Dateien und Ordnern (z. B. aus dem Explorer)
    eine Liste aller MP3-Dateien machen – ohne doppelte Einträge.
    """
    ergebnis: dict[str, Path] = {}
    for pfad in pfade:
        pfad = Path(pfad)
        if pfad.is_dir():
            for datei in finde_mp3_dateien(pfad, mit_unterordnern):
                ergebnis.setdefault(str(datei).lower(), datei)
        elif pfad.is_file() and pfad.suffix.lower() == ".mp3":
            ergebnis.setdefault(str(pfad).lower(), pfad)
    return sorted(ergebnis.values(), key=lambda p: str(p).lower())


# ---------------------------------------------------------------------------
# 9. ID3-Tag mehrerer Dateien gleichzeitig bearbeiten
# ---------------------------------------------------------------------------

# Felder, die bei mehreren Dateien NICHT gemeinsam geändert werden dürfen,
# weil sie für jedes Lied anders sind.
NUR_EINZELN = {"TIT2", "TRCK"}


def gemeinsame_tag_felder(dateien: list[Path]) -> dict[str, str | None]:
    """
    Für jedes Feld: der Wert, wenn er in ALLEN Dateien gleich ist,
    sonst None (= "verschiedene Werte").
    """
    gemeinsam: dict[str, str | None] = {}
    for nr, datei in enumerate(dateien):
        werte = lese_tag_felder(datei)
        for kennung, wert in werte.items():
            if nr == 0:
                gemeinsam[kennung] = wert
            elif gemeinsam.get(kennung) != wert:
                gemeinsam[kennung] = None
    return gemeinsam


# ---------------------------------------------------------------------------
# 10. Dateinamen aus dem ID3-Tag bilden
#     Schema: Interpret - Album - 01 - Titel.mp3
# ---------------------------------------------------------------------------

# Zeichen, die in Windows-Dateinamen verboten sind
_VERBOTEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sauber(text: str) -> str:
    """Macht einen Text als Teil eines Dateinamens tauglich."""
    text = _VERBOTEN.sub("_", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().rstrip(".")


def tracknummer_zweistellig(track: str) -> str:
    """ "3" → "03", "3/12" → "03", "12" → "12", "" → "" """
    treffer = re.match(r"\s*(\d+)", track or "")
    if not treffer:
        return ""
    return f"{int(treffer.group(1)):02d}"


def neuer_dateiname(datei: Path) -> tuple[str | None, str]:
    """
    Liefert (neuer Name, Hinweis). Ist der neue Name None, kann die Datei
    nicht umbenannt werden – der Hinweis sagt dann, warum.
    Album und Tracknummer werden weggelassen, wenn sie im Tag fehlen.
    """
    werte = lese_tag_felder(datei)
    interpret = _sauber(werte["TPE1"])
    album = _sauber(werte["TALB"])
    track = tracknummer_zweistellig(werte["TRCK"])
    titel = _sauber(werte["TIT2"])

    if not interpret or not titel:
        fehlt = " und ".join(n for n, w in (("Interpret", interpret),
                                            ("Titel", titel)) if not w)
        return None, f"{fehlt} fehlt im ID3-Tag"

    teile = [interpret, album, track, titel]
    name = " - ".join(t for t in teile if t)
    # Windows erlaubt höchstens 255 Zeichen pro Dateiname
    name = name[:250 - len(".mp3")].rstrip(" .")
    hinweis = ""
    fehlend = [n for n, w in (("Album", album), ("Tracknummer", track)) if not w]
    if fehlend:
        hinweis = " und ".join(fehlend) + " fehlt – weggelassen"
    return name + ".mp3", hinweis


@dataclass
class Umbenennung:
    alt: Path
    neu: Path | None   # None = wird nicht umbenannt
    hinweis: str


def plane_umbenennung(dateien: list[Path]) -> list[Umbenennung]:
    """Berechnet für jede Datei den neuen Namen – ändert aber noch nichts."""
    plan: list[Umbenennung] = []
    vergeben: set[str] = set()
    for datei in dateien:
        try:
            name, hinweis = neuer_dateiname(datei)
        except Exception as fehler:
            plan.append(Umbenennung(datei, None, f"Fehler: {fehler}"))
            continue
        if name is None:
            plan.append(Umbenennung(datei, None, hinweis))
            continue
        ziel = datei.with_name(name)
        schluessel = str(ziel).lower()  # Windows unterscheidet nicht Groß/klein
        if ziel.name == datei.name:
            plan.append(Umbenennung(datei, None, "Name ist schon richtig"))
        elif schluessel in vergeben or (ziel.exists() and
                                        str(ziel).lower() != str(datei).lower()):
            plan.append(Umbenennung(datei, None,
                                    f"„{name}“ gibt es schon"))
        else:
            vergeben.add(schluessel)
            plan.append(Umbenennung(datei, ziel, hinweis))
    return plan


def fuehre_umbenennung_aus(plan: list[Umbenennung]) -> list[tuple[Umbenennung, str]]:
    """Benennt um. Gibt pro Datei (Eintrag, Ergebnis-Text) zurück."""
    ergebnisse = []
    for eintrag in plan:
        if eintrag.neu is None:
            ergebnisse.append((eintrag, "übersprungen"))
            continue
        try:
            eintrag.alt.rename(eintrag.neu)
            ergebnisse.append((eintrag, "umbenannt"))
        except OSError as fehler:
            ergebnisse.append((eintrag, f"Fehler: {fehler}"))
    return ergebnisse
