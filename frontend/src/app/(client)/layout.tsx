import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { Me, serverApiOrNull } from "@/lib/api";

export default async function ClientLayout({ children }: { children: React.ReactNode }) {
  const me = await serverApiOrNull<Me>("/auth/me");
  if (!me) redirect("/login");
  if (me.role === "platform_admin") redirect("/admin");
  if (me.role === "member") redirect("/my"); // members: My Work portal only

  return (
    <Shell
      me={me}
      portalLabel="Client portal"
      nav={[
        { href: "/", label: "Projects", exact: true },
        { href: "/review-queue", label: "Review queue" },
        { href: "/team", label: "Team" },
        { href: "/config", label: "Config" },
      ]}
    >
      {children}
    </Shell>
  );
}
