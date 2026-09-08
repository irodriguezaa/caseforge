"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { AuthRole, AuthUser } from "@/lib/types";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
  canSeeDashboard: boolean;
  canSeeKpis: boolean;
  canSeeReleases: boolean;
  canLoadRn: boolean;
  canChangeReleaseStatus: boolean;
  canDeleteRelease: boolean;
  canUploadIcs: boolean;
  canExecuteCases: boolean;
  canRefreshKpis: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function homePathForRole(role: AuthRole): string {
  return role === "tester" ? "/releases" : "/";
}

export function isReleaseModulePath(pathname: string): boolean {
  return (
    pathname.startsWith("/releases") ||
    pathname.startsWith("/releases-be") ||
    pathname.startsWith("/operativas") ||
    pathname.startsWith("/test-cases")
  );
}

export function AuthProvider({ children }: { children: React.ReactNode }): React.ReactElement {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const logout = useCallback(async (): Promise<void> => {
    try {
      await api.logout();
    } finally {
      setUser(null);
      window.location.assign("/qcpulse/login");
    }
  }, []);

  const role = user?.role;
  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      refresh,
      logout,
      canSeeDashboard: role === "jefe" || role === "lider" || role === "consulta",
      canSeeKpis: role === "jefe" || role === "lider" || role === "consulta",
      canSeeReleases: role === "jefe" || role === "lider" || role === "tester",
      canLoadRn: role === "jefe" || role === "lider" || role === "tester",
      canChangeReleaseStatus: role === "jefe" || role === "lider",
      canDeleteRelease: role === "jefe",
      canUploadIcs: role === "jefe",
      canExecuteCases: role === "jefe" || role === "lider" || role === "tester",
      canRefreshKpis: role === "jefe" || role === "lider",
    }),
    [user, loading, refresh, logout, role],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
