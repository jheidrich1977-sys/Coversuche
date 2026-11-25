"""
Startet Coversuche.
  python start.py                      → Hauptfenster
  python start.py --cover  <Pfade>     → Cover für Dateien/Ordner suchen
  python start.py --tag    <Pfade>     → ID3-Tag bearbeiten
  python start.py --umbenennen <Pfade> → Dateien nach ID3-Tag umbenennen
(So ruft auch das Explorer-Kontextmenü das Programm auf.)
"""
from coversuche.explorer import main

if __name__ == "__main__":
    main()
