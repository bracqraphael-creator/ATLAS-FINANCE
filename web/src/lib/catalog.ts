// Familles de modules et modules prévus (affichés grisés tant qu'ils ne sont pas livrés).
// Source : docs/ARCHITECTURE.md, catalogue des modules.

export const FAMILIES: { id: string; label: string }[] = [
  { id: "portefeuille", label: "Portefeuille" },
  { id: "long-terme", label: "Long terme" },
  { id: "risque", label: "Risque" },
  { id: "marches", label: "Marchés" },
  { id: "fiscalite", label: "Fiscalité" },
];

export const UPCOMING: { family: string; name: string }[] = [
  { family: "long-terme", name: "Comparateur d'ETF" },
  { family: "long-terme", name: "Rééquilibrage" },
  { family: "risque", name: "Stress tests" },
  { family: "risque", name: "Projections" },
  { family: "marches", name: "Graphiques et indicateurs" },
  { family: "marches", name: "Force relative" },
  { family: "marches", name: "Backtest" },
  { family: "fiscalite", name: "Revenus à déclarer" },
];
