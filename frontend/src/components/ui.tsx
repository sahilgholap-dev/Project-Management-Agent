// Shared UI primitives — the single place the design language lives.
// Server-component safe (no hooks); interactive widgets stay in feature
// components and compose these.

import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

// ---- buttons ---------------------------------------------------------------

const BUTTON_VARIANTS = {
  primary:
    "bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-indigo-300",
  secondary:
    "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-400",
  danger:
    "border border-red-200 bg-white text-red-600 hover:bg-red-50 disabled:text-red-300",
  ghost: "text-slate-500 hover:bg-slate-100 hover:text-slate-800",
} as const;

export type ButtonVariant = keyof typeof BUTTON_VARIANTS;

export function buttonCls(variant: ButtonVariant = "primary", small = false) {
  return cx(
    "inline-flex items-center justify-center gap-1.5 rounded-md font-medium",
    "transition-colors focus-visible:outline-2 focus-visible:outline-indigo-500",
    "disabled:cursor-not-allowed",
    small ? "px-2.5 py-1 text-xs" : "px-3.5 py-2 text-sm",
    BUTTON_VARIANTS[variant],
  );
}

export function Button({
  variant = "primary",
  small = false,
  className,
  ...props
}: ComponentProps<"button"> & { variant?: ButtonVariant; small?: boolean }) {
  return (
    <button {...props} className={cx(buttonCls(variant, small), className)} />
  );
}

// ---- form fields -----------------------------------------------------------

export const inputCls =
  "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm " +
  "text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 " +
  "focus:outline-2 focus:outline-indigo-200 disabled:bg-slate-50";

export const labelCls = "block space-y-1 text-xs font-medium text-slate-600";

export function Field({ label, children, className }: {
  label: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cx(labelCls, className)}>
      <span>{label}</span>
      {children}
    </label>
  );
}

// ---- surfaces --------------------------------------------------------------

export function Card({ title, description, actions, children, className }: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cx(
      "rounded-lg border border-slate-200 bg-white shadow-sm", className,
    )}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
            {description && (
              <p className="mt-0.5 text-xs text-slate-500">{description}</p>
            )}
          </div>
          {actions}
        </header>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

export function PageHeader({ title, description, actions }: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">
          {title}
        </h1>
        {description && (
          <p className="mt-1 text-sm text-slate-500">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
      {children}
    </p>
  );
}

// ---- tables ----------------------------------------------------------------

export function Table({ headers, children }: {
  headers: ReactNode[];
  children: ReactNode;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50">
            {headers.map((h, i) => (
              <th key={i} className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">{children}</tbody>
      </table>
    </div>
  );
}

export function Td({ className, ...props }: ComponentProps<"td">) {
  return <td {...props} className={cx("px-4 py-2.5 align-middle", className)} />;
}

export function TdLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Td>
      <Link href={href} className="font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
        {children}
      </Link>
    </Td>
  );
}

// ---- badges ----------------------------------------------------------------

const BADGE_TONES = {
  neutral: "bg-slate-100 text-slate-700",
  info: "bg-indigo-50 text-indigo-700",
  success: "bg-emerald-50 text-emerald-700",
  warning: "bg-amber-50 text-amber-700",
  danger: "bg-red-50 text-red-700",
} as const;

export type BadgeTone = keyof typeof BADGE_TONES;

export function Badge({ tone = "neutral", children }: {
  tone?: BadgeTone;
  children: ReactNode;
}) {
  return (
    <span className={cx(
      "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
      BADGE_TONES[tone],
    )}>
      {children}
    </span>
  );
}

export function statusTone(status: string): BadgeTone {
  if (["active", "done", "resolved", "approved", "completed", "closed"].includes(status)) return "success";
  if (["invited", "pending", "in_progress", "paused"].includes(status)) return "warning";
  if (["disabled", "blocked", "rejected", "halted", "overdue"].includes(status)) return "danger";
  return "neutral";
}

// ---- inline alerts ----------------------------------------------------------

export function Alert({ tone = "danger", title, children }: {
  tone?: "danger" | "warning" | "success";
  title?: ReactNode;
  children: ReactNode;
}) {
  const tones = {
    danger: "border-red-200 bg-red-50 text-red-800",
    warning: "border-amber-300 bg-amber-50 text-amber-800",
    success: "border-emerald-200 bg-emerald-50 text-emerald-800",
  } as const;
  return (
    <div className={cx("rounded-md border p-3 text-xs", tones[tone])}>
      {title && <p className="mb-1 font-semibold">{title}</p>}
      {children}
    </div>
  );
}
