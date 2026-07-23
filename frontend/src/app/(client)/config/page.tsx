import { ConfigForm, ConfigValue } from "@/components/ConfigForm";
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
    <main className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold">Client configuration</h1>
        <p className="text-xs text-slate-500">
          Client-level defaults (PRD section 5). Any project may override any
          value from its settings page; resolution is project-override first.
          {!config && " No config saved yet — the form is seeded with defaults."}
        </p>
      </header>
      {me.role !== "client_admin" ? (
        <p className="rounded border bg-white p-4 text-sm text-slate-500">
          Read-only for members. Current config:{" "}
          <pre className="mt-2 overflow-auto rounded bg-slate-50 p-2 text-xs">
            {JSON.stringify(config, null, 2)}
          </pre>
        </p>
      ) : (
        <div className="rounded border bg-white p-4">
          <ConfigForm initial={config} users={users} />
        </div>
      )}
    </main>
  );
}
