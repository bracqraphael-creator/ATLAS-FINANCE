-- Vérification des alertes : du mardi au samedi à 6 h 30 UTC (7 h 30 à Paris l'hiver, 8 h 30 l'été),
-- sur les clôtures de la veille (Europe et États-Unis). Appliqué à la main, hors migrations (pg_cron, pg_net).
-- Le jeton privé (private.settings, créé par la migration 0005) authentifie l'appel auprès de la fonction.
select cron.unschedule(jobid) from cron.job where jobname = 'atlas-alerts-morning';
select cron.schedule(
  'atlas-alerts-morning',
  '30 6 * * 2-6',
  $$select net.http_post(
      url := 'https://gbiaqdkkahjswhizdxkh.supabase.co/functions/v1/alerts-run',
      headers := jsonb_build_object('Content-Type', 'application/json',
                                    'x-atlas-cron', (select value from private.settings where key = 'alerts_cron_token')),
      body := '{}'::jsonb,
      timeout_milliseconds := 120000)$$
);
