-- Alertes : règles rattachées à un portefeuille, historique des déclenchements, jeton de la tâche planifiée.

-- Règles (table créée en 0001, complétée ici) : condition = {kind, symbol, threshold, direction}
alter table public.alerts
  add column portfolio_id uuid references public.portfolios (id) on delete cascade,
  add column name text;
create index if not exists alerts_portfolio_idx on public.alerts (portfolio_id);
create trigger portfolio_owner_alerts before insert or update on public.alerts
  for each row when (new.portfolio_id is not null) execute function public.check_portfolio_owner();

-- Déclenchements : écrits par la fonction serveur (rôle service), lus et effacés par leur propriétaire
create table public.alert_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  alert_id uuid not null references public.alerts (id) on delete cascade,
  portfolio_id uuid references public.portfolios (id) on delete cascade,
  event_key text not null unique,          -- règle + titre + date : un même franchissement n'est noté qu'une fois
  triggered_on date not null,
  symbol text,
  value numeric,
  message text not null,
  notified_at timestamptz,                 -- e-mail envoyé
  created_at timestamptz not null default now()
);
create index on public.alert_events (user_id, created_at desc);

alter table public.alert_events enable row level security;
create policy "déclenchements : lecture" on public.alert_events for select using (auth.uid() = user_id);
create policy "déclenchements : effacement" on public.alert_events for delete using (auth.uid() = user_id);

-- Jeton de la tâche planifiée : seule la fonction serveur (rôle service) peut le vérifier
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
create table private.settings (key text primary key, value text not null);
insert into private.settings (key, value)
  values ('alerts_cron_token', replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''))
  on conflict (key) do nothing;

create or replace function public.check_alerts_cron_token(token text)
returns boolean
language sql
security definer set search_path = public, private
as $$
  select exists (select 1 from private.settings where key = 'alerts_cron_token' and value = token);
$$;
revoke execute on function public.check_alerts_cron_token(text) from public, anon, authenticated;
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant execute on function public.check_alerts_cron_token(text) to service_role;
  end if;
end $$;
