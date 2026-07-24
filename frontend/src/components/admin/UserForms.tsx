"use client";

// PRD s4 steps 1-2. The "invite" is credential GENERATION + on-screen display
// for manual handoff — this system sends nothing, by design (the backend's
// import allowlist makes sending structurally impossible). Buttons say
// "Generate credentials" / "Reset password", never "Send invite".

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Badge, Button, Field, inputCls, statusTone } from "@/components/ui";
import type { AdminUser } from "@/lib/api";
import { apiFetch } from "@/lib/client";

type Credentials = { email: string; password: string; handoff_note: string };

export function CredentialsBox({ credentials }: { credentials: Credentials }) {
  return (
    <Alert tone="warning" title="Shown once — copy now and relay manually:">
      <p className="font-mono">email: {credentials.email}</p>
      <p className="font-mono">password: {credentials.password}</p>
      <p className="mt-1 text-amber-700">{credentials.handoff_note}</p>
    </Alert>
  );
}

export function CreateUserForm({ companies, fixedClientId }: {
  companies: { client_id: number; name: string }[];
  fixedClientId?: number;
}) {
  const router = useRouter();
  const [credentials, setCredentials] = useState<Credentials | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        Credentials are generated and shown once, below, for manual handoff.
        Nothing is emailed or sent — this system has no send capability.
      </p>
      <form
        className="flex flex-wrap items-end gap-2"
        action={async (fd) => {
          setError(null);
          setCredentials(null);
          try {
            setCredentials(await apiFetch("/admin/users", {
              method: "POST",
              body: {
                client_id: fixedClientId ?? Number(fd.get("client_id")),
                email: fd.get("email"),
                display_name: fd.get("display_name"),
                role: fd.get("role"),
              },
            }));
            router.refresh();
          } catch (err) {
            setError((err as Error).message);
          }
        }}
      >
        {fixedClientId === undefined && (
          <Field label="Company" className="w-44">
            <select name="client_id" required className={inputCls}>
              {companies.map((c) => (
                <option key={c.client_id} value={c.client_id}>{c.name}</option>
              ))}
            </select>
          </Field>
        )}
        <Field label="Email" className="w-56">
          <input name="email" type="email" required className={inputCls} />
        </Field>
        <Field label="Display name" className="w-44">
          <input name="display_name" required className={inputCls} />
        </Field>
        <Field label="Role" className="w-36">
          <select name="role" className={inputCls}>
            <option value="client_admin">client_admin</option>
            <option value="member">member</option>
          </select>
        </Field>
        <Button disabled={companies.length === 0 && fixedClientId === undefined}>
          Generate credentials
        </Button>
      </form>
      {companies.length === 0 && fixedClientId === undefined && (
        <p className="text-xs text-slate-500">Create a company first.</p>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
      {credentials && <CredentialsBox credentials={credentials} />}
    </div>
  );
}

export function UserRowActions({ user }: { user: AdminUser }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [credentials, setCredentials] = useState<Credentials | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function patch(body: Record<string, unknown>) {
    setError(null);
    try {
      await apiFetch(`/admin/users/${user.user_id}`, { method: "PATCH", body });
      setEditing(false);
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="space-y-2">
      {editing ? (
        <form
          className="flex flex-wrap items-center gap-2"
          action={(fd) => patch({
            display_name: fd.get("display_name"),
            role: fd.get("role"),
          })}
        >
          <input name="display_name" defaultValue={user.display_name} required
                 className={`${inputCls} w-40`} />
          <select name="role" defaultValue={user.role} className={`${inputCls} w-36`}>
            <option value="client_admin">client_admin</option>
            <option value="member">member</option>
          </select>
          <Button small>Save</Button>
          <Button small type="button" variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </form>
      ) : (
        <div className="flex flex-wrap items-center gap-1.5">
          <Button small variant="secondary" onClick={() => setEditing(true)}>
            Edit
          </Button>
          {user.invite_status === "disabled" ? (
            <Button small variant="secondary"
                    onClick={() => patch({ invite_status: "active" })}>
              Enable
            </Button>
          ) : (
            <Button small variant="danger"
                    onClick={() => patch({ invite_status: "disabled" })}>
              Disable
            </Button>
          )}
          <Button
            small
            variant="secondary"
            onClick={async () => {
              if (!confirm(`Reset ${user.email}'s password? The old one stops working immediately.`)) return;
              setError(null);
              setCredentials(null);
              try {
                setCredentials(await apiFetch(
                  `/admin/users/${user.user_id}/reset-password`, { method: "POST" },
                ));
              } catch (err) {
                setError((err as Error).message);
              }
            }}
          >
            Reset password
          </Button>
        </div>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
      {credentials && <CredentialsBox credentials={credentials} />}
    </div>
  );
}

export function InviteStatusBadge({ status }: { status: string }) {
  return <Badge tone={statusTone(status)}>{status}</Badge>;
}
