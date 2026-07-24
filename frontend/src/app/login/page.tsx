"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(formData: FormData) {
    setBusy(true);
    setError(null);
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        email: formData.get("email"),
        password: formData.get("password"),
      }),
    });
    setBusy(false);
    if (!response.ok) {
      setError("Invalid credentials");
      return;
    }
    const me = await response.json();
    router.replace(me.role === "platform_admin" ? "/admin"
      : me.role === "member" ? "/my" : "/");
    router.refresh();
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100">
      <form action={submit}
            className="w-88 space-y-4 rounded-xl border border-slate-200 bg-white p-8 shadow-md">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">
            NEXUS <span className="text-indigo-600">PM</span>
          </h1>
          <p className="mt-1 text-sm text-slate-500">Sign in to your portal</p>
        </div>
        <input name="email" type="email" required placeholder="Email" autoComplete="email"
               className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-2 focus:outline-indigo-200" />
        <input name="password" type="password" required placeholder="Password"
               autoComplete="current-password"
               className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-2 focus:outline-indigo-200" />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button disabled={busy}
                className="w-full rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:bg-indigo-300">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
