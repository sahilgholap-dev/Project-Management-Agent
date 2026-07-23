"use client";

// PRD s4 steps 1-2. The "invite" is credential GENERATION + on-screen display
// for manual handoff — this system sends nothing, by design (the backend's
// import allowlist makes sending structurally impossible). The button says
// "Generate credentials", never "Send invite".

import { useState } from "react";

async function post(path: string, body: unknown) {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof data?.detail === "string"
      ? data.detail : JSON.stringify(data?.detail));
  }
  return data;
}

export function AdminForms() {
  const [clientMessage, setClientMessage] = useState<string | null>(null);
  const [credentials, setCredentials] = useState<{
    email: string; password: string; handoff_note: string;
  } | null>(null);
  const [userError, setUserError] = useState<string | null>(null);

  return (
    <main className="space-y-8 text-sm">
      <section className="rounded border bg-white p-4">
        <h2 className="mb-3 font-semibold">1. Create the client company (once)</h2>
        <form
          action={async (fd) => {
            try {
              await post("/admin/clients", { name: fd.get("name") });
              setClientMessage(`✓ client "${fd.get("name")}" created`);
            } catch (err) {
              setClientMessage(`✖ ${(err as Error).message}`);
            }
          }}
          className="flex gap-2"
        >
          <input name="name" required placeholder="Client company name"
                 className="flex-1 rounded border px-3 py-2" />
          <button className="rounded bg-slate-800 px-4 py-2 text-white">Create</button>
        </form>
        {clientMessage && <p className="mt-2 text-xs">{clientMessage}</p>}
      </section>

      <section className="rounded border bg-white p-4">
        <h2 className="mb-1 font-semibold">2. Create a user</h2>
        <p className="mb-3 text-xs text-slate-500">
          Credentials are generated and shown once, below, for manual handoff.
          Nothing is emailed or sent — this system has no send capability.
        </p>
        <form
          action={async (fd) => {
            setUserError(null);
            setCredentials(null);
            try {
              setCredentials(await post("/admin/users", {
                email: fd.get("email"),
                display_name: fd.get("display_name"),
                role: fd.get("role"),
              }));
            } catch (err) {
              setUserError((err as Error).message);
            }
          }}
          className="space-y-2"
        >
          <div className="flex gap-2">
            <input name="email" type="email" required placeholder="Email"
                   className="flex-1 rounded border px-3 py-2" />
            <input name="display_name" required placeholder="Display name"
                   className="flex-1 rounded border px-3 py-2" />
            <select name="role" className="rounded border px-2 py-2">
              <option value="client_admin">client_admin</option>
              <option value="member">member</option>
            </select>
          </div>
          <button className="rounded bg-slate-800 px-4 py-2 text-white">
            Generate credentials
          </button>
        </form>
        {userError && <p className="mt-2 text-xs text-red-600">{userError}</p>}
        {credentials && (
          <div className="mt-3 rounded border border-amber-300 bg-amber-50 p-3 text-xs">
            <p className="font-semibold">
              Shown once — copy now and relay manually:
            </p>
            <p className="mt-1 font-mono">email: {credentials.email}</p>
            <p className="font-mono">password: {credentials.password}</p>
            <p className="mt-1 text-slate-600">{credentials.handoff_note}</p>
          </div>
        )}
      </section>
    </main>
  );
}
