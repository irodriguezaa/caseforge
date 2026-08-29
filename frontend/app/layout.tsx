import type { Metadata } from "next";
import "./styles.css";
import { Sidebar } from "./components/Sidebar";

export const metadata: Metadata = {
  title: "CaseForge",
  description: "QC Intelligence Platform",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>): React.ReactElement {
  return (
    <html lang="es">
      <body>
        <div className="app-shell">
          <Sidebar />
          <div className="app-main">{children}</div>
        </div>
      </body>
    </html>
  );
}
