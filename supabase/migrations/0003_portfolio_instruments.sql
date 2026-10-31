-- Métadonnées des titres saisies ou importées par l'utilisateur, propres à chaque portefeuille
-- (classe d'actif, pays, secteur), utilisées par le module Exposition réelle.
create table public.portfolio_instruments (
  portfolio_id uuid not null references public.portfolios (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  symbol text not null,
  name text,
  asset_class public.asset_class not null default 'other',
  currency char(3) not null default 'EUR',
  country text,
  sector text,
  updated_at timestamptz not null default now(),
  primary key (portfolio_id, symbol)
);
create index on public.portfolio_instruments (user_id);

alter table public.portfolio_instruments enable row level security;
create policy "données personnelles" on public.portfolio_instruments
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Un portefeuille, une transaction ou un import ne peut référencer qu'un portefeuille de son propriétaire
create or replace function public.check_portfolio_owner()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  if not exists (select 1 from public.portfolios p where p.id = new.portfolio_id and p.user_id = new.user_id) then
    raise exception 'Portefeuille introuvable pour cet utilisateur' using errcode = '42501';
  end if;
  return new;
end;
$$;
revoke execute on function public.check_portfolio_owner() from public, anon, authenticated;

create trigger portfolio_owner_transactions before insert or update on public.transactions
  for each row execute function public.check_portfolio_owner();
create trigger portfolio_owner_imports before insert or update on public.imports
  for each row execute function public.check_portfolio_owner();
create trigger portfolio_owner_instruments before insert or update on public.portfolio_instruments
  for each row execute function public.check_portfolio_owner();
