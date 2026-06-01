#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================
  BRVM Invest Pro — Récupération des actualités
  Sources : agenceecofin.com, sikafinance.com,
            fratmat.info, abidjan.net, commodafrica.com
  Usage   : python brvm_news.py
  Sortie  : brvm_actualites.json
====================================================
PRÉREQUIS :
  pip install requests beautifulsoup4 lxml feedparser
====================================================
"""

import json, sys, re, time, datetime
from pathlib import Path

OUTPUT_FILE = Path(__file__).parent / "brvm_actualites.json"
LOG_FILE    = Path(__file__).parent / "brvm_news.log"

try:
    import requests
    from bs4 import BeautifulSoup
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    import feedparser
    FEED_OK = True
except ImportError:
    FEED_OK = False

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# Tickers BRVM pour détecter les sociétés dans les titres
TICKER_KEYWORDS = {
    "SNTS":  ["sonatel", "orange sénégal", "orange senegal"],
    "ORAC":  ["orange ci", "orange côte d'ivoire", "orange ivoire"],
    "SGBC":  ["société générale", "sgbci", "société générale côte"],
    "ETIT":  ["ecobank", "eti "],
    "BACI":  ["banque atlantique", "baci"],
    "BOAB":  ["bank of africa", "boa bénin", "boa benin"],
    "NSBC":  ["nsia banque", "nsia"],
    "CBIBF": ["coris bank", "coris bourse"],
    "SIBC":  ["sib ", "société ivoirienne de banque"],
    "PALC":  ["palmci", "palm ci", "palme"],
    "SIFC":  ["sifca", "hévéa"],
    "SLBR":  ["solibra", "brasserie"],
    "STAB":  ["sitab", "tabac"],
    "TTLS":  ["total ci", "totalenergies", "total énergie"],
    "CIEC":  ["cie ", "compagnie ivoirienne d'élect", "électricité ci"],
    "SDCI":  ["sodeci", "eau potable ci"],
    "CFAC":  ["cfao", "cfao ci"],
    "ONTBF": ["onatel", "telecel burkina"],
    "CBIBF": ["coris bank"],
}

def log(msg, level="INFO"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def detect_ticker(text):
    text_low = text.lower()
    for ticker, keywords in TICKER_KEYWORDS.items():
        for kw in keywords:
            if kw in text_low:
                return ticker
    return None

def detect_impact(text):
    text_low = text.lower()
    positive = ["hausse", "croissance", "bénéfice", "dividende", "augmentation",
                "record", "succès", "progression", "amélioration", "gain", "+"]
    negative = ["baisse", "perte", "chute", "recul", "difficulté", "crise",
                "déficit", "suspension", "fermeture", "sanction", "-"]
    score = sum(1 for w in positive if w in text_low) - sum(1 for w in negative if w in text_low)
    return "positive" if score > 0 else "negative" if score < 0 else "neutral"

def detect_category(text):
    text_low = text.lower()
    if any(w in text_low for w in ["dividende", "distribution", "coupon"]): return "Dividende"
    if any(w in text_low for w in ["résultat", "bénéfice", "chiffre d'affaires", "profit", "perte"]): return "Résultats"
    if any(w in text_low for w in ["acquisition", "fusion", "stratégie", "partenariat", "direction", "nomination"]): return "Stratégie"
    if any(w in text_low for w in ["brvm", "indice", "marché boursier", "cotation", "volume"]): return "Marché"
    return "Macro"

def fetch_url(url, timeout=20):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
        r.raise_for_status()
        return r.text
    except Exception as e:
        log(f"Erreur {url}: {e}", "WARN")
        return None

def clean_text(t):
    if not t: return ""
    t = re.sub(r'\s+', ' ', t).strip()
    t = re.sub(r'<[^>]+>', '', t)
    return t[:500]

# ══════════════════════════════════════════════════════════════════════════════
#  SOURCES RSS (plus fiables que le scraping HTML)
# ══════════════════════════════════════════════════════════════════════════════
RSS_FEEDS = [
    { "name": "Agence Ecofin", "url": "https://www.agenceecofin.com/rss/bourse.xml" },
    { "name": "Agence Ecofin Finance", "url": "https://www.agenceecofin.com/rss/finance.xml" },
    { "name": "Commodafrica", "url": "https://www.commodafrica.com/feed" },
]

def fetch_rss_feeds():
    if not FEED_OK:
        log("feedparser non installé — RSS ignorés", "WARN")
        return []
    all_news = []
    for feed_info in RSS_FEEDS:
        log(f"RSS: {feed_info['name']}")
        try:
            feed = feedparser.parse(feed_info["url"])
            count = 0
            for entry in feed.entries[:15]:
                title = clean_text(entry.get("title", ""))
                summary = clean_text(entry.get("summary", entry.get("description", "")))
                url = entry.get("link", "")
                pub_date = entry.get("published", "")
                # Formater la date
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(pub_date)
                    date_str = dt.strftime("%Y-%m-%d")
                except:
                    date_str = datetime.date.today().isoformat()

                ticker = detect_ticker(title + " " + summary)
                impact = detect_impact(title + " " + summary)
                cat = detect_category(title + " " + summary)

                if title:
                    all_news.append({
                        "titre": title, "source": feed_info["name"],
                        "date": date_str, "ticker": ticker,
                        "categorie": cat, "resume": summary or title,
                        "url": url, "impact": impact
                    })
                    count += 1
            log(f"  → {count} articles depuis {feed_info['name']}")
        except Exception as e:
            log(f"  Erreur RSS {feed_info['name']}: {e}", "WARN")
        time.sleep(1)
    return all_news

# ══════════════════════════════════════════════════════════════════════════════
#  SCRAPING HTML : sikafinance.com
# ══════════════════════════════════════════════════════════════════════════════
def fetch_sika_news():
    log("HTML: sikafinance.com/actualites")
    html = fetch_url("https://www.sikafinance.com/actualites")
    if not html: return []
    soup = BeautifulSoup(html, "lxml")
    news = []
    # Chercher les articles
    articles = soup.find_all(["article", "div"], class_=re.compile(r"article|news|post|card", re.I))
    for art in articles[:20]:
        title_tag = art.find(["h1","h2","h3","h4","a"])
        if not title_tag: continue
        title = clean_text(title_tag.get_text())
        if len(title) < 20: continue
        link = title_tag.get("href", "") if title_tag.name == "a" else (art.find("a") or {}).get("href", "")
        if link and not link.startswith("http"): link = "https://www.sikafinance.com" + link
        summary_tag = art.find("p")
        summary = clean_text(summary_tag.get_text()) if summary_tag else ""
        ticker = detect_ticker(title + " " + summary)
        news.append({
            "titre": title, "source": "Sika Finance",
            "date": datetime.date.today().isoformat(),
            "ticker": ticker,
            "categorie": detect_category(title + " " + summary),
            "resume": summary or title[:200],
            "url": link or "https://www.sikafinance.com/actualites",
            "impact": detect_impact(title + " " + summary)
        })
    log(f"  → {len(news)} articles depuis sikafinance.com")
    return news

# ══════════════════════════════════════════════════════════════════════════════
#  SCRAPING HTML : fratmat.info
# ══════════════════════════════════════════════════════════════════════════════
def fetch_fratmat_news():
    log("HTML: fratmat.info/economie")
    html = fetch_url("https://www.fratmat.info/economie")
    if not html: return []
    soup = BeautifulSoup(html, "lxml")
    news = []
    for tag in soup.find_all(["h2","h3","h4"])[:25]:
        a = tag.find("a")
        if not a: continue
        title = clean_text(a.get_text())
        if len(title) < 20: continue
        link = a.get("href", "")
        if link and not link.startswith("http"): link = "https://www.fratmat.info" + link
        ticker = detect_ticker(title)
        news.append({
            "titre": title, "source": "Fratmat.info",
            "date": datetime.date.today().isoformat(),
            "ticker": ticker,
            "categorie": detect_category(title),
            "resume": title,
            "url": link or "https://www.fratmat.info",
            "impact": detect_impact(title)
        })
    log(f"  → {len(news)} articles depuis fratmat.info")
    return news

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("\n" + "="*60)
    print("  📰  BRVM Invest Pro — Récupération des actualités")
    print(f"  📅  {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("="*60 + "\n")

    if not REQUESTS_OK:
        print("❌ Installez : pip install requests beautifulsoup4 lxml feedparser")
        sys.exit(1)

    all_news = []

    # RSS (le plus fiable)
    all_news.extend(fetch_rss_feeds())
    time.sleep(2)

    # HTML scraping
    all_news.extend(fetch_sika_news())
    time.sleep(1.5)
    all_news.extend(fetch_fratmat_news())

    # Dédoublonner par titre
    seen = set()
    unique = []
    for n in all_news:
        key = n["titre"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(n)

    # Trier par date décroissante
    unique.sort(key=lambda x: x.get("date",""), reverse=True)

    # Sauvegarder
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    print("\n" + "="*60)
    print(f"  ✅  {len(unique)} actualités sauvegardées → {OUTPUT_FILE.name}")
    print("="*60)
    print("\n  Importez brvm_actualites.json dans l'app :")
    print("  Onglet '📰 Actualités' → bouton 'Charger actualités'\n")

if __name__ == "__main__":
    if not REQUESTS_OK:
        print("❌ pip install requests beautifulsoup4 lxml feedparser")
        sys.exit(1)
    try:
        main()
    except KeyboardInterrupt:
        print("\n⛔ Interrompu.")
    except Exception as e:
        log(f"Erreur: {e}", "ERROR")
        import traceback; traceback.print_exc()
