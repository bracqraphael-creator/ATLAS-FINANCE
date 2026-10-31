// Relais vers le moteur de calcul : le navigateur ne parle qu'au site, jamais directement au moteur.
import { NextRequest } from "next/server";

const ENGINE_URL = process.env.ENGINE_URL ?? "http://localhost:8000";
const ALLOWED = /^(health|modules|imports|imports\/analyze|compute\/[a-z_]+|demo\/[a-z_]+)$/;

async function relay(req: NextRequest, path: string[]) {
  const target = path.join("/");
  if (!ALLOWED.test(target)) {
    return Response.json({ detail: "Route non autorisée" }, { status: 404 });
  }
  const init: RequestInit = { method: req.method, headers: {} };
  if (req.method === "POST") {
    const type = req.headers.get("content-type") ?? "";
    init.body = await req.arrayBuffer();
    init.headers = { "content-type": type };
  }
  try {
    const res = await fetch(`${ENGINE_URL}/${target}`, { ...init, cache: "no-store" });
    return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") ?? "application/json" } });
  } catch {
    return Response.json({ detail: "Moteur de calcul injoignable. Est-il lancé (uvicorn atlas.api:app) ?" }, { status: 502 });
  }
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return relay(req, (await ctx.params).path);
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return relay(req, (await ctx.params).path);
}
