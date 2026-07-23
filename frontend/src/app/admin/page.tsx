import { redirect } from "next/navigation";
import { AdminForms } from "@/components/AdminForms";
import { LogoutButton } from "@/components/LogoutButton";
import { Me, serverApiOrNull } from "@/lib/api";

export default async function AdminPage() {
  const me = await serverApiOrNull<Me>("/auth/me");
  if (!me) redirect("/login");
  if (me.role !== "platform_admin") redirect("/");

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <header className="mb-6 flex items-center justify-between border-b pb-3">
        <h1 className="text-lg font-semibold">Admin portal</h1>
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <span>{me.display_name}</span>
          <LogoutButton />
        </div>
      </header>
      <AdminForms />
    </div>
  );
}
