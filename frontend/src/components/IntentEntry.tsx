"use client";

import { useEffect, useState } from "react";
import { IntentForm, type IntentMode } from "@/components/IntentForm";
import { fetchLocalStatus, type LocalStatus } from "@/lib/localAi";

// Picks how /design runs the full pipeline (#204). If the API says this browser is the person at the
// machine running Keystone (GET /local/status), the form runs on /local/* with no sign-in and your
// own Claude. Otherwise it is the signed-in pipeline, unchanged.
const API = process.env.NEXT_PUBLIC_API_URL;

export function IntentEntry() {
  // undefined = still asking; null = no local AI here (or no API address baked in at build time)
  const [status, setStatus] = useState<LocalStatus | null | undefined>(API ? undefined : null);

  useEffect(() => {
    if (!API) return;
    const controller = new AbortController();
    void fetchLocalStatus(API, controller.signal).then((s) => {
      if (!controller.signal.aborted) setStatus(s);
    });
    return () => controller.abort();
  }, []);

  if (status === undefined) {
    return (
      <p className="font-mono text-provenance uppercase tracking-widest text-ink-muted-strong">
        checking how Keystone is running…
      </p>
    );
  }

  const mode: IntentMode = status?.available ? "local" : "account";
  return (
    <div className="flex flex-col gap-6">
      {mode === "local" && status && (
        <p className="font-mono text-provenance text-ink-muted-strong max-w-[70ch]">
          LOCAL · running on this machine with your own AI (design: {status.ingest_provider} · decisions:{" "}
          {status.council_provider}) · no sign-in, nothing saved to an account
        </p>
      )}
      <IntentForm mode={mode} />
    </div>
  );
}
