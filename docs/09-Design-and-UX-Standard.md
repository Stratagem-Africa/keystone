# Keystone — Design, UX & Storytelling Standard

**Document:** `docs/09-Design-and-UX-Standard.md`
**Owner:** Design system (Jem, builder) · ratified against the Accuracy & Trust Charter (`03-Accuracy-and-Trust-Charter.md`)
**Status:** Definitive. This is the spine. Read the [Fixed vs. Latitude](#11-fixed-vs-latitude-the-contract-with-jem) contract before you touch a token.

---

## 0. How to read this document

This standard synthesizes the winning design direction (**trust-hero**) and grafts the strongest moves the judges flagged from the three runners-up. It is opinionated on purpose: Keystone's credibility *is* the product, so the design system is not decoration over a tool — it is the mechanism by which the trust thesis becomes physically true on screen.

There are three kinds of statements here:

- **MUST / NEVER** — load-bearing law. Violating one breaks the trust thesis. These are lint-gated where possible (Section 11).
- **SHOULD** — strong default. Deviate only with a recorded reason.
- **LATITUDE** — explicitly handed to Jem. Make it beautiful; the standard will not second-guess you here.

If two rules ever appear to conflict, the tiebreak order is fixed: **honesty > clarity > speed > craft.** Aesthetics never win against the first three. A beautiful screen that overstates confidence is a defect, not a polish item.

---

## 1. North Star

> **Keystone is the architecture tool that is afraid of being wrong in public — so it shows you exactly where it might be, before you ask.**

We are not selling "AI that designs your system." Everyone will claim that within a year, and it sounds like a toy. We are selling **a second opinion you can audit**: a grounded council of AI architects designs your system, defends every decision on the record, and a *deterministic engine* proves the numbers — each one shipped with its assumptions, a confidence band, and a "where this is wrong" section.

The ambition: **the most beautiful honest object on the internet.** When an engineer screenshots a Keystone report, the thing that spreads is not a flashy number — it is a *credible* one, visibly wearing its uncertainty, and looking better for it. We want Awwwards-grade craft (scroll-driven motion, microinteractions, bold type, polish) in service of a feeling no competitor can fake: *this thing isn't trying to dazzle me into not checking its work.*

Three commitments fall out of the north star and govern everything below:

1. **Honesty is structural, not asserted.** The design system literally cannot render a lie — uncertainty is a primitive, provenance is typography, and the flaws lead. If a rule can be enforced in code rather than trusted to a designer's discipline, it MUST be.
2. **Two temperatures, one system.** The same canonical model renders warm and teacherly for the v1 builder (a junior/self-taught dev who can code but can't yet architect for scale), and flat-affect and audit-grade for the skeptical Fortune-500 reviewer. We never ship only the cold one.
3. **We out-position by being more honest and more legible than the technical-dark incumbent — never edgier.** Against `syssimulator.com` (dark terminal, electric-cyan, "No login. No nonsense.") we deliberately do **not** cosplay a hacker terminal. That aesthetic signals "fast hobby tool." We sell *judgment*, and judgment reads as calm, lit, and accountable — closer to a flight-data recorder or a courtroom transcript than a CLI.

---

## 2. Brand Identity

### 2.1 Name & wordmark

The wordmark is **`keystone`**, lowercase, set in a humanist-but-engineered grotesque with tight tracking. It feels like precision instrumentation, not startup-friendly-round.

The signature glyph is the **confidence-ring "o"**: the `o` in *keystone* is rendered as a thin **270° arc that closes to a full circle only when a claim is GROUNDED**, and sits visibly open when it is an ASSUMPTION. The mark is therefore *alive* — the logo is the confidence band, not the disclaimer. In static contexts (favicon, OG image of a low-confidence report) the open ring is correct and on-brand; do not "fix" it to a closed circle for tidiness.

The secondary brand mark is the **keystone-arch**: a five-stone arch where the center stone (the keystone) locks the others. It doubles as the metaphor for consensus — many architects, one load-bearing decision. It assembles stone-by-stone in the council narrative (Section 7), the center stone seating last.

**MUST:** the ring's open/closed state is driven by real confidence state wherever it annotates a real claim. It is never decorative animation. A closed ring on an ungrounded number is a lie and a defect.

### 2.2 Tagline lockups (priority order)

1. **"Show your work."** — primary.
2. **"The model reasons. The engine computes."** — product-truth lockup.
3. **"Every number ships with its doubts."** — honesty lockup.

Near-fold brand line (the sentence that *is* the brand): **"We'll tell you when we're guessing."** This is our answer to the incumbent's "No nonsense." We out-honest, we don't out-edge.

### 2.3 Voice

Calm, precise, structurally humble — a principal engineer who has been burned in production and now over-communicates risk on purpose. The authority volunteers its own error bars.

**Voice law (MUST):**

1. **Never a bare number.** Every metric in copy and UI is followed by its band and provenance tag, in the same breath. This is NFR-1, applied to marketing as strictly as to product.
2. **Plain over clever.** We earn punch through precision, not slang. Where the incumbent says "No nonsense," we say "We'll tell you when we're guessing."
3. **Provenance is a vocabulary, not a tone.** `GROUNDED` / `GAP` / `ASSUMPTION` are real words the user learns to read, the way they learn HTTP status codes.
4. **Dissent is shown, never smoothed.** The council's minority opinion gets its own quoted line — named, not averaged away.
5. **Refusal is a feature sentence, not an error.** "Insufficient model — out of scope" is said with the confidence of someone who knows their limits.
6. **Verbs of record, not verbs of magic.** *Commission, deliberate, dissent, synthesize, derive, bound, simulate, validate, calibrate, flag, retract.*

**Banned words:** *certified, guaranteed, perfect, 100%, magic, effortless, instantly, just, 10x, game-changing, revolutionary, AI-powered.* The strongest claim we permit ourselves is **"directional, and here's the band."**

**Two temperatures:** BUILDER voice is encouraging and teacherly ("here's why architects reach for a cache here"). AUDIT voice is flat-affect, no adjectives, audit-grade. Same facts, two registers.

### 2.4 Palette

A **"lit instrument panel"** palette — authoritative, low-glare, with meaning colors that are *spent only on truth and doubt*, so confidence is communicated by hue, not just by words.

#### Core surfaces

| Token | Hex | Use |
|---|---|---|
| `slate-ink` | `#0E1622` | Primary dark surface (hero, reports). Near-black, cool blue cast — "instrument," not "terminal." |
| `paper` | `#F7F8FA` | Primary light surface for the reading/report mode. Legibility is the brand. |
| `graphite` | `#1B2736` | Elevated panels on dark. |
| `steel` | `#2A3A4D` | Card strokes, table rules on dark. |
| `mist` | `#E3E8EF` | Hairlines, table rules, disabled states on light. |

#### The two meaning colors — the heart of the system, NEVER decorative

| Token | Hex | Reserved meaning |
|---|---|---|
| `grounded-green` | `#2FB67C` | **EXCLUSIVELY** GROUNDED / high-confidence / "the engine computed this." A calm, surgical green, not neon. The only color allowed to say *trust me*. |
| `assumption-amber` | `#E8A33D` | **EXCLUSIVELY** ASSUMPTION / GAP / "where this is wrong" / editable inputs. Amber is the honesty signature: a Keystone report is visibly dusted with amber, on purpose. Amber means *we're being upfront* — **never** error. |

#### Failure & support

| Token | Hex | Use |
|---|---|---|
| `signal-red` | `#E5484D` | True failure / SPOF / "refuses to imply production-safe" / high-stakes domain flags. Used sparingly so it keeps its teeth. |
| `architect-blue` | `#4C7DF0` | Interactive / links / **council-voice attribution only** (who said what). Distinct from green so "clickable" never reads as "grounded." |
| `dissent-indigo` | `#3B4C8A` | Recorded dissent — the minority report. The marginalia color (see Section 6.3). Ink-blue, never alarm. |
| `ink-muted` | `#8A98A8` | Secondary text, provenance metadata, timestamps. |

#### Confidence gradient (for bands & rings ONLY)

A 3-stop ramp Doubt → Trust: `assumption-amber #E8A33D` → `teal #36A0A6` → `grounded-green #2FB67C`. Bands fill along this ramp; a wide amber band reads instantly as low confidence, a tight green one as grounded. **Color and width encode the same truth, redundantly on purpose** — for the colorblind and the skim-reader both.

#### The discipline rule that makes the brand (MUST, lint-gated)

> **`grounded-green` and `assumption-amber` are LOAD-BEARING, not palette.** A designer may NEVER use green to make a button look nice or amber to warm up a hero. Those hues are spent only on confidence semantics. This is the visual sibling of "no bare numbers." Chrome accents come from `architect-blue` and the neutrals — never from the two meaning colors. See Section 11 for the token-lint rule.

**Accessibility (MUST):** every confidence state carries a non-color cue — band width, an icon, and the literal provenance word. Meaning never rides on hue alone. Confidence is encoded as **width + label + hue**, never opacity alone (opacity-only confidence is an accessibility defect — a lesson grafted from the calm-intelligence critique). Verify WCAG AA on `ink-muted` and on all text over `assumption-amber`.

### 2.5 Typography — provenance IS typography

Three families, each with a *job*. The reader can identify the **source** of any token by its typeface alone — this is how NFR-3 (separation) is proven by reading, not claimed in a footer.

- **Serif → the model reasoned it.**
- **Mono → the engine computed it.**
- **Grotesque → it's chrome.**

| Role | Family (licensed) | Open fallback (ships on Next/Cloudflare) | Job |
|---|---|---|---|
| Display / wordmark / chrome | ABC Whyte / Söhne | **Inter** / Geist Sans | Wordmark, hero headlines, verdict lines, UI labels, dense chrome. |
| Reading / reasoning | Newsreader / Source Serif 4 | **Newsreader** (Google Fonts) | Body of reports, ADR rationale, the "where this is wrong" prose. The contrarian, brand-defining choice: a serif says *read this carefully, this is a document of record.* |
| Data / numbers | Berkeley Mono | **Geist Mono** / JetBrains Mono | EVERY engine number, metric, band label, provenance tag, spec block. Tabular figures always on — alignment is a credibility signal. |

**The typographic law (MUST):** if it's in **mono**, the engine computed it; if it's in **serif**, the model reasoned it; if it's in the **grotesque**, it's chrome. A number set in serif, or reasoning prose set in mono, is a defect — it misattributes provenance. Enforce with the `<Metric>` and `<Claim>` primitives (Section 11).

**Type scale** (1.250 major-third, 16px base for reading comfort, fluid clamp on the editorial jumps):

| Token | Size / leading | Family |
|---|---|---|
| Display / Verdict | 61 / 49px (clamp) | Grotesque, −2% tracking |
| H1 ("Where this is wrong") | 39px | Grotesque |
| H2 | 31px | Grotesque |
| H3 | 25px | Grotesque |
| Body (reading) | 19px / 1.65 | Serif — generous, document-grade |
| UI label / table header | 14px, uppercase, +6% tracking | Grotesque, muted |
| Mono data | 15px, tabular, tight leading | Mono |
| Provenance tag | 12px, all-caps, in a pill | Mono |

**Open-source-first:** ship the fallback stack (Inter + Newsreader + Geist Mono) as the launch default — it is genuinely excellent and native to the stack. Treat the premium faces as a funded upgrade once revenue exists. The load-bearing distinction is **mono-vs-not** (it carries NFR-3); if the serif must ever be cut for performance or dev-reception reasons, keep mono-vs-not intact and A/B the serif against a humanist sans. Cap to 3 weights per family; subset aggressively; self-host woff2 on Cloudflare (no FOUT).

### 2.6 Motion principles — "instruments settle, they don't bounce"

Every animation must read as a **measurement resolving**, never as decoration celebrating.

1. **SETTLE, DON'T SPRING.** No playful overshoot. Easing is a critically-damped settle: `cubic-bezier(0.2, 0.8, 0.2, 1)`. Durations 180–420ms for UI, up to ~1.2s for the hero band reveal. `prefers-reduced-motion`: bands snap to final width, no count-up — and the static state is *equally complete and equally beautiful*.
2. **NUMBERS COUNT UP THROUGH THEIR BAND, THEN LOCK.** When a metric resolves, the digit rolls (tabular mono, no layout shift) while a faint band breathes; on lock the band sets to true width and a provenance pill fades in. Counting happens *only* for engine numbers — LLM prose never animates as if it were data.
3. **THE BAND IS ALIVE WHILE UNCERTAIN, STILL WHEN GROUNDED.** Low-confidence bands carry a barely-perceptible amber widen-breath (≤2% amplitude); as confidence rises toward GROUNDED the motion damps to perfectly still green. **Stillness = trust.**
4. **SCROLL IS A DERIVATION, NOT A RIDE.** Scroll advances the *argument* (intent → council → engine → bands → caveats), each section pinning just long enough to land one idea. The keystone-arch assembles stone-by-stone; the center stone seats last with a soft *seat*, not a bounce.
5. **DISSENT INTERRUPTS.** A recorded minority line cuts in from the margin with a sharper, faster rhythm than consensus text — a deliberate visual "but—." Honesty has a different rhythm than agreement.
6. **REFUSAL IS COMPOSED.** When Keystone fails closed, there is no shake, no red flash. The panel calmly desaturates and states its limit. Confidence in one's own boundaries is shown by restraint.

**Stack reality (MUST):** heavy motion is **quarantined to the marketing route**. The confidence band is cheap CSS/SVG (width + hue), never canvas. Hard frame gate: 60fps on a mid laptop or the moment is cut. Auto-degrade any scroll set-piece to a static seeded poster frame. `prefers-reduced-motion` is a first-class, equally-complete path — never an afterthought. See Section 10 for budgets.

---

## 3. The Signature Move: Visualizing Uncertainty Honestly *and* Beautifully

This is the differentiator no competitor leans into. The trust-viz is **three interlocking primitives**: the Living Confidence Band (the atom), the visible Reasoning→Computation Seam (the architecture), and the "Where This Is Wrong" Marquee (the flex). Together they make honesty the most beautiful thing on the page.

### 3.1 The Living Confidence Band — the atom

Every engine number renders as **`[value]` wrapped in a horizontal band** whose **width = uncertainty** and whose **hue rides the Doubt→Trust ramp** (amber → teal → green).

- `p95 ~86ms` → tight green band.
- A low-confidence DB-sizing number → wide amber band.
- Hover/tap expands the band into a mini-distribution with the **formula** (e.g. `M/M/1 sojourn, W = service / (1−ρ)`), the **inputs**, and the **provenance tag**.

The band is the **same primitive everywhere** — hero, tables, exports — so users learn to read uncertainty at a glance the way they read a progress bar.

**MUST:** there is no code path that renders a bare number. Uncertainty is a *primitive*, not a state. Every number is *born inside* a band. This is NFR-1 made physically impossible to violate, even by accident. The `<Metric>` primitive (Section 11) cannot compile without a band, a model attribution, and a provenance tag.

This is the visual thesis: **uncertainty is a designed object, never fine print.** It is also the screenshot surface — the thing that spreads on Twitter is a number visibly wearing its doubt.

### 3.2 The Reasoning→Computation Seam — the architecture *(grafted: calm-intelligence)*

The signature *spatial* move — a stronger, more legible proof of separation than the typographic rule alone. Throughout the product there is a **literal recurring visual seam** between two zones:

- a **warm REASONING zone** (paper ground, serif/grotesque, the council's prose), and
- a **cool COMPUTATION zone** (slate ground, mono, the engine's numbers),

divided by a single hairline labelled in micro-caps **`parameters →`**. When the council hands a value to the engine, you **watch it cross the seam as a parameter token**; when the engine returns a metric, it **crosses back as a settled number inside its band**.

The user learns the architecture's honesty by watching it operate: **the LLM literally cannot reach into the number column.** This renders NFR-3 as architecture you watch run, not just typography you must decode. Make this the **centerpiece scroll section** on the landing and a persistent structural seam in the report layout.

### 3.3 The Assumption Ledger + Live Ripple — uncertainty made interactive

The *Assumptions (each editable)* table is promoted from report-footer to a **persistent right rail** — every row in amber mono with a provenance pill. Editing any assumption (e.g. cache hit-rate `90% → 70%`) fires a **visible ripple**: the changed input pulses, a wavefront travels down the dependency graph re-widening and re-coloring every band it touches, with deltas (`+/- ms`, `util%`) ghosting in beside each.

You literally **watch your own guess propagate into the verdict.** This is the calibration loop made tactile and the strongest possible answer to "why should I trust this?" — *because you can move it yourself.* When you replace an assumption with a measured value, its chip flips `ASSUMPTION → GROUNDED`, the band narrows and cools toward green, and the accuracy-ladder badge can climb. **The user feels the product get more accurate as reality is fed in** — the single most important, least-demoable idea in the product, made tangible.

### 3.4 The "Where This Is Wrong" Marquee — the flex

Not a footnote — a full, designed section with its own **amber left-rule**, serif body, and a standing headline: **"Read before trusting a number."** Each caveat is a card pairing a plain-English limit (e.g. *"percentiles use an exponential-tail approximation and OVER-state the tail"*) with the exact metric it qualifies. Hovering a caveat highlights the affected number elsewhere on the page, and vice versa.

**MUST:** on the landing this section is positioned **ABOVE the pricing/CTA**. We show our flaws before we ask for the card. In product it is a **persistent, non-dismissable surface** on every report. For high-stakes domains (payments, health, election, safety-critical) it contains a **non-dismissable `signal-red` block**: *"Requires expert / legal / security review. Keystone produces decision support, not certification."* No competitor does this; it is the trust wedge rendered as layout hierarchy.

### 3.5 The Provenance X-ray — separation in one keystroke

A persistent **"Show provenance"** toggle tints the whole report by source: serif reasoning gets a faint `architect-blue` wash, mono engine-numbers a green/amber confidence wash, ASSUMPTIONS light amber. In one keystroke the user *sees* the separation principle — which words a language model reasoned vs. which numbers a deterministic engine computed. For the F500 reviewer this is the audit view; for the dev it's the "aha — the AI never made up a number" moment. **On by default in AUDIT mode.**

### 3.6 The Accuracy-Ladder Badge — honest status, not a trust-me seal

A small persistent chip reads **`L0 · Directional`**, with the L0→L3 ladder revealed on click. Keystone advertises its *current, modest* accuracy level as a **climbable trajectory**, never overclaiming L3. Later the same chip shows per-component calibration (`within X% on workloads like yours · N actuals reported`). This turns the accuracy charter into a visible, *earned* status bar — the opposite of a gold `CERTIFIED` seal. Trust is a visible trajectory, not a launch boast.

---

## 4. The Storytelling Arc

### 4.1 Landing — a five-act scroll-derivation that *argues* the thesis

The page itself behaves like a Keystone report: it argues, it doesn't assert. **Critical sequencing rule (MUST):** the hero **demonstrates competence within 3 seconds, BEFORE it confesses limits**, so honesty reads as *mastery*, not weakness. This is the single most important narrative constraint in the document.

**ACT 1 — THE CONFESSION (hero).** On `slate-ink`, one calm grotesque line: *"No tool can predict your system perfectly."* Beat. *"…so we show you exactly where we're guessing."* Behind it, a single real metric resolves live — a number counts up through a breathing amber band that settles to green — demonstrating the product in the first three seconds. CTA mirrors the incumbent's friction-free promise in our voice: **"Describe what you're building →"** with a sub-line *"No login to see a sample report. We'll tell you when we're guessing."*

> **The behind-the-confession proof *(grafted: developer-bold)*.** The hero's live element is the **reseedable living simulation**: a real `LB → app → cache → Postgres` stack on a faint substrate grid. **"Push it to 10×"** floods request packets; the bottleneck component's ring goes coral/hatched and the grid reddens locally; a breakpoint readout snaps in (`~12,240 rps at the 85% safe ceiling`) — beside it, its confidence band. A **`reseed`** button replays the run **byte-identical**, proving NFR-7 determinism. **Reproducibility IS the spectacle**, and it proves competence in the first 8 seconds — the single strongest answer to trust-hero's #1 risk (honesty reading as weakness before competence is shown). This is the *only* place a heavier motion budget is justified; it is WebGL/canvas-quarantined and ships a static seeded poster frame for reduced-motion and JS-off. Competence first, *then* the confession.

**ACT 2 — THE INTENT.** A builder types a plain-English brief (*"a URL shortener, ~10k req/s, mostly reads"*). Ingestion turns prose into a canonical model; every INFERRED assumption surfaces as an editable amber chip. The machine *declares* what it assumed instead of hiding it. If two input docs disagree, the reconciliation view halts and asks — *we don't design on a contradiction* — disarming the skeptic before a single clever answer.

**ACT 3 — THE COUNCIL (the arch assembles).** The consensus convenes as an **attributed transcript** (Section 6). Personas propose; the YAGNI-skeptic pushes back; dissent slides into the indigo margin. Stones drop into the arch with each resolved ADR; the keystone seats last. Takeaway: *"Not one model's opinion. A council that argues — on the record."*

**ACT 4 — THE PROOF (separation made visible).** The view crosses the **seam** (Section 3.2): serif reasoning hands off to mono numbers as the deterministic engine computes the verdict — bottleneck, p50/p95/p99, cost — each wrapped in its living band. The **"Show provenance"** X-ray flashes the green/amber/blue wash: *"The model reasoned the design. The engine computed the numbers. No metric came from the LLM."*

**ACT 5 — WHERE THIS IS WRONG (the flex, before the ask).** The full caveat section lands **ABOVE** the CTA, amber-ruled, headlined *"Read before trusting a number."* Then — and only then — the accuracy-ladder chip (*"we ship at L0 and say so — here's how we climb to L3"*) and the pricing/CTA. Closing lockup: **"Show your work."**

### 4.2 In-product — the report IS the brand

Three reading modes off one canonical model:

1. **BUILDER mode** — teacherly, serif rationale foregrounded, bands and assumptions inviting edits, the ripple loop encouraging interrogation (*"change a guess, watch the verdict move"*). Warm temperature. This is the v1 user's home.
2. **REVIEW / AUDIT mode** — flat-affect, provenance X-ray on by default, every claim tagged `GROUNDED`/`GAP`/`ASSUMPTION`, dissent and kill-criteria expanded. The view you forward to a skeptical CTO or F500 reviewer. Cold temperature.
3. **EXPORT** — the shareable Markdown/spec-file carries the same hierarchy (Verdict → bands → "Where this is wrong" → editable Assumptions → provenance tags) so honesty survives leaving the app.

**The narrative constant** across landing and product: **intent → grounded consensus → deterministic proof → honest bounds → climbable accuracy.** The loop *is* the story. The in-product workspace is **fast and dense** — editorial *styling*, never editorial *pacing*; no scrolljacking inside the app. Long-form choreography lives only on the marketing route.

---

## 5. The Shareable "Issue" — the viral surface *(grafted: editorial-story)*

When a design validates, it becomes a **shareable, versioned "issue"** — deterministic (same corpus + seed = same issue, per NFR-7) with a real cover, a **masthead listing the named architects**, a byline, and an issue number. Sharing your architecture is *publishing a record* about your own system. A screenshot of your system's cover, with its confidence grade and its named council, is something engineers post **precisely because it looks credible, not flashy** — the viral surface trust-hero otherwise lacks. The "issue" carries the confidence bands and the "Where This Is Wrong" page intact, so the honesty survives the screenshot.

---

## 6. The Council Transcript — consensus you can read and argue with

### 6.1 Attributed, not monolithic

Consensus is shown as an **attributed transcript**, not a single answer. Each persona (Backend, Data, Security, SRE, Cloud/FinOps, AI, YAGNI-skeptic) has a name in `architect-blue`. Agreement is calm serif. The three stages are replayable as a quiet horizontal timeline: **independent design → blind peer review → chairman synthesis.**

### 6.2 Blind peer review, shown literally

The anti-sycophancy mechanic is *rendered*: in the peer-review stage, author names redact to `▮▮▮▮▮` so critiques collide on merit, not authority. The user sees the mechanism that prevents the council from rubber-stamping itself.

### 6.3 Dissent as indigo marginalia *(grafted: editorial-story)*

Recorded dissent is typeset as a **senior engineer's pen-notes running down the outer column** — `dissent-indigo`, slightly off-grid, in the margin of the ADR. **You physically cannot read a recommendation without the objection in your peripheral vision.** This converts "never hide dissent" (Charter §6) from a slide-in animation into **permanent spatial layout** — more credible to an F500 auditor than motion, because it cannot be toggled away. Click the marginalia and the dissenting architect argues their full case in a side-sheet, with their **kill-criteria** (*"revisit if write-RPS exceeds 8k"*).

### 6.4 Kill criteria — every decision is falsifiable

Each ADR ends with a `grounded-green`-bordered **"Kill criteria — revisit if…"** block, framing every decision as falsifiable, not final. A subtle **agreement meter** beside each ADR shows how aligned the seven lenses were; low agreement is shown honestly as a thinner, hesitant bar — never hidden.

---

## 7. The Keystone-Arch Build

As the council converges, the five-stone arch assembles — one stone per resolved ADR — and the **center keystone seats last and locks** (soft seat, motion principle 4). It is the only "delight" flourish in the council narrative, earned once per design, so it reads as a press-stamp moment rather than confetti. On the validated "issue," the closed confidence-ring "o" and the locked arch are the two marks that say *this passed the record*.

---

## 8. "What Great Looks Like" — the bar

A Keystone surface is **great** when all of the following are simultaneously true:

- **Honest at a glance.** You feel the confidence level *before* you read a word — the page is visibly, permanently color-coded by how-sure-we-are. No bare number exists anywhere on it.
- **Competent in 3 seconds.** The first interaction demonstrates mastery (the reseedable sim, a number resolving) *before* any confession of limits. Honesty reads as rigor, never as weakness.
- **Legibly separated.** A reader can tell the *source* of any token — model-reasoned vs. engine-computed vs. chrome — by typeface and by which side of the seam it sits on, without being told.
- **Screenshot-credible.** The single most beautiful, most prominent object on the page is a number wearing its uncertainty, or the "Where This Is Wrong" spread. The thing that spreads is the honesty.
- **Two-temperature true.** The same model reads warm and teacherly for the junior builder and flat/audit-grade for the F500 reviewer, with no rebrand and no second design system.
- **Fast.** LCP < 2.0s on the marketing route; the workspace is dense and instant. A janky trust product is self-refuting — speed is part of the credibility promise, not traded against it.
- **Still where it should be still.** Grounded things don't move. Motion is reserved for things that are genuinely resolving or genuinely uncertain. Nothing animates merely to impress.
- **Composed under failure.** Refusal and high-stakes flags are designed, calm, confident moments — not error states bolted on.

If a screen is beautiful but fails *any* of the first three, it is **not** great — it is a defect dressed up. Honesty > clarity > speed > craft.

---

## 9. QA / Review Rubric

Every surface is reviewed against these eight dimensions. Score each **0–3** (0 = violates a MUST / blocks ship; 1 = weak; 2 = solid; 3 = exemplary). **Any 0 on a starred (★) dimension blocks ship regardless of total** — these encode the trust thesis and are non-negotiable.

| # | Dimension | What we check | ★ |
|---|---|---|---|
| 1 | **Thesis integrity** | No bare numbers; every metric has band + provenance + model attribution; nothing computed is misattributed to the model (or vice-versa) by typeface or seam-side. | ★ |
| 2 | **Provenance legibility** | Serif = reasoned, mono = computed, grotesque = chrome holds at every size incl. 14px; the seam and the X-ray make separation visible without explanation. | ★ |
| 3 | **Semantic-color discipline** | `grounded-green` and `assumption-amber` appear *only* on confidence semantics; chrome uses neutrals + `architect-blue`; `signal-red` is rare. Passes the token-lint. | ★ |
| 4 | **Competence-before-confession** | The first 3–8 seconds demonstrate mastery before any limitation is shown; caveats are framed as mastery, not apology. | ★ |
| 5 | **Honesty surfacing** | "Where this is wrong" is prominent (above the CTA on landing; non-dismissable in product); dissent is in peripheral vision, not a buried tab; high-stakes flag is non-dismissable. | ★ |
| 6 | **Craft & motion** | Settle-not-spring easing; stillness = trust; choreography carries meaning; microinteractions feel measured; the static/reduced-motion state is itself beautiful. | |
| 7 | **Performance budget** | LCP < 2.0s marketing / dense+instant workspace; heavy motion quarantined to marketing; 60fps gate honored; band is CSS/SVG not canvas; JS budget met. | ★ |
| 8 | **Two-temperature & a11y** | BUILDER warm vs. AUDIT flat both legible from one model; confidence carries width + label + hue (never hue/opacity alone); WCAG AA verified. | |

**Review cadence:** every PR that touches a user-facing surface gets a rubric pass. A surface ships at **≥ 16/24 with no starred 0.** The semantic-color and no-bare-number rules additionally run as automated lint on every commit (Section 11), so dimensions 1 and 3 are caught before review.

---

## 10. Stack Reality — design choices the platform constrains

Frontend is **Next.js + Tailwind on Cloudflare (OpenNext)**. This shapes design, not just engineering:

- **Performance budgets are a design constraint, not an afterthought.** Target **LCP < 2.0s** and **JS < 150KB on the cover**. A credibility brand that loads slowly refutes itself on contact. If a moment costs the speed thesis, **cut it** (clarity & speed outrank craft).
- **Server-render the substance.** The report and its bands render server-side; the page must read fully with JS off (ship static OG/poster frames). The reduced-motion, no-JS fallback is a **first-class, genuinely beautiful** static layout — design it *first*, animate *second*.
- **The confidence band is cheap by mandate.** Width + hue in CSS/SVG — never canvas. This is what lets the signature primitive appear *everywhere* (hero, tables, exports) without a motion-cost penalty.
- **Heavy motion is quarantined to the marketing route** and lives behind a hard 60fps gate with auto-degrade to a seeded poster. WebGL/canvas is permitted **only** for the hero living-sim; CSS transforms everywhere else; in-product motion is React-state-driven and interruptible.
- **Fonts are edge-cached, self-hosted woff2,** subset aggressively, ≤ 3 weights per family, no FOUT. The open-source stack (Inter + Newsreader + Geist Mono) ships native to Next — premium faces are a later funded upgrade.
- **Determinism is a design asset, not just a backend property.** Because the engine is seeded (NFR-7), the hero sim and the shareable "issue" replay byte-identical — the `reseed` control turns reproducibility into the cheapest, most un-fakeable spectacle we have.

---

## 11. Fixed vs. Latitude — the contract with Jem

This section is the contract. **FIXED** items are the trust thesis encoded as design law — change them only via a recorded decision and a Charter cross-check. **LATITUDE** items are explicitly yours to make beautiful; the standard will not second-guess you there.

### FIXED (MUST — do not change without a decision record)

1. **No bare numbers.** Every metric is born inside a confidence band with a provenance tag and model attribution. Enforced by a `<Metric>` primitive that **cannot render** without all three, and a CI lint that fails any raw numeric in a result surface.
2. **Provenance is typography + space.** Serif = reasoned, mono = computed, grotesque = chrome; the reasoning/computation seam is structural. A `<Claim>` primitive requires a provenance tag.
3. **Two meaning colors are load-bearing.** `grounded-green` and `assumption-amber` are confidence-only tokens; a separate neutral/`architect-blue` token set serves all chrome. A **token-lint rule** fails any decorative use of the meaning colors. This needs a named owner.
4. **The flaws lead.** "Where this is wrong" is above the CTA on landing and non-dismissable in product; the high-stakes review block is non-dismissable; the accuracy ladder advertises L0, never L3.
5. **Competence before confession** in any hero/first-run sequence (the 3-second rule).
6. **Dissent is never hidden** — it lives in the margin (spatial), not a tab.
7. **Never certify.** Banned words list (Section 2.3) holds in product *and* marketing. The strongest claim is "directional, and here's the band."
8. **Honesty > clarity > speed > craft** is the tiebreak, always.
9. **`prefers-reduced-motion` is a complete, equal, beautiful path**; confidence never rides on hue or opacity alone (width + label + hue).
10. **Performance budgets** (LCP < 2.0s, marketing-only heavy motion, band as CSS/SVG) are non-negotiable.

### LATITUDE (yours — make it sing)

- **Exact hue tuning** within each token's role (e.g. dialing `assumption-amber` saturation so a full page of it still feels *calm, upfront* rather than *alarming* — a known risk worth your craft; keep it strictly separated from `signal-red`).
- **The reseedable-sim hero's visual language** — substrate grid texture, packet rendering, how the bottleneck ring goes coral/hatched, the breakpoint readout's choreography. Make it the best 8 seconds on the internet, within the frame budget.
- **The arch-assembly choreography** and the seating of the keystone — timing, weight, the exact feel of the "lock."
- **Scroll-derivation pacing** — how long each act pins, transitions between seam crossings, the ripple wavefront's physics.
- **Microinteraction inventory** — hover states, the formula-popover layout, magnetic detents on assumption sliders at the council's recommended value, the "thinking" breath on deliberating personas.
- **Editorial layout of the "issue"** — cover composition, masthead treatment, folio markers, drop-caps on long-form ADR rationale, pull-quote styling.
- **Illustration / texture / iconography** system, empty states, loading states (so long as a loading number never fakes precision).
- **Choice of premium vs. open faces** at any given moment (subject to the mono-vs-not law holding).
- **Light/dark report treatments** and the exact temperature shift between BUILDER and AUDIT modes (subject to both being legible from one model).

When in doubt: if your idea makes honesty *more* visible, more legible, or more beautiful **without** weakening clarity, speed, or credibility, you almost certainly have the latitude to ship it. If it makes a number look more confident than the engine earned, you do not — that is the one line that never moves.

---

*The model reasons. The engine computes. We never let them lie for each other. Show your work.*
