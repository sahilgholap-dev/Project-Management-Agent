import { Shell } from "@/components/Shell";
import { requireMember } from "@/lib/api";

export default async function MyLayout({ children }: { children: React.ReactNode }) {
  const me = await requireMember();
  return (
    <Shell
      me={me}
      portalLabel="My Work"
      nav={[{ href: "/my", label: "My Work", exact: true }]}
    >
      {children}
    </Shell>
  );
}
