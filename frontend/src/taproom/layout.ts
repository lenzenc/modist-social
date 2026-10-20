import type { Presence } from "../types";

// Floor plan in world units (1 unit ~ 60px of the modist.png sketch). x runs right, z runs toward the viewer.
export type Vec2 = [number, number];
export interface Spot {
  pos: Vec2;
  sit: boolean;
}

export const ROOM = { w: 20.3, d: 10.7 };
export const BAR = { x: 2.1, z: 1.9, w: 12.8, d: 1.1 };
export const COUNTER = { x: 15, z: 1.9, w: 1.95, d: 1.1 };
export const PATIO = { x: 5.45, z: 10.75, w: 9.4, d: 3.2 };
export const DOORS: Vec2[] = [[1.5, ROOM.d], [17.4, ROOM.d]];
export const CENTER: Vec2 = [10.2, 7];

export const STOOLS: Vec2[] = Array.from({ length: 14 }, (_, i) => [2.7 + i * 0.93, 3.5]);
const BARTENDER_SPOTS: Vec2[] = [[5.5, 1.35], [8.5, 1.35], [11.5, 1.35]];

export const TABLES: Record<string, Vec2[]> = {
  "high-tops": [3.7, 7.1, 10.1, 13.2].flatMap((x) => [4.8, 6.9].map((z): Vec2 => [x, z])).sort((a, b) => a[1] - b[1] || a[0] - b[0]),
  patio: [
    [7.2, 11.6], [12.8, 11.6],
    [7.2, 13.1], [12.8, 13.1],
  ],
};
export const TABLE_SIZE: Vec2 = [1.9, 1.1];
const SEATS: Vec2[] = [[-0.5, -0.9], [0.5, -0.9], [-0.5, 0.9], [0.5, 0.9]];

const QUEUE: Vec2[] = Array.from({ length: 9 }, (_, i) => [15.4 + (i % 3) * 0.65, 3.7 + Math.floor(i / 3) * 0.7]);
// Guests with no seat stand along the edge of their area.
const STANDING: Record<string, (i: number) => Vec2> = {
  "high-tops": (i) => [2.5 + (i % 12) * 1.3, 8.9 + Math.floor(i / 12) * 0.7],
  patio: (i) => [9.9 + ((i % 3) - 1) * 0.7, 12.3 + Math.floor(i / 3) * 0.6],
  bar: (i) => [2.6 + (i % 10) * 1.2, 4.3],
};

export const doorFor = (id: string): Vec2 => DOORS[[...id].reduce((a, c) => a + c.charCodeAt(0), 0) % DOORS.length];

/** Where each present person should be, derived purely from the sim's presence snapshot. */
export function placeAll(presence: Presence[], isBartender: (id: string) => boolean, onShift: string[]): Record<string, Spot> {
  const out: Record<string, Spot> = {};
  const byId = [...presence].sort((a, b) => a.id.localeCompare(b.id));
  const counters: Record<string, number> = {};
  const next = (key: string) => (counters[key] = (counters[key] ?? -1) + 1);

  const bartenders = byId.filter((p) => isBartender(p.id));
  bartenders.sort((a, b) => onShift.indexOf(a.id) - onShift.indexOf(b.id));
  bartenders.forEach((p, i) => (out[p.id] = { pos: BARTENDER_SPOTS[i % BARTENDER_SPOTS.length], sit: false }));

  for (const p of byId) {
    if (isBartender(p.id)) continue;
    const loc = p.location ?? "ordering";
    if (loc === "ordering") {
      out[p.id] = { pos: QUEUE[next("ordering") % QUEUE.length], sit: false };
    } else if (loc === "bar" && p.stool != null && STOOLS[p.stool]) {
      out[p.id] = { pos: STOOLS[p.stool], sit: true };
    } else if (p.table != null && TABLES[loc]?.[p.table]) {
      const seat = SEATS[next(`${loc}:${p.table}`) % SEATS.length];
      const [tx, tz] = TABLES[loc][p.table];
      out[p.id] = { pos: [tx + seat[0], tz + seat[1]], sit: true };
    } else {
      out[p.id] = { pos: (STANDING[loc] ?? STANDING.bar)(next(`stand:${loc}`)), sit: false };
    }
  }
  return out;
}
