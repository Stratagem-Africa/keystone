"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  Handle,
  Position,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
  type NodeProps,
  type NodeTypes,
  type Connection,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  KIND_META,
  COMPONENT_KINDS,
  type ComponentKind,
  type ArchMap,
  type ArchMapNode,
  type NodeStatus,
  type Provenance,
  type SimulateRequest,
  type ApiErrorBody,
  type SeedNode,
} from "@/lib/archMap";

// The engine (POST /simulate -> build_arch_map) is the ONLY source of every number shown
// here — utilization, status, provenance, cost, latency. This component never computes a
// metric; it only serializes the drawn topology, renders whatever the engine returns, and
// formats it (numeric vs. plain-language phrasing) for display. Prime directive intact.

const STATUS_COLOR: Record<NodeStatus, string> = {
  ok: "var(--cv-green)",
  hot: "var(--cv-amber)",
  saturated: "var(--cv-red)",
};

function simpleStat(status: NodeStatus): string {
  if (status === "saturated") return "✕ over its limit";
  if (status === "hot") return "⚠ running near its limit";
  return "✓ plenty of headroom";
}

interface ComponentNodeData extends Record<string, unknown> {
  kind: ComponentKind;
  name: string;
  per_instance_rps?: number;
  instances?: number;
  base_latency_ms?: number;
  monthly_cost_cents?: number;
}

interface CanvasDisplayValue {
  archMapById: Record<string, ArchMapNode> | null;
  mode: "simple" | "technical";
  activeFlowNodeIds: Set<string> | null;
  isStale: boolean;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
}

const CanvasDisplayContext = createContext<CanvasDisplayValue>({
  archMapById: null,
  mode: "simple",
  activeFlowNodeIds: null,
  isStale: false,
  onRename: () => {},
  onDelete: () => {},
});

function ProvenanceBadge({ value }: { value: Provenance }) {
  // GROUNDED is the only "trust this" color; RECONCILE/ASSUMPTION/GAP all read as amber
  // (docs/09 §2.4 — meaning colors are load-bearing, not decorative).
  const color = value === "GROUNDED" ? "var(--cv-green)" : "var(--cv-amber)";
  return (
    <span
      className="font-mono text-[9px] uppercase tracking-wide px-1 rounded border w-fit"
      style={{ borderColor: color, color }}
    >
      {value}
    </span>
  );
}

function ComponentNode({ id, data, selected }: NodeProps<Node<ComponentNodeData>>) {
  const { archMapById, mode, activeFlowNodeIds, isStale, onRename, onDelete } = useContext(CanvasDisplayContext);
  const result = archMapById?.[id] ?? null;
  const meta = KIND_META[data.kind];
  const dimmed = activeFlowNodeIds !== null && !activeFlowNodeIds.has(id);
  const statusColor = result ? STATUS_COLOR[result.status] : "var(--cv-steel)";
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(data.name);

  return (
    <div
      className="cv-panel min-w-[168px] px-3 py-2 flex flex-col gap-1 transition-opacity duration-ui"
      style={{
        opacity: dimmed ? 0.25 : 1,
        borderColor: statusColor,
        borderWidth: selected ? 2 : 1,
        // Dashed = "this status is from a verdict that no longer matches the drawn topology"
        // (topology edited since the last Simulate) — still shown, never hidden, just flagged.
        borderStyle: result && isStale ? "dashed" : "solid",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: "var(--cv-blue)" }} />
      <div className="flex items-center gap-1.5">
        <span aria-hidden>{meta.icon}</span>
        {editing ? (
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => {
              setEditing(false);
              const next = draft.trim();
              if (next) onRename(id, next);
              else setDraft(data.name);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") (e.currentTarget as HTMLInputElement).blur();
              if (e.key === "Escape") {
                setDraft(data.name);
                setEditing(false);
              }
            }}
            className="font-sans text-xs bg-transparent border-b border-[var(--cv-steel)] outline-none text-[var(--cv-ink)] w-24 nodrag"
          />
        ) : (
          <button
            type="button"
            onDoubleClick={() => setEditing(true)}
            title="Double-click to rename"
            className="font-sans text-xs font-semibold text-left text-[var(--cv-ink)] nodrag"
          >
            {data.name}
          </button>
        )}
        <button
          type="button"
          aria-label={`Delete ${data.name}`}
          onClick={() => onDelete(id)}
          className="ml-auto text-[10px] text-[var(--cv-muted)] hover:text-[var(--cv-red)] nodrag"
        >
          ✕
        </button>
      </div>
      <div className="font-sans text-[10px] text-[var(--cv-muted)] leading-snug">{meta.role}</div>
      {result &&
        (mode === "simple" ? (
          <div className="font-sans text-[11px] text-[var(--cv-ink)]">{simpleStat(result.status)}</div>
        ) : (
          <div className="font-mono text-[10px] text-[var(--cv-muted)] flex flex-col">
            <span>{result.utilization !== null ? `${Math.round(result.utilization * 100)}% util` : "no data"}</span>
            <span>{result.arrival_rps !== null ? `${Math.round(result.arrival_rps)} rps` : "-"}</span>
            <span>{result.mean_latency_ms !== null ? `${result.mean_latency_ms.toFixed(1)} ms` : "-"}</span>
          </div>
        ))}
      {result && <ProvenanceBadge value={result.provenance} />}
      <Handle type="source" position={Position.Bottom} style={{ background: "var(--cv-blue)" }} />
    </div>
  );
}

