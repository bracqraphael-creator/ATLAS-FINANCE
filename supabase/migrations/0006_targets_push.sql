-- Répartition cible par portefeuille (module Rééquilibrage) et abonnements aux notifications (application mobile).

-- Une répartition cible par portefeuille, rattachée à un portefeuille du même propriétaire
create unique index if not exists targets_portfolio_unique on public.targets (portfolio_id);
create trigger portfolio_owner_targets before insert or update on public.targets
  for each row execute function public.check_portfolio_owner();

-- Abonnements Web Push : un par navigateur ou téléphone, lus et gérés par leur propriétaire
create table public.push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  endpoint text not null unique,
  p256dh text not null,
  auth text not null,
  user_agent text,
  created_at timestamptz not null default now()
);
create index on public.push_subscriptions (user_id);
alter table public.push_subscriptions enable row level security;
create policy "données personnelles" on public.push_subscriptions
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Réglages serveur (clés VAPID des notifications) : écriture et lecture réservées au rôle service
create or replace function public.get_private_setting(setting text)
returns text language sql security definer set search_path = public, private
as $$ select value from private.settings where key = setting; $$;
create or replace function public.set_private_setting(setting text, val text)
returns void language sql security definer set search_path = public, private
as $$ insert into private.settings (key, value) values (setting, val)
      on conflict (key) do nothing; $$;
revoke execute on function public.get_private_setting(text) from public, anon, authenticated;
revoke execute on function public.set_private_setting(text, text) from public, anon, authenticated;
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant execute on function public.get_private_setting(text) to service_role;
    grant execute on function public.set_private_setting(text, text) to service_role;
  end if;
end $$;
