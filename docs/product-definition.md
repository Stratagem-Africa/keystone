# Keystone — Product Definition (v0.1)

**Working name:** Keystone *(placeholder — rename freely)*
**Status:** Internal working paper — Stratagem Africa IdeaBank. Personal venture concept. Not client-facing.
**Date:** 13 June 2026
**Evidence labels:** **[V]** verified · **[D]** directionally plausible · **[A]** assumption.

**One line:** *Describe what you're building in plain English — a grounded consensus of AI architects designs it, justifies every decision, and validates it with simulation.*

---

## 1. The problem

Most people who build software can *code* but cannot *architect for scale*. **[A]** Existing tools assume you already can: SysSimulator, Eraser, IcePanel, draw.io all start with a blank canvas you must fill yourself. If you don't already know whether you need a cache, a queue, or read replicas, the blank canvas is the wall you hit. There is no tool that takes you from **intent → design**.

## 2. Who it's for (v1)

- **Primary:** developers who can build but have never designed for scale — juniors, mids, bootcamp grads, self-taught engineers.
- **Secondary:** technical founders shipping without a senior architect on the team.
- **Distribution top-of-funnel:** learners and interview-preppers — reachable, vocal, and cheap to acquire (borrow SysSimulator's content-led model).
- **Explicitly NOT:** literally non-technical users. That market is thin; the real, large, underserved audience is the *can-build-can't-architect* middle.

## 3. The wedge

The field splits into **draw-first tools** (you architect, they render) and **simulators** (you architect, they stress-test). None of them *design*. Keystone's AI does the drawing **and** the reasoning. Simulation is a **feature inside Keystone**, not the product. We do not compete on the simulation engine — that is SysSimulator's deep, years-ahead moat — we compete on the AI design layer where it has nothing.

## 4. The core loop *(the loop is the moat — no single step is)*

**Intent (any format) → Grounded consensus design (+ decision log) → Simulate / stress-test → Calibrate against reality → repeat.**

## 5. What it does

- **Ingest:** natural language, functional spec, ideation/concept doc, voice note, or pasted diagram — one Claude ingestion layer normalises everything into a single **canonical system model** (the source of truth, and the versionable "design-as-code" artifact).
- **Design (consensus):** a panel of specialised lenses — backend/systems, data, security & integrity, SRE/operability, cloud/FinOps, AI engineer, and a simplicity/YAGNI skeptic — proposes, challenges, and converges. Each decision is written as an **ADR (Architecture Decision Record) with recorded dissent.** Grounded in real postmortems and reference architectures, **not** raw LLM priors.
- **Advise:** languages, frameworks, libraries, database, cache, pub/sub, component communication, API style (REST/gRPC/GraphQL/event), AI-infusion (including where *not* to use AI), cloud services, DevOps tooling, and layered security.
- **Validate:** deterministic capacity/bottleneck analysis of the core tier + "what-if" interrogation (10× traffic, kill a component, add a cache).
- **Output:** architecture diagram, versionable spec file, ADR decision log, stress-test report, rough multi-cloud cost, and a flagged **"needs expert/legal review"** list for high-stakes domains.

## 6. The moat

1. **Calibration data** — predicted vs actual, captured from day one. Compounds with every user; cannot be bought by an incumbent.
2. **Consensus grounded in real evidence** — not five models sharing the same training opinions.
3. **Transparent decision log** — auditable reasoning, not a black box.
4. **Audience + content/community** — a library of forkable, simulated reference architectures over time.

> **The council is NOT the moat.** The LLM-council/consensus pattern is commoditised — dozens of open-source implementations exist (incl. *Architect-Council*, a 5-agent architecture-decision authority). Spend zero novelty budget on the council; assemble it from proven patterns. The moat is the **loop** (council → simulation → calibration), which no council project does.

## 7. Trust principle *(non-negotiable)*

**Claude reasons. The engine computes.** Claude designs, advises, and critiques; the deterministic simulation produces the numbers. Claude never invents a throughput figure. Every estimate shows its **assumptions, confidence, and the model behind it.** We copy SysSimulator's discipline of an explicit "where this is wrong" section — honesty is the differentiator with skeptical engineer buyers.

## 8. v1 boundary *(frozen — resist creep)*

**In:**

- Text/voice/spec ingestion → canonical model, with every inferred assumption visible and editable
- Consensus design + ADR decision log
- Stack / cloud / DevOps / security recommendations
- Single-region web-stack simulation: load balancer, app servers, SQL + replicas, cache, queue, object store
- What-if interrogation
- Exports: versionable spec file + shareable Markdown report
- Calibration-data capture switched on from launch

**Deferred (v2+):** interactive visual canvas · streaming/microservice-mesh + multi-region/chaos simulation · repo & cloud import · full predicted-vs-actual calibration UI · community reference-architecture library.

## 9. What we borrow from SysSimulator

Blueprint-library onboarding · radical honesty about limitations · deterministic, shareable designs · the chaos-scenario taxonomy · local-first privacy as a selling point · the learn-hub content/SEO engine · "cost from architecture, not from config" (extend to multi-cloud + region-aware).

**From the LLM-Council ecosystem** (Karpathy's llm-council and its many forks): the proven 3-stage mechanism — *independent design → blind/anonymized peer review → chairman synthesis*; the output schema from *LLM-Council-Decide* — *convergent signal, named disagreements, confidence level, kill criteria* (our ADR-with-dissent format); and the **single-model-multi-persona** approach (*LLM-Council-Template*) to run the council on one model cheaply in v1, adding multi-provider diversity later.

## 10. Keystone vs SysSimulator

| | SysSimulator | Keystone |
|---|---|---|
| Starting point | Blank canvas you fill | Plain-English intent |
| Designs for you | No | Yes (consensus + ADRs) |
| AI in the loop | None | Core |
| Stack/cloud/security advice | No | Yes |
| Simulation | Excellent (Rust/WASM DES) | Lighter analytical model v1; feature, not product |
| Connects to reality | No | Calibration loop (the moat) |
| Audience | FAANG interview prep | Build-but-can't-architect + founders |

## 11. Mission

Democratise principal-engineer judgment to every builder on earth — especially the global-South majority who never get to sit beside a senior architect. That is the position Silicon Valley and the elite labs build *over*, not *for*. We win on wedge, focus, and a compounding data moat — never on headcount.

## 12. Risks (red-team)

- **The AI-design layer is contested** (funded players are heading here) and the **council pattern is already commoditised** (the entire LLM-Council ecosystem). → Treat the council as table stakes; win on the *integrated loop* (simulation + calibration) + specific audience + data moat, and move fast.
- **Don't out-engineer the simulator.** → Ship a lighter analytical/queueing model in v1; deeper DES later.
- **Confidently-wrong advice is fatal** with engineers. → Grounding + transparency + expert-review flags are load-bearing, not nice-to-have.
- **Inference cost at scale.** → Manageable; v1 build stays within budget.
- **Distribution.** → Dropping the pure-learner positioning raises the bar; seed early users through learner channels even though the product is built for pros.

## 13. Next

Build the **v1 engine slice**: Claude ingestion → canonical model → consensus design + ADRs → single-region capacity/bottleneck simulation → report. **First real test input: the Election OS concept note.** Then put it in front of 5 design-partner users from the target audience.

*— End of v0.1 —*
