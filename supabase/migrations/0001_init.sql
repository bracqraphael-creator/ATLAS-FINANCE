-- ATLAS FINANCE — schéma initial
-- Données privées : protégées par RLS (chaque utilisateur ne voit que ses lignes).
-- Données de marché : partagées, lecture seule pour les utilisateurs connectés,
-- écriture réservée au service (clé service_role, qui contourne RLS).

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Types
-- ---------------------------------------------------------------------------
create type public.plan_tier as enum ('free', 'base', 'pro', 'trader', 'advisor');
create type public.account_wrapper as enum ('pea', 'pea_pme', 'cto', 'assurance_vie', 'per', 'crypto', 'other');
create type public.transaction_type as enum ('buy', 'sell', 'dividend', 'fee', 'deposit', 'withdrawal', 'split');
create type public.asset_class as enum ('equity', 'etf', 'bond', 'crypto', 'cash', 'fund', 'commodity', 'other');

-- ---------------------------------------------------------------------------
-- Données privées
-- ---------------------------------------------------------------------------
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  base_currency char(3) not null default 'EUR',
  investor_profile jsonb not null default '{}'::jsonb,  -- horizon, style, temps disponible, tolérance au stress
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.subscriptions (
  user_id uuid primary key references auth.users (id) on delete cascade,
  plan public.plan_tier not null default 'free',
  status text not null default 'active',
  stripe_customer_id text,
  stripe_subscription_id text,
  current_period_end timestamptz,
  extra_modules text[] not null default '{}',
  updated_at timestamptz not null default now()
);

create table public.portfolios (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  wrapper public.account_wrapper not null default 'cto',
  broker text,
  currency char(3) not null default 'EUR',
  created_at timestamptz not null default now()
);
create index on public.portfolios (user_id);

create table public.imports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  portfolio_id uuid not null references public.portfolios (id) on delete cascade,
  file_path text,                 -- chemin dans Supabase Storage
  detected_format text,
  rows_imported integer not null default 0,
  rows_rejected jsonb not null default '[]'::jsonb,
  status text not null default 'pending',
  created_at timestamptz not null default now()
);
create index on public.imports (user_id);

create table public.transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  portfolio_id uuid not null references public.portfolios (id) on delete cascade,
  import_id uuid references public.imports (id) on delete set null,
  trade_date date not null,
  type public.transaction_type not null,
  symbol text,
  isin text,
  name text,
  quantity numeric(24, 10) not null default 0,
  price numeric(24, 10) not null default 0,
  currency char(3) not null default 'EUR',
  fees numeric(24, 10) not null default 0,
  amount numeric(24, 10),          -- montant pour dividendes, frais, dépôts, retraits
  note text,
  created_at timestamptz not null default now()
);
create index on public.transactions (user_id);
create index on public.transactions (portfolio_id, trade_date);

create table public.api_keys (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  portfolio_id uuid references public.portfolios (id) on delete cascade,
  exchange text not null,
  vault_secret_id uuid not null,   -- clé chiffrée dans Supabase Vault, jamais en clair ici
  read_only_verified boolean not null default false,
  last_sync_at timestamptz,
  created_at timestamptz not null default now()
);
create index on public.api_keys (user_id);

create table public.targets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  portfolio_id uuid not null references public.portfolios (id) on delete cascade,
  allocation jsonb not null default '{}'::jsonb,   -- {"CW8": 0.8, "PAEEM": 0.2}
  dca_amount numeric(14, 2),
  dca_frequency text,                              -- monthly, quarterly
  dca_day smallint,
  updated_at timestamptz not null default now()
);
create index on public.targets (user_id);

create table public.trading_rules (
  user_id uuid primary key references auth.users (id) on delete cascade,
  risk_per_trade_pct numeric(6, 3),
  max_daily_loss_pct numeric(6, 3),
  min_reward_risk numeric(6, 2),
  trend_timeframe text,
  signal_timeframe text,
  updated_at timestamptz not null default now()
);

create table public.strategies (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  rules jsonb not null,
  created_at timestamptz not null default now()
);
create index on public.strategies (user_id);

create table public.backtests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  strategy_id uuid not null references public.strategies (id) on delete cascade,
  params jsonb not null default '{}'::jsonb,
  result jsonb,
  created_at timestamptz not null default now()
);
create index on public.backtests (user_id);

create table public.dashboards (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null default 'Mon tableau de bord',
  layout jsonb not null default '[]'::jsonb,       -- [{module, x, y, w, h, params}]
  updated_at timestamptz not null default now()
);
create index on public.dashboards (user_id);

create table public.alerts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  condition jsonb not null,
  channels text[] not null default '{email}',
  active boolean not null default true,
  last_triggered_at timestamptz,
  created_at timestamptz not null default now()
);
create index on public.alerts (user_id);

