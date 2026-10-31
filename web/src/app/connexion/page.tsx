"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Logo } from "@/components/Logo";
import { createClient } from "@/lib/supabase/client";

type Mode = "signin" | "signup" | "reset";

const MESSAGES: Record<string, string> = {
  "Invalid login credentials": "E-mail ou mot de passe incorrect.",
  "Email not confirmed": "Confirmez d'abord votre adresse avec le lien reçu par e-mail.",
  "User already registered": "Un compte existe déjà avec cette adresse. Connectez-vous.",
  "Password should be at least 6 characters.": "Le mot de passe doit faire au moins 8 caractères.",
};

function translate(message: string): string {
  if (MESSAGES[message]) return MESSAGES[message];
  if (/rate limit/i.test(message)) return "Trop de tentatives. Réessayez dans quelques minutes.";
  if (/password/i.test(message)) return "Mot de passe refusé : utilisez au moins 8 caractères, avec lettres et chiffres.";
  return message;
}

function AuthForm() {
  const params = useSearchParams();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(params.get("erreur") === "lien" ? "Ce lien a expiré ou a déjà servi. Connectez-vous ou demandez-en un nouveau." : null);
  const [info, setInfo] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null); setInfo(null);
    const supabase = createClient();
    const callback = `${window.location.origin}/auth/callback`;
    try {
      if (mode === "signin") {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        router.push("/"); router.refresh();
      } else if (mode === "signup") {
        if (password.length < 8) throw new Error("Le mot de passe doit faire au moins 8 caractères.");
        const { data, error } = await supabase.auth.signUp({ email, password, options: { emailRedirectTo: callback } });
        if (error) throw error;
        if (data.session) { router.push("/"); router.refresh(); }
        else setInfo(`Un e-mail de confirmation a été envoyé à ${email}. Cliquez sur le lien pour activer votre compte.`);
      } else {
        const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: `${callback}?next=/compte` });
        if (error) throw error;
        setInfo(`Si un compte existe pour ${email}, un lien de réinitialisation vient d'être envoyé.`);
      }
    } catch (err) {
      setError(translate((err as Error).message));
    } finally {
      setBusy(false);
    }
  };

  const titles: Record<Mode, string> = { signin: "Connexion", signup: "Créer un compte", reset: "Mot de passe oublié" };
  const actions: Record<Mode, string> = { signin: "Se connecter", signup: "Créer mon compte", reset: "Envoyer le lien" };

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-[400px]">
        <Link href="/" className="mb-8 flex items-center justify-center gap-2.5">
          <Logo />
          <span className="text-[15px] font-semibold tracking-[0.08em]">ATLAS</span>
          <span className="text-[15px] tracking-[0.08em] text-muted">FINANCE</span>
        </Link>

        <section className="rounded-2xl border border-line bg-panel p-6 sm:p-7">
          <h1 className="text-lg font-semibold">{titles[mode]}</h1>
          <p className="mt-1 text-sm text-muted">
            {mode === "signup" ? "Vos portefeuilles et vos imports sont enregistrés et accessibles depuis tous vos appareils."
             : mode === "reset" ? "Indiquez votre adresse : vous recevrez un lien pour choisir un nouveau mot de passe."
             : "Retrouvez vos portefeuilles et vos analyses."}
          </p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <label className="block text-sm">
              <span className="text-muted">Adresse e-mail</span>
              <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)}
                     className="mt-1.5 w-full rounded-lg border border-line bg-ink px-3 py-2.5 text-text placeholder:text-faint focus:border-brass focus:outline-none" />
            </label>
            {mode !== "reset" && (
              <label className="block text-sm">
                <span className="flex justify-between text-muted">
                  Mot de passe
                  {mode === "signin" && (
                    <button type="button" onClick={() => { setMode("reset"); setError(null); setInfo(null); }}
                            className="text-faint hover:text-text">Oublié ?</button>
                  )}
                </span>
                <input type="password" required minLength={mode === "signup" ? 8 : undefined}
                       autoComplete={mode === "signup" ? "new-password" : "current-password"}
                       value={password} onChange={(e) => setPassword(e.target.value)}
                       className="mt-1.5 w-full rounded-lg border border-line bg-ink px-3 py-2.5 text-text focus:border-brass focus:outline-none" />
                {mode === "signup" && <span className="mt-1 block text-xs text-faint">8 caractères minimum.</span>}
              </label>
            )}

            {error && <p role="alert" className="rounded-lg border border-loss/30 bg-loss/[0.08] px-3 py-2.5 text-sm text-loss">{error}</p>}
            {info && <p role="status" className="rounded-lg border border-gain/30 bg-gain/[0.08] px-3 py-2.5 text-sm text-gain">{info}</p>}

            <button type="submit" disabled={busy}
                    className="w-full rounded-lg bg-brass px-4 py-2.5 text-sm font-medium text-ink hover:opacity-90 disabled:opacity-50">
              {busy ? "Un instant…" : actions[mode]}
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-muted">
            {mode === "signin" ? (
              <>Pas encore de compte ? <button onClick={() => { setMode("signup"); setError(null); setInfo(null); }} className="text-brass hover:underline">Créer un compte</button></>
            ) : (
              <button onClick={() => { setMode("signin"); setError(null); setInfo(null); }} className="text-brass hover:underline">Revenir à la connexion</button>
            )}
          </p>
        </section>

        <p className="mt-6 text-center text-xs text-faint">
          <Link href="/" className="hover:text-muted">Continuer sans compte avec la démonstration</Link>
        </p>
      </div>
    </main>
  );
}

export default function ConnexionPage() {
  return <Suspense><AuthForm /></Suspense>;
}
