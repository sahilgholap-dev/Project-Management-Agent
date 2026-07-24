import { CreateUserForm, InviteStatusBadge, UserRowActions } from "@/components/admin/UserForms";
import { Badge, Card, EmptyState, PageHeader, Table, Td, TdLink } from "@/components/ui";
import { AdminUser, Company, requireAdmin, serverApi } from "@/lib/api";

export default async function AdminUsersPage() {
  await requireAdmin();
  const [users, companies] = await Promise.all([
    serverApi<AdminUser[]>("/admin/users"),
    serverApi<Company[]>("/admin/clients"),
  ]);

  return (
    <>
      <PageHeader
        title="Users"
        description="All client users across companies. Platform admin accounts are managed only via bootstrap."
      />
      <div className="space-y-6">
        <Card title="Create a user">
          <CreateUserForm companies={companies} />
        </Card>
        {users.length === 0 ? (
          <EmptyState>No users yet.</EmptyState>
        ) : (
          <Table headers={["User", "Company", "Role", "Status", "Actions"]}>
            {users.map((u) => (
              <tr key={u.user_id} className="hover:bg-slate-50">
                <Td>
                  <p className="font-medium text-slate-900">{u.display_name}</p>
                  <p className="text-xs text-slate-500">{u.email}</p>
                </Td>
                <TdLink href={`/admin/companies/${u.client_id}`}>
                  {u.client_name}
                </TdLink>
                <Td><Badge tone="info">{u.role}</Badge></Td>
                <Td><InviteStatusBadge status={u.invite_status} /></Td>
                <Td><UserRowActions user={u} /></Td>
              </tr>
            ))}
          </Table>
        )}
      </div>
    </>
  );
}
