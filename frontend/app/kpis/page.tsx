import { redirect } from "next/navigation";

export default function KpisIndexPage(): never {
  redirect("/kpis/releases");
}
