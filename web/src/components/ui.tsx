import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

export function cn(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

const btn = {
  primary: "bg-brand text-white hover:bg-brand-dark disabled:bg-zinc-300",
  secondary: "bg-white text-zinc-900 border border-zinc-300 hover:bg-zinc-50 disabled:text-zinc-400",
  danger: "bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300",
  ghost: "text-zinc-700 hover:bg-zinc-100",
};
const size = { sm: "px-3 py-1.5 text-sm", md: "px-4 py-2.5", lg: "px-6 py-3.5 text-lg" };

type BtnProps = { variant?: keyof typeof btn; size?: keyof typeof size; loading?: boolean };

export function Button({
  variant = "primary", size: s = "md", loading, className, children, disabled, ...rest
}: ComponentProps<"button"> & BtnProps) {
  return (
    <button
      className={cn("inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors disabled:cursor-not-allowed",
        btn[variant], size[s], className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}

export function ButtonLink({
  href, variant = "primary", size: s = "md", className, children,
}: { href: string; className?: string; children: ReactNode } & BtnProps) {
  return (
    <Link href={href} className={cn("inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors",
      btn[variant], size[s], className)}>
      {children}
    </Link>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span className={cn("inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent", className)}
      aria-label="Loading" />
  );
}

export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-zinc-800">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-zinc-500">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-red-600">{error}</span>}
    </label>
  );
}

const inputCls = "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-zinc-900 outline-none focus:border-brand focus:ring-2 focus:ring-brand/20 disabled:bg-zinc-100";

export function Input(props: ComponentProps<"input">) {
  return <input {...props} className={cn(inputCls, props.className)} />;
}
export function Textarea(props: ComponentProps<"textarea">) {
  return <textarea rows={4} {...props} className={cn(inputCls, props.className)} />;
}
export function Select(props: ComponentProps<"select">) {
  return <select {...props} className={cn(inputCls, "pr-8", props.className)} />;
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("rounded-xl border border-zinc-200 bg-white p-5", className)}>{children}</div>;
}

const badge = {
  green: "bg-emerald-100 text-emerald-800", yellow: "bg-amber-100 text-amber-800", red: "bg-red-100 text-red-800",
  gray: "bg-zinc-100 text-zinc-700", blue: "bg-sky-100 text-sky-800", brand: "bg-brand-light text-brand-dark",
};
export function Badge({ color = "gray", children }: { color?: keyof typeof badge; children: ReactNode }) {
  return <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold", badge[color])}>{children}</span>;
}

export function Alert({ kind = "error", children }: { kind?: "error" | "success" | "info"; children: ReactNode }) {
  const cls = { error: "bg-red-50 text-red-800 border-red-200", success: "bg-emerald-50 text-emerald-800 border-emerald-200",
    info: "bg-sky-50 text-sky-800 border-sky-200" }[kind];
  return <div role="alert" className={cn("rounded-lg border px-4 py-3 text-sm", cls)}>{children}</div>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-zinc-300 bg-white px-6 py-12 text-center">
      <p className="font-semibold text-zinc-800">{title}</p>
      {children && <div className="mt-2 text-sm text-zinc-500">{children}</div>}
    </div>
  );
}

export function PageLoader() {
  return <div className="flex justify-center py-24 text-brand"><Spinner className="h-8 w-8" /></div>;
}
