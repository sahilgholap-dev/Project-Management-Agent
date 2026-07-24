"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Table, Td, inputCls } from "@/components/ui";
import type { Stakeholder } from "@/app/(client)/team/page";

export function StakeholderForms({ stakeholders, canEdit }: {
  stakeholders: Stakeholder[];
  canEdit: boolean;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  async function create(formData: FormData) {
    setError(null);
    const projectId = String(formData.get("project_id") ?? "").trim();
    const response = await fetch("/api/stakeholders", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        name: formData.get("name"),
        email: formData.get("email") || null,
        audience_type: formData.get("audience_type"),
        project_id: projectId ? Number(projectId) : null,
      }),
    });
    if (!response.ok) {
      setError(JSON.stringify((await response.json().catch(() => null))?.detail));
      return;
    }
    router.refresh();
  }

  async function remove(id: number) {
    await fetch(`/api/stakeholders/${id}`, { method: "DELETE" });
    router.refresh();
  }

  return (
    <div className="space-y-3 text-sm">
      <Table headers={["Name", "Audience", "Scope", "Email", ""]}>
        {stakeholders.map((s) => (
          <tr key={s.stakeholder_id} className="hover:bg-slate-50">
            <Td className="font-medium text-slate-900">{s.name}</Td>
            <Td>{s.audience_type}</Td>
            <Td>
              {s.project_id ? `project ${s.project_id}` : "client-wide"}
            </Td>
            <Td>{s.email ?? "—"}</Td>
            <Td>
              {canEdit && (
                <Button variant="secondary" small
                        onClick={() => remove(s.stakeholder_id)}>
                  remove
                </Button>
              )}
            </Td>
          </tr>
        ))}
      </Table>

      {canEdit && (
        <form action={create}
              className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-sm">
          <input name="name" required placeholder="Name"
                 className={`${inputCls} w-auto px-2 py-1.5 text-xs`} />
          <select name="audience_type" className={`${inputCls} w-auto px-2 py-1.5 text-xs`}>
            <option>team</option>
            <option>exec</option>
            <option>client</option>
            <option>investor</option>
          </select>
          <input name="project_id" type="number" placeholder="project id (blank = client-wide)"
                 className={`${inputCls} w-56 px-2 py-1.5 text-xs`} />
          <input name="email" type="email" placeholder="email (optional)"
                 className={`${inputCls} w-auto px-2 py-1.5 text-xs`} />
          <Button small>Add stakeholder</Button>
          {error && <span className="text-red-600">{error}</span>}
        </form>
      )}
    </div>
  );
}
