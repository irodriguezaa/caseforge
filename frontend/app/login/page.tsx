"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiRequestError } from "@/lib/api";
import { homePathForRole, useAuth } from "@/lib/auth";

export default function LoginPage(): React.ReactElement {
  const router = useRouter();
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const user = await api.login(email.trim(), password);
      await refresh();
      router.replace(homePathForRole(user.role));
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "No se pudo iniciar sesión.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-backdrop" aria-hidden="true">
        <img className="login-backdrop-logo" src="/qcpulse/claro-video-logo.png" alt="" />
      </div>
      <form className="login-card" onSubmit={(event) => void handleSubmit(event)}>
        <img className="login-claro-logo" src="/qcpulse/claro-video-logo.png" alt="Claro video" />
        <div className="login-heading">
          <h1 className="login-title">QC Pulse</h1>
          <p className="login-subtitle">Plataforma de Calidad</p>
        </div>
        <div className="form-field">
          <label htmlFor="email">Correo</label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </div>
        <div className="form-field">
          <label htmlFor="password">Contraseña</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>
        {error && <p className="error-text">{error}</p>}
        <div className="form-actions">
          <button type="submit" disabled={submitting}>
            {submitting ? "Entrando…" : "Entrar"}
          </button>
        </div>
      </form>
    </div>
  );
}
