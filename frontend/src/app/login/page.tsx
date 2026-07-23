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
    router.replace(me.role === "platform_admin" ? "/admin" : "/");
    router.refresh();
  }

  return (
    <main className="flex min-h-screen items-center justify-center">
      <form action={submit} className="w-80 space-y-4 rounded border bg-white p-6 shadow-sm">
        <h1 className="text-lg font-semibold">NEXUS PM Agent</h1>
        <input name="email" type="email" required placeholder="Email"
               className="w-full rounded border px-3 py-2 text-sm" />
        <input name="password" type="password" required placeholder="Password"
               className="w-full rounded border px-3 py-2 text-sm" />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button disabled={busy}
                className="w-full rounded bg-slate-800 px-3 py-2 text-sm text-white disabled:opacity-50">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
