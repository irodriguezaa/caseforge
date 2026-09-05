"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Sidebar } from "@/app/components/Sidebar";
import { homePathForRole, isReleaseModulePath, useAuth } from "@/lib/auth";

export function AppShell({ children }: { children: React.ReactNode }): React.ReactElement {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, canSeeDashboard, canSeeKpis, canSeeReleases } = useAuth();
  const isLogin = pathname === "/login";

  useEffect(() => {
    if (loading) return;
    if (isLogin) {
      if (user) router.replace(homePathForRole(user.role));
      return;
    }
    if (!user) {
      router.replace("/login");
      return;
    }
    if (!canSeeDashboard && pathname === "/") {
      router.replace("/releases");
      return;
    }
    if (!canSeeKpis && pathname.startsWith("/kpis")) {
      router.replace("/releases");
      return;
    }
    if (!canSeeReleases && isReleaseModulePath(pathname)) {
      router.replace(homePathForRole(user.role));
    }
  }, [loading, isLogin, user, canSeeDashboard, canSeeKpis, canSeeReleases, pathname, router]);

  if (isLogin) {
    return <>{children}</>;
  }

  if (loading || !user) {
    return (
      <div className="app-shell app-shell-loading">
        <p className="muted" style={{ padding: "24px" }}>
          Cargando…
        </p>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">{children}</div>
    </div>
  );
}
