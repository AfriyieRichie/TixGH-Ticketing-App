import { SITE_NAME } from "@/lib/api";

export const metadata = { title: "Terms of Service" };
const UPDATED = "10 November 2026";

export default function Terms() {
  return (
    <>
      <h1>Terms of Service</h1>
      <p className="text-sm text-zinc-500">Last updated {UPDATED}</p>
      <p>
        These terms apply to everyone who uses {SITE_NAME} (&ldquo;we&rdquo;, &ldquo;us&rdquo;): people who buy tickets
        (&ldquo;buyers&rdquo;) and people who sell them (&ldquo;organizers&rdquo;). By using the website, apps or buying
        a ticket you agree to them.
      </p>

      <h2>1. What we do</h2>
      <p>
        {SITE_NAME} is a ticketing platform. Organizers list their events and sell tickets through us; we process the
        payment, deliver tickets and provide check-in tools. <b>The organizer, not {SITE_NAME}, runs the event</b> and is
        responsible for it happening as described, for the venue, safety, line-up and any age or entry rules.
      </p>

      <h2>2. Buying tickets</h2>
      <ul>
        <li>Prices are in Ghana cedis (GHS). A booking fee may be added to paid tickets and is shown before you pay.</li>
        <li>Payments are processed by our payment partner (Paystack) by Mobile Money or card. We never see or store your card details.</li>
        <li>Unpaid orders hold tickets for a short time (about 10 minutes) and are then released.</li>
        <li>Each ticket&apos;s QR code admits its holder once (or as stated for re-entry events). Don&apos;t share or post your QR code: the first scan gets in.</li>
        <li>Tickets transferred to someone else get a new code; the old one stops working.</li>
        <li>Reselling tickets above face value may be restricted by the organizer, and tickets obtained fraudulently may be cancelled without refund.</li>
      </ul>

      <h2>3. Refunds</h2>
      <p>See our <a href="/legal/refunds" className="text-brand underline">Refund Policy</a>. In short: if an event is cancelled you get a full refund; otherwise refunds depend on the organizer&apos;s policy shown on the event page, and the booking fee isn&apos;t refundable.</p>

      <h2>4. Organizers</h2>
      <ul>
        <li>You must give accurate information about yourself and your events and have the right to hold and sell them.</li>
        <li>You agree to the fees shown in your dashboard. Ticket revenue is paid to your payout account through our payment partner, minus any fees and refunds.</li>
        <li>You&apos;re responsible for delivering the event, honouring your stated refund policy, and for refunds if you cancel.</li>
        <li>Marketing emails may only be sent to people who followed you or opted in, through our tools, and must respect unsubscribes.</li>
        <li>We may suspend events or accounts that are fraudulent, unlawful, misleading or that put buyers at risk, and may withhold payouts while we investigate.</li>
      </ul>

      <h2>5. Acceptable use</h2>
      <p>Don&apos;t misuse the platform: no fraud, fake listings, scraping, attempts to break security, abusive reviews or content you don&apos;t have rights to.</p>

      <h2>6. Liability</h2>
      <p>
        To the extent the law allows, {SITE_NAME} isn&apos;t liable for the conduct of organizers or attendees, or for losses
        arising from an event itself. Our total liability to a buyer for a ticket is limited to the amount paid for it.
        Nothing here limits rights you have under Ghanaian consumer protection law.
      </p>

      <h2>7. Changes and contact</h2>
      <p>We may update these terms; the date above shows the latest version. Questions: contact us through the support details on our website.</p>
      <p>These terms are governed by the laws of the Republic of Ghana.</p>
    </>
  );
}
