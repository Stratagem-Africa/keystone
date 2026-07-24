import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { AuthPanel } from "@/components/AuthPanel";

export const metadata: Metadata = {
  title: "keystone · sign in",
  description: "Sign in or create a Keystone account.",
};

// Route: /auth — Epic 4.5, issue #19. A plain Server Component (keeps `metadata`
// working); all the session-dependent logic lives in the Client Component below.
export default function AuthPage() {
  return (
    <>
      <Nav />
      <main className="flex-1 bg-paper px-6 py-16">
        <div className="max-w-sm mx-auto flex flex-col gap-8">
          <div className="flex flex-col gap-3">
            <h1 className="font-sans text-h2 font-semibold tracking-tight text-slate-ink">
              Sign in
            </h1>
            <p className="font-serif text-body text-ink-muted">
              An account lets you save and revisit your designs.
            </p>
          </div>

          <AuthPanel />
        </div>
      </main>
    </>
  );
}
