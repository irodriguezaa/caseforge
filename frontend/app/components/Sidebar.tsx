"use client";

import { Bug, ChevronDown, ChevronRight, Gauge, LayoutDashboard, LogOut, Package } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuthRole } from "@/lib/types";

type ReleaseChildId = "app" | "be" | "ope";
type DefectKpiChildId = "operativas" | "release";

const RELEASE_CHILDREN: { id: ReleaseChildId; href: string; label: string }[] = [
  { id: "app", href: "/releases", label: "Release Apps" },
  { id: "be", href: "/releases-be", label: "Release BE" },
  { id: "ope", href: "/operativas/release-notes", label: "Operativas" },
];

const DEFECT_KPI_CHILDREN: { id: DefectKpiChildId; href: string; label: string }[] = [
  { id: "operativas", href: "/kpis/operativas", label: "Operativa" },
  { id: "release", href: "/kpis/release", label: "Release" },
];

function pathIsAppsList(pathname: string): boolean {
  return pathname === "/releases";
}

function pathIsReleaseDetail(pathname: string): boolean {
  return /^\/releases\/\d+/.test(pathname);
}

const ROLE_LABEL: Record<AuthRole, string> = {
  jefe: "Manager",
  lider: "Líder",
  tester: "Tester",
  consulta: "Consulta",
};

