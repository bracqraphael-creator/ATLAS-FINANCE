# ATLAS FINANCE — SaaS d'analyse boursière modulable

## Ce que fait le produit
- Outil d'ANALYSE de portefeuilles et de marchés. Aucun passage d'ordre, aucune conservation de fonds.
- Un socle (comptes, portefeuilles, données de marché, tableau de bord) + des modules indépendants.
- Référence : `docs/ARCHITECTURE.md` (catalogue des modules, modèle de données, feuille de route).

## Structure
- `engine/` : moteur de calcul Python (FastAPI + pandas).
  - `engine/atlas/core/` : modèles (transactions, positions), contrat `ModuleResult`, registre, imports.
  - `engine/atlas/modules/<id>/` : un dossier par module (`manifest.json`, `compute.py`, `texts.fr.json`).
  - `engine/tests/` : tests pytest.
- `web/` : interface Next.js + TypeScript + Tailwind.
- `supabase/migrations/` : schéma PostgreSQL et politiques RLS.

## Commandes
- Moteur : `cd engine && pip install -e ".[dev]" && pytest` ; serveur : `uvicorn atlas.api:app --reload`
- Web : `cd web && npm install && npm run dev` ; vérification : `npm run lint && npm run build`

## Règles de code
- Un module = une fonction pure `compute(portfolio, market, params) -> ModuleResult`. Pas d'accès réseau ni base dans `compute`.
- Les transactions sont la seule source de vérité ; positions, performances et fiscalité se recalculent.
- Toute table privée a une politique RLS (et un test qui vérifie qu'un autre utilisateur ne la lit pas).
- Devise toujours explicite. `Decimal` pour les calculs fiscaux.
- Préférer une bibliothèque éprouvée (QuantStats, PyPortfolioOpt, pandas-ta, vectorbt) à une formule réécrite.

## Calculs financiers
- Chaque calcul a des tests chiffrés (valeur attendue écrite dans le test, calcul justifié en commentaire).
- Cas limites obligatoires : portefeuille vide, une ligne, historique court, devise étrangère, division d'action.
- Backtests : frais inclus, aucune donnée future (look-ahead), résultat hors échantillon affiché.

## Textes affichés (règle de conformité)
- Décrire et mesurer, jamais recommander : pas de « achetez », « vendez », « le meilleur pour vous ».
- Sous chaque résultat : méthode, date des données, mention « Ceci n'est pas un conseil en investissement ».
- Projections : plusieurs scénarios + hypothèses + « non garanti ».
- Alertes : constater (« le RSI est passé au-dessus de 70 »), jamais conseiller.

## Façon de travailler
- Petites étapes : une fonctionnalité, ses tests, vérification, commit.
- Lancer les tests avant de déclarer une tâche terminée.
- Ne jamais committer de secrets ; variables dans `.env` (modèle dans `.env.example`).
- Textes de l'interface en français.