const nodeTypes: NodeTypes = { component: ComponentNode };

interface StarterNode {
  id: string;
  kind: ComponentKind;
  name: string;
  x: number;
  y: number;
  instances?: number;
}

// The same topology prototype/tests/test_simulate_endpoint.py + test_topology.py use as
// their fixture — guaranteed to simulate cleanly, so the canvas never opens to a dead end.
const STARTER_NODES: StarterNode[] = [
  { id: "client", kind: "client", name: "Users", x: 320, y: 0 },
  { id: "lb", kind: "load_balancer", name: "LB", x: 320, y: 130 },
  { id: "app", kind: "app_server", name: "App", x: 320, y: 260, instances: 12 },
  { id: "cache", kind: "cache", name: "Cache", x: 140, y: 400 },
  { id: "db", kind: "sql_db", name: "DB", x: 500, y: 400 },
];
const STARTER_EDGES: [string, string][] = [
  ["client", "lb"],
  ["lb", "app"],
  ["app", "cache"],
  ["app", "db"],
];

const initialNodes: Node<ComponentNodeData>[] = STARTER_NODES.map((n) => ({
  id: n.id,
  type: "component",
  position: { x: n.x, y: n.y },
  data: { kind: n.kind, name: n.name, ...(n.instances ? { instances: n.instances } : {}) },
}));
const initialEdges: Edge[] = STARTER_EDGES.map(([source, target]) => ({
  id: `${source}->${target}`,
  source,
  target,
}));

// The studio seeds the canvas from a generated design (see `seedFromArchMap`), so it opens on the
// generated architecture with the engine's verdict already populated — never a blank/starter grid.
export interface CanvasSeed {
  nodes: SeedNode[];
  edges: [string, string][];
  systemRps?: number;
  archMap?: ArchMap | null;
}

function seedToFlowNodes(seed: SeedNode[]): Node<ComponentNodeData>[] {
  return seed.map((n) => ({
    id: n.id,
    type: "component",
    position: { x: n.x, y: n.y },
    data: {
      kind: n.kind,
      name: n.name,
      ...(n.per_instance_rps ? { per_instance_rps: n.per_instance_rps } : {}),
      ...(n.instances ? { instances: n.instances } : {}),
    },
  }));
}
function seedToFlowEdges(edges: [string, string][]): Edge[] {
  return edges.map(([source, target]) => ({ id: `${source}->${target}`, source, target }));
}

// The signature of a drawn topology — a verdict is only honest while this is unchanged (see below).
// Module-level so the seed's initial "already-simulated" signature can be computed the same way.
function signatureOf(systemRps: number, nodes: Node<ComponentNodeData>[], edges: Edge[]): string {
  return JSON.stringify({
    systemRps,
    nodes: nodes.map((n) => [
      n.id, n.data.kind, n.data.name,
      n.data.per_instance_rps ?? null, n.data.instances ?? null,
      n.data.base_latency_ms ?? null, n.data.monthly_cost_cents ?? null,
    ]),
    edges: edges.map((e) => [e.source, e.target]),
  });
}

const DRAG_KIND_TYPE = "application/keystone-kind";

