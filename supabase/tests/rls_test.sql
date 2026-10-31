-- Test RLS : un utilisateur ne doit jamais lire ni écrire les données d'un autre.
-- Lancement : voir supabase/tests/run_rls_test.sh
\set ON_ERROR_STOP on
grant select, insert, update, delete on all tables in schema public to authenticated;

insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-00000000000a', 'alice@example.com'),
  ('00000000-0000-0000-0000-00000000000b', 'bob@example.com');

-- Le trigger a créé profil, abonnement gratuit et tableau de bord
do $$ begin
  assert (select count(*) from public.profiles) = 2, 'profils non créés';
  assert (select count(*) from public.subscriptions where plan = 'free') = 2, 'abonnements non créés';
end $$;

insert into public.portfolios (id, user_id, name, wrapper) values
  ('10000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-00000000000a', 'PEA Alice', 'pea'),
  ('10000000-0000-0000-0000-00000000000b', '00000000-0000-0000-0000-00000000000b', 'CTO Bob', 'cto');
insert into public.transactions (user_id, portfolio_id, trade_date, type, symbol, quantity, price) values
  ('00000000-0000-0000-0000-00000000000a', '10000000-0000-0000-0000-00000000000a', '2024-01-15', 'buy', 'CW8', 10, 450),
  ('00000000-0000-0000-0000-00000000000b', '10000000-0000-0000-0000-00000000000b', '2024-02-01', 'buy', 'AAPL', 5, 180);
insert into public.instruments (symbol, name, asset_class, currency) values ('CW8', 'Amundi MSCI World', 'etf', 'EUR');
insert into public.imports (id, user_id, portfolio_id, detected_format)
values ('20000000-0000-0000-0000-00000000000b', '00000000-0000-0000-0000-00000000000b', '10000000-0000-0000-0000-00000000000b', 'csv');

-- On devient Alice
set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', false);

do $$ begin
  assert (select count(*) from public.portfolios) = 1, 'Alice voit des portefeuilles qui ne sont pas à elle';
  assert (select count(*) from public.transactions) = 1, 'Alice voit des transactions de Bob';
  assert (select symbol from public.transactions) = 'CW8', 'mauvaise transaction visible';
  assert (select count(*) from public.profiles) = 1, 'Alice voit le profil de Bob';
  assert (select count(*) from public.instruments) = 1, 'données de marché non lisibles';
end $$;

-- Alice ne peut pas écrire chez Bob
do $$ begin
  begin
    insert into public.transactions (user_id, portfolio_id, trade_date, type, quantity, price)
    values ('00000000-0000-0000-0000-00000000000b', '10000000-0000-0000-0000-00000000000b', '2024-03-01', 'buy', 1, 1);
    raise exception 'ECHEC : Alice a pu écrire chez Bob';
  exception when insufficient_privilege then null;  -- refus attendu par la politique RLS
  end;
end $$;

-- Alice ne peut ni modifier ni supprimer les lignes de Bob (0 ligne touchée)
update public.transactions set price = 0 where symbol = 'AAPL';
delete from public.portfolios where name = 'CTO Bob';

-- Alice ne peut pas changer son propre abonnement
do $$ begin
  begin
    update public.subscriptions set plan = 'trader';
    assert (select plan from public.subscriptions) = 'free', 'Alice a pu s''attribuer une formule payante';
  exception when insufficient_privilege then null;
  end;
end $$;

-- Alice ne peut pas écrire dans les données de marché
do $$ begin
  begin
    insert into public.instruments (symbol, name, asset_class, currency) values ('X', 'X', 'equity', 'EUR');
    raise exception 'ECHEC : écriture dans les données de marché';
  exception when insufficient_privilege then null;
  end;
end $$;

