import Link from "next/link";

// Shared top nav — appears on every page via direct import (not layout.tsx,
// so individual pages can opt into a bare full-screen view later if needed).
export function Nav() {
  return (
    <nav className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 bg-slate-ink border-b border-steel">
      <Link
        href="/"
        className="font-sans font-semibold tracking-tight text-paper transition-colors ease-settle duration-ui hover:text-ink-muted"
      >
        keystone
      </Link>
      {/* Accuracy-ladder badge — docs/09 §3.6 */}
      <span className="font-mono text-provenance text-ink-muted border border-steel rounded px-2 py-px">
        L0 · Directional
      </span>
    </nav>
  );
}
