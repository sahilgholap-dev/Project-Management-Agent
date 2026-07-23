"use client";

// OQ-5 (approved): manual refresh only — no polling. With a single tester,
// items appearing mid-inspection obscure the cause-effect timeline.

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export function RefreshBar() {
  const router = useRouter();
  // set only after mount: a render-time timestamp differs between server
  // and client (clock tick + locale formatting) and breaks hydration
  const [last, setLast] = useState<string | null>(null);
  useEffect(() => setLast(new Date().toLocaleTimeString()), []);
  return (
    <div className="flex items-center gap-2 text-xs text-slate-500">
      <span>{last ? `last refreshed ${last}` : " "}</span>
      <button
        className="rounded border px-3 py-1.5 hover:bg-slate-100"
        onClick={() => {
          router.refresh();
          setLast(new Date().toLocaleTimeString());
        }}
      >
        Refresh
      </button>
    </div>
  );
}
