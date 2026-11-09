"use client";

import { useEffect, useState } from "react";

import { Alert, Button, Field, Input, Select, Textarea } from "@/components/ui";
import { apiFetch, mediaUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fromLocalInput, REGIONS, toLocalInput } from "@/lib/format";
import type { Category, OrgEvent, Venue } from "@/lib/types";

import { useOrg } from "./org";

type Form = {
  title: string; summary: string; description: string; category: string; format: OrgEvent["format"];
  venue: string; online_url: string; start_at: string; end_at: string; visibility: OrgEvent["visibility"];
  age_restriction: string; max_tickets_per_order: string; fee_bearer: string; allow_transfers: boolean;
  reentry_allowed: boolean; max_reentries: string; reentry_cutoff_at: string;
  refund_policy: string; refund_policy_details: string;
};

function initial(ev?: OrgEvent): Form {
  return {
    title: ev?.title ?? "", summary: ev?.summary ?? "", description: ev?.description ?? "",
    category: ev?.category ?? "", format: ev?.format ?? "in_person", venue: ev?.venue ? String(ev.venue) : "",
    online_url: ev?.online_url ?? "", start_at: toLocalInput(ev?.start_at), end_at: toLocalInput(ev?.end_at),
    visibility: ev?.visibility ?? "public", age_restriction: String(ev?.age_restriction ?? 0),
    max_tickets_per_order: String(ev?.max_tickets_per_order ?? 10), fee_bearer: ev?.fee_bearer ?? "",
    allow_transfers: ev?.allow_transfers ?? true,
    reentry_allowed: ev?.reentry_allowed ?? false,
    max_reentries: ev?.max_reentries != null ? String(ev.max_reentries) : "",
    reentry_cutoff_at: toLocalInput(ev?.reentry_cutoff_at), refund_policy: ev?.refund_policy ?? "no_refunds",
    refund_policy_details: ev?.refund_policy_details ?? "",
  };
}

