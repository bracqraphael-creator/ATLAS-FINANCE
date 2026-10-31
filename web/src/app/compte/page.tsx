"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import { createClient } from "@/lib/supabase/client";

export default function ComptePage() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      if (!data.user) router.replace("/connexion");
      else setEmail(data.user.email ?? null);
    });
  }, [router]);

  const changePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 8) { setMessage({ ok: false, text: "Le mot de passe doit faire au moins 8 caractères." }); return; }
    setBusy(true);
    const { error } = await createClient().auth.updateUser({ password });
    setBusy(false);
    setPassword("");
    setMessage(error ? { ok: false, text: "Le mot de passe n'a pas pu être changé. Reconnectez-vous puis réessayez." }
                     : { ok: true, text: "Mot de passe mis à jour." });
  };

  const signOut = async () => {
    await createClient().auth.signOut();
    router.push("/"); router.refresh();
  };

  return (
    <main className="mx-auto max-w-[560px] px-4 py-10">
      <Link href="/" className="mb-8 flex items-center gap-2.5">
        <Logo />
        <span className="text-[15px] font-semibold tracking-[0.08em]">ATLAS</span>
        <span className="text-[15px] tracking-[0.08em] text-muted">FINANCE</span>
      </Link>
      <h1 className="text-xl font-semibold">Mon compte</h1>
      <p className="mt-1 text-sm text-muted">{email ?? "…"}</p>

      <section className="mt-6 rounded-xl border border-line bg-panel p-5">
        <h2 className="text-sm font-medium">Changer de mot de passe</h2>
        <form onSubmit={changePassword} className="mt-4 flex flex-col gap-3 sm:flex-row">
          <input type="password" autoComplete="new-password" placeholder="Nouveau mot de passe" value={password}
                 onChange={(e) => setPassword(e.target.value)}
                 className="min-w-0 flex-1 rounded-lg border border-line bg-ink px-3 py-2.5 text-sm text-text placeholder:text-faint focus:border-brass focus:outline-none" />
          <button disabled={busy} className="rounded-lg bg-brass px-4 py-2.5 text-sm font-medium text-ink hover:opacity-90 disabled:opacity-50">
            Enregistrer
          </button>
        </form>
        {message && <p className={`mt-3 text-sm ${message.ok ? "text-gain" : "text-loss"}`}>{message.text}</p>}
      </section>

      <div className="mt-6 flex items-center justify-between">
        <Link href="/" className="text-sm text-muted hover:text-text">Retour au tableau de bord</Link>
        <button onClick={signOut} className="rounded-lg border border-line px-4 py-2 text-sm text-muted hover:border-faint hover:text-text">
          Se déconnecter
        </button>
      </div>
    </main>
  );
}
