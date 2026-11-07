"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Alert, Button, Field, Input, PageLoader } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuthResponse } from "@/lib/types";

export default function Page() {
  return <Suspense fallback={<PageLoader />}><Login /></Suspense>;
}

function Login() {
  const { signIn } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next");
  const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : "/tickets";

  const [identifier, setIdentifier] = useState("");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [usePassword, setUsePassword] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function requestCode(e?: React.FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await apiFetch<{ sent_to: string }>("/auth/otp/request/", { body: { identifier, purpose: "login" } });
      setSentTo(res.sent_to);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Network error.");
    } finally {
      setBusy(false);
    }
  }

  async function passwordLogin(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      signIn(await apiFetch<AuthResponse>("/auth/login/", { body: { identifier, password } }));
      router.replace(safeNext);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Network error.");
      setBusy(false);
    }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await apiFetch<AuthResponse>("/auth/otp/verify/", { body: { identifier, code, full_name: name } });
      signIn(res);
      router.replace(safeNext);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Network error.");
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-sm px-4 py-16">
      <h1 className="text-2xl font-extrabold">Sign in or create an account</h1>
      <p className="mt-2 text-zinc-600">We&apos;ll send a 6-digit code. No password needed.</p>
      {usePassword ? (
        <form onSubmit={passwordLogin} className="mt-8 space-y-4">
          <Field label="Phone number or email">
            <Input autoFocus required value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" />
          </Field>
          <Field label="Password">
            <Input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </Field>
          {error && <Alert>{error}</Alert>}
          <Button type="submit" className="w-full" loading={busy}>Sign in</Button>
          <button type="button" className="text-sm font-semibold text-brand" onClick={() => { setUsePassword(false); setError(""); }}>
            Use a one-time code instead
          </button>
        </form>
      ) : !sentTo ? (
        <form onSubmit={requestCode} className="mt-8 space-y-4">
          <Field label="Phone number or email">
            <Input autoFocus required value={identifier} onChange={(e) => setIdentifier(e.target.value)}
              placeholder="024 123 4567" autoComplete="username" />
          </Field>
          {error && <Alert>{error}</Alert>}
          <Button type="submit" className="w-full" loading={busy}>Send code</Button>
          <button type="button" className="text-sm font-semibold text-brand" onClick={() => { setUsePassword(true); setError(""); }}>
            Use password instead
          </button>
          <p className="text-xs text-zinc-500">Bought tickets as a guest? Sign in with the same phone number or email and they&apos;ll appear in your account.</p>
        </form>
      ) : (
        <form onSubmit={verify} className="mt-8 space-y-4">
          <Alert kind="info">Code sent to <b>{sentTo}</b>.</Alert>
          <Field label="6-digit code">
            <Input autoFocus required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="text-center text-2xl tracking-[0.5em]"
              autoComplete="one-time-code" />
          </Field>
          <Field label="Your name" hint="Only needed the first time">
            <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
          </Field>
          {error && <Alert>{error}</Alert>}
          <Button type="submit" className="w-full" loading={busy}>Continue</Button>
          <div className="flex justify-between text-sm">
            <button type="button" className="font-semibold text-brand" onClick={() => { setSentTo(""); setCode(""); }}>Change number</button>
            <button type="button" className="font-semibold text-brand" onClick={() => requestCode()} disabled={busy}>Resend code</button>
          </div>
        </form>
      )}
    </main>
  );
}