create table public.module_results (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  portfolio_id uuid not null references public.portfolios (id) on delete cascade,
  module_id text not null,
  params_hash text not null,
  data_as_of date not null,
  result jsonb not null,
  computed_at timestamptz not null default now(),
  unique (portfolio_id, module_id, params_hash, data_as_of)
);
create index on public.module_results (user_id);

-- ---------------------------------------------------------------------------
-- Données de marché partagées
-- ---------------------------------------------------------------------------
create table public.instruments (
  id uuid primary key default gen_random_uuid(),
  symbol text not null,
  exchange text not null default '',
  isin text,
  name text not null,
  asset_class public.asset_class not null,
  currency char(3) not null,
  country text,
  sector text,
  pea_eligible boolean,
  unique (symbol, exchange)
);
create index on public.instruments (isin);

create table public.prices_daily (
  instrument_id uuid not null references public.instruments (id) on delete cascade,
  price_date date not null,
  open numeric(24, 10),
  high numeric(24, 10),
  low numeric(24, 10),
  close numeric(24, 10) not null,
  adj_close numeric(24, 10),
  volume numeric(24, 4),
  primary key (instrument_id, price_date)
);

create table public.etf_details (
  instrument_id uuid primary key references public.instruments (id) on delete cascade,
  issuer text,
  index_name text,
  replication text,              -- physique, synthétique, échantillonnage
  distribution text,             -- capitalisant, distribuant
  hedged boolean not null default false,
  ter_pct numeric(6, 4),
  aum numeric(20, 2),
  inception_date date
);

create table public.etf_holdings (
  etf_id uuid not null references public.instruments (id) on delete cascade,
  as_of date not null,
  holding_name text not null,
  holding_isin text,
  weight numeric(10, 8) not null,
  country text,
  sector text,
  primary key (etf_id, as_of, holding_name)
);

create table public.index_returns (
  index_name text not null,
  variant text not null,         -- price, net, gross
  currency char(3) not null,
  year smallint not null,
  return_pct numeric(10, 6) not null,
  primary key (index_name, variant, currency, year)
);

create table public.corporate_actions (
  id uuid primary key default gen_random_uuid(),
  instrument_id uuid not null references public.instruments (id) on delete cascade,
  action_date date not null,
  kind text not null,            -- split, dividend, merger
  ratio numeric(20, 10),
  amount numeric(24, 10),
  currency char(3)
);
create index on public.corporate_actions (instrument_id, action_date);

create table public.fx_rates (
  rate_date date not null,
  base char(3) not null,
  quote char(3) not null,
  rate numeric(20, 10) not null,
  primary key (rate_date, base, quote)
);

-- ---------------------------------------------------------------------------
-- Sécurité par ligne (RLS)
-- ---------------------------------------------------------------------------
alter table public.profiles enable row level security;
alter table public.subscriptions enable row level security;
alter table public.portfolios enable row level security;
alter table public.imports enable row level security;
alter table public.transactions enable row level security;
alter table public.api_keys enable row level security;
alter table public.targets enable row level security;
alter table public.trading_rules enable row level security;
alter table public.strategies enable row level security;
alter table public.backtests enable row level security;
alter table public.dashboards enable row level security;
alter table public.alerts enable row level security;
alter table public.module_results enable row level security;

-- Profils : clé = id
create policy "profil personnel" on public.profiles
  for all using (auth.uid() = id) with check (auth.uid() = id);

-- Abonnement : lecture seule pour l'utilisateur ; écrit par le webhook Stripe (service_role)
create policy "abonnement en lecture" on public.subscriptions
  for select using (auth.uid() = user_id);

-- Cache de résultats : lecture seule pour l'utilisateur ; écrit par le moteur (service_role)
create policy "résultats en lecture" on public.module_results
  for select using (auth.uid() = user_id);

-- Tables privées classiques : clé = user_id
do $$
declare t text;
begin
  foreach t in array array['portfolios', 'imports', 'transactions', 'api_keys', 'targets',
                           'trading_rules', 'strategies', 'backtests', 'dashboards', 'alerts']
  loop
    execute format(
      'create policy "données personnelles" on public.%I for all '
      'using (auth.uid() = user_id) with check (auth.uid() = user_id)', t);
  end loop;
end $$;

-- Données de marché : lecture pour tout utilisateur connecté
alter table public.instruments enable row level security;
alter table public.prices_daily enable row level security;
alter table public.etf_details enable row level security;
alter table public.etf_holdings enable row level security;
alter table public.index_returns enable row level security;
alter table public.corporate_actions enable row level security;
alter table public.fx_rates enable row level security;

do $$
declare t text;
begin
  foreach t in array array['instruments', 'prices_daily', 'etf_details', 'etf_holdings',
                           'index_returns', 'corporate_actions', 'fx_rates']
  loop
    execute format(
      'create policy "lecture marché" on public.%I for select to authenticated using (true)', t);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- Création automatique du profil et de l'abonnement gratuit à l'inscription
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1)));
  insert into public.subscriptions (user_id) values (new.id);
  insert into public.dashboards (user_id) values (new.id);
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
