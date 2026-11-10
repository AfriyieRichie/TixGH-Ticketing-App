import Link from "next/link";

const PAGES = [
  { href: "/legal/terms", label: "Terms of Service" },
  { href: "/legal/privacy", label: "Privacy Policy" },
  { href: "/legal/refunds", label: "Refund Policy" },
];

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <nav className="mb-8 flex flex-wrap gap-4 text-sm">
        {PAGES.map((p) => <Link key={p.href} href={p.href} className="font-semibold text-brand hover:underline">{p.label}</Link>)}
      </nav>
      <article className="space-y-4 leading-relaxed text-zinc-700 [&_h1]:text-3xl [&_h1]:font-extrabold [&_h1]:text-zinc-900 [&_h2]:mt-8 [&_h2]:text-xl [&_h2]:font-bold [&_h2]:text-zinc-900 [&_li]:ml-5 [&_li]:list-disc">
        {children}
      </article>
    </main>
  );
}
