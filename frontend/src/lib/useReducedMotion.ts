import { useSyncExternalStore } from "react";

// Reduced-motion must be decided in REACT, not CSS (docs/09 §11.9).
// Two reasons, both learned the hard way:
//   1. Lightning CSS purges a custom class nested inside @media (prefers-reduced-motion: reduce),
//      and Tailwind v4 here does not emit the `motion-reduce:` variant for every utility — so a
//      CSS-only gate silently does nothing.
//   2. The global reduced-motion reset kills animation *duration*, which leaves an element parked
//      at its base style (no `forwards` fill) — a frozen packet mid-flight, which is noise.
// `useSyncExternalStore` (not useState + useEffect, which trips react-hooks/set-state-in-effect)
// with a server snapshot of `false` means SSR renders the motion path, matching the poster frame,
// with no hydration mismatch.
const QUERY = "(prefers-reduced-motion: reduce)";

export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia(QUERY);
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    },
    () => window.matchMedia(QUERY).matches,
    () => false,
  );
}
