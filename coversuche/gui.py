"""
Die Oberfläche von Coversuche (das Fenster, das man sieht).

Aufbau:
  oben:   Ordner wählen, "Unterordner einbeziehen", Knöpfe
  links:  scrollbare Liste aller MP3-Dateien mit Status
  rechts: Vorschau des Covers der ausgewählten Datei
  unten:  Fortschrittsbalken und Statuszeile

Langsame Arbeiten (Ordner einlesen, online suchen) laufen in einem
Hintergrund-Thread, damit das Fenster dabei nicht "einfriert".
Der Thread schickt seine Ergebnisse über eine Warteschlange (queue)
an das Fenster.
"""

from __future__ import annotations

import io
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from . import core

VORSCHAU_GROESSE = 360  # Pixel

# Farben für die Statusspalte der Dateiliste
FARBEN = {
    core.STATUS_VORHANDEN: "#1b7f3b",
    core.STATUS_ERGAENZT: "#0b5cad",
    core.STATUS_FEHLT: "#a15c00",
    core.STATUS_NICHT_GEFUNDEN: "#b3261e",
    core.STATUS_FEHLER: "#b3261e",
}


class CoversucheApp:
    def __init__(self, fenster: tk.Tk, start_pfade: list[str] | None = None,
                 sofort_ergaenzen: bool = False):
        """
        start_pfade: Dateien/Ordner, die gleich beim Start geladen werden
                     (z. B. aus dem Explorer-Kontextmenü).
        sofort_ergaenzen: nach dem Einlesen automatisch die Coversuche starten.
        """
        self.fenster = fenster
        self.fenster.title("Coversuche – MP3-Cover finden und ergänzen")
        self.fenster.geometry("1100x650")
        self.fenster.minsize(800, 450)

        self.ordner = tk.StringVar()
        self.unterordner = tk.BooleanVar(value=True)
        self.statuszeile = tk.StringVar(value="Bitte einen Ordner wählen.")

        self.dateien: list[Path] = []
        self.nachrichten: queue.Queue = queue.Queue()
        self.stopp = threading.Event()
        self.arbeitet = False
        self._vorschau_bild = None  # muss gemerkt werden, sonst verschwindet es

        self._sofort_ergaenzen = sofort_ergaenzen

        self._baue_oberflaeche()
        self.fenster.after(100, self._pruefe_nachrichten)
        if start_pfade:
            self.fenster.after(50, lambda: self._lade_start_pfade(start_pfade))

    def _lade_start_pfade(self, pfade: list[str]) -> None:
        """Lädt Dateien/Ordner, die beim Start übergeben wurden."""
        if len(pfade) == 1 and os.path.isdir(pfade[0]):
            # Ein Ordner: wie "Durchsuchen …", aber ohne Unterordner
            self.ordner.set(os.path.normpath(pfade[0]))
            self.unterordner.set(False)
            self._starte_einlesen()
            return
        dateien = core.sammle_mp3(pfade)
        if not dateien:
            messagebox.showinfo("Coversuche", "Keine MP3-Dateien gefunden.")
            return
        self.ordner.set(str(dateien[0].parent))
        self._starte_einlesen(dateien)

    # ------------------------------------------------------------------
    # Aufbau des Fensters
    # ------------------------------------------------------------------
    def _baue_oberflaeche(self) -> None:
        # --- obere Leiste ---------------------------------------------
        oben = ttk.Frame(self.fenster, padding=8)
        oben.pack(fill="x")

        ttk.Label(oben, text="Ordner:").pack(side="left")
        ttk.Entry(oben, textvariable=self.ordner).pack(
            side="left", fill="x", expand=True, padx=(4, 4))
        self.knopf_waehlen = ttk.Button(oben, text="Durchsuchen …",
                                        command=self._ordner_waehlen)
        self.knopf_waehlen.pack(side="left")
        ttk.Checkbutton(oben, text="Unterordner einbeziehen",
                        variable=self.unterordner).pack(side="left", padx=8)

        knoepfe = ttk.Frame(self.fenster, padding=(8, 0, 8, 8))
        knoepfe.pack(fill="x")
        self.knopf_einlesen = ttk.Button(knoepfe, text="1. Dateien einlesen",
                                         command=self._starte_einlesen)
        self.knopf_einlesen.pack(side="left")
        self.knopf_ergaenzen = ttk.Button(
            knoepfe, text="2. Fehlende Cover suchen und ergänzen",
            command=self._starte_ergaenzen, state="disabled")
        self.knopf_ergaenzen.pack(side="left", padx=6)
        self.knopf_stopp = ttk.Button(knoepfe, text="Stopp",
                                      command=self.stopp.set, state="disabled")
        self.knopf_stopp.pack(side="left")
        self.knopf_log = ttk.Button(knoepfe, text="Log öffnen",
                                    command=self._log_oeffnen, state="disabled")
        self.knopf_log.pack(side="right")
        self.log_pfad: Path | None = None

        # --- Mitte: links Liste, rechts Vorschau ----------------------
        mitte = ttk.PanedWindow(self.fenster, orient="horizontal")
        mitte.pack(fill="both", expand=True, padx=8)

        links = ttk.Frame(mitte)
        self.liste = ttk.Treeview(links, columns=("datei", "status"),
                                  show="headings", selectmode="browse")
        self.liste.heading("datei", text="Datei")
        self.liste.heading("status", text="Status")
        self.liste.column("datei", width=520, anchor="w")
        self.liste.column("status", width=170, anchor="w", stretch=False)
        for status, farbe in FARBEN.items():
            self.liste.tag_configure(status, foreground=farbe)
        scroll_y = ttk.Scrollbar(links, orient="vertical",
                                 command=self.liste.yview)
        scroll_x = ttk.Scrollbar(links, orient="horizontal",
                                 command=self.liste.xview)
        self.liste.configure(yscrollcommand=scroll_y.set,
                             xscrollcommand=scroll_x.set)
        self.liste.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        links.rowconfigure(0, weight=1)
        links.columnconfigure(0, weight=1)
        self.liste.bind("<<TreeviewSelect>>", self._auswahl_geaendert)
        # Rechtsklick öffnet das Kontextmenü (Button-3 = rechte Maustaste)
        self.liste.bind("<Button-3>", self._kontextmenue_zeigen)
        self.kontextmenue = tk.Menu(self.fenster, tearoff=False)
        self.kontextmenue.add_command(label="Cover entfernen",
                                      command=self._cover_entfernen)
        self.kontextmenue.add_command(label="Cover manuell hinzufügen …",
                                      command=self._cover_hinzufuegen)
        self.kontextmenue.add_separator()
        self.kontextmenue.add_command(label="ID3-Tag bearbeiten …",
                                      command=self._tag_bearbeiten)
        mitte.add(links, weight=3)

        rechts = ttk.Frame(mitte, padding=(12, 0, 0, 0))
        ttk.Label(rechts, text="Cover-Vorschau",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        # fester Rahmen, damit die Vorschau immer gleich groß bleibt
        rahmen = tk.Frame(rechts, width=VORSCHAU_GROESSE,
                          height=VORSCHAU_GROESSE, bg="#e8e8e8",
                          relief="groove", bd=2)
        rahmen.pack_propagate(False)
        rahmen.pack(pady=6)
        self.vorschau = tk.Label(rahmen, text="Keine Datei ausgewählt",
                                 bg="#e8e8e8", fg="#555")
        self.vorschau.pack(fill="both", expand=True)
        self.vorschau_info = ttk.Label(rechts, text="", wraplength=VORSCHAU_GROESSE,
                                       justify="left")
        self.vorschau_info.pack(anchor="w")
        mitte.add(rechts, weight=1)

        # --- untere Leiste --------------------------------------------
        unten = ttk.Frame(self.fenster, padding=8)
        unten.pack(fill="x")
        self.fortschritt = ttk.Progressbar(unten, mode="determinate")
        self.fortschritt.pack(fill="x")
        ttk.Label(unten, textvariable=self.statuszeile).pack(anchor="w",
                                                             pady=(4, 0))

    # ------------------------------------------------------------------
    # Knöpfe
    # ------------------------------------------------------------------
    def _ordner_waehlen(self) -> None:
        ordner = filedialog.askdirectory(title="Ordner mit MP3-Dateien wählen")
        if ordner:
            self.ordner.set(os.path.normpath(ordner))
            self._starte_einlesen()

    def _gueltiger_ordner(self) -> Path | None:
        ordner = Path(self.ordner.get().strip())
        if not self.ordner.get().strip() or not ordner.is_dir():
            messagebox.showwarning("Coversuche",
                                   "Bitte zuerst einen gültigen Ordner wählen.")
            return None
        return ordner

    def _starte_einlesen(self, feste_liste: list[Path] | None = None) -> None:
        """Liest den Ordner ein – oder, falls angegeben, genau diese Dateien."""
        ordner = self._gueltiger_ordner()
        if ordner is None:
            return
        self.liste.delete(*self.liste.get_children())
        self.dateien = []
        self._zeige_cover(None, "")
        self._beschaeftigt(True)
        self.statuszeile.set("Lese Dateien ein …")
        threading.Thread(target=self._arbeit_einlesen,
                         args=(ordner, self.unterordner.get(), feste_liste),
                         daemon=True).start()

    def _starte_ergaenzen(self) -> None:
        ordner = self._gueltiger_ordner()
        if ordner is None or not self.dateien:
            return
        try:
            logbuch = core.Logbuch(ordner)
        except OSError as fehler:
            messagebox.showerror("Coversuche",
                                 f"Log-Datei konnte nicht angelegt werden:\n{fehler}")
            return
        self.log_pfad = logbuch.pfad
        self._beschaeftigt(True)
        threading.Thread(target=self._arbeit_ergaenzen,
                         args=(list(self.dateien), logbuch),
                         daemon=True).start()

    def _log_oeffnen(self) -> None:
        if self.log_pfad and self.log_pfad.exists():
            os.startfile(self.log_pfad)  # öffnet die Datei im Standard-Editor

    def _beschaeftigt(self, ja: bool) -> None:
        self.arbeitet = ja
        self.stopp.clear()
        normal = "disabled" if ja else "normal"
        self.knopf_waehlen.configure(state=normal)
        self.knopf_einlesen.configure(state=normal)
        self.knopf_ergaenzen.configure(
            state="normal" if (not ja and self.dateien) else "disabled")
        self.knopf_stopp.configure(state="normal" if ja else "disabled")
        self.knopf_log.configure(
            state="normal" if (not ja and self.log_pfad) else "disabled")

    # ------------------------------------------------------------------
    # Hintergrund-Arbeiten (laufen NICHT im Fenster-Thread!)
    # ------------------------------------------------------------------
    def _arbeit_einlesen(self, ordner: Path, mit_unterordnern: bool,
                         feste_liste: list[Path] | None = None) -> None:
        try:
            dateien = (feste_liste if feste_liste is not None
                       else core.finde_mp3_dateien(ordner, mit_unterordnern))
        except OSError as fehler:
            self.nachrichten.put(("fehler", f"Ordner nicht lesbar: {fehler}"))
            self.nachrichten.put(("einlesen_fertig", 0))
            return
        self.nachrichten.put(("anzahl", len(dateien)))
        for nr, datei in enumerate(dateien):
            if self.stopp.is_set():
                break
            try:
                status = (core.STATUS_VORHANDEN if core.hat_cover(datei)
                          else core.STATUS_FEHLT)
            except Exception:
                status = core.STATUS_FEHLER
            self.nachrichten.put(("datei", (datei, status, ordner)))
            self.nachrichten.put(("fortschritt", nr + 1))
        self.nachrichten.put(("einlesen_fertig", len(dateien)))

    def _arbeit_ergaenzen(self, dateien: list[Path], logbuch: core.Logbuch) -> None:
        sitzung = core.neue_sitzung()
        self.nachrichten.put(("anzahl", len(dateien)))
        abgebrochen = False
        for nr, datei in enumerate(dateien):
            if self.stopp.is_set():
                abgebrochen = True
                break
            self.nachrichten.put(("text", f"Bearbeite {nr + 1}/{len(dateien)}: "
                                          f"{datei.name}"))
            status, details = core.bearbeite_datei(datei, sitzung)
            logbuch.eintrag(datei, status, details)
            self.nachrichten.put(("status", (nr, status)))
            self.nachrichten.put(("fortschritt", nr + 1))
        logbuch.schliessen(abgebrochen)
        self.nachrichten.put(("ergaenzen_fertig", abgebrochen))

    # ------------------------------------------------------------------
    # Nachrichten aus dem Hintergrund im Fenster anzeigen
    # ------------------------------------------------------------------
    def _pruefe_nachrichten(self) -> None:
        try:
            while True:
                art, inhalt = self.nachrichten.get_nowait()
                self._verarbeite(art, inhalt)
        except queue.Empty:
            pass
        self.fenster.after(100, self._pruefe_nachrichten)

    def _verarbeite(self, art: str, inhalt) -> None:
        if art == "anzahl":
            self.fortschritt.configure(maximum=max(inhalt, 1), value=0)
        elif art == "fortschritt":
            self.fortschritt.configure(value=inhalt)
        elif art == "text":
            self.statuszeile.set(inhalt)
        elif art == "fehler":
            messagebox.showerror("Coversuche", inhalt)
        elif art == "datei":
            datei, status, ordner = inhalt
            nr = len(self.dateien)
            self.dateien.append(datei)
            try:
                anzeige = str(datei.relative_to(ordner))
            except ValueError:
                anzeige = str(datei)
            self.liste.insert("", "end", iid=str(nr),
                              values=(anzeige, status), tags=(status,))
        elif art == "status":
            nr, status = inhalt
            iid = str(nr)
            self.liste.set(iid, "status", status)
            self.liste.item(iid, tags=(status,))
            if self.liste.selection() == (iid,):
                self._auswahl_geaendert()
        elif art == "einlesen_fertig":
            self._beschaeftigt(False)
            ohne = sum(1 for i in self.liste.get_children()
                       if self.liste.set(i, "status") == core.STATUS_FEHLT)
            self.statuszeile.set(f"{len(self.dateien)} MP3-Dateien gefunden, "
                                 f"davon {ohne} ohne Cover.")
            if self._sofort_ergaenzen:
                self._sofort_ergaenzen = False  # nur beim ersten Mal
                if ohne:
                    self._starte_ergaenzen()
        elif art == "ergaenzen_fertig":
            self._beschaeftigt(False)
            zaehler: dict[str, int] = {}
            for i in self.liste.get_children():
                s = self.liste.set(i, "status")
                zaehler[s] = zaehler.get(s, 0) + 1
            text = ", ".join(f"{s}: {n}" for s, n in zaehler.items())
            if inhalt:
                text = "Abgebrochen. " + text
            self.statuszeile.set(f"Fertig. {text}  –  Log: {self.log_pfad}")

    # ------------------------------------------------------------------
    # Kontextmenü (Rechtsklick auf eine Datei)
    # ------------------------------------------------------------------
    def _kontextmenue_zeigen(self, event) -> None:
        zeile = self.liste.identify_row(event.y)
        if not zeile:
            return
        # Die angeklickte Zeile auswählen, damit klar ist, worum es geht
        self.liste.selection_set(zeile)
        self.liste.focus(zeile)
        if self.arbeitet:
            # Während der automatischen Suche nichts von Hand ändern
            self.statuszeile.set("Bitte warten, bis der laufende Vorgang "
                                 "fertig ist (oder Stopp drücken).")
            return
        try:
            hat_cover = core.hat_cover(self.dateien[int(zeile)])
        except Exception:
            hat_cover = False
        # Eintrag 0 = "Cover entfernen" – nur anklickbar, wenn es ein Cover gibt
        self.kontextmenue.entryconfigure(
            0, state="normal" if hat_cover else "disabled")
        try:
            self.kontextmenue.tk_popup(event.x_root, event.y_root)
        finally:
            self.kontextmenue.grab_release()

    def _ausgewaehlt(self) -> tuple[str, Path] | None:
        auswahl = self.liste.selection()
        if not auswahl:
            return None
        return auswahl[0], self.dateien[int(auswahl[0])]

    def _status_neu_setzen(self, iid: str, datei: Path) -> None:
        """Status der Zeile und Vorschau nach einer manuellen Änderung aktualisieren."""
        try:
            status = (core.STATUS_VORHANDEN if core.hat_cover(datei)
                      else core.STATUS_FEHLT)
        except Exception:
            status = core.STATUS_FEHLER
        self.liste.set(iid, "status", status)
        self.liste.item(iid, tags=(status,))
        self._auswahl_geaendert()

    def _cover_entfernen(self) -> None:
        gewaehlt = self._ausgewaehlt()
        if not gewaehlt:
            return
        iid, datei = gewaehlt
        if not messagebox.askyesno(
                "Cover entfernen",
                f"Soll das Cover wirklich aus dieser Datei entfernt werden?\n\n"
                f"{datei.name}"):
            return
        try:
            core.entferne_cover(datei)
        except Exception as fehler:
            messagebox.showerror("Coversuche",
                                 f"Cover konnte nicht entfernt werden:\n{fehler}")
            return
        self._status_neu_setzen(iid, datei)
        self.statuszeile.set(f"Cover entfernt: {datei.name}")

    def _cover_hinzufuegen(self) -> None:
        gewaehlt = self._ausgewaehlt()
        if not gewaehlt:
            return
        iid, datei = gewaehlt
        bildpfad = filedialog.askopenfilename(
            title=f"Cover für „{datei.name}“ wählen",
            initialdir=self._start_ordner_fuer_cover(datei),
            filetypes=[("JPEG-Bilder", "*.jpg *.jpeg"),
                       ("Andere Bilder", "*.png *.bmp *.gif *.webp"),
                       ("Alle Dateien", "*.*")])
        if not bildpfad:
            return  # Dialog abgebrochen
        # Ordner merken – auch für den nächsten Programmstart
        core.speichere_einstellung("letzter_cover_ordner",
                                   os.path.dirname(bildpfad))
        try:
            core.cover_aus_bilddatei(datei, bildpfad)
        except Exception as fehler:
            messagebox.showerror("Coversuche",
                                 f"Cover konnte nicht hinzugefügt werden:\n{fehler}")
            return
        self._status_neu_setzen(iid, datei)
        self.statuszeile.set(f"Cover hinzugefügt: {datei.name}")

    @staticmethod
    def _start_ordner_fuer_cover(datei: Path) -> str:
        """Zuletzt benutzter Cover-Ordner – falls es ihn noch gibt –, sonst der MP3-Ordner."""
        letzter = core.lade_einstellungen().get("letzter_cover_ordner")
        if letzter and os.path.isdir(letzter):
            return letzter
        return str(datei.parent)

    def _tag_bearbeiten(self) -> None:
        gewaehlt = self._ausgewaehlt()
        if not gewaehlt:
            return
        iid, datei = gewaehlt
        try:
            werte = core.lese_tag_felder(datei)
        except Exception as fehler:
            messagebox.showerror("Coversuche",
                                 f"ID3-Tag konnte nicht gelesen werden:\n{fehler}")
            return
        TagDialog(self.fenster, datei, werte,
                  beim_speichern=lambda: self._nach_tag_speichern(iid, datei))

    def _nach_tag_speichern(self, iid: str, datei: Path) -> None:
        self._status_neu_setzen(iid, datei)
        self.statuszeile.set(f"ID3-Tag gespeichert: {datei.name}")

    # ------------------------------------------------------------------
    # Cover-Vorschau
    # ------------------------------------------------------------------
    def _auswahl_geaendert(self, _event=None) -> None:
        auswahl = self.liste.selection()
        if not auswahl:
            return
        datei = self.dateien[int(auswahl[0])]
        try:
            bild = core.lese_cover(datei)
        except Exception as fehler:
            self._zeige_cover(None, f"{datei.name}\n\nFehler beim Lesen: {fehler}")
            return
        self._zeige_cover(bild, datei.name)

    def _zeige_cover(self, bilddaten: bytes | None, info: str) -> None:
        if bilddaten:
            try:
                bild = Image.open(io.BytesIO(bilddaten))
                breite, hoehe = bild.size
                bild.thumbnail((VORSCHAU_GROESSE, VORSCHAU_GROESSE))
                self._vorschau_bild = ImageTk.PhotoImage(bild)
                self.vorschau.configure(image=self._vorschau_bild, text="")
                self.vorschau_info.configure(
                    text=f"{info}\nOriginalgröße: {breite} × {hoehe} Pixel")
                return
            except Exception:
                info += "\n\nCover ist vorhanden, aber nicht lesbar."
        self._vorschau_bild = None
        self.vorschau.configure(image="", text="Kein Cover vorhanden"
                                if info else "Keine Datei ausgewählt")
        self.vorschau_info.configure(text=info)


class TagDialog(tk.Toplevel):
    """
    Eigenes kleines Fenster zum Bearbeiten des ID3-Tags.
    Bei mehreren Dateien werden nur die Felder geändert, die man anfasst.
    """

    def __init__(self, eltern: tk.Misc, dateien: Path | list[Path],
                 werte: dict[str, str | None] | None = None,
                 beim_speichern=None):
        super().__init__(eltern)
        self.dateien = [dateien] if isinstance(dateien, Path) else list(dateien)
        mehrere = len(self.dateien) > 1
        if werte is None:
            werte = (core.gemeinsame_tag_felder(self.dateien) if mehrere
                     else core.lese_tag_felder(self.dateien[0]))
        self.anfangswerte = werte
        self.beim_speichern = beim_speichern or (lambda: None)

        if mehrere:
            self.title(f"ID3-Tag bearbeiten – {len(self.dateien)} Dateien")
            kopf = (f"{len(self.dateien)} Dateien in {self.dateien[0].parent}\n"
                    "Nur Felder, die du änderst, werden in alle Dateien "
                    "geschrieben.")
        else:
            self.title(f"ID3-Tag bearbeiten – {self.dateien[0].name}")
            kopf = str(self.dateien[0])
        self.resizable(True, False)
        if eltern.winfo_viewable():
            self.transient(eltern)  # bleibt vor dem Hauptfenster

        rahmen = ttk.Frame(self, padding=12)
        rahmen.pack(fill="both", expand=True)
        ttk.Label(rahmen, text=kopf, foreground="#555",
                  wraplength=520, justify="left").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        self.felder: dict[str, tk.StringVar] = {}
        erstes_feld = None
        for zeile, (name, kennung) in enumerate(core.TAG_FELDER, start=1):
            ttk.Label(rahmen, text=name + ":").grid(row=zeile, column=0,
                                                    sticky="w", pady=2)
            wert = werte.get(kennung)
            variable = tk.StringVar(value=wert or "")
            eingabe = ttk.Entry(rahmen, textvariable=variable, width=50)
            eingabe.grid(row=zeile, column=1, sticky="ew", padx=(8, 0), pady=2)
            hinweis = ""
            if mehrere and kennung in core.NUR_EINZELN:
                eingabe.configure(state="disabled")
                hinweis = "nur einzeln änderbar"
            elif wert is None:
                hinweis = "verschiedene Werte"
            if hinweis:
                ttk.Label(rahmen, text=hinweis, foreground="#888").grid(
                    row=zeile, column=2, sticky="w", padx=(6, 0))
            self.felder[kennung] = variable
            if erstes_feld is None and str(eingabe.cget("state")) != "disabled":
                erstes_feld = eingabe
        rahmen.columnconfigure(1, weight=1)

        knoepfe = ttk.Frame(rahmen)
        knoepfe.grid(row=len(core.TAG_FELDER) + 1, column=0, columnspan=3,
                     sticky="e", pady=(12, 0))
        ttk.Button(knoepfe, text="Speichern",
                   command=self._speichern).pack(side="left", padx=(0, 6))
        ttk.Button(knoepfe, text="Abbrechen",
                   command=self.destroy).pack(side="left")

        # Enter = Speichern, Escape = Abbrechen
        self.bind("<Return>", lambda _e: self._speichern())
        self.bind("<Escape>", lambda _e: self.destroy())

        # "modal": solange dieses Fenster offen ist, ist das Hauptfenster gesperrt
        self.grab_set()
        self.lift()
        self.focus_force()
        if erstes_feld is not None:
            erstes_feld.focus_set()

    def _geaenderte_werte(self) -> dict[str, str]:
        """Nur die Felder, die sich gegenüber dem Anfang geändert haben."""
        geaendert = {}
        for kennung, var in self.felder.items():
            anfang = self.anfangswerte.get(kennung)
            if var.get().strip() != (anfang or "").strip():
                geaendert[kennung] = var.get()
        return geaendert

    def _speichern(self) -> None:
        werte = self._geaenderte_werte()
        fehler_liste = []
        if werte:
            for datei in self.dateien:
                try:
                    core.schreibe_tag_felder(datei, werte)
                except Exception as fehler:
                    fehler_liste.append(f"{datei.name}: {fehler}")
        if fehler_liste:
            messagebox.showerror(
                "Coversuche",
                "ID3-Tag konnte nicht gespeichert werden:\n\n"
                + "\n".join(fehler_liste[:15]), parent=self)
            return
        self.destroy()
        self.beim_speichern()


class UmbenennenDialog(tk.Toplevel):
    """
    Zeigt eine Vorschau "alter Name → neuer Name" und benennt erst nach
    einem Klick auf "Umbenennen" wirklich um.
    """

    def __init__(self, eltern: tk.Misc, dateien: list[Path], beim_fertig=None):
        super().__init__(eltern)
        self.beim_fertig = beim_fertig or (lambda: None)
        self.title(f"Dateien umbenennen – {len(dateien)} Datei(en)")
        self.geometry("1000x500")
        self.minsize(600, 300)
        if eltern.winfo_viewable():
            self.transient(eltern)

        self.plan = core.plane_umbenennung(dateien)
        anzahl = sum(1 for e in self.plan if e.neu is not None)

        rahmen = ttk.Frame(self, padding=12)
        rahmen.pack(fill="both", expand=True)
        ttk.Label(rahmen, justify="left", text=(
            "Neues Schema:  Interpret - Album - Tracknummer - Titel.mp3\n"
            f"{anzahl} von {len(self.plan)} Dateien werden umbenannt. "
            "Grau = wird übersprungen.")).pack(anchor="w", pady=(0, 8))

        tabelle = ttk.Frame(rahmen)
        tabelle.pack(fill="both", expand=True)
        liste = ttk.Treeview(tabelle, columns=("alt", "neu", "hinweis"),
                             show="headings")
        for spalte, text, breite in (("alt", "Bisheriger Name", 340),
                                     ("neu", "Neuer Name", 400),
                                     ("hinweis", "Hinweis", 200)):
            liste.heading(spalte, text=text)
            liste.column(spalte, width=breite, anchor="w")
        liste.tag_configure("aus", foreground="#999")
        scroll = ttk.Scrollbar(tabelle, orient="vertical", command=liste.yview)
        liste.configure(yscrollcommand=scroll.set)
        liste.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for eintrag in self.plan:
            liste.insert("", "end", values=(
                eintrag.alt.name, eintrag.neu.name if eintrag.neu else "–",
                eintrag.hinweis), tags=(() if eintrag.neu else ("aus",)))

        knoepfe = ttk.Frame(rahmen)
        knoepfe.pack(anchor="e", pady=(10, 0))
        self.knopf_ok = ttk.Button(knoepfe, text="Umbenennen",
                                   command=self._umbenennen,
                                   state="normal" if anzahl else "disabled")
        self.knopf_ok.pack(side="left", padx=(0, 6))
        ttk.Button(knoepfe, text="Abbrechen",
                   command=self.destroy).pack(side="left")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.lift()
        self.focus_force()

    def _umbenennen(self) -> None:
        ergebnisse = core.fuehre_umbenennung_aus(self.plan)
        ok = sum(1 for _, text in ergebnisse if text == "umbenannt")
        fehler = [f"{e.alt.name}: {text}" for e, text in ergebnisse
                  if text.startswith("Fehler")]
        meldung = f"{ok} Datei(en) umbenannt."
        if fehler:
            meldung += "\n\nProbleme:\n" + "\n".join(fehler[:15])
            messagebox.showwarning("Coversuche", meldung, parent=self)
        else:
            messagebox.showinfo("Coversuche", meldung, parent=self)
        self.destroy()
        self.beim_fertig()


def starte_aus_explorer(aktion: str, pfade: list[str]) -> None:
    """Wird vom Explorer-Kontextmenü aufgerufen (siehe explorer.py)."""
    fenster = tk.Tk()
    _design_waehlen()

    if aktion == "cover":
        CoversucheApp(fenster, pfade, sofort_ergaenzen=True)
        fenster.mainloop()
        return

    # Für "tag" und "umbenennen" braucht es kein Hauptfenster
    fenster.withdraw()
    dateien = core.sammle_mp3(pfade)
    if not dateien:
        messagebox.showinfo("Coversuche", "Keine MP3-Dateien gefunden.")
        fenster.destroy()
        return
    if aktion == "tag":
        dialog = TagDialog(fenster, dateien)
    else:
        dialog = UmbenennenDialog(fenster, dateien)
    # Wenn der Dialog geschlossen wird, ist das Programm fertig
    dialog.bind("<Destroy>", lambda e: e.widget is dialog and fenster.destroy())
    fenster.mainloop()


def _design_waehlen() -> None:
    try:
        # Unter Windows sieht das moderne Design schöner aus
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass


def main(start_pfade: list[str] | None = None) -> None:
    fenster = tk.Tk()
    _design_waehlen()
    CoversucheApp(fenster, start_pfade)
    fenster.mainloop()


if __name__ == "__main__":
    main()
