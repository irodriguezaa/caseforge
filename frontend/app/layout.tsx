import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "CaseForge",
  description: "QC Intelligence Platform",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>): React.ReactElement {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
