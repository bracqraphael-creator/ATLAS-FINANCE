-- Maintient le moteur de calcul éveillé (offre gratuite Render : mise en veille après 15 min sans requête).
-- Spécifique à l'hébergement : appliqué à la main sur le projet Supabase, hors migrations (il exige pg_cron
-- et pg_net, absents d'un PostgreSQL local). Le moteur garde ainsi en mémoire les cours déjà téléchargés.
-- 750 h d'instance gratuites par mois chez Render : un service éveillé en permanence en consomme ~744.
create extension if not exists pg_cron;
create extension if not exists pg_net schema extensions;   -- hors du schéma public (conseiller Supabase)

select cron.unschedule(jobid) from cron.job where jobname = 'atlas-engine-keepalive';
select cron.schedule(
  'atlas-engine-keepalive',
  '*/10 * * * *',
  $$select net.http_get(url := 'https://atlas-engine-y6oi.onrender.com/health', timeout_milliseconds := 60000)$$
);

-- Pour arrêter : select cron.unschedule('atlas-engine-keepalive');
