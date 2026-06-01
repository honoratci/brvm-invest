#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║  BRVM Scraper — BOA Direct + Actualités                     ║
║  Utilisé par GitHub Actions pour mettre à jour les données  ║
╚══════════════════════════════════════════════════════════════╝
Usage : python scripts/brvm_scrape_boa.py
Sortie : brvm_cours.json, brvm_actualites.json
"""

import json, re, datetime, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ═════════════════════════════════════════════════════════════════════════════
#  EXTRACTION DES COURS — BOA Direct (Playwright headless)
# ═════════════════════════════════════════════════════════════════════════════
JS_EXTRACT = """
() => {
    const tickerEl = document.querySelector('[class*="ticker"]');
    if (!tickerEl) return '';
    const raw = tickerEl.innerText;
    const lines = raw.split('\\n').map(l => l.trim()).filter(l => l);
    const out = [];
    for (let i = 0; i < lines.length - 2; i++) {
        const t = lines[i];
        if (/^[A-Z]{3,6}(\\.[A-Z0-9]+)?$/.test(t)) {
            const price = parseFloat(lines[i+1]?.replace(/\\s/g, ''));
            const vari  = parseFloat(lines[i+2]?.replace(/\\s/g, ''));
            if (!isNaN(price) && price > 0 && price < 1_000_000) {
                out.push(t + '|' + price + '|' + (isNaN(vari) ? 0 : vari));
                i += 2;
            }
        }
    }
    return out.join('\\n');
}
"""


def scrape_boa_direct():
    """Charge boaksdirect.com avec Playwright et extrait les cours."""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print("🌐 Connexion à BOA Direct...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
            locale="fr-FR",
        )
        page = context.new_page()

        try:
            page.goto("https://boaksdirect.com/index.html", wait_until="networkidle", timeout=30_000)
        except PWTimeout:
            page.goto("https://boaksdirect.com/index.html", timeout=20_000)

        # Attendre que le ticker soit peuplé
        try:
            page.wait_for_function(
                "document.querySelector('[class*=\"ticker\"]')?.innerText?.length > 100",
                timeout=10_000,
            )
        except PWTimeout:
            page.wait_for_timeout(5_000)

        raw = page.evaluate(JS_EXTRACT)
        browser.close()

    if not raw:
        print("⚠️  Aucune donnée extraite depuis le ticker BOA Direct")
        return {}

    cours = {}
    for line in raw.strip().split("\n"):
        parts = line.strip().split("|")
        if len(parts) == 3:
            t, p, v = parts
            try:
                cours[t] = {"price": float(p), "var1d": round(float(v), 2)}
            except ValueError:
                pass

    print(f"✅ BOA Direct : {len(cours)} titres extraits")
    return cours


# ═════════════════════════════════════════════════════════════════════════════
#  FALLBACK — sikafinance.com (sans JS)
# ═════════════════════════════════════════════════════════════════════════════
def scrape_sikafinance():
    """Fallback : scraping sikafinance.com (HTML statique)."""
    import requests
    from bs4 import BeautifulSoup

    print("🌐 Fallback : sikafinance.com...")
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
    cours = {}
    urls = [
        "https://www.sikafinance.com/marches/cotations",
        "https://www.sikafinance.com/marches/cotations-brvm",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
            soup = BeautifulSoup(r.text, "lxml")
            for row in soup.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) >= 4:
                    ticker = cols[0].get_text(strip=True).upper()
                    if not re.match(r"^[A-Z]{3,6}$", ticker):
                        continue
                    try:
                        price = float(cols[2].get_text(strip=True).replace(" ", "").replace(",", "."))
                        var   = float(cols[3].get_text(strip=True).replace(" ", "").replace(",", ".").replace("%",""))
                        cours[ticker] = {"price": price, "var1d": round(var, 2)}
                    except (ValueError, IndexError):
                        pass
        except Exception as e:
            print(f"  Erreur {url}: {e}")
    print(f"✅ Sikafinance : {len(cours)} titres")
    return cours


# ═════════════════════════════════════════════════════════════════════════════
#  ACTUALITÉS — WebSearch via requêtes ciblées
# ═════════════════════════════════════════════════════════════════════════════
def fetch_news_rss():
    """Tente de récupérer des actualités via flux RSS."""
    import feedparser, requests

    FEEDS = [
        ("Agence Ecofin Bourse",   "https://www.agenceecofin.com/rss/bourse.xml"),
        ("Agence Ecofin Finance",  "https://www.agenceecofin.com/rss/finance.xml"),
        ("Commodafrica",           "https://www.commodafrica.com/feed"),
    ]
    TICKERS = {
        "sonatel": "SNTS", "orange ci": "ORAC", "société générale": "SGBC",
        "sgbci": "SGBC", "ecobank ci": "ECOC", "palm ci": "PALC", "palmci": "PALC",
        "coris bank": "CBIBF", "onatel": "ONTBF", "totalenergies ci": "TTLC",
        "totalenergies sn": "TTLS", "bank of africa": "BOAB", "nsia": "NSBC",
        "solibra": "SLBC", "cie ": "CIEC", "setao": "STAC",
    }
    POS_KW = ["hausse","croissance","bénéfice","dividende","record","succès","progression"]
    NEG_KW = ["baisse","perte","chute","recul","crise","déficit","suspension"]
    CAT_KW = {
        "Dividende": ["dividende","coupon","distribution"],
        "Résultats": ["résultat","bénéfice","profit","chiffre"],
        "Stratégie": ["acquisition","fusion","partenariat","nomination"],
        "Marché":    ["brvm","indice","cotation","volume"],
    }

    news = []
    for name, url in FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:12]:
                title   = re.sub(r"<[^>]+>", "", e.get("title", "")).strip()
                summary = re.sub(r"<[^>]+>", "", e.get("summary", e.get("description", ""))).strip()[:300]
                if not title:
                    continue
                txt = (title + " " + summary).lower()

                # Ticker
                ticker = next((v for k, v in TICKERS.items() if k in txt), None)

                # Impact
                pos = sum(1 for w in POS_KW if w in txt)
                neg = sum(1 for w in NEG_KW if w in txt)
                impact = "positive" if pos > neg else "negative" if neg > pos else "neutral"

                # Catégorie
                cat = next((k for k, kws in CAT_KW.items() if any(w in txt for w in kws)), "Macro")

                # Date
                try:
                    from email.utils import parsedate_to_datetime
                    date = parsedate_to_datetime(e.get("published", "")).strftime("%Y-%m-%d")
                except Exception:
                    date = datetime.date.today().isoformat()

                news.append({
                    "titre":    title,
                    "source":   name,
                    "date":     date,
                    "ticker":   ticker,
                    "categorie": cat,
                    "resume":   summary or title,
                    "url":      e.get("link", ""),
                    "impact":   impact,
                })
        except Exception as ex:
            print(f"  Flux RSS {name}: {ex}")

    # Dédoublonner
    seen, unique = set(), []
    for n in news:
        key = n["titre"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(n)

    unique.sort(key=lambda x: x["date"], reverse=True)
    return unique[:50]


# ═════════════════════════════════════════════════════════════════════════════
#  MISE À JOUR brvm_cours.json
# ═════════════════════════════════════════════════════════════════════════════
def save_cours(cours, source_info):
    today  = datetime.date.today().isoformat()
    output = [
        {"ticker": t, "price": d["price"], "var1d": d["var1d"],
         "date": today, "source": source_info}
        for t, d in sorted(cours.items())
    ]
    path = ROOT / "brvm_cours.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ brvm_cours.json — {len(output)} titres")


def save_news(news):
    path = ROOT / "brvm_actualites.json"
    path.write_text(json.dumps(news, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ brvm_actualites.json — {len(news)} articles")


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════════
def main():
    print("\n" + "═"*55)
    print(f"  📊 BRVM Scraper — {datetime.datetime.now():%d/%m/%Y %H:%M}")
    print("═"*55 + "\n")

    # ── Cours ────────────────────────────────────────────────────────────────
    cours = {}
    source = "BOA Direct — boaksdirect.com"

    # Essai 1 : BOA Direct (Playwright)
    try:
        cours = scrape_boa_direct()
    except Exception as e:
        print(f"⚠️  BOA Direct échoué : {e}")

    # Essai 2 : sikafinance.com
    if len(cours) < 5:
        try:
            import requests, urllib3
            urllib3.disable_warnings()
            cours  = scrape_sikafinance()
            source = "Sika Finance — sikafinance.com"
        except Exception as e:
            print(f"⚠️  Sikafinance échoué : {e}")

    if cours:
        save_cours(cours, source)
        print(f"  Source : {source}")
    else:
        print("❌ Aucune donnée de cours disponible")

    # ── Actualités ────────────────────────────────────────────────────────────
    try:
        news = fetch_news_rss()
        if news:
            save_news(news)
        else:
            print("⚠️  Aucune actualité RSS disponible")
    except Exception as e:
        print(f"⚠️  Actualités : {e}")

    print("\n✅ Terminé\n")


if __name__ == "__main__":
    main()
