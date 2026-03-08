# Codebasis-Review: Konkrete Aufgabenvorschläge

Dieses Dokument sammelt vier konkrete Aufgaben aus einer kurzen Durchsicht der Codebasis: Tippfehler, Programmierfehler, Kommentar/Doku-Unstimmigkeit und Testverbesserung.

## 1) Aufgabe: Tippfehler/Formatierungsfehler in der XScreenSaver-Doku korrigieren

**Fundort**
- `docs/xscreensaver-hack-entry.txt`

**Problem**
- Der Beispiel-Eintrag enthält am Zeilenende ein wörtliches `\n\`, was wie ein Artefakt aussieht und in die Irre führt.

**Vorschlag**
- Den Eintrag so darstellen, wie er in `~/.xscreensaver` tatsächlich geschrieben werden soll (mit realem Zeilenumbruch + `\` am Ende, aber ohne `\n`-Literal).

**Akzeptanzkriterien**
- Der Doku-Snippet ist direkt copy/paste-fähig.
- Keine Literal-Sequenz `\n\` mehr in der Anleitung.

---

## 2) Aufgabe: Programmierfehler bei `XSCREENSAVER_WINDOW`-Parsing beheben

**Fundorte**
- `main.py` (`resolve_launch_config`)
- `scripts/east-frisia-castaway-xscreensaver`

**Problem**
- `resolve_launch_config` akzeptiert nur dezimale IDs (`str.isdigit()`).
- X11-Window-IDs werden in der Praxis häufig auch hexadezimal (`0x...`) dargestellt. Solche Werte werden aktuell als ungültig verworfen.

**Risiko/Auswirkung**
- Bei gültiger, aber hexadezimaler `XSCREENSAVER_WINDOW`-Variable fällt die App unerwartet auf Fullscreen zurück statt in das Ziel-Fenster zu embedden.

**Vorschlag**
- Parsing robust machen, z. B. über `int(value, 0)` (akzeptiert `1234` und `0x4d2`).
- Bei erfolgreichem Parse die numerische ID wieder als String speichern.

**Akzeptanzkriterien**
- `XSCREENSAVER_WINDOW=424242` und `XSCREENSAVER_WINDOW=0x67932` führen beide zu `mode="embed"`.
- Ungültige Werte werden weiterhin sauber verworfen und geloggt.

---

## 3) Aufgabe: Doku-Unstimmigkeit zwischen README und tatsächlichem Verhalten bereinigen

**Fundorte**
- `README.md` (Quick Test Commands)
- `main.py` (`resolve_launch_config`)

**Problem**
- README empfiehlt `XSCREENSAVER_WINDOW=0 ... --preview` als „Preview-like embedding smoke test“.
- Im Code hat jedoch die Umgebungsvariable Vorrang vor `--preview`; dadurch läuft der Startpfad nicht als echtes Preview.

**Vorschlag**
- README-Kommando und Beschreibung an den tatsächlichen Prioritätsbaum anpassen (oder Priorität im Code explizit ändern und dokumentieren).
- Optional zwei getrennte Beispiele: „echtes Preview“ ohne `XSCREENSAVER_WINDOW` und „Embedding-Smoketest“ mit `XSCREENSAVER_WINDOW`.

**Akzeptanzkriterien**
- Dokumentation und Laufzeitverhalten widersprechen sich nicht mehr.
- Ein neuer Contributor kann anhand README zuverlässig den gewünschten Modus starten.

---

## 4) Aufgabe: Testsuite für Launch-Config-Edgecases ausbauen

**Fundort**
- `tests/test_windowid_env.py`

**Problem**
- Aktuell fehlen gezielte Tests für kritische Edgecases beim Window-ID-Handling und Flag-Prioritäten.

**Vorschlag**
- Neue Tests ergänzen für:
  1. hexadezimale `XSCREENSAVER_WINDOW`-Werte,
  2. leere/whitespace-Werte in `XSCREENSAVER_WINDOW`,
  3. Priorität CLI vs. Environment (`--window-id` übersteuert Env; gewünschtes Verhalten für `--preview`/`--fullscreen` explizit absichern).

**Akzeptanzkriterien**
- Die Tests decken mindestens die drei obigen Fälle explizit ab.
- `python -m unittest` bleibt grün.
