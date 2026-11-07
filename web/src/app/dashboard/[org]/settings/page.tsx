"use client";

import { useCallback, useEffect, useState } from "react";

import { useOrg } from "@/components/dashboard/org";
import { Alert, Badge, Button, Card, Field, Input, Select, Textarea } from "@/components/ui";
import { apiFetch, mediaUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { REGIONS } from "@/lib/format";
import type { Organization } from "@/lib/types";

export default function SettingsPage() {
  const { can } = useOrg();
  return (
    <div className="space-y-10">
      <h1 className="text-2xl font-extrabold">Settings</h1>
      {can("manage_org") && <Profile />}
      {(can("view_finance") || can("manage_payouts")) && <Payouts />}
      <Team />
    </div>
  );
}

function Profile() {
  const { org, reload } = useOrg();
  const { request } = useAuth();
  const fields = ["name", "description", "email", "phone", "website", "instagram", "x_handle", "facebook", "tiktok", "region", "city", "fee_bearer"] as const;
  const [f, setF] = useState(() => Object.fromEntries(fields.map((k) => [k, (org[k] as string) ?? ""])) as Record<(typeof fields)[number], string>);
  const [logo, setLogo] = useState<File | null>(null);
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState("");
  const set = (k: (typeof fields)[number]) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy("save");
    setMsg(null);
    try {
      await request<Organization>(`/organizations/${org.slug}/`, { method: "PATCH", body: f });
      if (logo) {
        const fd = new FormData();
        fd.append("logo", logo);
        await request(`/organizations/${org.slug}/`, { method: "PATCH", body: fd });
      }
      reload();
      setMsg({ kind: "success", text: "Profile saved." });
    } catch (err) {
      setMsg({ kind: "error", text: err instanceof Error ? err.message : "Could not save." });
    } finally {
      setBusy("");
    }
  }
  async function verify() {
    setBusy("verify");
    setMsg(null);
    try {
      await request(`/organizations/${org.slug}/submit-verification/`, { method: "POST" });
      reload();
      setMsg({ kind: "success", text: "Submitted for verification. We'll review it shortly." });
    } catch (err) {
      setMsg({ kind: "error", text: err instanceof Error ? err.message : "Could not submit." });
    } finally {
      setBusy("");
    }
  }

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold">Organizer profile</h2>
        <Badge color={org.verification_status === "verified" ? "green" : org.verification_status === "pending" ? "yellow" : "gray"}>
          {org.verification_status === "verified" ? "✓ Verified" : org.verification_status === "pending" ? "Verification pending" : "Not verified"}
        </Badge>
      </div>
      <form onSubmit={save} className="space-y-4">
        <div className="flex items-center gap-4">
          <div className="grid h-16 w-16 place-items-center overflow-hidden rounded-xl bg-brand text-2xl font-bold text-white">
            {logo ? <img src={URL.createObjectURL(logo)} alt="" className="h-full w-full object-cover" />
              : org.logo ? <img src={mediaUrl(org.logo)!} alt="" className="h-full w-full object-cover" /> : org.name[0]}
          </div>
          <Input type="file" accept="image/*" className="max-w-xs py-1.5" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name"><Input required value={f.name} onChange={set("name")} /></Field>
          <Field label="Contact phone"><Input value={f.phone} onChange={set("phone")} /></Field>
          <Field label="Contact email"><Input type="email" value={f.email} onChange={set("email")} /></Field>
          <Field label="Website"><Input type="url" value={f.website} onChange={set("website")} placeholder="https://" /></Field>
          <Field label="Region"><Select value={f.region} onChange={set("region")}>
            <option value="">Choose…</option>{Object.entries(REGIONS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select></Field>
          <Field label="City / town"><Input value={f.city} onChange={set("city")} /></Field>
          <Field label="Instagram"><Input value={f.instagram} onChange={set("instagram")} placeholder="@handle" /></Field>
          <Field label="X (Twitter)"><Input value={f.x_handle} onChange={set("x_handle")} placeholder="@handle" /></Field>
          <Field label="Facebook"><Input value={f.facebook} onChange={set("facebook")} /></Field>
          <Field label="TikTok"><Input value={f.tiktok} onChange={set("tiktok")} placeholder="@handle" /></Field>
          <Field label="Default booking fee" hint="Can be changed per event">
            <Select value={f.fee_bearer} onChange={set("fee_bearer")}>
              <option value="">Platform default (buyer pays)</option>
              <option value="buyer">Buyer pays</option>
              <option value="organizer">I absorb fees</option>
            </Select>
          </Field>
        </div>
        <Field label="About" hint="Shown on your public organizer page"><Textarea value={f.description} onChange={set("description")} /></Field>
        {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" loading={busy === "save"}>Save profile</Button>
          {["unverified", "rejected"].includes(org.verification_status) && (
            <Button type="button" variant="secondary" onClick={verify} loading={busy === "verify"}>Request ✓ verification</Button>
          )}
        </div>
      </form>
    </Card>
  );
}

type Payout = { id: number; method: string; mobile_money_provider: string; bank_name: string; masked_account_number: string;
  account_name: string; is_default: boolean; is_verified: boolean };

function Payouts() {
  const { org, can } = useOrg();
  const { request } = useAuth();
  const base = `/organizations/${org.slug}/payout-accounts/`;
  const [list, setList] = useState<Payout[]>([]);
  const [banks, setBanks] = useState<{ name: string; code: string }[]>([]);
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ method: "mobile_money", mobile_money_provider: "mtn", bank_code: "", account_number: "", account_name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => { request<Payout[]>(base).then(setList).catch(() => {}); }, [request, base]);
  useEffect(load, [load]);
  useEffect(() => { if (adding && f.method === "bank" && !banks.length) apiFetch<typeof banks>("/payments/banks/").then(setBanks).catch(() => {}); }, [adding, f.method, banks.length]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const bank = banks.find((b) => b.code === f.bank_code);
      await request(base, { body: { ...f, bank_name: bank?.name ?? "" } });
      setAdding(false);
      setF({ ...f, account_number: "", account_name: "" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add account.");
    } finally {
      setBusy(false);
    }
  }
  const MOMO: Record<string, string> = { mtn: "MTN MoMo", telecel: "Telecel Cash", airteltigo: "AT Money" };

  return (
    <Card>
      <h2 className="text-lg font-bold">Payout accounts</h2>
      <p className="mt-1 text-sm text-zinc-600">Ticket earnings are paid here automatically, usually the next business day.</p>
      <div className="mt-4 space-y-2">
        {list.length === 0 && <Alert kind="info">Add a payout account before selling paid tickets.</Alert>}
        {list.map((p) => (
          <div key={p.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-zinc-200 p-3">
            <span className="font-semibold">{p.method === "mobile_money" ? MOMO[p.mobile_money_provider] : p.bank_name}</span>
            <span className="font-mono text-sm">{p.masked_account_number}</span>
            <span className="text-sm text-zinc-600">{p.account_name}</span>
            {p.is_default && <Badge color="brand">Default</Badge>}
            {p.is_verified && <Badge color="green">Verified</Badge>}
          </div>
        ))}
      </div>
      {can("manage_payouts") && (adding ? (
        <form onSubmit={add} className="mt-4 space-y-4 rounded-lg border border-dashed border-zinc-300 p-4">
          <div className="flex gap-2">
            {[["mobile_money", "Mobile Money"], ["bank", "Bank account"]].map(([v, l]) => (
              <button type="button" key={v} onClick={() => setF({ ...f, method: v })}
                className={`rounded-full px-4 py-1.5 text-sm font-semibold ${f.method === v ? "bg-brand text-white" : "border border-zinc-300"}`}>{l}</button>
            ))}
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            {f.method === "mobile_money" ? (
              <Field label="Network"><Select value={f.mobile_money_provider} onChange={(e) => setF({ ...f, mobile_money_provider: e.target.value })}>
                {Object.entries(MOMO).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select></Field>
            ) : (
              <Field label="Bank"><Select required value={f.bank_code} onChange={(e) => setF({ ...f, bank_code: e.target.value })}>
                <option value="">Choose bank…</option>{banks.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
              </Select></Field>
            )}
            <Field label={f.method === "mobile_money" ? "MoMo number" : "Account number"}>
              <Input required value={f.account_number} onChange={(e) => setF({ ...f, account_number: e.target.value })} />
            </Field>
            <Field label="Account name" hint="Exactly as registered"><Input required value={f.account_name} onChange={(e) => setF({ ...f, account_name: e.target.value })} /></Field>
          </div>
          {error && <Alert>{error}</Alert>}
          <div className="flex gap-2">
            <Button type="submit" loading={busy}>Save account</Button>
            <Button type="button" variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
          </div>
        </form>
      ) : <Button variant="secondary" className="mt-4" onClick={() => setAdding(true)}>+ Add payout account</Button>)}
    </Card>
  );
}

type Member = { id: number; role: string; user: { id: number; full_name: string; email: string | null; phone: string | null } };
type Invite = { id: number; contact: string; role: string; status: string; delivery_failed?: boolean };
const ROLES: Record<string, string> = {
  owner: "Owner: everything", admin: "Admin: events, team, sales", finance: "Finance: sales and payouts",
  marketing: "Marketing: events and promo codes", scanner: "Gate scanner: check-in only",
};

function Team() {
  const { org, can, reload: reloadOrg } = useOrg();
  const { request, user } = useAuth();
  const base = `/organizations/${org.slug}`;
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [f, setF] = useState({ contact: "", role: "scanner" });
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const manage = can("manage_members");

  const load = useCallback(() => {
    request<Member[]>(`${base}/members/`).then(setMembers);
    if (manage) request<{ results: Invite[] }>(`${base}/invitations/`).then((r) => setInvites(r.results));
  }, [request, base, manage]);
  useEffect(load, [load]);

  async function run(fn: () => Promise<unknown>, ok?: string) {
    setMsg(null);
    try {
      await fn();
      if (ok) setMsg({ kind: "success", text: ok });
      load();
      reloadOrg();
    } catch (err) {
      setMsg({ kind: "error", text: err instanceof Error ? err.message : "Failed." });
    }
  }

  return (
    <Card>
      <h2 className="text-lg font-bold">Team</h2>
      <div className="mt-4 divide-y divide-zinc-100">
        {members.map((m) => (
          <div key={m.id} className="flex flex-wrap items-center gap-3 py-3">
            <div className="min-w-0 flex-1">
              <p className="font-medium">{m.user.full_name || m.user.phone || m.user.email}{m.user.id === user?.id && " (you)"}</p>
              <p className="text-xs text-zinc-500">{[m.user.phone, m.user.email].filter(Boolean).join(" · ")}</p>
            </div>
            {manage && m.user.id !== user?.id ? (
              <>
                <Select value={m.role} className="w-auto py-1.5 text-sm"
                  onChange={(e) => run(() => request(`${base}/members/${m.id}/`, { method: "PATCH", body: { role: e.target.value } }))}>
                  {Object.keys(ROLES).map((r) => <option key={r} value={r}>{r}</option>)}
                </Select>
                <Button size="sm" variant="ghost" className="text-red-600"
                  onClick={() => confirm("Remove from team?") && run(() => request(`${base}/members/${m.id}/`, { method: "DELETE" }))}>Remove</Button>
              </>
            ) : <Badge>{m.role}</Badge>}
          </div>
        ))}
      </div>
      {manage && (
        <>
          {invites.length > 0 && (
            <div className="mt-4 space-y-1 text-sm">
              <p className="font-semibold">Pending invitations</p>
              {invites.map((i) => (
                <div key={i.id} className="flex items-center gap-2">
                  <span>{i.contact}</span><Badge>{i.role}</Badge>{i.delivery_failed && <Badge color="red">not delivered</Badge>}
                  <button className="text-xs text-red-600" onClick={() => run(() => request(`${base}/invitations/${i.id}/`, { method: "DELETE" }))}>revoke</button>
                </div>
              ))}
            </div>
          )}
          <form className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto_auto]"
            onSubmit={(e) => { e.preventDefault(); run(() => request(`${base}/invitations/`, { body: f }), `Invitation sent to ${f.contact}.`).then(() => setF({ ...f, contact: "" })); }}>
            <Input required placeholder="Phone or email to invite" value={f.contact} onChange={(e) => setF({ ...f, contact: e.target.value })} />
            <Select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} className="w-auto">
              {Object.entries(ROLES).filter(([r]) => r !== "owner" || org.my_role === "owner").map(([r, l]) => <option key={r} value={r}>{l}</option>)}
            </Select>
            <Button type="submit">Invite</Button>
          </form>
        </>
      )}
      {msg && <div className="mt-3"><Alert kind={msg.kind}>{msg.text}</Alert></div>}
    </Card>
  );
}