-- Alice ne peut pas rattacher une transaction à SON compte mais au portefeuille de Bob
do $$ begin
  begin
    insert into public.transactions (user_id, portfolio_id, trade_date, type, quantity, price)
    values ('00000000-0000-0000-0000-00000000000a', '10000000-0000-0000-0000-00000000000b', '2024-03-01', 'buy', 1, 1);
    raise exception 'ECHEC : transaction rattachée au portefeuille de Bob';
  exception when insufficient_privilege then null;
  end;
end $$;

-- Métadonnées de titres : Alice écrit dans son portefeuille, pas dans celui de Bob
insert into public.portfolio_instruments (portfolio_id, user_id, symbol, asset_class)
values ('10000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-00000000000a', 'CW8', 'etf');
do $$ begin
  begin
    insert into public.portfolio_instruments (portfolio_id, user_id, symbol)
    values ('10000000-0000-0000-0000-00000000000b', '00000000-0000-0000-0000-00000000000a', 'X');
    raise exception 'ECHEC : métadonnée écrite dans le portefeuille de Bob';
  exception when insufficient_privilege then null;
  end;
  assert (select count(*) from public.portfolio_instruments) = 1, 'métadonnées mal isolées';
end $$;

-- Suppression d'un import : ses opérations partent avec lui ; Alice ne peut pas supprimer l'import de Bob
insert into public.imports (id, user_id, portfolio_id, detected_format)
values ('20000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-00000000000a', '10000000-0000-0000-0000-00000000000a', 'csv');
insert into public.transactions (user_id, portfolio_id, import_id, trade_date, type, symbol, quantity, price) values
  ('00000000-0000-0000-0000-00000000000a', '10000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-00000000000a', '2024-04-01', 'buy', 'ESE', 3, 25),
  ('00000000-0000-0000-0000-00000000000a', '10000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-00000000000a', '2024-05-01', 'buy', 'ESE', 2, 26);
do $$ begin
  assert (select count(*) from public.transactions) = 3, 'import non enregistré';
end $$;
delete from public.imports where id = '20000000-0000-0000-0000-00000000000a';
delete from public.imports where id = '20000000-0000-0000-0000-00000000000b';  -- import de Bob : 0 ligne touchée
delete from public.transactions where symbol = 'AAPL';                         -- ligne de Bob : 0 ligne touchée
do $$ begin
  assert (select count(*) from public.transactions) = 1, 'les opérations de l''import supprimé sont restées';
  assert (select count(*) from public.imports) = 0, 'import non supprimé';
end $$;

-- Alertes : sur son portefeuille oui, sur celui de Bob non ; déclenchements et jeton réservés au serveur
insert into public.alerts (user_id, portfolio_id, condition)
values ('00000000-0000-0000-0000-00000000000a', '10000000-0000-0000-0000-00000000000a', '{"kind": "rsi", "threshold": 70}');
do $$ begin
  begin
    insert into public.alerts (user_id, portfolio_id, condition)
    values ('00000000-0000-0000-0000-00000000000a', '10000000-0000-0000-0000-00000000000b', '{"kind": "rsi"}');
    raise exception 'ECHEC : alerte rattachée au portefeuille de Bob';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.alert_events (user_id, alert_id, event_key, triggered_on, message)
    select user_id, id, 'x', current_date, 'faux' from public.alerts limit 1;
    raise exception 'ECHEC : déclenchement écrit par un utilisateur';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.check_alerts_cron_token('x');
    raise exception 'ECHEC : jeton vérifiable par un utilisateur';
  exception when insufficient_privilege then null;
  end;
  assert (select count(*) from public.alerts) = 1, 'alerte non enregistrée';
end $$;

reset role;
do $$ begin
  assert (select count(*) from public.imports) = 1, 'l''import de Bob a été supprimé';
  assert (select count(*) from public.transactions where symbol = 'AAPL') = 1, 'la transaction de Bob a été supprimée';
  assert (select price from public.transactions where symbol = 'AAPL') = 180, 'la transaction de Bob a été modifiée';
  assert (select count(*) from public.portfolios) = 2, 'le portefeuille de Bob a été supprimé';
end $$;

\echo 'RLS : tous les tests sont passés'
