import { StakeholderForms } from "@/components/StakeholderForms";
import { TeamForms } from "@/components/TeamForms";
import { PageHeader } from "@/components/ui";
import { requireClientUser, serverApi } from "@/lib/api";

export type Member = {
  member_id: number;
  user_id: number | null; // linked login for the My Work portal
  name: string;
  role: string;
  skill_tags: string[];
  capacity_hrs: number;
  allocated_hrs: number;
  is_active: number;
};

export type ClientUser = {
  user_id: number;
  display_name: string;
  email: string;
  role: string;
  invite_status: string;
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
  const [members, stakeholders, users] = await Promise.all([
    serverApi<Member[]>("/team-members"),
    serverApi<Stakeholder[]>("/stakeholders"),
    serverApi<ClientUser[]>("/users"),
  ]);

  return (
    <>
      <PageHeader
        title="Team"
        description="One shared roster across every project (PRD section 9). allocated_hrs is the current-week load cache — display only, never a decision input."
      />
      <div className="space-y-8">
        <TeamForms members={members} users={users}
                   canEdit={me.role === "client_admin"} />

        <section className="space-y-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Stakeholders</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Comms audiences (PRD 8.8). Project id empty = client-wide.
            </p>
          </div>
          <StakeholderForms stakeholders={stakeholders}
                            canEdit={me.role === "client_admin"} />
        </section>
      </div>
    </>
  );
}
