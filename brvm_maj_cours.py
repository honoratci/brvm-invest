#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================
  BRVM Invest Pro — Mise à jour automatique des cours
  Sources : sikafinance.com (principal) + Yahoo Finance (secours)
  Usage   : python brvm_maj_cours.py
  Sortie  : brvm_cours.csv  (importable dans l'app HTML)
====================================================
PRÉREQUIS (une seule fois) :
  pip install requests beautifulsoup4 yfinance pandas lxml
====================================================
"""

import csv, sys, time, datetime, re
from pathlib import Path

OUTPUT_FILE = Path(__file__).parent / "brvm_cours.csv"
LOG_FILE    = Path(__file__).parent / "brvm_maj.log"

# ─── Import des dépendances ───────────────────────────────────────────────────
try:
    import requests
    from bs4 import BeautifulSoup
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    import yfinance as yf
    YF_OK = True
except ImportError:
    YF_OK = False

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ─── Correspondances tickers BRVM ↔ Yahoo Finance ────────────────────────────
# Format Yahoo Finance pour BRVM : ticker + suffixe selon pays de cotation
TICKER_MAP = {
    # Ticker BRVM  : (Yahoo ticker,       Secteur,      Dividende ref, PER ref)
    "SNTS":  ("SNTS.SN",  "Telecom",      8.5,  14.8),
    "ORAC":  ("ORAC.CI",  "Telecom",      7.2,  13.2),
    "SGBC":  ("SGBC.CI",  "Finance",      5.2,  12.4),
    "ETIT":  ("ETI.GH",   "Finance",      4.8,   8.2),
    "BACI":  ("BACI.CI",  "Finance",      6.1,   9.5),
    "BOAB":  ("BOAB.BJ",  "Finance",      4.5,  10.8),
    "NSBC":  ("NSBC.CI",  "Finance",      5.8,  11.2),
    "CBIBF": ("CBIBF.BF", "Finance",      5.5,   9.8),
    "SIBC":  ("SIBC.CI",  "Finance",      4.9,  10.1),
    "BNCI":  ("BNCI.CI",  "Finance",      3.8,  13.5),
    "PALC":  ("PALC.CI",  "Agriculture",  6.8,   8.9),
    "SIFC":  ("SIFC.CI",  "Agriculture",  4.2,  11.5),
    "SLBR":  ("SLBR.CI",  "Industrie",    3.1,  16.8),
    "STAB":  ("STAB.CI",  "Industrie",    7.5,   9.2),
    "TTLS":  ("TTLS.CI",  "Energie",      5.9,  12.8),
    "CIEC":  ("CIEC.CI",  "Energie",      6.4,  10.5),
    "SDCI":  ("SDCI.CI",  "Energie",      5.7,  11.8),
    "CFAC":  ("CFAC.CI",  "Distribution", 3.5,  15.2),
    "ONTBF": ("ONTBF.BF", "Telecom",      6.8,  11.9),
    "NEIM":  ("NEIM.CI",  "Industrie",    2.2,  18.5),
    "BOAM":  ("BOAM.ML",  "Finance",      4.0,  11.0),
    "CBSE":  ("CBSE.SN",  "Finance",      4.2,  10.5),
}

# Cours de référence (fallback si toutes les sources échouent)
PRIX_REF = {
    "SGBC": 11500, "ETIT": 16, "BACI": 5200, "BOAB": 5500,
    "NSBC": 6800, "CBIBF": 8900, "SIBC": 4850, "BNCI": 5100,
    "SNTS": 18500, "ORAC": 9200, "PALC": 6500, "SIFC": 5700,
    "SLBR": 185000, "STAB": 8500, "TTLS": 2400, "CIEC": 1850,
    "SDCI": 4500, "CFAC": 820, "ONTBF": 3250, "NEIM": 950,
}


def log(msg, level="INFO"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def check_deps():
    missing = []
    if not REQUESTS_OK:
        missing.extend(["requests", "beautifulsoup4", "lxml"])
    if not YF_OK:
        missing.append("yfinance")
    if missing:
        print("\n" + "="*60)
        print("  ❌  Bibliothèques manquantes. Lancez :")
        print(f"\n  pip install {' '.join(missing)}\n")
        print("="*60 + "\n")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE 1 : SIKA.FINANCE
# ══════════════════════════════════════════════════════════════════════════════
SIKA_URLS = [
    "https://www.sikafinance.com/marches/cotations",
    "https://www.sikafinance.com/marches/cotations-brvm",
]

def fetch_sika() -> list[dict]:
    """Scrape les cours BRVM depuis sikafinance.com."""
    if not REQUESTS_OK:
        return []

    log("━━━ Source 1 : sikafinance.com ━━━")
    session = requests.Session()
    session.headers.update(HEADERS)

    for url in SIKA_URLS:
        log(f"  Tentative : {url}")
        try:
            resp = session.get(url, timeout=25, verify=False)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            results = _parse_sika(soup)
            if results:
                log(f"  ✅ {len(results)} titres récupérés depuis sikafinance.com")
                return results
        except Exception as e:
            log(f"  ⚠️  {e}", "WARN")
            time.sleep(2)

    log("  ❌ sikafinance.com indisponible", "WARN")
    return []


def _parse_sika(soup: BeautifulSoup) -> list[dict]:
    """Extrait les données depuis le HTML de sikafinance.com."""
    results = []

    # Sika.finance utilise généralement un tableau avec classe "table"
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue

        headers = [th.get_text(" ", strip=True).lower() for th in rows[0].find_all(["th", "td"])]

        # Détecter les colonnes
        idx = {}
        for i, h in enumerate(headers):
            if re.search(r"ticker|code|valeur|titre|symbole", h):
                idx["ticker"] = i
            elif re.search(r"cours|dernier|clôture|close|price", h):
                idx["cours"] = i
            elif re.search(r"variation|var|%|evol|change", h):
                idx["variation"] = i
            elif re.search(r"volume|vol|quantité", h):
                idx["volume"] = i

        if "ticker" not in idx or "cours" not in idx:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(idx.values()):
                continue
            try:
                ticker = cells[idx["ticker"]].get_text(" ", strip=True).upper()
                ticker = re.sub(r"[^A-Z0-9]", "", ticker)[:6]
                if len(ticker) < 2:
                    continue

                cours_txt = cells[idx["cours"]].get_text(" ", strip=True)
                cours = float(re.sub(r"[^\d.]", "", cours_txt.replace(",", ".")))

                var = 0.0
                if "variation" in idx:
                    var_txt = cells[idx["variation"]].get_text(" ", strip=True)
                    m = re.search(r"[-+]?\d+[.,]\d+", var_txt)
                    if m:
                        var = float(m.group().replace(",", "."))

                if cours > 0:
                    results.append({
                        "ticker": ticker,
                        "cours": cours,
                        "variation": round(var, 2),
                        "dividende": TICKER_MAP.get(ticker, ("", "", 0, 0))[2] or "",
                        "per": TICKER_MAP.get(ticker, ("", "", 0, 0))[3] or "",
                    })
            except (ValueError, IndexError):
                continue

    # Fallback : chercher des balises avec data-attributes ou classes spécifiques
    if not results:
        results = _parse_sika_dynamic(soup)

    return results


def _parse_sika_dynamic(soup: BeautifulSoup) -> list[dict]:
    """Fallback : cherche les données dans des div/span avec les bons attributs."""
    results = []
    # Chercher des patterns ticker + cours dans tout le texte
    text = soup.get_text(" ")
    for ticker in TICKER_MAP.keys():
        pattern = rf"{ticker}\s+[\d\s]+([0-9][0-9\s.,]+)"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                cours = float(re.sub(r"[^\d.]", "", m.group(1).replace(",", ".")[:10]))
                if cours > 0:
                    results.append({
                        "ticker": ticker, "cours": cours, "variation": 0.0,
                        "dividende": TICKER_MAP[ticker][2], "per": TICKER_MAP[ticker][3],
                    })
            except ValueError:
                pass
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE 2 : YAHOO FINANCE (yfinance)
# ══════════════════════════════════════════════════════════════════════════════
def fetch_yahoo(missing_tickers: list[str]) -> list[dict]:
    """Récupère les cours depuis Yahoo Finance pour les tickers manquants."""
    if not YF_OK or not missing_tickers:
        return []

    log(f"━━━ Source 2 : Yahoo Finance ({len(missing_tickers)} tickers) ━━━")
    results = []

    for brvm_ticker in missing_tickers:
        if brvm_ticker not in TICKER_MAP:
            continue
        yf_ticker, sector, div_ref, per_ref = TICKER_MAP[brvm_ticker]
        try:
            data = yf.Ticker(yf_ticker)
            hist = data.history(period="2d")
            if hist.empty:
                log(f"  ⚠️  {brvm_ticker} ({yf_ticker}) : pas de données", "WARN")
                continue
            cours = round(float(hist["Close"].iloc[-1]), 2)
            var = 0.0
            if len(hist) >= 2:
                prev = float(hist["Close"].iloc[-2])
                var = round(((cours - prev) / prev) * 100, 2)

            # Yahoo renvoie en USD/GBP pour certains — convertir si nécessaire
            info = data.info
            currency = info.get("currency", "XOF")
            if currency == "GBp":  # pence → livres
                cours = cours / 100
            # Note : les vraies cotations BRVM sont en FCFA (XOF)

            results.append({
                "ticker": brvm_ticker,
                "cours": cours,
                "variation": var,
                "dividende": div_ref,
                "per": per_ref,
            })
            log(f"  ✅ {brvm_ticker} ({yf_ticker}) : {cours} ({currency}) Var:{var}%")
            time.sleep(0.3)
        except Exception as e:
            log(f"  ⚠️  {brvm_ticker} ({yf_ticker}) : {e}", "WARN")

    log(f"  → {len(results)} titres récupérés depuis Yahoo Finance")
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  ASSEMBLAGE & SAUVEGARDE
# ══════════════════════════════════════════════════════════════════════════════
def build_final(sika_data: list[dict], yahoo_data: list[dict]) -> list[dict]:
    """Fusionne les données des deux sources, complète avec les valeurs de référence."""
    final = {}

    # Priorité 1 : sikafinance.com
    for row in sika_data:
        final[row["ticker"]] = row

    # Priorité 2 : Yahoo Finance pour les manquants
    for row in yahoo_data:
        if row["ticker"] not in final:
            final[row["ticker"]] = row

    # Priorité 3 : valeurs de référence pour ce qui reste manquant
    for ticker in TICKER_MAP.keys():
        if ticker not in final and ticker in PRIX_REF:
            final[ticker] = {
                "ticker": ticker,
                "cours": PRIX_REF[ticker],
                "variation": 0.0,
                "dividende": TICKER_MAP[ticker][2],
                "per": TICKER_MAP[ticker][3],
            }
            log(f"  📌 {ticker} : valeur de référence utilisée (aucune source live)", "WARN")

    return list(final.values())


def save_csv(data: list[dict]):
    if not data:
        log("Aucune donnée à sauvegarder.", "WARN")
        return False
    fields = ["ticker", "cours", "variation", "dividende", "per"]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    log(f"✅ {len(data)} lignes sauvegardées → {OUTPUT_FILE.name}")
    return True


def print_summary(data: list[dict]):
    print("\n" + "="*60)
    print("  📊  RÉSUMÉ DE LA MISE À JOUR")
    print("="*60)
    print(f"  {'TICKER':<8} {'COURS':>10}  {'VAR%':>7}  {'DIV%':>6}  {'PER':>6}")
    print("  " + "-"*50)
    for row in sorted(data, key=lambda x: x["ticker"]):
        var = float(row.get("variation", 0))
        arrow = "▲" if var > 0 else ("▼" if var < 0 else "─")
        color_var = f"{arrow} {abs(var):.2f}%"
        print(f"  {row['ticker']:<8} {str(row['cours']):>10}  {color_var:>8}  "
              f"{str(row.get('dividende','')):>5}%  {str(row.get('per','')):>6}")
    print("="*60)
    print(f"\n  📂  Fichier généré : {OUTPUT_FILE.name}")
    print("  ➡️   Importez-le dans l'app : onglet 'Mettre à Jour' → 'Import CSV'\n")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("\n" + "="*60)
    print("  🏦  BRVM Invest Pro — Mise à jour des cours")
    print(f"  📅  {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("  🔌  Sources : sikafinance.com + Yahoo Finance")
    print("="*60 + "\n")

    check_deps()

    # Source 1 : sikafinance.com
    sika_data = fetch_sika()
    sika_tickers = {r["ticker"] for r in sika_data}

    # Source 2 : Yahoo Finance pour les tickers non trouvés sur sika
    missing = [t for t in TICKER_MAP.keys() if t not in sika_tickers]
    if missing:
        log(f"Tickers non trouvés sur sika ({len(missing)}) → Yahoo Finance : {', '.join(missing)}")
    yahoo_data = fetch_yahoo(missing)

    # Fusion
    final_data = build_final(sika_data, yahoo_data)

    # Sauvegarde
    if save_csv(final_data):
        print_summary(final_data)
    else:
        print("\n❌ Échec de la sauvegarde. Consultez brvm_maj.log\n")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⛔ Interrompu.")
    except Exception as e:
        log(f"Erreur inattendue : {e}", "ERROR")
        import traceback
        traceback.print_exc()
        sys.exit(1)
