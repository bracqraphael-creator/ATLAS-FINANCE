// Évaluation des alertes et envoi des e-mails.
// - Appel planifié (pg_cron, chaque soir après la clôture) : en-tête x-atlas-cron = jeton privé -> tous les utilisateurs.
// - Appel depuis le site (« Vérifier maintenant ») : jeton de session -> les alertes de cet utilisateur seulement.
// Les règles sont évaluées par le moteur de calcul (/alerts/evaluate) sur les dernières clôtures ; un franchissement
// n'est enregistré qu'une fois (clé unique), l'e-mail ne part que pour les nouveaux déclenchements.
// Variables : RESEND_API_KEY (sans elle, les alertes sont enregistrées et visibles sur le site, sans e-mail),
// ALERTS_FROM, ENGINE_URL, SITE_URL (valeurs par défaut ci-dessous).
import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2.118.0";
import webpush from "npm:web-push@3.6.7";

const ENGINE = Deno.env.get("ENGINE_URL") ?? "https://atlas-engine-y6oi.onrender.com";
const SITE = Deno.env.get("SITE_URL") ?? "https://atlas-finance-psi.vercel.app";
const FROM = Deno.env.get("ALERTS_FROM") ?? "ATLAS FINANCE <onboarding@resend.dev>";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

type Rule = { id: string; user_id: string; portfolio_id: string; name: string | null; channels: string[];
              condition: { kind: string; symbol?: string | null; threshold: number; direction?: string } };
type EngineEvent = { rule_id: string; key: string; date: string; symbol: string | null; value: number; message: string };
type NewEvent = { user_id: string; alert_id: string; portfolio_id: string; message: string; triggered_on: string };

/** Clés VAPID des notifications : créées une fois côté serveur, la clé privée ne quitte jamais la base. */
async function vapidKeys(admin: SupabaseClient): Promise<{ publicKey: string; privateKey: string }> {
  const read = async () => {
    const [pub, priv] = await Promise.all([
      admin.rpc("get_private_setting", { setting: "vapid_public" }),
      admin.rpc("get_private_setting", { setting: "vapid_private" }),
    ]);
    return pub.data && priv.data ? { publicKey: pub.data as string, privateKey: priv.data as string } : null;
  };
  const existing = await read();
  if (existing) return existing;
  const keys = webpush.generateVAPIDKeys();
  await admin.rpc("set_private_setting", { setting: "vapid_public", val: keys.publicKey });
  await admin.rpc("set_private_setting", { setting: "vapid_private", val: keys.privateKey });
  return (await read())!;   // relu : en cas de création simultanée, la première paire enregistrée fait foi
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, "content-type": "application/json" } });

