import { createBrowserClient } from "@supabase/ssr";

/** Client Supabase côté navigateur. La clé publiable est faite pour être exposée :
 *  les données sont protégées par les politiques RLS de la base. */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
  );
}