function CanvasInner({ seed, onSimulated }: { seed?: CanvasSeed; onSimulated?: (arch: ArchMap) => void }) {
  const { screenToFlowPosition } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<ComponentNodeData>>(
    seed ? seedToFlowNodes(seed.nodes) : initialNodes,
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(
    seed ? seedToFlowEdges(seed.edges) : initialEdges,
  );
  const [systemRps, setSystemRps] = useState(seed?.systemRps ?? 10_000);
  // Seeded with a generated design → open with its engine verdict already shown (not stale, not blank).
  const [archMap, setArchMap] = useState<ArchMap | null>(seed?.archMap ?? null);
  const [simLoading, setSimLoading] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);
  const [mode, setMode] = useState<"simple" | "technical">("simple");
  const [activeFlowIndex, setActiveFlowIndex] = useState<number | null>(null);
  const idCounter = useRef(0);

  const handleRename = useCallback(
    (id: string, name: string) => {
      setNodes((nds) => nds.map((n) => (n.id === id ? { ...n, data: { ...n.data, name } } : n)));
    },
    [setNodes],
  );

  const handleDelete = useCallback(
    (id: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== id));
      setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id));
    },
    [setNodes, setEdges],
  );

  const handleConnect = useCallback(
    (connection: Connection) => setEdges((eds) => addEdge(connection, eds)),
    [setEdges],
  );

  const addNode = useCallback(
    (kind: ComponentKind, position?: { x: number; y: number }) => {
      idCounter.current += 1;
      const id = `${kind}-${idCounter.current}`;
      const pos =
        position ??
        { x: 60 + ((nodes.length * 48) % 520), y: 60 + Math.floor((nodes.length * 48) / 520) * 150 };
      setNodes((nds) => nds.concat({ id, type: "component", position: pos, data: { kind, name: KIND_META[kind].label } }));
    },
    [nodes.length, setNodes],
  );

  // Drag a palette item onto the canvas to add it there (prototype/outputs/_canvas_prototype.html's
  // reference UX) — click-to-add above still works too, per the issue's "click or drag to add".
  const onCanvasDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const onCanvasDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const kind = e.dataTransfer.getData(DRAG_KIND_TYPE) as ComponentKind;
      if (!COMPONENT_KINDS.includes(kind)) return;
      addNode(kind, screenToFlowPosition({ x: e.clientX, y: e.clientY }));
    },
    [addNode, screenToFlowPosition],
  );

  // A verdict is only honest while it still describes the drawn topology. Anything that
  // changes the simulated shape (add/delete/rename/rewire a node or edge, or the offered
  // load) makes the last verdict stale — dragging a node's position, panning, or selecting
  // does not. Compared against the signature captured at the moment Simulate was last run.
  const topologySignature = useMemo(
    () => signatureOf(systemRps, nodes, edges),
    [nodes, edges, systemRps],
  );
  // If seeded with a generated design, its verdict already matches the drawn topology → not stale.
  const [simulatedSignature, setSimulatedSignature] = useState<string | null>(() =>
    seed?.archMap
      ? signatureOf(seed.systemRps ?? 10_000, seedToFlowNodes(seed.nodes), seedToFlowEdges(seed.edges))
      : null,
  );
  const isStale = archMap !== null && simulatedSignature !== topologySignature;

  async function handleSimulate() {
    setSimLoading(true);
    setSimError(null);
    setActiveFlowIndex(null);
    try {
      const payload: SimulateRequest = {
        name: "Canvas design",
        system_rps: systemRps,
        nodes: nodes.map((n) => ({
          id: n.id,
          kind: n.data.kind,
          name: n.data.name,
          ...(n.data.per_instance_rps ? { per_instance_rps: n.data.per_instance_rps } : {}),
          ...(n.data.instances ? { instances: n.data.instances } : {}),
          ...(n.data.base_latency_ms ? { base_latency_ms: n.data.base_latency_ms } : {}),
          ...(n.data.monthly_cost_cents ? { monthly_cost_cents: n.data.monthly_cost_cents } : {}),
        })),
        edges: edges.map((e) => [e.source, e.target] as [string, string]),
        render: true, // get the self-contained map HTML back too, so the studio can re-render the pretty view
      };
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body: ApiErrorBody = await res.json().catch(() => ({}) as ApiErrorBody);
        throw new Error(body.detail ?? `the engine rejected this topology (status ${res.status})`);
      }
      const data: ArchMap = await res.json();
      setSimulatedSignature(topologySignature);
      setArchMap(data);
      onSimulated?.(data); // hand the fresh verdict + rendered map up to the studio (map view reflects the edit)
    } catch (err) {
      setArchMap(null);
      setSimError(err instanceof Error ? err.message : "couldn't reach the simulate endpoint");
    } finally {
      setSimLoading(false);
    }
  }

  const archMapById = useMemo(() => {
    if (!archMap) return null;
    return Object.fromEntries(archMap.nodes.map((n) => [n.id, n]));
  }, [archMap]);

  const activeFlow = activeFlowIndex !== null ? (archMap?.flows[activeFlowIndex] ?? null) : null;

  const activeFlowNodeIds = useMemo(
    () => (activeFlow ? new Set(activeFlow.steps.map((s) => s.component_id)) : null),
    [activeFlow],
  );

  const activeFlowEdgeKeys = useMemo(() => {
    if (!activeFlow) return null;
    const keys = new Set<string>();
    for (let i = 0; i < activeFlow.steps.length - 1; i++) {
      keys.add(`${activeFlow.steps[i].component_id}->${activeFlow.steps[i + 1].component_id}`);
    }
    return keys;
  }, [activeFlow]);

  const displayEdges = useMemo(
    () =>
      edges.map((e) => {
        const inFlow = activeFlowEdgeKeys?.has(`${e.source}->${e.target}`) ?? false;
        const dimmed = activeFlowEdgeKeys !== null && !inFlow;
        return {
          ...e,
          animated: inFlow,
          style: {
            stroke: inFlow ? activeFlow?.color : "var(--cv-steel)",
            opacity: dimmed ? 0.15 : 1,
            strokeWidth: inFlow ? 2.5 : 1.5,
          },
        };
      }),
    [edges, activeFlowEdgeKeys, activeFlow],
  );

  const contextValue: CanvasDisplayValue = useMemo(
    () => ({ archMapById, mode, activeFlowNodeIds, isStale, onRename: handleRename, onDelete: handleDelete }),
    [archMapById, mode, activeFlowNodeIds, isStale, handleRename, handleDelete],
  );

  return (
    <div className="canvas-glass flex flex-col h-full min-h-0">
      <div className="cv-panel m-3 px-4 py-3 flex flex-wrap items-center gap-4">
        <span className="font-sans text-[10px] uppercase tracking-widest text-[var(--cv-muted)]">Palette</span>
        <div className="flex flex-wrap gap-1.5">
          {COMPONENT_KINDS.map((kind) => (
            <button
              key={kind}
              type="button"
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData(DRAG_KIND_TYPE, kind);
                e.dataTransfer.effectAllowed = "move";
              }}
              onClick={() => addNode(kind)}
              title={`${KIND_META[kind].role} — click or drag onto the canvas`}
              className="font-sans text-xs px-2 py-1 rounded border border-[var(--cv-steel)] text-[var(--cv-ink)] hover:border-[var(--cv-blue)] hover:text-[var(--cv-blue)] transition-colors duration-ui cursor-grab active:cursor-grabbing"
            >
              {KIND_META[kind].icon} {KIND_META[kind].label}
            </button>
          ))}
        </div>

        <label className="ml-auto flex items-center gap-2 font-sans text-xs text-[var(--cv-muted)]">
          offered load (rps)
          <input
            type="number"
            min={1}
            max={10_000_000}
            value={systemRps}
            onChange={(e) => setSystemRps(Math.max(1, Number(e.target.value) || 1))}
            className="w-24 bg-transparent border border-[var(--cv-steel)] rounded px-2 py-1 font-mono text-[var(--cv-ink)]"
          />
        </label>

        <div className="flex items-center rounded border border-[var(--cv-steel)] overflow-hidden">
          <button
            type="button"
            onClick={() => setMode("simple")}
            className={`font-sans text-xs px-2 py-1 transition-colors duration-ui ${
              mode === "simple" ? "bg-[var(--cv-blue)] text-[#04121f]" : "text-[var(--cv-muted)]"
            }`}
          >
            Simple
          </button>
          <button
            type="button"
            onClick={() => setMode("technical")}
            className={`font-sans text-xs px-2 py-1 transition-colors duration-ui ${
              mode === "technical" ? "bg-[var(--cv-blue)] text-[#04121f]" : "text-[var(--cv-muted)]"
            }`}
          >
            Technical
          </button>
        </div>

        <button
          type="button"
          onClick={handleSimulate}
          disabled={simLoading}
          className="font-sans text-xs font-semibold px-4 py-2 rounded bg-[var(--cv-blue)] text-[#04121f] disabled:opacity-50 transition-opacity duration-ui"
        >
          {simLoading ? "Simulating…" : "Simulate"}
        </button>
      </div>

      {simError && (
        <div
          role="alert"
          className="cv-panel mx-3 mb-3 px-4 py-2 border-[var(--cv-red)] text-[var(--cv-red)] font-sans text-xs"
        >
          {simError}
        </div>
      )}

      <div
        className="flex-1 mx-3 mb-3 rounded-xl overflow-hidden border border-[var(--cv-line)]"
        onDragOver={onCanvasDragOver}
        onDrop={onCanvasDrop}
      >
        <CanvasDisplayContext.Provider value={contextValue}>
          <ReactFlow
            nodes={nodes}
            edges={displayEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={handleConnect}
            nodeTypes={nodeTypes}
            deleteKeyCode={["Backspace", "Delete"]}
            fitView
            colorMode="dark"
          >
            <Background color="var(--cv-line)" gap={24} />
            <Controls />
          </ReactFlow>
        </CanvasDisplayContext.Provider>
      </div>

      {archMap && (
        <div className="cv-panel mx-3 mb-3 p-4 flex flex-col gap-3 max-h-64 overflow-y-auto">
          {isStale && (
            <div className="font-sans text-xs text-[var(--cv-amber)] border border-[var(--cv-amber)] rounded px-2 py-1 w-fit">
              ⚠ topology changed since this verdict — hit Simulate again
            </div>
          )}
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
            <span className="font-mono text-[10px] px-2 py-0.5 rounded border border-[var(--cv-blue)] text-[var(--cv-blue)] uppercase tracking-wide">
              {archMap.meta.accuracy_level}
            </span>
            <span className="font-sans text-xs text-[var(--cv-muted)]">confidence: {archMap.meta.confidence}</span>
            {archMap.verdict.bottleneck_id && (
              <span className="font-sans text-xs text-[var(--cv-ink)]">
                bottleneck: <strong className="font-mono">{archMap.verdict.bottleneck_name}</strong>
                {archMap.verdict.bottleneck_utilization !== null &&
                  ` at ${Math.round(archMap.verdict.bottleneck_utilization * 100)}%`}
              </span>
            )}
            <span className="font-sans text-xs text-[var(--cv-ink)]">
              safe RPS:{" "}
              <span className="font-mono">
                {archMap.verdict.breakpoint_rps_safe !== null
                  ? Math.round(archMap.verdict.breakpoint_rps_safe)
                  : "unbounded"}
              </span>
            </span>
            <span className="font-sans text-xs text-[var(--cv-ink)]">
              cost:{" "}
              <span className="font-mono">${(archMap.verdict.monthly_cost_cents / 100).toLocaleString()}/mo</span>
            </span>
            {archMap.verdict.spofs.length > 0 && (
              <span className="font-sans text-xs text-[var(--cv-red)]">SPOFs: {archMap.verdict.spofs.join(", ")}</span>
            )}
          </div>

          {archMap.flows.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-sans text-[10px] uppercase tracking-widest text-[var(--cv-muted)] mr-1">
                journeys
              </span>
              {archMap.flows.map((flow, i) => (
                <button
                  key={flow.name}
                  type="button"
                  onClick={() => setActiveFlowIndex(activeFlowIndex === i ? null : i)}
                  className="font-mono text-[10px] px-2 py-1 rounded border transition-colors duration-ui"
                  style={{
                    borderColor: flow.color,
                    color: activeFlowIndex === i ? "#04121f" : flow.color,
                    background: activeFlowIndex === i ? flow.color : "transparent",
                  }}
                >
                  {flow.name}
                </button>
              ))}
              {activeFlow?.latency && (
                <span className="font-mono text-[10px] text-[var(--cv-muted)] ml-2">
                  p50 {activeFlow.latency.p50_ms.toFixed(1)}ms · p95 {activeFlow.latency.p95_ms.toFixed(1)}ms · p99{" "}
                  {activeFlow.latency.p99_ms.toFixed(1)}ms
                </span>
              )}
            </div>
          )}

          {archMap.caveats.length > 0 && (
            <div className="flex flex-col gap-1">
              <span className="font-sans text-[10px] uppercase tracking-widest text-[var(--cv-amber)]">
                where this is wrong
              </span>
              <ul className="font-sans text-xs text-[var(--cv-muted)] list-disc list-inside flex flex-col gap-0.5">
                {archMap.caveats.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// screenToFlowPosition (for drag-to-add) only works inside a <ReactFlowProvider>, so the
// provider wraps the whole editor, not just the <ReactFlow> element. `seed` opens the canvas on a
// generated design (the studio passes it + a `key` so a new generation remounts fresh); omitted, it
// opens on the starter fixture.
export function CanvasEditor(
  { seed, onSimulated }: { seed?: CanvasSeed; onSimulated?: (arch: ArchMap) => void } = {},
) {
  return (
    <ReactFlowProvider>
      <CanvasInner seed={seed} onSimulated={onSimulated} />
    </ReactFlowProvider>
  );
}