export function Sidebar(): React.ReactElement {
  const pathname = usePathname();
  const { user, logout, canSeeDashboard, canSeeKpis, canSeeReleases } = useAuth();
  const [detailOrigin, setDetailOrigin] = useState<ReleaseChildId | null>(null);
  const [releaseOpen, setReleaseOpen] = useState(true);
  const [kpisOpen, setKpisOpen] = useState(true);
  const [defectsKpiOpen, setDefectsKpiOpen] = useState(true);

  useEffect(() => {
    if (!canSeeReleases) {
      setDetailOrigin(null);
      return;
    }
    const match = pathname.match(/^\/releases\/(\d+)/);
    if (!match) {
      setDetailOrigin(null);
      return;
    }
    let cancelled = false;
    api
      .getRelease(Number(match[1]))
      .then((release) => {
        if (cancelled) return;
        if (release.be_release_id) setDetailOrigin("be");
        else if (release.operativa_release_id) setDetailOrigin("ope");
        else setDetailOrigin("app");
      })
      .catch(() => {
        if (!cancelled) setDetailOrigin("app");
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, canSeeReleases]);

  const activeReleaseChild: ReleaseChildId | null = useMemo(() => {
    if (pathname.startsWith("/releases-be")) return "be";
    if (pathname.startsWith("/operativas")) return "ope";
    if (pathIsAppsList(pathname)) return "app";
    if (pathIsReleaseDetail(pathname)) return detailOrigin;
    return null;
  }, [pathname, detailOrigin]);

  const releaseGroupActive = activeReleaseChild !== null;

  useEffect(() => {
    if (releaseGroupActive) setReleaseOpen(true);
  }, [releaseGroupActive]);

  const dashboardActive = pathname === "/";
  const kpisActive = pathname.startsWith("/kpis");
  const releasesKpiActive = pathname === "/kpis/releases" || pathname.startsWith("/kpis/releases/");
  const defectsOperativaActive = pathname.startsWith("/kpis/operativas");
  const defectsReleaseActive = pathname.startsWith("/kpis/release") && !releasesKpiActive;
  const defectsKpiActive = defectsOperativaActive || defectsReleaseActive;
  const activeDefectChild: DefectKpiChildId | null = defectsOperativaActive
    ? "operativas"
    : defectsReleaseActive
      ? "release"
      : null;

  useEffect(() => {
    if (kpisActive) setKpisOpen(true);
  }, [kpisActive]);

  useEffect(() => {
    if (defectsKpiActive) setDefectsKpiOpen(true);
  }, [defectsKpiActive]);

  return (
    <aside className="sidebar">
      <Link href={canSeeDashboard ? "/" : "/releases"} className="sidebar-brand">
        <img className="sidebar-logo" src="/qcpulse/claro-video-logo.png" alt="Claro video" />
        <span className="brand-name">QC Pulse</span>
        <span className="brand-tag">Plataforma de Calidad</span>
      </Link>
      <nav className="sidebar-nav">
        {canSeeDashboard && (
          <Link href="/" className={`sidebar-link${dashboardActive ? " active" : ""}`}>
            <LayoutDashboard size={16} strokeWidth={2} aria-hidden="true" />
            <span>Dashboard</span>
          </Link>
        )}

        {canSeeReleases && (
        <div>
          <button
            type="button"
            className={`sidebar-link sidebar-group-toggle${releaseGroupActive ? " active" : ""}`}
            aria-expanded={releaseOpen}
            onClick={() => setReleaseOpen((open) => !open)}
          >
            <Package size={16} strokeWidth={2} aria-hidden="true" />
            <span>Release</span>
            {releaseOpen ? (
              <ChevronDown size={14} aria-hidden="true" className="sidebar-chevron" />
            ) : (
              <ChevronRight size={14} aria-hidden="true" className="sidebar-chevron" />
            )}
          </button>
          {releaseOpen && (
            <div className="sidebar-subnav">
              {RELEASE_CHILDREN.map((child) => (
                <Link
                  key={child.id}
                  href={child.href}
                  className={`sidebar-sublink${activeReleaseChild === child.id ? " active" : ""}`}
                >
                  {child.label}
                </Link>
              ))}
            </div>
          )}
        </div>
        )}

        {canSeeReleases && (
        <span className="sidebar-link disabled" title="Próximamente">
          <Bug size={16} strokeWidth={2} aria-hidden="true" />
          <span>Matrices QC</span>
        </span>
        )}

        {canSeeKpis && (
        <div>
          <button
            type="button"
            className={`sidebar-link sidebar-group-toggle${kpisActive ? " active" : ""}`}
            aria-expanded={kpisOpen}
            onClick={() => setKpisOpen((open) => !open)}
          >
            <Gauge size={16} strokeWidth={2} aria-hidden="true" />
            <span>KPIs</span>
            {kpisOpen ? (
              <ChevronDown size={14} aria-hidden="true" className="sidebar-chevron" />
            ) : (
              <ChevronRight size={14} aria-hidden="true" className="sidebar-chevron" />
            )}
          </button>
          {kpisOpen && (
            <div className="sidebar-subnav">
              <Link
                href="/kpis/releases"
                className={`sidebar-sublink sidebar-subgroup-toggle${releasesKpiActive ? " active" : ""}`}
              >
                Releases
              </Link>
              <button
                type="button"
                className={`sidebar-sublink sidebar-subgroup-toggle${defectsKpiActive ? " active" : ""}`}
                aria-expanded={defectsKpiOpen}
                onClick={() => setDefectsKpiOpen((open) => !open)}
              >
                <span>Defectos</span>
                {defectsKpiOpen ? (
                  <ChevronDown size={12} aria-hidden="true" className="sidebar-chevron" />
                ) : (
                  <ChevronRight size={12} aria-hidden="true" className="sidebar-chevron" />
                )}
              </button>
              {defectsKpiOpen &&
                DEFECT_KPI_CHILDREN.map((child) => (
                  <Link
                    key={child.id}
                    href={child.href}
                    className={`sidebar-sublink sidebar-sublink-nested${activeDefectChild === child.id ? " active" : ""}`}
                  >
                    {child.label}
                  </Link>
                ))}
            </div>
          )}
        </div>
        )}
      </nav>
      {user && (
        <div className="sidebar-footer">
          <div className="sidebar-user">
            {user.email}
            <br />
            {ROLE_LABEL[user.role]}
          </div>
          <button type="button" className="secondary" onClick={() => void logout()}>
            <LogOut size={12} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "6px" }} />
            Salir
          </button>
        </div>
      )}
    </aside>
  );
}
