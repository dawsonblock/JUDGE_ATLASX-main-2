import { ReactNode } from "react";
import { cookies } from "next/headers";

import { resolveAdminAccess } from "./authGuard";

export default async function AdminLayout({
  children,
}: {
  children: ReactNode;
}) {
  const token = cookies().get("jta_access_token")?.value;
  const access = await resolveAdminAccess(token);

  if (!access.allowed) {
    return (
      <div className="mx-auto max-w-3xl rounded border border-red-200 bg-red-50 p-6 text-sm text-red-700">
        Admin access denied. Sign in with an active admin account.
      </div>
    );
  }

  return <>{children}</>;
}
