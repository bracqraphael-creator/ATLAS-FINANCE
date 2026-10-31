import type { MetadataRoute } from "next";

// Application installable (écran d'accueil du téléphone ou de l'ordinateur)
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "ATLAS FINANCE",
    short_name: "ATLAS",
    description: "Analyse modulable de portefeuilles boursiers",
    lang: "fr",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#0e1420",
    theme_color: "#0e1420",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
