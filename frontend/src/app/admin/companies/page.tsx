import { CreateCompanyForm } from "@/components/admin/CompanyForms";
import { Card, EmptyState, PageHeader, Table, Td, TdLink } from "@/components/ui";
import { Company, requireAdmin, serverApi } from "@/lib/api";

export default async function CompaniesPage() {
  await requireAdmin();
  const companies = await serverApi<Company[]>("/admin/clients");

  return (
    <>
      <PageHeader
        title="Companies"
        description="Client companies on the platform. Open one to manage its users and configuration."
      />
      <div className="space-y-6">
        <Card title="Create a company">
          <CreateCompanyForm />
        </Card>
        {companies.length === 0 ? (
          <EmptyState>No companies yet — create the first one above.</EmptyState>
        ) : (
          <Table headers={["Company", "Users", "Projects", "Created", ""]}>
            {companies.map((c) => (
              <tr key={c.client_id} className="hover:bg-slate-50">
                <TdLink href={`/admin/companies/${c.client_id}`}>{c.name}</TdLink>
                <Td>{c.user_count}</Td>
                <Td>{c.project_count}</Td>
                <Td className="text-slate-500">{c.created_at.slice(0, 10)}</Td>
                <TdLink href={`/admin/companies/${c.client_id}`}>Manage →</TdLink>
              </tr>
            ))}
          </Table>
        )}
      </div>
    </>
  );
}
