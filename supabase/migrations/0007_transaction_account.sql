-- Compte d'origine de chaque opération (« Compte PEA », « Compte courant »…) : un portefeuille peut regrouper
-- plusieurs comptes d'un même courtier, ventilés comme dans l'application du courtier.
alter table public.transactions add column if not exists account text;
create index if not exists transactions_portfolio_account_idx on public.transactions (portfolio_id, account);
