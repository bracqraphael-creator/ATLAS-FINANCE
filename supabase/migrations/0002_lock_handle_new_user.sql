-- La fonction du déclencheur d'inscription ne doit pas être appelable via l'API publique
-- (signalé par le conseiller de sécurité Supabase).
revoke execute on function public.handle_new_user() from public, anon, authenticated;