export function EventForm({ event, onSaved }: { event?: OrgEvent; onSaved: (ev: OrgEvent) => void }) {
  const { org } = useOrg();
  const { request } = useAuth();
  const [f, setF] = useState<Form>(() => initial(event));
  const [categories, setCategories] = useState<Category[]>([]);
  const [venues, setVenues] = useState<Venue[]>([]);
  const [addingVenue, setAddingVenue] = useState(false);
  const [cover, setCover] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiFetch<Category[]>("/categories/").then(setCategories).catch(() => {});
    request<Venue[]>(`/organizations/${org.slug}/venues/`).then((v) => {
      setVenues(v);
      if (!v.length && !event) setAddingVenue(true);
    });
  }, [request, org.slug, event]);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => { setF((s) => ({ ...s, [k]: v })); setSaved(false); };
  const needsVenue = f.format !== "online";
  const needsLink = f.format !== "in_person";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = {
        ...f,
        category: f.category || null,
        venue: needsVenue && f.venue ? Number(f.venue) : null,
        online_url: needsLink ? f.online_url : "",
        start_at: fromLocalInput(f.start_at),
        end_at: fromLocalInput(f.end_at),
        age_restriction: Number(f.age_restriction),
        max_tickets_per_order: Number(f.max_tickets_per_order),
        max_reentries: f.reentry_allowed && f.max_reentries ? Number(f.max_reentries) : null,
        reentry_cutoff_at: f.reentry_allowed ? fromLocalInput(f.reentry_cutoff_at) : null,
      };
      const path = event ? `/organizations/${org.slug}/events/${event.slug}/` : `/organizations/${org.slug}/events/`;
      let ev = await request<OrgEvent>(path, { method: event ? "PATCH" : "POST", body });
      if (cover) {
        const fd = new FormData();
        fd.append("cover_image", cover);
        ev = await request<OrgEvent>(`/organizations/${org.slug}/events/${ev.slug}/`, { method: "PATCH", body: fd });
        setCover(null);
      }
      setSaved(true);
      onSaved(ev);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  const preview = cover ? URL.createObjectURL(cover) : mediaUrl(event?.cover_image);

  return (
    <form onSubmit={submit} className="space-y-8">
      <Section title="Basics">
        <Field label="Event title"><Input required maxLength={150} value={f.title} onChange={(e) => set("title", e.target.value)} placeholder="e.g. Afrobeats Live in Accra" /></Field>
        <Field label="Short summary" hint="One or two lines shown on event cards">
          <Input maxLength={280} value={f.summary} onChange={(e) => set("summary", e.target.value)} />
        </Field>
        <Field label="Description"><Textarea rows={6} value={f.description} onChange={(e) => set("description", e.target.value)} placeholder="Line-up, schedule, dress code, what's included…" /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Category">
            <Select value={f.category} onChange={(e) => set("category", e.target.value)}>
              <option value="">Choose…</option>
              {categories.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
            </Select>
          </Field>
          <Field label="Cover image" hint="Wide image (e.g. 1600×900), max 5 MB">
            <Input type="file" accept="image/*" onChange={(e) => { setCover(e.target.files?.[0] ?? null); setSaved(false); }} className="py-1.5" />
          </Field>
        </div>
        {preview && <img src={preview} alt="" className="aspect-[16/9] w-full max-w-md rounded-lg object-cover" />}
      </Section>

      <Section title="When">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Starts"><Input type="datetime-local" required value={f.start_at} onChange={(e) => set("start_at", e.target.value)} /></Field>
          <Field label="Ends"><Input type="datetime-local" required value={f.end_at} min={f.start_at} onChange={(e) => set("end_at", e.target.value)} /></Field>
        </div>
        <p className="text-xs text-zinc-500">Times are Ghana time (GMT).</p>
      </Section>

      <Section title="Where">
        <div className="flex flex-wrap gap-2">
          {([["in_person", "In person"], ["online", "Online"], ["hybrid", "Both"]] as const).map(([v, l]) => (
            <button type="button" key={v} onClick={() => set("format", v)}
              className={`rounded-full px-4 py-1.5 text-sm font-semibold ${f.format === v ? "bg-brand text-white" : "border border-zinc-300 bg-white"}`}>{l}</button>
          ))}
        </div>
        {needsVenue && (addingVenue ? (
          <VenueForm onCreated={(v) => { setVenues([...venues, v]); set("venue", String(v.id)); setAddingVenue(false); }}
            onCancel={venues.length ? () => setAddingVenue(false) : undefined} />
        ) : (
          <div className="flex gap-2">
            <Select value={f.venue} onChange={(e) => set("venue", e.target.value)} className="flex-1">
              <option value="">Choose a venue…</option>
              {venues.map((v) => <option key={v.id} value={v.id}>{v.name}, {v.city}</option>)}
            </Select>
            <Button type="button" variant="secondary" onClick={() => setAddingVenue(true)}>+ New</Button>
          </div>
        ))}
        {needsLink && (
          <Field label="Online event link" hint="Zoom, YouTube, etc. Only shown to ticket holders.">
            <Input type="url" value={f.online_url} onChange={(e) => set("online_url", e.target.value)} placeholder="https://" />
          </Field>
        )}
      </Section>

      <Section title="Settings">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Who pays the booking fee?" hint="Buyers usually pay it, as on most ticketing sites">
            <Select value={f.fee_bearer} onChange={(e) => set("fee_bearer", e.target.value)}>
              <option value="">Default (buyer pays)</option>
              <option value="buyer">Buyer pays: you get the full ticket price</option>
              <option value="organizer">I absorb it: buyers see one clean price</option>
            </Select>
          </Field>
          <Field label="Visibility">
            <Select value={f.visibility} onChange={(e) => set("visibility", e.target.value as Form["visibility"])}>
              <option value="public">Public: listed in search</option>
              <option value="unlisted">Unlisted: only people with the link</option>
            </Select>
          </Field>
          <Field label="Refund policy">
            <Select value={f.refund_policy} onChange={(e) => set("refund_policy", e.target.value)}>
              <option value="no_refunds">No refunds</option>
              <option value="1_day">Up to 1 day before</option>
              <option value="7_days">Up to 7 days before</option>
              <option value="30_days">Up to 30 days before</option>
            </Select>
          </Field>
          <Field label="Minimum age"><Select value={f.age_restriction} onChange={(e) => set("age_restriction", e.target.value)}>
            {["0", "13", "16", "18", "21"].map((a) => <option key={a} value={a}>{a === "0" ? "All ages" : `${a}+`}</option>)}
          </Select></Field>
          <Field label="Max tickets per order"><Input type="number" min={1} max={100} value={f.max_tickets_per_order} onChange={(e) => set("max_tickets_per_order", e.target.value)} /></Field>
          <label className="flex items-center gap-2 self-end pb-3 text-sm font-medium">
            <input type="checkbox" checked={f.allow_transfers} onChange={(e) => set("allow_transfers", e.target.checked)} className="h-4 w-4 accent-brand" />
            Let buyers send tickets to friends
          </label>
        </div>
      </Section>

      <Section title="Gate and re-entry">
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={f.reentry_allowed} onChange={(e) => set("reentry_allowed", e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-brand" />
          <span>
            <span className="font-medium">Allow re-entry</span>
            <span className="block text-zinc-500">Gate staff scan people out when they leave and back in when they return.
              A ticket can only be inside once, so screenshots shared with friends don&apos;t work.</span>
          </span>
        </label>
        {f.reentry_allowed && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Max re-entries per ticket" hint="Blank = unlimited">
              <Input type="number" min={1} max={50} value={f.max_reentries} onChange={(e) => set("max_reentries", e.target.value)} />
            </Field>
            <Field label="No re-entry after" hint="Optional, e.g. 10:00 PM">
              <Input type="datetime-local" value={f.reentry_cutoff_at} onChange={(e) => set("reentry_cutoff_at", e.target.value)} />
            </Field>
          </div>
        )}
      </Section>

      {error && <Alert>{error}</Alert>}
      <div className="flex items-center gap-3">
        <Button type="submit" size="lg" loading={busy}>{event ? "Save changes" : "Create event"}</Button>
        {saved && <span className="text-sm font-semibold text-emerald-700">Saved ✓</span>}
      </div>
    </form>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4 rounded-xl border border-zinc-200 bg-white p-5">
      <h2 className="font-bold">{title}</h2>
      {children}
    </section>
  );
}

function VenueForm({ onCreated, onCancel }: { onCreated: (v: Venue) => void; onCancel?: () => void }) {
  const { org } = useOrg();
  const { request } = useAuth();
  const [v, setV] = useState({ name: "", address: "", city: "", region: org.region || "greater_accra", digital_address: "", directions: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setV({ ...v, [k]: e.target.value });

  async function save() {
    setBusy(true);
    setError("");
    try {
      onCreated(await request<Venue>(`/organizations/${org.slug}/venues/`, { body: v }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save venue.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-3 rounded-lg border border-dashed border-zinc-300 p-4">
      <p className="text-sm font-semibold">New venue</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Venue name"><Input value={v.name} onChange={set("name")} placeholder="Accra International Conference Centre" /></Field>
        <Field label="Street / area"><Input value={v.address} onChange={set("address")} /></Field>
        <Field label="City / town"><Input value={v.city} onChange={set("city")} /></Field>
        <Field label="Region"><Select value={v.region} onChange={set("region")}>
          {Object.entries(REGIONS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </Select></Field>
        <Field label="GhanaPost GPS (optional)"><Input value={v.digital_address} onChange={set("digital_address")} placeholder="GA-123-4567" /></Field>
      </div>
      <Field label="Directions / landmarks (optional)"><Textarea rows={2} value={v.directions} onChange={set("directions")} /></Field>
      {error && <Alert>{error}</Alert>}
      <div className="flex gap-2">
        <Button type="button" size="sm" onClick={save} loading={busy} disabled={!v.name || !v.city}>Save venue</Button>
        {onCancel && <Button type="button" size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>}
      </div>
    </div>
  );
}
