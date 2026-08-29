"use client";

import { Activity, Bug, Gauge, LayoutDashboard, Package } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

// "Operativa" will house Ventanas (Operational/Release Windows) once that UI is built; "KPIs"
// and "Defectos" are placeholders until their screens exist. Only Dashboard/Releases are live.
const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, enabled: true },
  { href: "/releases", label: "Release", icon: Package, enabled: true },
  { href: "/operativa", label: "Operativa", icon: Activity, enabled: false },
  { href: "/kpis", label: "KPIs", icon: Gauge, enabled: true },
  { href: "/defects", label: "Defectos", icon: Bug, enabled: false },
] as const;

export function Sidebar(): React.ReactElement {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-name">CASEFORGE</span>
        <span className="brand-tag">QC Platform</span>
      </div>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map(({ href, label, icon: Icon, enabled }) => {
          if (!enabled) {
            return (
              <span key={href} className="sidebar-link disabled" title="Próximamente">
                <Icon size={16} strokeWidth={2} aria-hidden="true" />
                <span>{label}</span>
              </span>
            );
          }
          const isActive = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link key={href} href={href} className={`sidebar-link${isActive ? " active" : ""}`}>
              <Icon size={16} strokeWidth={2} aria-hidden="true" />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
