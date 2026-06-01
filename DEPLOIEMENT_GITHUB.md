# 🚀 Déploiement BRVM Invest Pro sur GitHub Pages

## Résultat final
→ App accessible sur : `https://VOTRE_USERNAME.github.io/brvm-invest/`
→ Données mises à jour automatiquement chaque soir à 18h30

---

## Étape 1 — Créer le dépôt GitHub

1. Aller sur https://github.com/new
2. **Repository name** : `brvm-invest`
3. **Visibility** : Public ✅ (nécessaire pour GitHub Pages gratuit)
4. Cliquer **Create repository**

---

## Étape 2 — Pousser les fichiers

Ouvrir un terminal (CMD ou PowerShell) dans le dossier `PROJET BRVM` :

```bash
# Initialiser Git
git init
git add .
git commit -m "🚀 Initial deployment BRVM Invest Pro"

# Connecter à GitHub (remplacer VOTRE_USERNAME)
git remote add origin https://github.com/VOTRE_USERNAME/brvm-invest.git
git branch -M main
git push -u origin main
```

---

## Étape 3 — Activer GitHub Pages

1. Aller dans ton repo → **Settings** → **Pages**
2. **Source** : Deploy from a branch
3. **Branch** : `main` / `/ (root)`
4. Cliquer **Save**

✅ Après 2-3 minutes, ton app est en ligne sur :
`https://VOTRE_USERNAME.github.io/brvm-invest/`

---

## Étape 4 — Vérifier GitHub Actions

1. Aller dans l'onglet **Actions** du repo
2. Tu verras le workflow `📈 Update BRVM Data`
3. Cliquer **Run workflow** pour tester manuellement

Le workflow se déclenche automatiquement :
- **Lundi à vendredi à 18h30 UTC** (= 18h30 Abidjan)
- Il scrape BOA Direct, met à jour `brvm_cours.json` et commit

---

## Structure du projet

```
brvm-invest/
├── brvm_investissement.html    ← Application principale
├── brvm_cours.json             ← Cours (mis à jour automatiquement)
├── brvm_actualites.json        ← Actualités (mis à jour automatiquement)
├── scripts/
│   └── brvm_scrape_boa.py     ← Script de scraping BOA Direct
└── .github/
    └── workflows/
        └── update-data.yml    ← GitHub Actions (auto-update)
```

---

## Comment ça marche après déploiement

```
Chaque soir 18h30
      ↓
GitHub Actions scrape BOA Direct (boaksdirect.com)
      ↓
Extrait 47+ cours BRVM en temps réel
      ↓
Met à jour brvm_cours.json dans le repo
      ↓
L'app GitHub Pages charge automatiquement brvm_cours.json
      ↓
Tu ouvres l'app → cours à jour depuis n'importe où dans le monde
```

---

## Partager l'accès

L'URL publique `https://VOTRE_USERNAME.github.io/brvm-invest/` est accessible :
- Sur mobile, tablette, PC
- Sans installation
- Depuis n'importe quel pays
- Les données sont mises à jour chaque soir automatiquement

Pour un accès **privé** (protégé par mot de passe), il faut passer à GitHub Pro
ou utiliser un VPS. Pour la plupart des usages, le mode public est suffisant.

---

## Mise à jour manuelle

Si tu veux forcer une mise à jour :
1. Aller dans **Actions** → **📈 Update BRVM Data**
2. Cliquer **Run workflow** → **Run workflow**

Ou depuis ton PC (si Python et Playwright installés) :
```bash
cd "PROJET BRVM"
python scripts/brvm_scrape_boa.py
git add brvm_cours.json brvm_actualites.json
git commit -m "📈 MAJ manuelle"
git push
```
