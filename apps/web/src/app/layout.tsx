import type { Metadata, Viewport } from "next";
import AppChrome from "@/components/AppChrome";
import "./globals.css";

export const metadata: Metadata = {
  title: "DexLens — Ontdek jouw Pokémon-kaarten",
  description:
    "Scan je Pokémon-kaarten, herken de juiste uitvoering en ontdek de catalogus.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,

  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f1e7" },
    { media: "(prefers-color-scheme: dark)", color: "#20251f" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="nl" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var theme;try{theme=localStorage.getItem('theme')}catch(e){}var dark=theme==='dark'||(theme!=='light'&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',dark)})();`,
          }}
        />
      </head>
      <body className="flex min-h-screen flex-col">
        <a className="skip-link" href="#main-content">
          Naar de inhoud
        </a>
        <AppChrome>{children}</AppChrome>
      </body>
    </html>
  );
}
