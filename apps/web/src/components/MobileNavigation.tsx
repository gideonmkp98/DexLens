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
          ["/scan", "Scannen", "02"],
          ["/cards", "Kaarten", "03"],
          ["/sets", "Sets", "04"],
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
        >
          <span aria-hidden="true">{num}</span>
          {label}
        </Link>
      ))}
    </nav>
  );
}
