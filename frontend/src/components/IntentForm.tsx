"use client";

import { useState, useRef } from "react";

// Inputs wear assumption-amber — user-provided text is unverified until the engine grounds it.
// docs/09 §2.4: "editable inputs" are an explicit amber use case.

type FormState = "idle" | "submitting" | "submitted";

export function IntentForm() {
  const [brief, setBrief] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [formState, setFormState] = useState<FormState>("idle");
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!brief.trim()) return;
    setFormState("submitting");
    // Stub: ingestion API not yet connected (Epic 3.3 / issue #10).
    await new Promise((r) => setTimeout(r, 800));
    setFormState("submitted");
  }

  if (formState === "submitted") {
    return (
      <div className="border border-assumption-amber rounded-lg p-6">
        <p className="font-mono text-provenance text-assumption-amber uppercase tracking-widest mb-3">
          ASSUMPTION · stub
        </p>
        <p className="font-serif text-body text-slate-ink">
          Intent received. The ingestion layer is not yet connected — your brief
          will route to the API in a future update.
        </p>
        <p className="font-mono text-provenance text-ink-muted mt-3">
          Brief: &ldquo;{brief}&rdquo;
          {file && ` · File: ${file.name}`}
        </p>
        <button
          onClick={() => { setBrief(""); setFile(null); setFormState("idle"); }}
          className="mt-4 font-sans text-label text-ink-muted underline underline-offset-2"
        >
          Start again
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">

      {/* Brief — text area, amber border signals user input is ASSUMPTION */}
      <div className="flex flex-col gap-2">
        <label
          htmlFor="brief"
          className="font-sans text-label uppercase tracking-widest text-ink-muted"
        >
          Describe what you&apos;re building
        </label>
        <textarea
          id="brief"
          rows={5}
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="e.g. a URL shortener, ~10k req/s, mostly reads, Postgres + Redis"
          required
          className="w-full rounded-lg border border-assumption-amber bg-paper text-slate-ink font-serif text-body px-4 py-3 placeholder:text-ink-muted/60 focus:outline-none focus:ring-2 focus:ring-assumption-amber resize-none transition-all ease-settle duration-ui"
        />
        <p className="font-mono text-provenance text-ink-muted">
          ASSUMPTION · everything you write is treated as unverified until the engine grounds it
        </p>
      </div>

      {/* File upload — optional, dashed amber border matches the input theme */}
      <div className="flex flex-col gap-2">
        <label className="font-sans text-label uppercase tracking-widest text-ink-muted">
          Attach a document{" "}
          <span className="normal-case tracking-normal">(optional)</span>
        </label>
        <div
          onClick={() => fileInputRef.current?.click()}
          className="cursor-pointer rounded-lg border border-dashed border-assumption-amber px-4 py-6 text-center transition-all ease-settle duration-ui hover:bg-assumption-amber/5"
        >
          {file ? (
            <p className="font-mono text-mono-data text-slate-ink">{file.name}</p>
          ) : (
            <p className="font-mono text-provenance text-ink-muted">
              Click to attach a PDF, Markdown, or text file
            </p>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.md,.txt"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={!brief.trim() || formState === "submitting"}
        className="self-start font-sans text-label font-medium px-6 py-3 rounded-full bg-slate-ink text-paper transition-all ease-settle duration-ui hover:bg-graphite disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {formState === "submitting" ? "Sending…" : "Describe what you’re building →"}
      </button>

    </form>
  );
}
