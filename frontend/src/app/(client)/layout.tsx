import Link from "next/link";
import { redirect } from "next/navigation";
import { LogoutButton } from "@/components/LogoutButton";
import { Me, serverApiOrNull } from "@/lib/api";

export default async function ClientLayout({ children }: { children: React.ReactNode }) {
  const me = await serverApiOrNull<Me>("/auth/me");
  if (!me) redirect("/login");
  if (me.role === "platform_admin") redirect("/admin");

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6 flex items-center justify-between border-b pb-3">
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/" className="font-semibold">NEXUS PM</Link>
          <Link href="/review-queue" className="text-slate-600 hover:text-slate-900">
            Review queue
          </Link>
          <Link href="/team" className="text-slate-600 hover:text-slate-900">
            Team
          </Link>
          <Link href="/config" className="text-slate-600 hover:text-slate-900">
            Config
          </Link>
        </nav>
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <span>{me.display_name} · {me.role}</span>
          <LogoutButton />
        </div>
      </header>
      {children}
    </div>
  );
}
