# ATLAS FINANCE — Architecture (résumé de référence)

Document complet (avec schémas, sources, modèle économique) :
https://claude.ai/artifact/3ZA8J9uRead4hKT74Vk9iy

## Positionnement
SaaS d'analyse boursière modulable. L'utilisateur importe ses positions (CSV, saisie, clé API crypto en
lecture seule) et compose son tableau de bord à partir de modules. Aucun passage d'ordre.
Deux publics : investisseur long terme (ETF, risque, fiscalité) et trader actif (graphiques, backtests).

## Trois couches
1. **Interface** (`web/`, Next.js) : affiche les résultats, lit uniquement le cache de résultats.
2. **Socle** (Supabase / PostgreSQL) : comptes, abonnements, portefeuilles, transactions, données de marché, cache.
3. **Moteur** (`engine/`, FastAPI) : registre de modules ; chaque module lit portefeuille + marché et écrit un résultat.

## Contrat d'un module
Dossier `engine/atlas/modules/<id>/` :
- `manifest.json` : id, nom, version, famille, formule requise, paramètres (défaut, bornes), données nécessaires.
- `compute.py` : `compute(portfolio, market, params) -> ModuleResult`, fonction pure.
- `texts.fr.json` : libellés, méthode, avertissement.
- tests dans `engine/tests/`.

`ModuleResult` = liste de blocs typés : `kpi`, `table`, `timeseries`, `distribution`, `allocation`,
`chart_overlay`, `alert`, `note`. Chaque bloc porte la date des données.

## Catalogue (priorités)
**P1 (lancement)** : Vue d'ensemble, Exposition réelle, Chevauchement des ETF, Frais cumulés, Journal des opérations,
Comparateur d'ETF (tracking difference), Plan DCA, Tableau de risque, Profil et onboarding.

**P2** : Dividendes, Rééquilibrage, Portefeuilles modèles, Stress tests, VaR / Expected Shortfall, Projections
Monte-Carlo, Graphiques et indicateurs, Vue multi-échelles, Screener force relative, Alertes, Calculateur de
position, Plan et risque ouvert, Statistiques de trading, Suivi crypto, Enveloppes, Plus-values CTO (2074),
Plus-values crypto (2086), Synthèse IA.

**P3** : Somme importante (une fois vs étalé), Frontière efficiente, Volatilité par changements directionnels,
Détection de figures, Intermarchés, Indicateurs adaptatifs (Kalman), Backtest de stratégies, Fiche jeton crypto,
Veille actualités.

## Données
- Privées (RLS) : profiles, subscriptions, portfolios, transactions, imports, api_keys, targets, trading_rules,
  strategies, backtests, dashboards, alerts, module_results.
- Partagées (lecture seule) : instruments, prices_daily, etf_details, etf_holdings, index_returns,
  corporate_actions, dividends, fx_rates.
- Les transactions sont la seule source de vérité ; les positions se recalculent.

## Formules commerciales (hypothèses)
Gratuit, Base (6,99 €/mois), Pro (12,99 €/mois), Trader (19,99 €/mois), Conseiller (49 €/mois+).
