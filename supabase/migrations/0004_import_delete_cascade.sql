-- Supprimer un import supprime les opérations qu'il a créées (auparavant elles restaient, détachées).
-- Les politiques RLS existantes s'appliquent : un utilisateur ne supprime que ses propres imports.
alter table public.transactions drop constraint if exists transactions_import_id_fkey;
alter table public.transactions
  add constraint transactions_import_id_fkey
  foreign key (import_id) references public.imports (id) on delete cascade;
create index if not exists transactions_import_id_idx on public.transactions (import_id);
