"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
export default function MobileNavigation() {
  const pathname = usePathname();
  return (
    <nav className="mobile-nav" aria-label="Mobiele navigatie">
      {(
        [
          ["/", "Start", "01"],
          ["/scan", "Live Scan", "02"],
          ["/collection", "Collectie", "03"],
          ["/cards", "Kaarten", "04"],
          ["/sets", "Sets", "05"],
        ] as const
      ).map(([href, label, num]) => (
        <Link
          key={href}
          href={href}
          aria-current={
            (href === "/" ? pathname === href : pathname.startsWith(href))
              ? "page"
              : undefined
          }
          className={
            href === "/scan" ? "font-bold text-[var(--red)]" : undefined
          }
        >
          <span aria-hidden="true">{num}</span>
          {label}
        </Link>
      ))}
    </nav>
  );
}
