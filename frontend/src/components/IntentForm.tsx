"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";

// Inputs wear assumption-amber — user-provided text is unverified until the engine grounds it.
// docs/09 §2.4: "editable inputs" are an explicit amber use case.

type FormState = "idle" | "submitting" | "polling" | "done" | "error";

type JobStatusResponse = {
  job_id: string;
  status: "queued" | "processing" | "done" | "error";
  error?: string;
};

const POLL_INTERVAL_MS = 1000;
const MAX_POLL_ATTEMPTS = 600;   // 10 minutes at 1s/poll — a bound so a stuck job fails loudly instead of spinning forever

export function IntentForm() {
  const { session, loading: authLoading } = useAuth();
  const [brief, setBrief] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [formState, setFormState] = useState<FormState>("idle");
  const [report, setReport] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // A submit -> poll -> fetch-report chain can run for up to 10 minutes. If the user
  // navigates away mid-flight, this stops the loop from firing more requests and — more
  // importantly — stops it from calling setState on a component that's no longer mounted.
  const cancelledRef = useRef(false);
  useEffect(() => {
    // Undo React Strict Mode's dev-only synthetic mount -> cleanup -> mount: without
    // this reset, the cleanup below fires once during that double-invoke and leaves
    // cancelledRef permanently true, so every real poll silently no-ops forever
    // (issue #164).
    cancelledRef.current = false;
    return () => { cancelledRef.current = true; };
  }, []);

  async function pollUntilDone(jobId: string, token: string) {
    for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
      if (cancelledRef.current) return;
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      if (cancelledRef.current) return;
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/jobs/${jobId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`polling job status returned ${res.status}`);
      const status: JobStatusResponse = await res.json();
      if (status.status === "done") return;
      if (status.status === "error") throw new Error(status.error ?? "the pipeline failed");
      // still queued/processing — keep polling
    }
    throw new Error("timed out waiting for the design to finish (10 min) — the job may still be running server-side");
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!brief.trim() && !file) return;
    if (!session) return;   // form is gated on sign-in below; this is just a safety guard
    setFormState("submitting");
    setErrorMsg(null);

    try {
      const token = session.access_token;
      const formData = new FormData();
      if (brief.trim()) formData.append("text", brief.trim());
      if (file) formData.append("file", file);

      const submitRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/intent`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },   // no Content-Type — the browser sets the multipart boundary
        body: formData,
      });
      if (!submitRes.ok) {
        const detail = await submitRes.json().catch(() => null);
        throw new Error(detail?.detail ?? `submitting the intent returned ${submitRes.status}`);
      }
      const { job_id } = await submitRes.json();

      setFormState("polling");
      await pollUntilDone(job_id, token);
      if (cancelledRef.current) return;   // unmounted while polling — nothing left to update

      const reportRes = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/jobs/${job_id}/report?fmt=markdown`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!reportRes.ok) throw new Error(`fetching the report returned ${reportRes.status}`);
      const text = await reportRes.text();
      if (cancelledRef.current) return;
      setReport(text);
      setFormState("done");
    } catch (err) {
      if (cancelledRef.current) return;   // unmounted mid-request — don't touch state on the way out
      setErrorMsg(err instanceof Error ? err.message : "something went wrong");
      setFormState("error");
    }
  }

  function reset() {
    setBrief("");
    setFile(null);
    setReport(null);
    setErrorMsg(null);
    setFormState("idle");
    if (fileInputRef.current) fileInputRef.current.value = "";   // else re-selecting the same filename won't fire onChange
  }

  // Same honest-hold treatment as report/page.tsx while we check for an existing session.
  if (authLoading) {
    return (
      <p className="font-mono text-provenance uppercase tracking-widest text-ink-muted-strong">
        checking your session…
      </p>
    );
  }

  // The API rejects anonymous calls (#10) — send the person to sign in rather than
  // letting them submit into a guaranteed 401.
  if (!session) {
    return (
      <div className="border border-assumption-amber rounded-lg p-6 flex flex-col gap-3">
        <p className="font-mono text-provenance uppercase tracking-widest text-ink-muted-strong">
          sign in required
        </p>
        <p className="font-serif text-body text-slate-ink max-w-[60ch]">
          Designs are generated per signed-in user.{" "}
          <Link href="/auth" className="underline">Sign in</Link> to submit one.
        </p>
      </div>
    );
  }

  if (formState === "done" && report !== null) {
    return (
      <div className="flex flex-col gap-4">
        <p className="font-mono text-provenance text-ink-muted-strong">
          Brief: &ldquo;{brief || "(no text — file upload only)"}&rdquo;
          {file && ` · File: ${file.name}`}
        </p>
        <pre className="w-full max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-lg border border-mist bg-paper p-4 font-mono text-mono-data text-slate-ink">
          {report}
        </pre>
        <button
          onClick={reset}
          className="self-start font-sans text-label text-ink-muted-strong underline underline-offset-2 rounded-sm hover:text-slate-ink transition-colors ease-settle duration-ui focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue"
        >
          Start a new design
        </button>
      </div>
    );
  }

  if (formState === "error") {
    return (
      <div className="border border-assumption-amber rounded-lg p-6 flex flex-col gap-3">
        <p className="font-mono text-provenance uppercase tracking-widest text-ink-muted-strong">
          could not complete the design
        </p>
        <p className="font-serif text-body text-slate-ink max-w-[60ch]">{errorMsg}</p>
        <button
          onClick={reset}
          className="self-start font-sans text-label text-ink-muted-strong underline underline-offset-2 rounded-sm hover:text-slate-ink transition-colors ease-settle duration-ui focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue"
        >
          Start again
        </button>
      </div>
    );
  }

  const isBusy = formState === "submitting" || formState === "polling";

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">

      {/* Brief — text area, amber border signals user input is ASSUMPTION */}
      <div className="flex flex-col gap-2">
        <label
          htmlFor="brief"
          className="font-sans text-label uppercase tracking-widest text-ink-muted-strong"
        >
          Describe what you&apos;re building
        </label>
        <textarea
          id="brief"
          rows={5}
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="e.g. a URL shortener, ~10k req/s, mostly reads, Postgres + Redis"
          className="w-full rounded-lg border border-assumption-amber bg-paper text-slate-ink font-serif text-body px-4 py-3 placeholder:text-ink-muted-strong/60 resize-none transition-all ease-settle duration-ui focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-assumption-amber"
        />
        <p className="font-mono text-provenance text-ink-muted-strong">
          ASSUMPTION · everything you write is treated as unverified until the engine grounds it
        </p>
      </div>

      {/* File upload — optional, dashed amber border matches the input theme */}
      <div className="flex flex-col gap-2">
        <label className="font-sans text-label uppercase tracking-widest text-ink-muted-strong">
          Attach a document{" "}
          <span className="normal-case tracking-normal">(optional)</span>
        </label>
        {/* button not div — gets Tab focus + Enter/Space activation + screen reader announcement for free */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="w-full cursor-pointer rounded-lg border border-dashed border-assumption-amber px-4 py-6 text-center transition-all ease-settle duration-ui hover:bg-assumption-amber/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-assumption-amber"
        >
          {file ? (
            <p className="font-mono text-mono-data text-slate-ink">{file.name}</p>
          ) : (
            <p className="font-mono text-provenance text-ink-muted-strong">
              Click to attach a Markdown or text file
            </p>
          )}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".md,.txt"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={(!brief.trim() && !file) || isBusy}
        className="self-start font-sans text-label font-medium px-6 py-3 rounded-full bg-slate-ink text-paper transition-all ease-settle duration-ui hover:bg-graphite hover:shadow-sm active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
      >
        {formState === "submitting" ? "Sending…" : formState === "polling" ? "Designing…" : "Send to ingestion →"}
      </button>

    </form>
  );
}
