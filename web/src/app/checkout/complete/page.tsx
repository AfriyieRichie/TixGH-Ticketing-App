"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { QRCodeSVG } from "qrcode.react";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Alert, Button, ButtonLink, PageLoader } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import { orderToken, useAuth } from "@/lib/auth";
import { cedis, eventDate } from "@/lib/format";
import type { Order } from "@/lib/types";

export default function Page() {
  return <Suspense fallback={<PageLoader />}><CheckoutComplete /></Suspense>;
}

function CheckoutComplete() {
  const params = useSearchParams();
  const reference = (params.get("reference") ?? "").toUpperCase();
  const { request, ready } = useAuth();
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState("");
  const [tries, setTries] = useState(0);

  const verify = useCallback(async () => {
    const token = params.get("token") ?? orderToken(reference);
    const q = token ? `?token=${encodeURIComponent(token)}` : "";
    try {
      // Signed-in buyers are recognised by their account; guests by the token saved at checkout.
      const o = token
        ? await apiFetch<Order>(`/orders/${reference}/verify/${q}`, { method: "POST" })
        : await request<Order>(`/orders/${reference}/verify/`, { method: "POST" });
      setOrder(o);
      setError("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setError("We couldn't find this order on this device. Check your SMS or email for your tickets.");
        return;
      }
      // Confirmation can be slow (e.g. a server waking up). The order may
      // already be paid via Paystack's webhook, so show its current state.
      try {
        const o = token
          ? await apiFetch<Order>(`/orders/${reference}/${q}`)
          : await request<Order>(`/orders/${reference}/`);
        setOrder(o);
        setError("");
      } catch {
        setError("We couldn't confirm your payment yet.");
      }
    }
  }, [params, reference, request]);

  useEffect(() => {
    if (ready && reference) verify();
  }, [ready, reference, verify]);

  // Mobile Money approvals can take a little while: poll a few times.
  useEffect(() => {
    if (order?.status === "pending" && tries < 10) {
      const t = setTimeout(() => { setTries((n) => n + 1); verify(); }, 4000);
      return () => clearTimeout(t);
    }
  }, [order, tries, verify]);

  if (!reference) return <Centered><Alert>Missing order reference.</Alert></Centered>;
  if (error && !order) return <Centered><Alert>{error}</Alert><Button className="mt-4" onClick={verify}>Try again</Button></Centered>;
  if (!order) return <PageLoader />;

  if (order.status === "pending") {
    return (
      <Centered>
        <div className="text-5xl">⏳</div>
        <h1 className="mt-4 text-2xl font-bold">Waiting for your payment</h1>
        <p className="mt-2 text-zinc-600">If you paid with Mobile Money, approve the prompt on your phone. This page updates automatically.</p>
        <p className="mt-2 text-sm text-zinc-500">Your tickets are held for another {Math.ceil(order.seconds_left / 60)} min.</p>
        {order.payment?.authorization_url && tries >= 3 && (
          <ButtonLink href={order.payment.authorization_url} variant="secondary" className="mt-6">Return to payment page</ButtonLink>
        )}
      </Centered>
    );
  }
  if (order.status !== "paid") {
    const msg = {
      expired: "This order expired before payment was completed. The tickets have been released.",
      failed: "The payment didn't go through. No money was taken.",
      needs_review: "We received your payment and our team is reviewing your order. We'll contact you shortly.",
    }[order.status as string] ?? `This order is ${order.status}.`;
    return (
      <Centered>
        <Alert kind={order.status === "needs_review" ? "info" : "error"}>{msg}</Alert>
        <ButtonLink href={`/e/${order.event.slug}`} className="mt-6">Back to event</ButtonLink>
      </Centered>
    );
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <div className="text-center">
        <div className="text-5xl">🎉</div>
        <h1 className="mt-3 text-3xl font-extrabold">You&apos;re going!</h1>
        <p className="mt-2 text-zinc-600">
          We&apos;ve sent your tickets {order.buyer_phone && <>by SMS to <b>{order.buyer_phone}</b></>}
          {order.buyer_phone && order.buyer_email && " and "}
          {order.buyer_email && <>by email to <b>{order.buyer_email}</b></>}.
        </p>
      </div>

      <div className="mt-8 rounded-xl border border-zinc-200 bg-white p-5">
        <h2 className="text-xl font-bold">{order.event.title}</h2>
        <p className="text-zinc-600">{eventDate(order.event.start_at, { year: true })}{order.event.venue_name && ` · ${order.event.venue_name}, ${order.event.venue_city}`}</p>
        <p className="mt-2 text-sm text-zinc-500">Order {order.reference} · Paid {cedis(order.total)}</p>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {order.tickets.map((t) => (
          <div key={t.code} className="rounded-xl border border-zinc-200 bg-white p-5 text-center">
            <p className="font-bold">{t.ticket_type_name}</p>
            {t.qr_payload ? (
              <div className="mx-auto my-3 w-fit rounded-lg bg-white p-2"><QRCodeSVG value={t.qr_payload} size={180} level="M" /></div>
            ) : <p className="my-6 text-sm text-zinc-500">{t.transferred ? "Sent to someone else" : t.status}</p>}
            <p className="font-mono text-lg font-bold tracking-widest">{t.code}</p>
          </div>
        ))}
      </div>

      <RefundBox reference={order.reference} token={params.get("token") ?? orderToken(reference)} onDone={verify} />

      {Number(order.refunded_amount) > 0 && (
        <p className="mt-4 text-center text-sm text-zinc-600">Refunded so far: {cedis(order.refunded_amount)}</p>
      )}
      {order.links && (
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          <ButtonLink href={order.links.tickets_page} variant="secondary">Open ticket page</ButtonLink>
          <ButtonLink href={order.links.pdf} variant="secondary">Download PDF</ButtonLink>
          <ButtonLink href={order.links.whatsapp_share} variant="secondary">Share on WhatsApp</ButtonLink>
        </div>
      )}
      <p className="mt-6 text-center text-sm text-zinc-500">
        Tip: screenshot your QR codes in case there&apos;s no network at the venue.{" "}
        <Link href="/login?next=/tickets" className="font-semibold text-brand">Sign in</Link> with the same phone number to keep all your tickets in one place.
      </p>
    </main>
  );
}

