import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { CanvasEditor } from "@/components/CanvasEditor";

export const metadata: Metadata = {
  title: "keystone · canvas",
  description: "Draw a system, hit Simulate, get the engine's verdict back on the diagram.",
};

// Route: /canvas — the interactive editable canvas (issue #186). Unlike /design and /report,
// this page needs no auth: /simulate is a stateless calculator with no per-user data.
export default function CanvasPage() {
  return (
    <>
      <Nav />
      <CanvasEditor />
    </>
  );
}