const escape = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
                             { auth: { persistSession: false } });

  // Qui appelle ?
  let onlyUser: string | null = null;
  const cron = req.headers.get("x-atlas-cron");
  if (cron) {
    const { data } = await admin.rpc("check_alerts_cron_token", { token: cron });
    if (data !== true) return json({ error: "jeton invalide" }, 401);
  } else {
    const token = (req.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
    const { data, error } = await admin.auth.getUser(token);
    if (error || !data.user) return json({ error: "session requise" }, 401);
    onlyUser = data.user.id;
  }

  // Le site demande la clé publique pour abonner un appareil aux notifications
  const payload = await req.json().catch(() => ({})) as { action?: string };
  if (payload.action === "vapid") {
    const { publicKey } = await vapidKeys(admin);
    return json({ publicKey });
  }

  let query = admin.from("alerts").select("id, user_id, portfolio_id, name, channels, condition")
    .eq("active", true).not("portfolio_id", "is", null);
  if (onlyUser) query = query.eq("user_id", onlyUser);
  const { data: rules, error: rulesError } = await query;
  if (rulesError) return json({ error: rulesError.message }, 500);

  const byPortfolio = new Map<string, Rule[]>();
  for (const r of (rules ?? []) as Rule[]) byPortfolio.set(r.portfolio_id, [...(byPortfolio.get(r.portfolio_id) ?? []), r]);

  const fresh: NewEvent[] = [];
  const errors: string[] = [];
  for (const [portfolioId, list] of byPortfolio) {
    try {
      const [tx, inst] = await Promise.all([
        admin.from("transactions").select("trade_date, type, symbol, name, quantity, price, currency, fees, amount")
          .eq("portfolio_id", portfolioId).order("trade_date").range(0, 19999),
        admin.from("portfolio_instruments").select("symbol, name, asset_class, currency, country, sector")
          .eq("portfolio_id", portfolioId),
      ]);
      if (tx.error || inst.error) throw new Error((tx.error ?? inst.error)!.message);
      if (!tx.data?.length) continue;
      const body = {
        transactions: tx.data.map((t) => ({
          date: t.trade_date, type: t.type, symbol: t.symbol, name: t.name, quantity: Number(t.quantity),
          price: Number(t.price), currency: String(t.currency).trim(), fees: Number(t.fees),
          amount: t.amount === null ? null : Number(t.amount),
        })),
        instruments: Object.fromEntries((inst.data ?? []).map((i) => [i.symbol, { ...i, currency: String(i.currency).trim() }])),
        rules: list.map((r) => ({ id: r.id, kind: r.condition.kind, symbol: r.condition.symbol ?? null,
                                  threshold: Number(r.condition.threshold), direction: r.condition.direction ?? "below" })),
      };
      const res = await fetch(`${ENGINE}/alerts/evaluate`, {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
        signal: AbortSignal.timeout(90_000),
      });
      if (!res.ok) throw new Error(`moteur : ${res.status} ${await res.text()}`);
      const { events } = await res.json() as { events: EngineEvent[] };
      if (!events.length) continue;
      const owner = list[0].user_id;
      const rows = events.map((e) => ({
        user_id: owner, alert_id: e.rule_id, portfolio_id: portfolioId, event_key: e.key,
        triggered_on: e.date, symbol: e.symbol, value: e.value, message: e.message,
      }));
      // Un franchissement déjà noté (même clé) est ignoré : seuls les nouveaux sont renvoyés
      const { data: inserted, error } = await admin.from("alert_events")
        .upsert(rows, { onConflict: "event_key", ignoreDuplicates: true }).select("user_id, alert_id, portfolio_id, message, triggered_on");
      if (error) throw new Error(error.message);
      fresh.push(...((inserted ?? []) as NewEvent[]));
      const ids = [...new Set((inserted ?? []).map((e) => e.alert_id))];
      if (ids.length) await admin.from("alerts").update({ last_triggered_at: new Date().toISOString() }).in("id", ids);
    } catch (e) {
      errors.push(`${portfolioId} : ${(e as Error).message}`);
    }
  }

  // E-mails : un message par utilisateur, regroupé par portefeuille
  const resendKey = Deno.env.get("RESEND_API_KEY");
  let sent = 0;
  if (resendKey && fresh.length) {
    const emailRules = new Set(((rules ?? []) as Rule[]).filter((r) => (r.channels ?? ["email"]).includes("email")).map((r) => r.id));
    const users = [...new Set(fresh.filter((e) => emailRules.has(e.alert_id)).map((e) => e.user_id))];
    const { data: pfs } = await admin.from("portfolios").select("id, name").in("id", [...new Set(fresh.map((e) => e.portfolio_id))]);
    const pfName = new Map((pfs ?? []).map((p) => [p.id, p.name as string]));
    for (const userId of users) {
      const mine = fresh.filter((e) => e.user_id === userId && emailRules.has(e.alert_id));
      const { data: u } = await admin.auth.admin.getUserById(userId);
      const to = u?.user?.email;
      if (!to || !mine.length) continue;
      const groups = new Map<string, string[]>();
      for (const e of mine) groups.set(pfName.get(e.portfolio_id) ?? "Portefeuille", [...(groups.get(pfName.get(e.portfolio_id) ?? "Portefeuille") ?? []), e.message]);
      const html = `<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#1c2333">
        <h2 style="font-size:18px;margin:0 0 4px">ATLAS FINANCE</h2>
        <p style="margin:0 0 16px;color:#5a6478">${mine.length} alerte(s) déclenchée(s)</p>
        ${[...groups].map(([pf, msgs]) => `<h3 style="font-size:15px;margin:16px 0 6px">${escape(pf)}</h3>
          <ul style="padding-left:18px;margin:0">${msgs.map((m) => `<li style="margin:4px 0">${escape(m)}</li>`).join("")}</ul>`).join("")}
        <p style="margin:20px 0"><a href="${SITE}" style="background:#c9a45c;color:#0e1420;padding:10px 16px;border-radius:8px;text-decoration:none">Voir mes portefeuilles</a></p>
        <p style="font-size:12px;color:#8a93a6">Ces alertes constatent le franchissement des seuils que vous avez définis, sur les dernières clôtures disponibles. Ceci n'est pas un conseil en investissement.<br>Pour modifier ou désactiver vos alertes : menu Alertes sur le site.</p></div>`;
      const text = [...groups].map(([pf, msgs]) => `${pf}\n${msgs.map((m) => `- ${m}`).join("\n")}`).join("\n\n")
        + `\n\n${SITE}\nCes alertes constatent le franchissement de vos seuils. Ceci n'est pas un conseil en investissement.`;
      const res = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: { authorization: `Bearer ${resendKey}`, "content-type": "application/json" },
        body: JSON.stringify({ from: FROM, to: [to], subject: `ATLAS FINANCE : ${mine.length} alerte(s)`, html, text }),
      });
      if (res.ok) {
        sent++;
        await admin.from("alert_events").update({ notified_at: new Date().toISOString() })
          .eq("user_id", userId).is("notified_at", null);
      } else {
        errors.push(`e-mail : ${res.status} ${await res.text()}`);
      }
    }
  }

  // Notifications sur les appareils abonnés (application installée ou navigateur)
  let pushed = 0;
  if (fresh.length) {
    const users = [...new Set(fresh.map((e) => e.user_id))];
    const { data: subs } = await admin.from("push_subscriptions").select("id, user_id, endpoint, p256dh, auth").in("user_id", users);
    if (subs?.length) {
      const keys = await vapidKeys(admin);
      webpush.setVapidDetails(SITE, keys.publicKey, keys.privateKey);
      for (const sub of subs) {
        const mine = fresh.filter((e) => e.user_id === sub.user_id);
        const body = JSON.stringify({
          title: `ATLAS FINANCE : ${mine.length} alerte(s)`,
          body: mine.length === 1 ? mine[0].message : `${mine[0].message} (+${mine.length - 1} autre(s))`,
          url: SITE,
        });
        try {
          await webpush.sendNotification({ endpoint: sub.endpoint, keys: { p256dh: sub.p256dh, auth: sub.auth } }, body, { TTL: 86400 });
          pushed++;
        } catch (e) {
          const code = (e as { statusCode?: number }).statusCode;
          if (code === 404 || code === 410) await admin.from("push_subscriptions").delete().eq("id", sub.id);   // appareil désabonné
          else errors.push(`notification : ${code ?? (e as Error).message}`);
        }
      }
    }
  }

  return json({ portfolios: byPortfolio.size, rules: rules?.length ?? 0, new_events: fresh.length, emails_sent: sent,
                push_sent: pushed, email_configured: Boolean(resendKey), errors });
});
