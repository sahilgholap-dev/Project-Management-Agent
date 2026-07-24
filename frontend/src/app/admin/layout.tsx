import { Shell } from "@/components/Shell";
import { requireAdmin } from "@/lib/api";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const me = await requireAdmin();
  return (
    <Shell
      me={me}
      portalLabel="Platform admin"
      nav={[
        { href: "/admin/companies", label: "Companies" },
        { href: "/admin/users", label: "Users" },
      ]}
    >
      {children}
    </Shell>
  );
}
