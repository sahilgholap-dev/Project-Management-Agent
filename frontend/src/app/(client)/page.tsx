import { CreateProjectForm } from "@/components/CreateProjectForm";
import { Badge, Card, EmptyState, PageHeader, statusTone, Table, Td, TdLink } from "@/components/ui";
import { ProjectSummary, requireClientUser, serverApi } from "@/lib/api";

export default async function ProjectListPage() {
  const me = await requireClientUser(); // gate BEFORE data (403-race guard)
  const projects = await serverApi<ProjectSummary[]>("/projects");

  return (
    <>
      <PageHeader title="Projects" />
      <div className="space-y-6">
        {projects.length === 0 ? (
          <EmptyState>No projects yet.</EmptyState>
        ) : (
          <Table headers={["Project", "Timeline", "Status"]}>
            {projects.map((p) => (
              <tr key={p.project_id} className="hover:bg-slate-50">
                <TdLink href={`/projects/${p.project_id}`}>{p.name}</TdLink>
                <Td className="text-slate-500">
                  {p.timeline_start} → {p.timeline_end}
                </Td>
                <Td>
                  <Badge tone={statusTone(p.status)}>{p.status}</Badge>
                </Td>
              </tr>
            ))}
          </Table>
        )}

        {me.role === "client_admin" && (
          <Card title="New project">
            <CreateProjectForm />
          </Card>
        )}
      </div>
    </>
  );
}
