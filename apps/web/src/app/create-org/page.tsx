import { CreateOrganization } from "@clerk/nextjs";

export default function CreateOrgPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <CreateOrganization afterCreateOrganizationUrl="/dashboard" />
    </div>
  );
}
