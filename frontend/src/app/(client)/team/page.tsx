import { StakeholderForms } from "@/components/StakeholderForms";
import { TeamForms } from "@/components/TeamForms";
import { requireClientUser, serverApi } from "@/lib/api";

export type Member = {
  member_id: number;
  name: string;
  role: string;
  skill_tags: string[];
  capacity_hrs: number;
  allocated_hrs: number;
  is_active: number;
};

export type Stakeholder = {
  stakeholder_id: number;
  name: string;
  email: string | null;
  audience_type: string;
  project_id: number | null;
};

export default async function TeamPage() {
  const me = await requireClientUser();
  const [members, stakeholders] = await Promise.all([
    serverApi<Member[]>("/team-members"),
    serverApi<Stakeholder[]>("/stakeholders"),
  ]);

  return (
    <main className="space-y-8">
      <section>
        <h1 className="mb-1 text-lg font-semibold">Team</h1>
        <p className="mb-3 text-xs text-slate-500">
          One shared roster across every project (PRD section 9). allocated_hrs
          is the current-week load cache — display only, never a decision input.
        </p>
        <TeamForms members={members} canEdit={me.role === "client_admin"} />
      </section>

      <section>
        <h2 className="mb-1 text-sm font-semibold">Stakeholders</h2>
        <p className="mb-3 text-xs text-slate-500">
          Comms audiences (PRD 8.8). Project id empty = client-wide.
        </p>
        <StakeholderForms stakeholders={stakeholders}
                          canEdit={me.role === "client_admin"} />
      </section>
    </main>
  );
}
