import { SITE_NAME } from "@/lib/api";

export const metadata = { title: "Refund Policy" };
const UPDATED = "10 November 2026";

export default function Refunds() {
  return (
    <>
      <h1>Refund Policy</h1>
      <p className="text-sm text-zinc-500">Last updated {UPDATED}</p>

      <h2>If an event is cancelled</h2>
      <p>You get a <b>full refund, including the booking fee</b>, automatically. You don&apos;t need to do anything: we&apos;ll notify you by SMS or email.</p>

      <h2>If an event is postponed or changed</h2>
      <p>Your ticket stays valid for the new date. If you can&apos;t attend, refunds follow the organizer&apos;s policy below, or the organizer may offer refunds for the change.</p>

      <h2>If you can&apos;t attend</h2>
      <p>
        Each event shows its refund policy before you buy: <b>No refunds</b>, or refunds up to <b>1, 7 or 30 days</b> before
        the event. Within that window you can request a refund yourself from your order page (&ldquo;Manage order&rdquo; in
        your ticket email). You&apos;ll get the <b>ticket price back; the booking fee isn&apos;t refundable</b>. Used or
        transferred tickets can&apos;t be refunded.
      </p>
      <p>You can also send your ticket to a friend instead, if the organizer allows transfers.</p>

      <h2>How long refunds take</h2>
      <p>Money goes back to the Mobile Money wallet or card you paid with, usually within 1&ndash;5 working days after the refund is issued. Refunded tickets stop working at the gate.</p>

      <h2>Free tickets</h2>
      <p>Cancelling a free ticket simply releases your place.</p>

      <h2>Problems</h2>
      <p>If an event wasn&apos;t as described or you were refused entry with a valid ticket, contact the organizer first, then {SITE_NAME} support.</p>
    </>
  );
}
