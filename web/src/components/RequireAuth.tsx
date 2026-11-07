"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { PageLoader } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth();
  const router = useRouter();
  const path = usePathname();
  useEffect(() => {
    if (ready && !user) router.replace(`/login?next=${encodeURIComponent(path)}`);
  }, [ready, user, router, path]);
  if (!ready || !user) return <PageLoader />;
  return <>{children}</>;
}
