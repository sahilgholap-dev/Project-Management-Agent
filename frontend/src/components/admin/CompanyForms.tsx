"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Button, inputCls } from "@/components/ui";
import { apiFetch } from "@/lib/client";

export function CreateCompanyForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <form
      className="flex gap-2"
      action={async (fd) => {
        setError(null);
        setBusy(true);
        try {
          await apiFetch("/admin/clients", {
            method: "POST", body: { name: fd.get("name") },
          });
          router.refresh();
        } catch (err) {
          setError((err as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <input name="name" required placeholder="New company name"
             className={`${inputCls} w-64`} />
      <Button disabled={busy}>{busy ? "Creating…" : "Create company"}</Button>
      {error && <span className="self-center text-xs text-red-600">{error}</span>}
    </form>
  );
}

export function CompanyHeaderActions({ clientId, name, deletable }: {
  clientId: number;
  name: string;
  deletable: boolean;
}) {
  const router = useRouter();
  const [renaming, setRenaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (renaming) {
    return (
      <form
        className="flex items-center gap-2"
        action={async (fd) => {
          setError(null);
          try {
            await apiFetch(`/admin/clients/${clientId}`, {
              method: "PATCH", body: { name: fd.get("name") },
            });
            setRenaming(false);
            router.refresh();
          } catch (err) {
            setError((err as Error).message);
          }
        }}
      >
        <input name="name" defaultValue={name} required autoFocus
               className={`${inputCls} w-56`} />
        <Button small>Save</Button>
        <Button small type="button" variant="ghost" onClick={() => setRenaming(false)}>
          Cancel
        </Button>
        {error && <span className="text-xs text-red-600">{error}</span>}
      </form>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Button small variant="secondary" onClick={() => setRenaming(true)}>
        Rename
      </Button>
      <Button
        small
        variant="danger"
        disabled={!deletable}
        title={deletable ? undefined
          : "Companies with users or projects cannot be deleted — history is never removed"}
        onClick={async () => {
          if (!confirm(`Delete "${name}"? This only works while the company is empty.`)) return;
          setError(null);
          try {
            await apiFetch(`/admin/clients/${clientId}`, { method: "DELETE" });
            router.replace("/admin/companies");
            router.refresh();
          } catch (err) {
            setError((err as Error).message);
          }
        }}
      >
        Delete
      </Button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
}

export function CompanyDeleteNote() {
  return (
    <Alert tone="warning" title="Safe delete only">
      A company that has users or projects is part of the governance record and
      cannot be deleted. Disable its users instead.
    </Alert>
  );
}
