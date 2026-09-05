import type { Metadata } from "next";
import "./styles.css";
import { AppShell } from "./components/AppShell";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "QC Pulse",
  description: "QC Pulse Platform",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>): React.ReactElement {
  return (
    <html lang="es">
      <body>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
