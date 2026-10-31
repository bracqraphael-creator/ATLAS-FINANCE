import type { NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

export async function middleware(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  // Pas sur les fichiers statiques ni sur le relais vers le moteur de calcul
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/engine|.*\\.(?:svg|png|jpg|jpeg|gif|webp|woff2?)$).*)"],
};
