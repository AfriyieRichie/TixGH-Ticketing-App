"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert, Button, ButtonLink, PageLoader } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Organization } from "@/lib/types";

type Preview = { organization: { name: string; slug: string }; role: string; status: string };

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const { user, ready, request } = useAuth();
  const router = useRouter();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiFetch<Preview>(`/organizations/invitations/${token}/`).then(setPreview).catch(() => setError("This invitation link is not valid."));
  }, [token]);

  async function accept() {
    setBusy(true);
    setError("");
    try {
      const org = await request<Organization>(`/organizations/invitations/${token}/`, { method: "POST" });
      router.push(`/dashboard/${org.slug}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not accept the invitation.");
      setBusy(false);
    }
  }

  if (!preview && !error) return <PageLoader />;
  return (
    <main className="mx-auto max-w-md px-4 py-20 text-center">
      {preview && (
        <>
          <h1 className="text-2xl font-extrabold">Join {preview.organization.name}</h1>
          <p className="mt-2 text-zinc-600">You&apos;ve been invited to join their team as <b>{preview.role}</b>.</p>
          {preview.status !== "pending" ? <div className="mt-6"><Alert>This invitation is {preview.status}.</Alert></div>
            : !ready ? <PageLoader />
            : user ? <Button className="mt-6 w-full" onClick={accept} loading={busy}>Accept invitation</Button>
            : <ButtonLink href={`/login?next=/invites/${token}`} className="mt-6 w-full">Sign in to accept</ButtonLink>}
          <p className="mt-3 text-xs text-zinc-500">Sign in with the phone number or email the invitation was sent to.</p>
        </>
      )}
      {error && <div className="mt-6"><Alert>{error}</Alert></div>}
    </main>
  );
}
