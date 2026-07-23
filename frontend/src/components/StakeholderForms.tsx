"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
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
      <table className="w-full rounded border bg-white text-left text-xs">
        <thead className="text-slate-500">
          <tr className="border-b bg-slate-50">
            <th className="px-4 py-2">Name</th>
            <th className="px-2 py-2">Audience</th>
            <th className="px-2 py-2">Scope</th>
            <th className="px-2 py-2">Email</th>
            <th className="px-2 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {stakeholders.map((s) => (
            <tr key={s.stakeholder_id} className="border-b last:border-0">
              <td className="px-4 py-2">{s.name}</td>
              <td className="px-2 py-2">{s.audience_type}</td>
              <td className="px-2 py-2">
                {s.project_id ? `project ${s.project_id}` : "client-wide"}
              </td>
              <td className="px-2 py-2">{s.email ?? "—"}</td>
              <td className="px-2 py-2">
                {canEdit && (
                  <button className="rounded border px-2 py-0.5 hover:bg-slate-100"
                          onClick={() => remove(s.stakeholder_id)}>
                    remove
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {canEdit && (
        <form action={create}
              className="flex flex-wrap items-end gap-2 rounded border bg-white p-3 text-xs">
          <input name="name" required placeholder="Name"
                 className="rounded border px-2 py-1.5" />
          <select name="audience_type" className="rounded border px-2 py-1.5">
            <option>team</option>
            <option>exec</option>
            <option>client</option>
            <option>investor</option>
          </select>
          <input name="project_id" type="number" placeholder="project id (blank = client-wide)"
                 className="w-56 rounded border px-2 py-1.5" />
          <input name="email" type="email" placeholder="email (optional)"
                 className="rounded border px-2 py-1.5" />
          <button className="rounded bg-slate-800 px-3 py-1.5 text-white">
            Add stakeholder
          </button>
          {error && <span className="text-red-600">{error}</span>}
        </form>
      )}
    </div>
  );
}