type Quote = { eligible: boolean; reason: string; deadline: string | null; amount: string; tickets: string[] };

function RefundBox({ reference, token, onDone }: { reference: string; token: string | null; onDone: () => void }) {
  const { request } = useAuth();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const q = token ? `?token=${encodeURIComponent(token)}` : "";
  const call = useCallback(<T,>(method?: string) => token
    ? apiFetch<T>(`/orders/${reference}/refund/${q}`, method ? { method } : {})
    : request<T>(`/orders/${reference}/refund/`, method ? { method } : {}), [token, reference, q, request]);

  useEffect(() => { call<Quote>().then(setQuote).catch(() => {}); }, [call]);
  if (!quote || (!quote.eligible && !msg)) return null;

  async function go() {
    if (!confirm(`Refund ${quote!.tickets.length} ticket(s) for ${cedis(quote!.amount)}? Your tickets will stop working.`)) return;
    setBusy(true);
    try {
      const r = await call<{ amount: string }>("POST");
      setMsg(`Refund of ${cedis(r.amount)} is on its way to your MoMo wallet or card (usually 1-5 working days).`);
      setQuote({ ...quote!, eligible: false });
      onDone();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Refund failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mt-6 rounded-xl border border-zinc-200 bg-white p-5 text-sm">
      {msg ? <p className="font-semibold text-emerald-700">{msg}</p> : (
        <>
          <p className="font-semibold">Can&apos;t make it?</p>
          <p className="mt-1 text-zinc-600">
            You can get {cedis(quote.amount)} back for unused tickets
            {quote.deadline ? ` until ${eventDate(quote.deadline)}` : ""}. The booking fee isn&apos;t refundable.
          </p>
          <Button variant="secondary" size="sm" className="mt-3" loading={busy} onClick={go}>Request a refund</Button>
        </>
      )}
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <main className="mx-auto max-w-md px-4 py-20 text-center">{children}</main>;
}
