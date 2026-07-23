"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Member } from "@/app/(client)/team/page";

function MemberRow({ member, canEdit }: { member: Member; canEdit: boolean }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [skills, setSkills] = useState(member.skill_tags.join(", "));
  const [capacity, setCapacity] = useState(member.capacity_hrs);
  const [error, setError] = useState<string | null>(null);

  async function patch(body: Record<string, unknown>) {
    const response = await fetch(`/api/team-members/${member.member_id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      setError(JSON.stringify((await response.json().catch(() => null))?.detail));
      return false;
    }
    setError(null);
    router.refresh();
    return true;
  }

  return (
    <tr className={`border-b last:border-0 ${member.is_active ? "" : "opacity-50"}`}>
      <td className="px-4 py-2">{member.name}</td>
      <td className="px-2 py-2">{member.role}</td>
      <td className="px-2 py-2">
        {editing ? (
          <input value={skills} onChange={(e) => setSkills(e.target.value)}
                 className="w-full rounded border px-2 py-1" />
        ) : member.skill_tags.join(", ") || "—"}
      </td>
      <td className="px-2 py-2">
        {editing ? (
          <input type="number" min="1" value={capacity}
                 onChange={(e) => setCapacity(Number(e.target.value))}
                 className="w-20 rounded border px-2 py-1" />
        ) : `${member.capacity_hrs}h/wk`}
      </td>
      <td className="px-2 py-2 text-slate-500" title="current-week load (display only)">
        {member.allocated_hrs}h
      </td>
      <td className="px-2 py-2">
        {canEdit && (
          <div className="flex gap-1">
            {editing ? (
              <button
                className="rounded border px-2 py-0.5 hover:bg-slate-100"
                onClick={async () => {
                  const ok = await patch({
                    skill_tags: skills.split(",").map((s) => s.trim()).filter(Boolean),
                    capacity_hrs: capacity,
                  });
                  if (ok) setEditing(false);
                }}>
                save
              </button>
            ) : (
              <button className="rounded border px-2 py-0.5 hover:bg-slate-100"
                      onClick={() => setEditing(true)}>
                edit
              </button>
            )}
            <button className="rounded border px-2 py-0.5 hover:bg-slate-100"
                    onClick={() => patch({ is_active: !member.is_active })}>
              {member.is_active ? "deactivate" : "activate"}
            </button>
          </div>
        )}
        {error && <p className="text-red-600">{error}</p>}
      </td>
    </tr>
  );
}

export function TeamForms({ members, canEdit }: {
  members: Member[];
  canEdit: boolean;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  async function create(formData: FormData) {
    setError(null);
    const response = await fetch("/api/team-members", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        name: formData.get("name"),
        role: formData.get("role"),
        skill_tags: String(formData.get("skill_tags") ?? "")
          .split(",").map((s) => s.trim()).filter(Boolean),
        capacity_hrs: Number(formData.get("capacity_hrs") || 40),
      }),
    });
    if (!response.ok) {
      setError(JSON.stringify((await response.json().catch(() => null))?.detail));
      return;
    }
    router.refresh();
  }

  return (
    <div className="space-y-3 text-sm">
      <table className="w-full rounded border bg-white text-left text-xs">
        <thead className="text-slate-500">
          <tr className="border-b bg-slate-50">
            <th className="px-4 py-2">Name</th>
            <th className="px-2 py-2">Role</th>
            <th className="px-2 py-2">Skills</th>
            <th className="px-2 py-2">Capacity</th>
            <th className="px-2 py-2">This week</th>
            <th className="px-2 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <MemberRow key={m.member_id} member={m} canEdit={canEdit} />
          ))}
        </tbody>
      </table>

      {canEdit && (
        <form action={create}
              className="flex flex-wrap items-end gap-2 rounded border bg-white p-3 text-xs">
          <input name="name" required placeholder="Name"
                 className="rounded border px-2 py-1.5" />
          <input name="role" required placeholder="Role"
                 className="rounded border px-2 py-1.5" />
          <input name="skill_tags" placeholder="skills, comma-separated"
                 className="w-56 rounded border px-2 py-1.5" />
          <input name="capacity_hrs" type="number" min="1" defaultValue={40}
                 title="weekly capacity hours"
                 className="w-20 rounded border px-2 py-1.5" />
          <button className="rounded bg-slate-800 px-3 py-1.5 text-white">
            Add member
          </button>
          {error && <span className="text-red-600">{error}</span>}
        </form>
      )}
    </div>
  );
}
