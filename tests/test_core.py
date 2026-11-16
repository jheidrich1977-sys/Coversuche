"""Automatische Tests für die Logik (ohne Internet, ohne Fenster)."""

import io
from pathlib import Path

from mutagen.id3 import ID3, TIT2, TPE1
from PIL import Image

from coversuche import core

# Ein paar Bytes, die wie MP3-Audio aussehen (für die Tests reicht das).
MP3_DATEN = (b"\xff\xfb\x90\x64" + b"\x00" * 413) * 5


def mp3(pfad: Path, kuenstler: str = "", titel: str = "") -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(MP3_DATEN)
    if kuenstler or titel:
        tags = ID3()
        tags.add(TPE1(encoding=3, text=kuenstler))
        tags.add(TIT2(encoding=3, text=titel))
        tags.save(pfad, v2_version=3)
    return pfad


def bild(farbe="red", format="PNG") -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", (50, 50), farbe).save(puffer, format=format)
    return puffer.getvalue()


def test_finde_mp3_mit_und_ohne_unterordner(tmp_path):
    mp3(tmp_path / "a.mp3")
    mp3(tmp_path / "B.MP3")
    mp3(tmp_path / "unter" / "c.mp3")
    (tmp_path / "notiz.txt").write_text("x")
    assert [p.name for p in core.finde_mp3_dateien(tmp_path, False)] == ["a.mp3", "B.MP3"]
    assert len(core.finde_mp3_dateien(tmp_path, True)) == 3


def test_cover_schreiben_und_lesen(tmp_path):
    datei = mp3(tmp_path / "lied.mp3")
    assert not core.hat_cover(datei)
    core.schreibe_cover(datei, core.als_jpeg(bild()))
    assert core.hat_cover(datei)
    assert Image.open(io.BytesIO(core.lese_cover(datei))).format == "JPEG"


def test_vorhandene_tags_bleiben_erhalten(tmp_path):
    datei = mp3(tmp_path / "lied.mp3", "Queen", "Bohemian Rhapsody")
    core.schreibe_cover(datei, core.als_jpeg(bild()))
    assert core.lese_kuenstler_titel(datei) == ("Queen", "Bohemian Rhapsody")


def test_suchbegriff_aus_dateiname():
    f = lambda n: core.suchbegriff_aus_dateiname(Path(n))
    assert f("03 - Queen - Bohemian Rhapsody (Official Video).mp3") == "Queen Bohemian Rhapsody"
    assert f("Adele_-_Hello [HQ].mp3") == "Adele Hello"
    assert f("12. Nena - 99 Luftballons.mp3") == "Nena 99 Luftballons"


def test_passt():
    assert core._passt("Queen Bohemian Rhapsody", "Queen – Bohemian Rhapsody")
    assert not core._passt("Queen Bohemian Rhapsody", "Helene Fischer – Atemlos")


def test_bearbeite_datei_alle_faelle(tmp_path, monkeypatch):
    mit = mp3(tmp_path / "Queen - Bohemian Rhapsody.mp3")
    core.schreibe_cover(mit, core.als_jpeg(bild()))
    ohne = mp3(tmp_path / "Adele - Hello.mp3")
    unbekannt = mp3(tmp_path / "Gibt es nicht.mp3")

    def falsche_suche(begriff, sitzung=None):
        if "Adele" in begriff:
            return core.Treffer("Test", "Adele – Hello", "x"), core.als_jpeg(bild("blue"))
        return None

    monkeypatch.setattr(core, "suche_cover_online", falsche_suche)
    assert core.bearbeite_datei(mit)[0] == core.STATUS_VORHANDEN
    assert core.bearbeite_datei(ohne)[0] == core.STATUS_ERGAENZT
    assert core.hat_cover(ohne)
    assert core.bearbeite_datei(unbekannt)[0] == core.STATUS_NICHT_GEFUNDEN


def test_logbuch(tmp_path):
    log = core.Logbuch(tmp_path)
    log.eintrag(tmp_path / "a.mp3", core.STATUS_ERGAENZT, "iTunes: X")
    log.eintrag(tmp_path / "b.mp3", core.STATUS_VORHANDEN)
    log.schliessen()
    text = log.pfad.read_text(encoding="utf-8-sig")
    assert "Cover ergänzt" in text and "a.mp3" in text
    assert "Cover schon vorhanden: 1" in text


def test_cover_entfernen(tmp_path):
    datei = mp3(tmp_path / "lied.mp3", "Queen", "Bohemian Rhapsody")
    assert core.entferne_cover(datei) is False  # nichts zu entfernen
    core.schreibe_cover(datei, core.als_jpeg(bild()))
    assert core.entferne_cover(datei) is True
    assert not core.hat_cover(datei)
    assert core.lese_kuenstler_titel(datei) == ("Queen", "Bohemian Rhapsody")


def test_cover_aus_bilddatei(tmp_path):
    datei = mp3(tmp_path / "lied.mp3")
    jpg = tmp_path / "cover.jpg"
    jpg.write_bytes(bild("green", "JPEG"))
    core.cover_aus_bilddatei(datei, jpg)
    assert core.hat_cover(datei)


def test_tag_felder_lesen_und_schreiben(tmp_path):
    datei = mp3(tmp_path / "lied.mp3", "Queen", "Bohemian Rhapsody")
    core.schreibe_cover(datei, core.als_jpeg(bild()))
    werte = core.lese_tag_felder(datei)
    assert werte["TPE1"] == "Queen" and werte["TALB"] == ""

    werte.update({"TALB": "A Night at the Opera", "TDRC": "1975",
                  "TRCK": "11", "TCON": "Rock", "COMM": "Klassiker",
                  "TPE1": ""})  # leeres Feld = löschen
    core.schreibe_tag_felder(datei, werte)

    neu = core.lese_tag_felder(datei)
    assert neu["TALB"] == "A Night at the Opera"
    assert neu["TDRC"] == "1975"
    assert neu["TRCK"] == "11"
    assert neu["TCON"] == "Rock"
    assert neu["COMM"] == "Klassiker"
    assert neu["TPE1"] == ""
    assert core.hat_cover(datei)  # Cover bleibt erhalten


def test_tag_felder_bei_datei_ohne_tag(tmp_path):
    datei = mp3(tmp_path / "leer.mp3")
    assert all(w == "" for w in core.lese_tag_felder(datei).values())
    core.schreibe_tag_felder(datei, {"TIT2": "Neu"})
    assert core.lese_tag_felder(datei)["TIT2"] == "Neu"
