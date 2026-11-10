"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Alert, Button, Field, Input } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import { storedRef } from "@/components/growth/RefTracker";
import { rememberOrder, useAuth } from "@/lib/auth";
import { cedis, eventDate } from "@/lib/format";
import type { EventDetail, Order, Pricing, PublicTicketType } from "@/lib/types";

type PromoResult = {
  code: string;
  ticket_types: { id: number; name: string; hidden: boolean; sale_status: string; original: Pricing; discounted: Pricing }[];
};

const STATUS_LABEL: Record<string, string> = {
  scheduled: "Not on sale yet", ended: "Sales ended", sold_out: "Sold out", unavailable: "Unavailable",
};

export function TicketSelector({ event }: { event: EventDetail }) {
  const { user, request } = useAuth();
  const router = useRouter();
  const [qty, setQty] = useState<Record<number, number>>({});
  const [promoInput, setPromoInput] = useState("");
  const [promo, setPromo] = useState<PromoResult | null>(null);
  const [promoError, setPromoError] = useState("");
  const [step, setStep] = useState<"select" | "details">("select");
  const [buyer, setBuyer] = useState({ full_name: "", phone: "", email: "", organization: "", job_title: "",
    share_contact: event.badge_contact_default, marketing_opt_in: false });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) setBuyer((b) => ({
      ...b,
      full_name: b.full_name || user.full_name, phone: b.phone || user.phone || "", email: b.email || user.email || "",
    }));
  }, [user]);

  // Visible types, plus hidden ones unlocked by an access code.
  const types: (PublicTicketType & { hidden?: boolean })[] = useMemo(() => {
    const list: (PublicTicketType & { hidden?: boolean })[] = [...event.ticket_types];
    for (const p of promo?.ticket_types ?? []) {
      if (p.hidden && !list.some((t) => t.id === p.id)) {
        list.push({ id: p.id, name: p.name, description: "Unlocked with your code", admits: 1, min_per_order: 1,
          max_per_order: 10, sales_start_at: null, sales_end_at: null, sale_status: p.sale_status as PublicTicketType["sale_status"],
          pricing: p.original, remaining: null, hidden: true });
      }
    }
    return list;
  }, [event.ticket_types, promo]);

  const pricingFor = (id: number, base: Pricing) => promo?.ticket_types.find((p) => p.id === id)?.discounted ?? base;
  const lines = types.filter((t) => (qty[t.id] ?? 0) > 0).map((t) => ({ t, n: qty[t.id], p: pricingFor(t.id, t.pricing) }));
  const count = lines.reduce((s, l) => s + l.n, 0);
  const subtotal = lines.reduce((s, l) => s + Number(l.p.price) * l.n, 0);
  const fees = lines.reduce((s, l) => s + (l.p.fee_bearer === "buyer" ? Number(l.p.fee) : 0) * l.n, 0);
  const total = lines.reduce((s, l) => s + Number(l.p.buyer_pays) * l.n, 0);

  const set = (t: PublicTicketType, n: number) => {
    const max = Math.min(t.max_per_order, t.remaining ?? Infinity, event.max_tickets_per_order - count + (qty[t.id] ?? 0));
    const cur = qty[t.id] ?? 0;
    // Going below the minimum clears the line; going up jumps straight to the minimum.
    const next = n <= 0 || (n < cur && n < t.min_per_order) ? 0 : Math.max(Math.min(n, max), t.min_per_order);
    setQty({ ...qty, [t.id]: next });
  };

  async function applyPromo() {
    setPromoError("");
    try {
      setPromo(await apiFetch<PromoResult>(`/events/${event.slug}/promo-check/`, { body: { code: promoInput } }));
    } catch (e) {
      setPromo(null);
      setPromoError(e instanceof Error ? e.message : "Invalid code");
    }
  }

  async function checkout() {
    setBusy(true);
    setError("");
    try {
      const order = await request<Order>("/checkout/", {
        body: {
          event: event.slug,
          items: lines.map((l) => ({ ticket_type: l.t.id, quantity: l.n })),
          promo_code: promo?.code ?? "",
          ref: storedRef(event.slug),
          buyer,
        },
      });
      rememberOrder(order.reference, order.access_token);
      if (order.status === "paid") router.push(`/checkout/complete?reference=${order.reference}`);
      else if (order.payment?.authorization_url) window.location.href = order.payment.authorization_url;
      else setError("We couldn't start the payment. Please try again.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Network error. Check your connection and try again.");
      setBusy(false);
    }
  }

  if (event.status === "cancelled" || event.has_ended) {
    return <Box><p className="font-semibold">{event.has_ended ? "This event has ended." : "This event was cancelled."}</p></Box>;
  }

  return (
    <Box>
      {step === "select" ? (
        <>
          <h2 className="text-lg font-bold">Tickets</h2>
          <div className="mt-3 divide-y divide-zinc-100">
            {types.map((t) => {
              const p = pricingFor(t.id, t.pricing);
              const discounted = p.price !== t.pricing.price;
              const onSale = t.sale_status === "on_sale";
              return (
                <div key={t.id} className="flex items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">{t.name}{t.hidden && " 🔓"}</p>
                    <p className="text-sm">
                      {Number(p.buyer_pays) === 0 ? <b>Free</b> : <b>{cedis(p.buyer_pays)}</b>}
                      {discounted && <s className="ml-2 text-zinc-400">{cedis(t.pricing.buyer_pays)}</s>}
                      {t.admits > 1 && <span className="text-zinc-500"> · admits {t.admits}</span>}
                    </p>
                    {t.description && <p className="text-xs text-zinc-500">{t.description}</p>}
                    {t.remaining !== null && onSale && <p className="text-xs font-semibold text-amber-700">Only {t.remaining} left</p>}
                    {t.sale_status === "scheduled" && t.sales_start_at && (
                      <p className="text-xs text-zinc-500">On sale {eventDate(t.sales_start_at)}</p>
                    )}
                  </div>
                  {onSale ? (
                    <div className="flex items-center gap-2">
                      <Step onClick={() => set(t, (qty[t.id] ?? 0) - 1)} disabled={!qty[t.id]}>−</Step>
                      <span className="w-6 text-center font-semibold">{qty[t.id] ?? 0}</span>
                      <Step onClick={() => set(t, (qty[t.id] ?? 0) + 1)}>+</Step>
                    </div>
                  ) : <span className="text-sm font-medium text-zinc-500">{STATUS_LABEL[t.sale_status]}</span>}
                </div>
              );
            })}
          </div>
          <div className="mt-2 flex gap-2">
            <Input placeholder="Promo or access code" value={promoInput} onChange={(e) => setPromoInput(e.target.value.toUpperCase())}
              className="py-2 text-sm uppercase" />
            <Button variant="secondary" size="sm" onClick={applyPromo} disabled={!promoInput}>Apply</Button>
          </div>
          {promoError && <p className="mt-1 text-xs text-red-600">{promoError}</p>}
          {promo && <p className="mt-1 text-xs font-semibold text-emerald-700">Code {promo.code} applied ✓</p>}
          <Summary subtotal={subtotal} fees={fees} total={total} />
          <Button className="mt-4 w-full" size="lg" disabled={!count} onClick={() => setStep("details")}>
            {count ? `Continue · ${count} ticket${count > 1 ? "s" : ""}` : "Select tickets"}
          </Button>
        </>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); checkout(); }} className="space-y-3">
          <button type="button" onClick={() => setStep("select")} className="text-sm font-semibold text-brand">← Change tickets</button>
          <h2 className="text-lg font-bold">Your details</h2>
          <Field label="Full name"><Input required value={buyer.full_name} onChange={(e) => setBuyer({ ...buyer, full_name: e.target.value })} autoComplete="name" /></Field>
          <Field label="Phone number" hint="We'll send your tickets here by SMS">
            <Input type="tel" inputMode="tel" placeholder="024 123 4567" value={buyer.phone}
              onChange={(e) => setBuyer({ ...buyer, phone: e.target.value })} required={!buyer.email} autoComplete="tel" />
          </Field>
          <Field label="Email (optional)" hint="For a receipt and PDF tickets">
            <Input type="email" value={buyer.email} onChange={(e) => setBuyer({ ...buyer, email: e.target.value })} autoComplete="email" />
          </Field>
          {event.badges_enabled && (
            <div className="space-y-3 rounded-lg bg-zinc-50 p-3">
              <p className="text-sm font-semibold">For your name badge</p>
              <Field label="Organization (optional)"><Input value={buyer.organization} onChange={(e) => setBuyer({ ...buyer, organization: e.target.value })} autoComplete="organization" /></Field>
              <Field label="Job title (optional)"><Input value={buyer.job_title} onChange={(e) => setBuyer({ ...buyer, job_title: e.target.value })} autoComplete="organization-title" /></Field>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-0.5 h-4 w-4 accent-brand" checked={buyer.share_contact}
                  onChange={(e) => setBuyer({ ...buyer, share_contact: e.target.checked })} />
                <span>Put my contact (phone and email) on my badge QR so people I meet can save it</span>
              </label>
            </div>
          )}
          <label className="flex items-start gap-2 text-sm text-zinc-700">
            <input type="checkbox" className="mt-0.5 h-4 w-4 accent-brand" checked={buyer.marketing_opt_in}
              onChange={(e) => setBuyer({ ...buyer, marketing_opt_in: e.target.checked })} />
            <span>Email me about future events from {event.organizer.name}</span>
          </label>
          <Summary subtotal={subtotal} fees={fees} total={total} lines={lines.map((l) => `${l.n} × ${l.t.name}`)} />
          {error && <Alert>{error}</Alert>}
          <Button type="submit" className="w-full" size="lg" loading={busy}>
            {total === 0 ? "Get tickets" : `Pay ${cedis(total)}`}
          </Button>
          {total > 0 && <p className="text-center text-xs text-zinc-500">Mobile Money (MTN, Telecel, AT) or card. Tickets are held for 10 minutes.</p>}
          <p className="text-center text-xs text-zinc-500">
            By continuing you agree to our <a href="/legal/terms" target="_blank" className="underline">Terms</a> and{" "}
            <a href="/legal/refunds" target="_blank" className="underline">Refund Policy</a>.
          </p>
        </form>
      )}
    </Box>
  );
}

function Box({ children }: { children: React.ReactNode }) {
  return <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">{children}</div>;
}

function Step({ children, ...rest }: React.ComponentProps<"button">) {
  return (
    <button type="button" {...rest}
      className="grid h-9 w-9 place-items-center rounded-full border border-zinc-300 text-lg font-bold hover:border-brand hover:text-brand disabled:opacity-30">
      {children}
    </button>
  );
}

function Summary({ subtotal, fees, total, lines }: { subtotal: number; fees: number; total: number; lines?: string[] }) {
  if (!total && !subtotal) return null;
  return (
    <div className="mt-4 space-y-1 border-t border-zinc-100 pt-3 text-sm">
      {lines?.map((l) => <p key={l} className="text-zinc-600">{l}</p>)}
      <Row label="Tickets" value={cedis(subtotal)} />
      {fees > 0 && <Row label="Booking fee" value={cedis(fees)} />}
      <Row label="Total" value={cedis(total)} bold />
    </div>
  );
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className={`flex justify-between ${bold ? "pt-1 text-base font-bold" : "text-zinc-600"}`}>
      <span>{label}</span><span>{value}</span>
    </div>
  );
}
