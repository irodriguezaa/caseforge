"use client";

import { Activity, Bug, Gauge, LayoutDashboard, Package } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

// "Operativa" will house Ventanas (Operational/Release Windows) once that UI is built;
// "Defectos" is a placeholder until that screen exists. "KPIs" is a group with two navigable
// sub-items (Defectos Operativa / Defectos Release) instead of a single flat link.
const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, enabled: true },
  { href: "/releases", label: "Release", icon: Package, enabled: true },
  { href: "/operativa", label: "Operativa", icon: Activity, enabled: false },
  {
    label: "KPIs",
    icon: Gauge,
    children: [
      { href: "/kpis/operativas", label: "Defectos Operativa" },
      { href: "/kpis/release", label: "Defectos Release" },
    ],
  },
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
        {NAV_ITEMS.map((item) => {
          if ("children" in item) {
            const groupActive = pathname.startsWith("/kpis");
            return (
              <div key={item.label}>
                <span className={`sidebar-link${groupActive ? " active" : ""}`}>
                  <item.icon size={16} strokeWidth={2} aria-hidden="true" />
                  <span>{item.label}</span>
                </span>
                {item.children.map((child) => {
                  const isActive = pathname.startsWith(child.href);
                  return (
                    <Link
                      key={child.href}
                      href={child.href}
                      className={`sidebar-link${isActive ? " active" : ""}`}
                      style={{ paddingLeft: "34px", fontSize: "13px" }}
                    >
                      <span>{child.label}</span>
                    </Link>
                  );
                })}
              </div>
            );
          }

          if (!item.enabled) {
            return (
              <span key={item.href} className="sidebar-link disabled" title="Próximamente">
                <item.icon size={16} strokeWidth={2} aria-hidden="true" />
                <span>{item.label}</span>
              </span>
            );
          }
          const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} className={`sidebar-link${isActive ? " active" : ""}`}>
              <item.icon size={16} strokeWidth={2} aria-hidden="true" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
