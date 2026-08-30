import { redirect } from "next/navigation";

// Entrar directo a /kpis ya no muestra pestañas Operativas/Release -- redirige al default
// (Defectos Operativa), consistente con que la navegación ahora vive en el sidebar.
export default function KpisIndexPage(): never {
  redirect("/kpis/operativas");
}
