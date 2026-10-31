# ATLAS FINANCE

Plateforme web d'analyse de portefeuilles boursiers, modulable : chaque utilisateur compose son tableau de bord
à partir de modules d'analyse (exposition, risque, ETF, fiscalité, analyse technique…).

> Outil d'analyse uniquement. Aucun passage d'ordre. Ceci n'est pas un conseil en investissement.

## Organisation du dépôt

| Dossier | Contenu |
| --- | --- |
| `engine/` | Moteur de calcul Python (FastAPI) : registre de modules, imports, calculs |
| `web/` | Interface web Next.js |
| `supabase/migrations/` | Schéma de base de données et politiques de sécurité |
| `docs/` | Architecture et décisions |

## Démarrer en local

### Moteur de calcul
```bash
cd engine
pip install -e ".[dev]"
pytest                          # lance les tests
uvicorn atlas.api:app --reload  # API sur http://localhost:8000 (documentation : /docs)
```

### Interface web
```bash
cd web
npm install
npm run dev                     # http://localhost:3000
```
L'interface appelle le moteur à l'adresse définie dans `ENGINE_URL` (par défaut `http://localhost:8000`).

### Base de données
Créer un projet Supabase (région Europe), puis appliquer `supabase/migrations/0001_init.sql`
(éditeur SQL de Supabase ou `supabase db push`).

## Format d'import CSV standard
```csv
date,type,symbol,name,quantity,price,currency,fees,asset_class,country,sector
2024-01-15,buy,CW8,Amundi MSCI World,10,450.20,EUR,1.99,etf,World,Diversifié
```
Types acceptés : `buy`, `sell`, `dividend`, `fee`, `deposit`, `withdrawal`.
Des connecteurs spécifiques par courtier (Trade Republic, Degiro, Boursorama…) s'ajoutent dans
`engine/atlas/core/importers/`.
