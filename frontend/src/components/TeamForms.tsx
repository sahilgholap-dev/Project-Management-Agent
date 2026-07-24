"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Table, Td, inputCls } from "@/components/ui";
import type { ClientUser, Member } from "@/app/(client)/team/page";

function MemberRow({ member, users, canEdit }: {
  member: Member;
  users: ClientUser[];
  canEdit: boolean;
}) {
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
    <tr className={member.is_active ? "hover:bg-slate-50" : "opacity-50 hover:bg-slate-50"}>
      <Td className="font-medium text-slate-900">{member.name}</Td>
      <Td>{member.role}</Td>
      <Td>
        {editing ? (
          <input value={skills} onChange={(e) => setSkills(e.target.value)}
                 className={`${inputCls} px-2 py-1`} />
        ) : member.skill_tags.join(", ") || "—"}
      </Td>
      <Td>
        {editing ? (
          <input type="number" min="1" value={capacity}
                 onChange={(e) => setCapacity(Number(e.target.value))}
                 className={`${inputCls} w-20 px-2 py-1`} />
        ) : `${member.capacity_hrs}h/wk`}
      </Td>
      <Td className="text-slate-500" title="current-week load (display only)">
        {member.allocated_hrs}h
      </Td>
      <Td title="the login this roster row belongs to — powers the My Work portal">
        {canEdit ? (
          <select
            value={member.user_id ?? ""}
            onChange={(e) => patch({
              user_id: e.target.value === "" ? null : Number(e.target.value),
            })}
            className={`${inputCls} w-44 px-2 py-1 text-xs`}
          >
            <option value="">— no login linked —</option>
            {users.filter((u) => u.role !== "platform_admin").map((u) => (
              <option key={u.user_id} value={u.user_id}>
                {u.email}
              </option>
            ))}
          </select>
        ) : (
          users.find((u) => u.user_id === member.user_id)?.email ?? "—"
        )}
      </Td>
      <Td>
        {canEdit && (
          <div className="flex gap-1">
            {editing ? (
              <Button
                variant="secondary"
                small
                onClick={async () => {
                  const ok = await patch({
                    skill_tags: skills.split(",").map((s) => s.trim()).filter(Boolean),
                    capacity_hrs: capacity,
                  });
                  if (ok) setEditing(false);
                }}>
                save
              </Button>
            ) : (
              <Button variant="secondary" small onClick={() => setEditing(true)}>
                edit
              </Button>
            )}
            <Button variant="secondary" small
                    onClick={() => patch({ is_active: !member.is_active })}>
              {member.is_active ? "deactivate" : "activate"}
            </Button>
          </div>
        )}
        {error && <p className="text-xs text-red-600">{error}</p>}
      </Td>
    </tr>
  );
}

export function TeamForms({ members, users, canEdit }: {
  members: Member[];
  users: ClientUser[];
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
      <Table headers={["Name", "Role", "Skills", "Capacity", "This week", "Login", ""]}>
        {members.map((m) => (
          <MemberRow key={m.member_id} member={m} users={users} canEdit={canEdit} />
        ))}
      </Table>

      {canEdit && (
        <form action={create}
              className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-sm">
          <input name="name" required placeholder="Name"
                 className={`${inputCls} w-auto px-2 py-1.5 text-xs`} />
          <input name="role" required placeholder="Role"
                 className={`${inputCls} w-auto px-2 py-1.5 text-xs`} />
          <input name="skill_tags" placeholder="skills, comma-separated"
                 className={`${inputCls} w-56 px-2 py-1.5 text-xs`} />
          <input name="capacity_hrs" type="number" min="1" defaultValue={40}
                 title="weekly capacity hours"
                 className={`${inputCls} w-20 px-2 py-1.5 text-xs`} />
          <Button small>Add member</Button>
          {error && <span className="text-red-600">{error}</span>}
        </form>
      )}
    </div>
  );
}
