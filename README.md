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

## Import des opérations
L'assistant d'import (bouton « Importer des opérations ») accepte les fichiers **CSV et Excel** :
- **DEGIRO** (export « Transactions », FR/EN) est reconnu automatiquement ;
- les autres exports (courtiers, banques, logiciels) sont analysés : colonnes reconnues en français, anglais,
  allemand et néerlandais, type d'opération lu dans une colonne dédiée, dans le libellé (« ACHAT COMPTANT… »)
  ou déduit du signe de la quantité ; l'utilisateur vérifie et corrige la correspondance avant d'importer ;
- la correspondance validée est mémorisée pour les imports suivants du même format.

Code : `engine/atlas/core/importers/` (`reader.py` lecture, `universal.py` détection et conversion).
Pour ajouter un préréglage courtier : un vrai fichier d'export (montants modifiés) + un test dans
`engine/tests/test_universal_import.py`.

Format standard ATLAS (le plus simple à produire à la main) :
```csv
date,type,symbol,name,quantity,price,currency,fees,amount,asset_class,country,sector
2024-01-15,buy,CW8,Amundi MSCI World,10,450.20,EUR,1.99,,etf,Monde,Diversifié
```
