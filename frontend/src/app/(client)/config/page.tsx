import { ConfigForm, ConfigValue } from "@/components/ConfigForm";
import { Card, PageHeader } from "@/components/ui";
import { requireClientUser, serverApi, serverApiOrNull } from "@/lib/api";

type UserRow = {
  user_id: number;
  display_name: string;
  role: string;
};

export default async function ConfigPage() {
  const me = await requireClientUser();
  const [config, users] = await Promise.all([
    serverApiOrNull<ConfigValue>("/config"),
    serverApi<UserRow[]>("/users"),
  ]);

  return (
    <>
      <PageHeader
        title="Client configuration"
        description={
          <>
            Client-level defaults (PRD section 5). Any project may override any
            value from its settings page; resolution is project-override first.
            {!config && " No config saved yet — the form is seeded with defaults."}
          </>
        }
      />
      {me.role !== "client_admin" ? (
        <Card>
          <p className="text-sm text-slate-500">Read-only for members. Current config:</p>
          <pre className="mt-2 overflow-auto rounded-md bg-slate-50 p-3 text-xs text-slate-700">
            {JSON.stringify(config, null, 2)}
          </pre>
        </Card>
      ) : (
        <Card>
          <ConfigForm initial={config} users={users} />
        </Card>
      )}
    </>
  );
}
