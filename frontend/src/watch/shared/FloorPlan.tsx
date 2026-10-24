import { memo, type ReactNode } from "react";
import { BAR, COUNTER, DOORS, PATIO, ROOM, STOOLS, TABLES, TABLE_SIZE } from "../../taproom/layout";
import type { Thread } from "../../types";
import { initials } from "../../util";
import { onColor } from "./scales";
import type { Guest } from "./useRoom";

export interface Hull {
  id: string | number;
  /** Positions in plan units. */
  points: [number, number][];
  color: string;
  pulse?: boolean;
  dim?: boolean;
  onClick?: () => void;
}

export interface Pin {
  guest: Guest;
  fill: string;
  /** Outer ring colour, e.g. for a drunk tier or a pin. */
  ring?: string;
  selected?: boolean;
  dim?: boolean;
  label?: string;
}

interface Props {
  guests: Pin[];
  hulls?: Hull[];
  /** Straight lines between people, in plan units, e.g. the ties of the person you picked. */
  links?: { a: [number, number]; b: [number, number]; color: string; width?: number }[];
  onPerson?: (id: string) => void;
  onPersonDouble?: (id: string) => void;
  /** Zoom in on a point (plan units) with a smooth camera move; null shows the whole room. */
  focus?: [number, number] | null;
  /** Drawn above the hulls but under the people, in plan units (e.g. zone captions). */
  children?: ReactNode;
  className?: string;
}

const PAD = 0.9;
const W = ROOM.w + 1.4;
const H = PATIO.z + PATIO.d + 0.7;

function hullPath(points: [number, number][]): [number, number][] {
  if (points.length < 3) return points;
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o: number[], a: number[], b: number[]) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: [number, number][] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: [number, number][] = [];
  for (const p of [...pts].reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  return [...lower.slice(0, -1), ...upper.slice(0, -1)];
}

function HullShape({ h }: { h: Hull }) {
  const pts = hullPath(h.points);
  if (!pts.length) return null;
  const cls = `fp-hull${h.pulse ? " fp-pulse" : ""}${h.dim ? " fp-dim" : ""}`;
  const common = { className: cls, stroke: h.color, fill: h.color, strokeWidth: PAD * 2, strokeLinejoin: "round" as const, strokeLinecap: "round" as const };
  const click = h.onClick ? { onClick: h.onClick, style: { cursor: "pointer" } } : {};
  if (pts.length === 1) return <circle {...click} className={cls} cx={pts[0][0]} cy={pts[0][1]} r={PAD} fill={h.color} />;
  if (pts.length === 2) return <line {...click} {...common} x1={pts[0][0]} y1={pts[0][1]} x2={pts[1][0]} y2={pts[1][1]} />;
  return <polygon {...click} {...common} points={pts.map((p) => p.join(",")).join(" ")} />;
}

const Room = memo(function Room() {
  const [tw, td] = TABLE_SIZE;
  return (
    <g>
      <rect className="fp-patio" x={PATIO.x} y={PATIO.z} width={PATIO.w} height={PATIO.d} rx={0.25} />
      <rect className="fp-floor" x={0} y={0} width={ROOM.w} height={ROOM.d} rx={0.2} />
      {DOORS.map(([x, z]) => (
        <rect key={x} className="fp-door" x={x - 0.8} y={z - 0.08} width={1.6} height={0.16} />
      ))}
      <rect className="fp-bar" x={BAR.x} y={BAR.z} width={BAR.w} height={BAR.d} rx={0.12} />
      <rect className="fp-bar fp-counter" x={COUNTER.x} y={COUNTER.z} width={COUNTER.w} height={COUNTER.d} rx={0.12} />
      {STOOLS.map(([x, z]) => (
        <circle key={x} className="fp-stool" cx={x} cy={z} r={0.2} />
      ))}
      {[...TABLES["inside-tables"], ...TABLES.patio].map(([x, z]) => (
        <rect key={`${x}-${z}`} className="fp-table" x={x - tw / 2} y={z - td / 2} width={tw} height={td} rx={0.12} />
      ))}
    </g>
  );
});

const Person = memo(function Person({ pin, onPerson, onPersonDouble }: { pin: Pin; onPerson?: (id: string) => void; onPersonDouble?: (id: string) => void }) {
  const { guest, fill, ring, selected, dim } = pin;
  const [x, z] = guest.spot.pos;
  return (
    <g
      className={`fp-person${dim ? " fp-dim" : ""}${selected ? " fp-selected" : ""}`}
      style={{ transform: `translate(${x}px, ${z}px)`, cursor: onPerson ? "pointer" : undefined }}
      onClick={() => onPerson?.(guest.person.id)}
      onDoubleClick={() => onPersonDouble?.(guest.person.id)}
    >
      <title>{guest.person.display}</title>
      {ring && <circle className="fp-ring" r={0.46} fill="none" stroke={ring} strokeWidth={0.1} />}
      {selected && <circle className="fp-sel" r={0.62} fill="none" strokeWidth={0.07} />}
      {guest.bartender ? (
        <rect className="fp-node" x={-0.34} y={-0.34} width={0.68} height={0.68} rx={0.14} fill={fill} />
      ) : (
        <circle className="fp-node" r={0.34} fill={fill} />
      )}
      <text className="fp-init" textAnchor="middle" dy="0.1" fontSize={0.3} fill={onColor(fill)}>
        {initials(guest.person.display)}
      </text>
      {pin.label && (
        <text className="fp-name" textAnchor="middle" y={0.78} fontSize={0.34}>
          {pin.label}
        </text>
      )}
    </g>
  );
});

/**
 * The taproom from above, drawn from the same floor plan as the 3D page. Styling comes from CSS variables
 * and `.fp-*` classes set by each view; the colours of people and conversation outlines come from props.
 */
export function FloorPlan({ guests, hulls = [], links = [], focus, onPerson, onPersonDouble, children, className }: Props) {
  const K = 2.6;
  const cx = -0.7 + W / 2;
  const cy = -0.7 + H / 2;
  const camera = focus
    ? `translate(${cx}px, ${cy}px) scale(${K}) translate(${-focus[0]}px, ${-focus[1]}px)`
    : `translate(${cx}px, ${cy}px) scale(1) translate(${-cx}px, ${-cy}px)`;
  return (
    <svg className={className} viewBox={`${-0.7} ${-0.7} ${W} ${H}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label="Floor plan of the taproom">
      <g className="fp-camera" style={{ transform: camera }}>
      <Room />
      <g>{hulls.map((h) => <HullShape key={h.id} h={h} />)}</g>
      <g>
        {links.map((l, i) => (
          <line key={i} x1={l.a[0]} y1={l.a[1]} x2={l.b[0]} y2={l.b[1]} stroke={l.color} strokeWidth={l.width ?? 0.08} strokeLinecap="round" className="fp-link" />
        ))}
      </g>
      {children}
      <g>
        {guests.map((pin) => (
          <Person key={pin.guest.person.id} pin={pin} onPerson={onPerson} onPersonDouble={onPersonDouble} />
        ))}
      </g>
      </g>
    </svg>
  );
}

/** Who is in a conversation right now (people still attached to it, plus bartenders who took part). */
export function membersOf(thread: Thread, guests: Guest[]): Guest[] {
  return guests.filter((g) => g.presence.thread_id === thread.id || (g.bartender && thread.participants.includes(g.person.id) && thread.channel === "bar"));
}

/** Where a conversation sits on the plan: the positions of its members. */
export const threadPoints = (thread: Thread, guests: Guest[]): [number, number][] => membersOf(thread, guests).map((g) => g.spot.pos);
