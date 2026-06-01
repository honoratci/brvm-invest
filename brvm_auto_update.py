#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║   BRVM Auto Update — Mise à jour automatique des cours      ║
╠══════════════════════════════════════════════════════════════╣
║  Workflow :                                                  ║
║  1. Télécharge le bulletin PDF depuis brvm.org              ║
║     Pattern : boc_YYYYMMDD_2.pdf                            ║
║  2. Surveille le dossier bulletins/ (dépôts manuels)        ║
║  3. Parse le PDF (même moteur que l'app HTML)               ║
║  4. Patche brvm_investissement.html → prix toujours à jour  ║
║  5. Génère brvm_cours.json                                  ║
╠══════════════════════════════════════════════════════════════╣
║  Usage :                                                     ║
║    python brvm_auto_update.py           → MAJ du jour       ║
║    python brvm_auto_update.py --watch   → Surveillance      ║
║    python brvm_auto_update.py --date 20260526 → Date fixe   ║
╚══════════════════════════════════════════════════════════════╝
PRÉREQUIS : pip install requests pymupdf
"""

import json, re, sys, time, datetime, shutil, os
from pathlib import Path

# ── Chemins ──────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
HTML_FILE    = BASE_DIR / "brvm_investissement.html"
JSON_OUTPUT  = BASE_DIR / "brvm_cours.json"
BULLETIN_DIR = BASE_DIR / "bulletins"
LOG_FILE     = BASE_DIR / "brvm_auto_update.log"
BULLETIN_DIR.mkdir(exist_ok=True)
(BULLETIN_DIR / "archives").mkdir(exist_ok=True)

# ── URL bulletins BRVM ────────────────────────────────────────────────────────
# Pattern confirmé : https://www.brvm.org/sites/default/files/boc_YYYYMMDD_2.pdf
BRVM_BASE = "https://www.brvm.org/sites/default/files"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "application/pdf,application/octet-stream,*/*",
    "Referer": "https://www.brvm.org/fr/bulletins-officiels-de-la-cote",
}

# ── Tickers BRVM (synchronisé avec brvm_investissement.html) ─────────────────
KNOWN_TICKERS = {
    "SGBC","ECOC","ETIT","BACI","BOAB","BOAC","BOABF","BOAM","BOAS","BOAN",
    "NSBC","CBIBF","SIBC","BICC","BICB","ORGT","SNTS","ORAC","ONTBF",
    "PALC","SPHC","SIFC","SCRC","SOGC","NTLC","SMBC","SLBC","STBC","NEIC",
    "CABC","STAC","SEMC","FTSC","SIVC","SICC","UNLC","CFAC","SDSC","ABJC",
    "BNBC","PRSC","UNXC","LNBB","TTLC","TTLS","SHEC","CIEC","SDCC","SAFC",
    "SOGBC","BICC","ORGT","LNBB"
}
SECTOR_CODES = {
    "CB","ENE","FIN","TEL","IND","AUT","AGR","DIS","TRA","IMM",
    "AGRI","INDUS","SPU","CD"
}

# ═════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ═════════════════════════════════════════════════════════════════════════════
def log(msg, level="INFO"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ═════════════════════════════════════════════════════════════════════════════
#  DÉPENDANCES
# ═════════════════════════════════════════════════════════════════════════════
def ensure_deps():
    missing = []
    try:
        import requests
    except ImportError:
        missing.append("requests")
    try:
        import fitz  # PyMuPDF
    except ImportError:
        missing.append("pymupdf")

    if missing:
        log(f"Installation : {', '.join(missing)}")
        import subprocess
        subprocess.run(
            [sys.executable, "-m", "pip", "install"] + missing +
            ["--break-system-packages", "-q"],
            check=False
        )

# ═════════════════════════════════════════════════════════════════════════════
#  TÉLÉCHARGEMENT DU BULLETIN
# ═════════════════════════════════════════════════════════════════════════════
def download_bulletin(target_date=None):
    """
    Télécharge le bulletin du jour depuis brvm.org.
    Essaie les 5 derniers jours ouvrés si le jour courant est indisponible.
    Retourne le Path du PDF téléchargé, ou None.
    """
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    d = target_date or datetime.date.today()

    for _ in range(7):  # remonter jusqu'à 7 jours
        if d.weekday() >= 5:  # samedi=5, dimanche=6 → pas de bulletin
            d -= datetime.timedelta(days=1)
            continue

        ds = d.strftime("%Y%m%d")
        dest = BULLETIN_DIR / f"bulletin_{ds}.pdf"

        # Ne pas re-télécharger si déjà présent
        if dest.exists() and dest.stat().st_size > 50_000:
            log(f"Bulletin {ds} déjà présent localement")
            return dest

        # Essayer plusieurs suffixes : _2 (standard), _1, sans suffixe
        for suffix in ["2", "1", "0"]:
            url = f"{BRVM_BASE}/boc_{ds}_{suffix}.pdf"
            try:
                log(f"  Essai : {url}")
                r = requests.get(url, headers=HEADERS, timeout=25, verify=False)
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    dest.write_bytes(r.content)
                    size_kb = len(r.content) // 1024
                    log(f"✅ Téléchargé : {dest.name} ({size_kb} Ko)")
                    return dest
                elif r.status_code == 404:
                    continue  # essayer le suffixe suivant
                else:
                    log(f"  HTTP {r.status_code}", "WARN")
            except Exception as e:
                log(f"  Erreur réseau : {e}", "WARN")

        # Essayer sans suffixe
        url = f"{BRVM_BASE}/boc_{ds}.pdf"
        try:
            r = requests.get(url, headers=HEADERS, timeout=25, verify=False)
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                dest.write_bytes(r.content)
                log(f"✅ Téléchargé : {dest.name}")
                return dest
        except Exception as e:
            log(f"  Erreur réseau : {e}", "WARN")

        log(f"  Bulletin {ds} non disponible sur brvm.org", "WARN")
        d -= datetime.timedelta(days=1)

    log("❌ Aucun bulletin disponible sur brvm.org", "ERROR")
    return None

# ═════════════════════════════════════════════════════════════════════════════
#  EXTRACTION DES COURS DEPUIS LE PDF
# ═════════════════════════════════════════════════════════════════════════════
def parse_fcfa(s):
    try:
        return float(str(s).replace("\xa0", "").replace(" ", "")
                          .replace(" ", "").replace(",", ".").strip())
    except Exception:
        return float("nan")

def extract_chunk(chunk):
    """
    Depuis un segment de texte contenant 3 prix + variation,
    retourne (cours_cloture, variation) ou None.
    Structure bulletin : PREV  OUV  CLOT  VAR%
    → cours = DERNIER prix avant la variation %.
    """
    m = re.search(r'([+-]?\s*\d{1,3}[,.]\d{2})\s*%', chunk)
    if not m:
        return None
    before = chunk[:m.start()]

    # Extraction des prix FCFA (format "36 000", "2 870", etc.)
    prices = []
    for pm in re.finditer(r'\b(\d{1,3}(?:\s\d{3})+)\b', before):
        v = parse_fcfa(pm.group(1))
        if not (v != v) and 10 <= v <= 500_000:
            prices.append(v)

    # Fallback pour les petits cours (ex : ETIT à 29 FCFA)
    if not prices:
        for pm in re.finditer(r'\b(\d{1,6})\b', before):
            v = float(pm.group(1))
            if 10 <= v <= 500_000:
                prices.append(v)

    if not prices:
        return None

    cours = prices[-1]  # clôture = dernier prix avant variation
    try:
        variation = round(float(m.group(1).replace(" ", "").replace(",", ".")), 2)
    except Exception:
        variation = 0.0
    return {"cours": cours, "variation": variation}


def extract_cours_from_text(text):
    """
    Deux stratégies de parsing (mêmes que l'app HTML) :
    S1 : ticker + variation sur la même ligne (Y-grouping)
    S2 : ticker seul sur sa ligne, données sur les suivantes
    """
    results = {}
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # ── Stratégie 1 : ligne complète ─────────────────────────────────────
    for line in lines:
        if "%" not in line:
            continue
        tokens = line.split()
        ticker = None
        for tok in tokens[:6]:
            t = re.sub(r'[^A-Za-z]', '', tok).upper()
            if t and t not in SECTOR_CODES and t in KNOWN_TICKERS:
                ticker = t
                break
        if not ticker or ticker in results:
            continue
        res = extract_chunk(line)
        if res:
            results[ticker] = res

    # ── Stratégie 2 : ticker seul sur sa ligne ────────────────────────────
    for i, line in enumerate(lines):
        t = re.sub(r'[^A-Za-z]', '', line).upper()
        if t not in KNOWN_TICKERS or t in results:
            continue
        win = []
        for k in range(i + 1, min(i + 20, len(lines))):
            lt = re.sub(r'[^A-Za-z]', '', lines[k]).upper()
            if lt in KNOWN_TICKERS:
                break
            win.append(lines[k])
        res = extract_chunk(" ".join(win))
        if res:
            results[t] = res

    return results


def extract_from_pdf(pdf_path):
    """
    Lit le PDF et retourne {ticker: {cours, variation}}.
    PyMuPDF extrait chaque valeur du tableau sur sa propre ligne (\n),
    ce que Strategy 2 de extract_cours_from_text gère parfaitement.
    """
    import fitz

    doc = fitz.open(str(pdf_path))
    log(f"  Lecture PDF : {pdf_path.name} ({doc.page_count} pages)")

    all_text = ""
    for page in doc:
        # get_text("text") retourne le texte avec \n entre chaque bloc PDF.
        # Pour le bulletin BRVM, cela donne une valeur par ligne, ex :
        #   CB\nSCRC\nSUCRIVOIRE\n   2 500\n2 550\n2 650\n6,00 %\n...
        all_text += page.get_text("text") + "\n"

    doc.close()
    cours = extract_cours_from_text(all_text)
    log(f"  → {len(cours)} titres extraits")
    return cours

# ═════════════════════════════════════════════════════════════════════════════
#  MISE À JOUR DU FICHIER HTML
# ═════════════════════════════════════════════════════════════════════════════
def update_html(cours_data, source_info):
    """
    Patche directement brvm_investissement.html :
    • Met à jour price et var1d pour chaque ticker trouvé
    • Met à jour la date de dernière MAJ dans le header
    """
    if not HTML_FILE.exists():
        log(f"❌ HTML introuvable : {HTML_FILE}", "ERROR")
        return 0

    html = HTML_FILE.read_text(encoding="utf-8")
    updated = 0

    for ticker, data in cours_data.items():
        cours = data["cours"]
        var   = data["variation"]

        # Recherche du bloc de ce ticker dans le tableau stocks
        # Format : ticker:"SGBC", name:"...", ..., price:XXXXX, var1d:X.XX, ...
        pat = (rf'(ticker:"{re.escape(ticker)}"'
               rf'(?:[^{{}}]{{0,300}}?))price:\s*[\d.]+([^{{}}]{{0,50}}?)var1d:\s*[+-]?[\d.]+')
        def make_replacer(c, v):
            def _r(m):
                return f'{m.group(1)}price:{c}{m.group(2)}var1d:{v}'
            return _r

        new_html, n = re.subn(pat, make_replacer(cours, var), html, count=1)
        if n:
            html = new_html
            updated += 1

    # Mettre à jour la date de MAJ affichée dans l'app
    now_str = datetime.datetime.now().strftime("%d/%m/%Y à %H:%M")
    # Remplacer le texte d'init de lastUpdate dans window.onload
    html = re.sub(
        r'("lastUpdate"\)\.textContent\s*=\s*")[^"]+(")',
        rf'\g<1>Mis à jour le {now_str} — {source_info}\g<2>',
        html
    )

    HTML_FILE.write_text(html, encoding="utf-8")
    log(f"✅ HTML patché : {updated}/{len(cours_data)} titres")
    return updated

# ═════════════════════════════════════════════════════════════════════════════
#  SAUVEGARDE JSON
# ═════════════════════════════════════════════════════════════════════════════
def save_json(cours_data, source_info):
    today = datetime.date.today().isoformat()
    output = [
        {
            "ticker":    t,
            "price":     d["cours"],
            "var1d":     d["variation"],
            "date":      today,
            "source":    source_info
        }
        for t, d in sorted(cours_data.items())
    ]
    JSON_OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log(f"✅ JSON : {JSON_OUTPUT.name} ({len(output)} titres)")

# ═════════════════════════════════════════════════════════════════════════════
#  TRAITEMENT D'UN PDF
# ═════════════════════════════════════════════════════════════════════════════
def process_pdf(pdf_path, source_info=None):
    if source_info is None:
        source_info = f"Bulletin {pdf_path.stem}"

    log(f"\n{'─'*50}")
    log(f"📄 Traitement : {pdf_path.name}")

    cours = extract_from_pdf(pdf_path)
    if not cours:
        log("❌ Aucun cours extrait", "ERROR")
        return False

    # Affichage récapitulatif
    log(f"\n  {'Ticker':<8} {'Clôture':>10}  {'Var':>8}")
    log(f"  {'─'*8} {'─'*10}  {'─'*8}")
    for t in sorted(cours):
        d = cours[t]
        arrow = "▲" if d["variation"] > 0 else "▼" if d["variation"] < 0 else "─"
        log(f"  {t:<8} {d['cours']:>10,.0f}  {arrow} {abs(d['variation']):.2f}%")

    save_json(cours, source_info)
    update_html(cours, source_info)

    # Archiver
    archive_path = BULLETIN_DIR / "archives" / pdf_path.name
    if not archive_path.exists():
        shutil.copy2(pdf_path, archive_path)

    log(f"\n✅ Terminé — {len(cours)} titres mis à jour")
    return True

# ═════════════════════════════════════════════════════════════════════════════
#  MODE SURVEILLANCE DOSSIER
# ═════════════════════════════════════════════════════════════════════════════
def watch_folder():
    """
    Surveille bulletins/ en continu.
    Dès qu'un nouveau PDF apparaît, le traite automatiquement.
    """
    log(f"👁️  Surveillance de : {BULLETIN_DIR}")
    log("    Dépose un bulletin PDF dans ce dossier pour lancer la MAJ")
    log("    Ctrl+C pour arrêter\n")

    processed = {p.name for p in (BULLETIN_DIR / "archives").glob("*.pdf")}

    while True:
        for pdf in sorted(BULLETIN_DIR.glob("*.pdf")):
            if pdf.name not in processed:
                time.sleep(1.5)  # laisser la copie se terminer
                process_pdf(pdf, f"Dépôt manuel — {pdf.name}")
                processed.add(pdf.name)
        time.sleep(10)

# ═════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════════
def main():
    print()
    print("╔" + "═"*56 + "╗")
    print("║  📊  BRVM Auto Update" + " "*35 + "║")
    print(f"║  📅  {datetime.datetime.now().strftime('%A %d %B %Y  %H:%M'):<50}║")
    print("╚" + "═"*56 + "╝")
    print()

    ensure_deps()

    # ── Mode surveillance continue ────────────────────────────────────────
    if "--watch" in sys.argv:
        watch_folder()
        return

    # ── Date forcée via --date YYYYMMDD ───────────────────────────────────
    forced_date = None
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            try:
                ds = sys.argv[idx + 1]
                forced_date = datetime.date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
                log(f"Date forcée : {forced_date}")
            except Exception:
                log("Format --date invalide. Attendu : YYYYMMDD", "WARN")

    # ── 1. Bulletin déposé manuellement ? ────────────────────────────────
    manual = sorted(BULLETIN_DIR.glob("*.pdf"))
    if manual:
        latest = manual[-1]
        log(f"📥 Bulletin manuel : {latest.name}")
        process_pdf(latest, f"Dépôt manuel — {latest.stem}")
        return

    # ── 2. Téléchargement depuis brvm.org ─────────────────────────────────
    log("🌐 Téléchargement depuis brvm.org...")
    pdf_path = download_bulletin(forced_date)

    if pdf_path:
        ds_pretty = pdf_path.stem.replace("bulletin_", "")
        try:
            dt = datetime.datetime.strptime(ds_pretty, "%Y%m%d")
            source = f"Bulletin BRVM du {dt.strftime('%d/%m/%Y')}"
        except Exception:
            source = f"Bulletin BRVM — {ds_pretty}"
        process_pdf(pdf_path, source)
    else:
        log("⚠️  Pas de bulletin disponible aujourd'hui (marché fermé ?)", "WARN")
        log("   → Dépose manuellement le PDF dans : bulletins/")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⛔ Arrêté.")
    except Exception as e:
        log(f"Erreur fatale : {e}", "ERROR")
        import traceback
        traceback.print_exc()
