"""Tests für Umbenennen, Mehrfach-Bearbeitung und Explorer-Start."""

import threading

from mutagen.id3 import ID3, TALB, TIT2, TPE1, TRCK

from coversuche import core, explorer
from tests.test_core import mp3


def mit_tag(pfad, interpret="", titel="", album="", track=""):
    datei = mp3(pfad)
    tags = ID3()
    for rahmen, wert in ((TPE1, interpret), (TIT2, titel),
                         (TALB, album), (TRCK, track)):
        if wert:
            tags.add(rahmen(encoding=3, text=wert))
    tags.save(datei, v2_version=3)
    return datei


def test_tracknummer_zweistellig():
    assert core.tracknummer_zweistellig("3") == "03"
    assert core.tracknummer_zweistellig("3/12") == "03"
    assert core.tracknummer_zweistellig("12") == "12"
    assert core.tracknummer_zweistellig("") == ""
    assert core.tracknummer_zweistellig("abc") == ""


def test_neuer_dateiname_vollstaendig(tmp_path):
    datei = mit_tag(tmp_path / "x.mp3", "Queen", "Bohemian Rhapsody",
                    "A Night at the Opera", "11/12")
    assert core.neuer_dateiname(datei) == (
        "Queen - A Night at the Opera - 11 - Bohemian Rhapsody.mp3", "")


def test_neuer_dateiname_verbotene_zeichen_und_fehlendes(tmp_path):
    datei = mit_tag(tmp_path / "x.mp3", "AC/DC", "What? Me: Worry", track="1")
    name, hinweis = core.neuer_dateiname(datei)
    assert name == "AC_DC - 01 - What_ Me_ Worry.mp3"
    assert "Album" in hinweis
    ohne = mit_tag(tmp_path / "y.mp3", "Queen")
    assert core.neuer_dateiname(ohne)[0] is None


def test_umbenennen_plan_und_ausfuehren(tmp_path):
    a = mit_tag(tmp_path / "a.mp3", "Nena", "99 Luftballons", "Nena", "4")
    b = mit_tag(tmp_path / "b.mp3", "Nena", "99 Luftballons", "Nena", "4")  # gleicher Name!
    c = mit_tag(tmp_path / "c.mp3")                                         # kein Tag
    plan = core.plane_umbenennung([a, b, c])
    assert plan[0].neu.name == "Nena - Nena - 04 - 99 Luftballons.mp3"
    assert plan[1].neu is None and "gibt es schon" in plan[1].hinweis
    assert plan[2].neu is None
    core.fuehre_umbenennung_aus(plan)
    assert (tmp_path / "Nena - Nena - 04 - 99 Luftballons.mp3").exists()
    assert b.exists() and c.exists() and not a.exists()


def test_bereits_richtiger_name_wird_uebersprungen(tmp_path):
    datei = mit_tag(tmp_path / "Queen - Hits - 01 - Hallo.mp3",
                    "Queen", "Hallo", "Hits", "1")
    assert core.plane_umbenennung([datei])[0].neu is None


def test_sammle_mp3_aus_dateien_und_ordnern(tmp_path):
    a = mp3(tmp_path / "a.mp3")
    mp3(tmp_path / "unter" / "b.mp3")
    (tmp_path / "bild.jpg").write_bytes(b"x")
    assert core.sammle_mp3([tmp_path]) == [a]                  # ohne Unterordner
    assert len(core.sammle_mp3([tmp_path], True)) == 2
    assert core.sammle_mp3([a, a, tmp_path / "bild.jpg"]) == [a]


def test_gemeinsame_tag_felder(tmp_path):
    a = mit_tag(tmp_path / "a.mp3", "Queen", "Eins", "Hits")
    b = mit_tag(tmp_path / "b.mp3", "Queen", "Zwei", "Hits")
    werte = core.gemeinsame_tag_felder([a, b])
    assert werte["TPE1"] == "Queen" and werte["TALB"] == "Hits"
    assert werte["TIT2"] is None  # verschieden


def test_explorer_argumente():
    assert explorer.lese_argumente(["--cover", "C:\\a.mp3"]) == ("cover", ["C:\\a.mp3"])
    assert explorer.lese_argumente([]) == (None, [])


def test_explorer_sammelt_mehrere_aufrufe(monkeypatch):
    monkeypatch.setattr(explorer, "PORT", 47999)
    ergebnis = {}

    def erster():
        ergebnis["erster"] = explorer.sammle_pfade("tag", ["1.mp3"])

    faden = threading.Thread(target=erster)
    faden.start()
    import time
    time.sleep(0.2)
    zweiter = explorer.sammle_pfade("tag", ["2.mp3"])
    dritter = explorer.sammle_pfade("tag", ["3.mp3"])
    faden.join()
    assert zweiter is None and dritter is None  # haben an den ersten übergeben
    assert sorted(ergebnis["erster"]) == ["1.mp3", "2.mp3", "3.mp3"]
