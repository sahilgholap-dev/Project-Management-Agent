import { notFound } from "next/navigation";
import { CompanyDeleteNote, CompanyHeaderActions } from "@/components/admin/CompanyForms";
import { CreateUserForm, InviteStatusBadge, UserRowActions } from "@/components/admin/UserForms";
import { ConfigForm, ConfigValue } from "@/components/ConfigForm";
import { Badge, Card, EmptyState, PageHeader, Table, Td } from "@/components/ui";
import { AdminUser, Company, requireAdmin, serverApi, serverApiOrNull } from "@/lib/api";

export default async function CompanyDetailPage({ params }: {
  params: Promise<{ id: string }>;
}) {
  await requireAdmin();
  const { id } = await params;
  const clientId = Number(id);
  const [companies, allUsers, config] = await Promise.all([
    serverApi<Company[]>("/admin/clients"),
    serverApi<AdminUser[]>("/admin/users"),
    serverApiOrNull<ConfigValue>(`/admin/clients/${clientId}/config`),
  ]);
  const company = companies.find((c) => c.client_id === clientId);
  if (!company) notFound();
  const users = allUsers.filter((u) => u.client_id === clientId);
  const deletable = company.user_count === 0 && company.project_count === 0;

  return (
    <>
      <PageHeader
        title={company.name}
        description={`${company.user_count} user(s) · ${company.project_count} project(s) · created ${company.created_at.slice(0, 10)}`}
        actions={
          <CompanyHeaderActions
            clientId={clientId}
            name={company.name}
            deletable={deletable}
          />
        }
      />
      <div className="space-y-6">
        {!deletable && <CompanyDeleteNote />}

        <Card
          title="Users"
          description="Users of this company. Credentials are generated and shown once for manual handoff — nothing is ever sent."
        >
          <div className="space-y-4">
            {users.length === 0 ? (
              <EmptyState>No users in this company yet.</EmptyState>
            ) : (
              <Table headers={["User", "Role", "Status", "Actions"]}>
                {users.map((u) => (
                  <tr key={u.user_id} className="hover:bg-slate-50">
                    <Td>
                      <p className="font-medium text-slate-900">{u.display_name}</p>
                      <p className="text-xs text-slate-500">{u.email}</p>
                    </Td>
                    <Td><Badge tone="info">{u.role}</Badge></Td>
                    <Td><InviteStatusBadge status={u.invite_status} /></Td>
                    <Td><UserRowActions user={u} /></Td>
                  </tr>
                ))}
              </Table>
            )}
            <div className="border-t border-slate-100 pt-4">
              <CreateUserForm companies={[company]} fixedClientId={clientId} />
            </div>
          </div>
        </Card>

        <Card
          title="Configuration"
          description={config
            ? "The company's operational config — same editor and validation the client_admin sees at /config."
            : "Not configured yet. Saving here validates exactly like the client portal's config screen."}
        >
          {users.length === 0 ? (
            <EmptyState>
              Config needs at least one user (reviewers and approvers are picked
              from the company&apos;s users) — create a user above first.
            </EmptyState>
          ) : (
            <ConfigForm
              initial={config}
              users={users}
              endpoint={`/api/admin/clients/${clientId}/config`}
            />
          )}
        </Card>
      </div>
    </>
  );
}
