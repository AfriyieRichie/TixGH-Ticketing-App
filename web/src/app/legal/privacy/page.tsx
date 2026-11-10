import { SITE_NAME } from "@/lib/api";

export const metadata = { title: "Privacy Policy" };
const UPDATED = "10 November 2026";

export default function Privacy() {
  return (
    <>
      <h1>Privacy Policy</h1>
      <p className="text-sm text-zinc-500">Last updated {UPDATED}</p>
      <p>
        This policy explains what personal data {SITE_NAME} collects, why, and your rights under Ghana&apos;s Data
        Protection Act, 2012 (Act 843).
      </p>

      <h2>What we collect</h2>
      <ul>
        <li><b>Account and order details:</b> name, phone number, email, and what you bought.</li>
        <li><b>Badge details</b> (conference events only): organization and job title, if you give them.</li>
        <li><b>Payment information:</b> handled by Paystack. We receive a confirmation and the payment method type, never your card number or MoMo PIN.</li>
        <li><b>Check-in records:</b> when and at which gate your ticket was scanned.</li>
        <li><b>Technical data:</b> basic logs (e.g. IP address, device type) to keep the service secure.</li>
      </ul>

      <h2>How we use it</h2>
      <ul>
        <li>To sell and deliver your tickets (SMS, email), check you in, and handle refunds and support.</li>
        <li>To share your name, contact details and ticket information with <b>the organizer of the event you bought for</b>, so they can run the event and contact attendees about it.</li>
        <li>To send you marketing from an organizer <b>only if you follow them or tick the opt-in box</b>. Every marketing email has an unsubscribe link.</li>
        <li>To put your contact details on a conference badge QR code <b>only if you leave that option ticked</b> when registering.</li>
        <li>To prevent fraud and meet legal and accounting obligations.</li>
      </ul>

      <h2>Who we share it with</h2>
      <p>
        Event organizers (as above), and service providers who help us run {SITE_NAME}: payment (Paystack), SMS and email
        delivery, hosting and image storage. Some of these providers store data outside Ghana; we use reputable providers
        with appropriate safeguards. We don&apos;t sell your personal data.
      </p>

      <h2>How long we keep it</h2>
      <p>Order and payment records are kept as long as needed for accounting and legal purposes (typically up to 6 years). You can ask us to delete your account; we&apos;ll keep only what the law requires.</p>

      <h2>Your rights</h2>
      <p>You can ask to see, correct or delete your personal data, or object to marketing at any time. Contact us through the support details on our website.</p>

      <h2>Security</h2>
      <p>We use encryption in transit (HTTPS), signed QR codes, hashed one-time codes and access controls for organizer teams. No system is perfectly secure; tell us right away if you suspect misuse of your account.</p>
    </>
  );
}
