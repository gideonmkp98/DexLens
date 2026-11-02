"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import AppHeader from "@/components/AppHeader";
import Footer from "@/components/Footer";
import MobileNavigation from "@/components/MobileNavigation";

export default function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isScannerWorkspace = pathname === "/scan";

  useEffect(() => {
    if (
      typeof window !== "undefined" &&
      "serviceWorker" in navigator &&
      process.env.NODE_ENV === "production"
    ) {
      window.addEventListener("load", () => {
        navigator.serviceWorker.register("/sw.js").catch(() => {
          // Non-fatal service worker registration failure
        });
      });
    }
  }, []);

  if (isScannerWorkspace) {
    return (
      <div className="h-[100dvh] min-h-0 overflow-hidden bg-[#20251f]">
        <div id="main-content" className="h-full min-h-0 overflow-hidden">
          {children}
        </div>
      </div>
    );
  }

  return (
    <>
      <AppHeader />
      <div id="main-content" className="flex-1">
        {children}
      </div>
      <Footer />
      <MobileNavigation />
    </>
  );
}
