import type { Tonight } from "../../types";
import { moodColor, buzzColor } from "../shared/scales";

export interface Pt {
  t: number;
  loc: string | null;
  thread: number | null;
  mood: number;
  buzz: number;
  battery: number;
  drinks: number;
  need: string;
  cut: boolean;
}

export interface Run {
  loc: string | null;
  thread: number | null;
  t0: number;
  t1: number;
}

export interface Shade { t0: number; t1: number; color: string }

export interface Person {
  id: string;
  pts: Pt[];
  first: number;
  last: number;
  runs: Run[];
  mood: Shade[];
  buzz: Shade[];
  beads: number[];
  needs: { t: number; need: string }[];
  cuts: number[];
}

export interface Night {
  t0: number;
  samples: number[];
  people: Person[];
  step: number;
}

const merge = <T extends { t1: number }>(list: T[], same: (a: T, b: T) => boolean): T[] => {
  const out: T[] = [];
  for (const x of list) {
    const prev = out[out.length - 1];
    if (prev && same(prev, x)) prev.t1 = x.t1;
    else out.push({ ...x });
  }
  return out;
};

/** Turn the night log into one record per person: where they were, in a chat or alone, how they felt, what they drank. */
export function buildNight(tonight: Tonight, nowMs: number): Night | null {
  if (!tonight.opened || !tonight.samples.length) return null;
  const times = tonight.samples.map((s) => new Date(s.t).getTime());
  const step = times.length > 1 ? Math.min(...times.slice(1).map((t, i) => t - times[i]).filter((d) => d > 0)) : 5 * 60_000;
  const byId = new Map<string, Pt[]>();
  tonight.samples.forEach((s, i) => {
    for (const [id, loc, thread, mood, buzz, battery, drinks, need, cut] of s.p) {
      if (!byId.has(id)) byId.set(id, []);
      byId.get(id)!.push({ t: times[i], loc, thread, mood, buzz, battery, drinks: drinks ?? 0, need: need ?? "", cut: !!cut });
    }
  });
  const people: Person[] = [];
  for (const [id, pts] of byId) {
    const end = (i: number) => (i + 1 < pts.length && pts[i + 1].t - pts[i].t <= step * 1.5 ? pts[i + 1].t : Math.min(pts[i].t + step, Math.max(nowMs, pts[i].t + 1)));
    const spans = pts.map((p, i) => ({ ...p, t0: p.t, t1: end(i) }));
    const runs = merge(
      spans.map((p) => ({ loc: p.loc, thread: p.thread, t0: p.t0, t1: p.t1 })),
      (a, b) => a.loc === b.loc && a.thread === b.thread && b.t0 <= a.t1 + 1,
    );
    const mood = merge(
      spans.map((p) => ({ t0: p.t0, t1: p.t1, color: moodColor(Math.round(p.mood * 8) / 8) })),
      (a, b) => a.color === b.color && b.t0 <= a.t1 + 1,
    );
    const buzz = merge(
      spans.filter((p) => p.buzz >= 0.1).map((p) => ({ t0: p.t0, t1: p.t1, color: buzzColor(Math.round(p.buzz * 10) / 10) })),
      (a, b) => a.color === b.color && b.t0 <= a.t1 + 1,
    );
    const beads: number[] = [];
    pts.forEach((p, i) => {
      const prev = i ? pts[i - 1].drinks : 0;
      for (let k = prev; k < p.drinks; k++) beads.push(p.t + ((k - prev + 0.5) / Math.max(1, p.drinks - prev)) * step * 0.9);
    });
    const needs = pts.filter((p, i) => p.need && (!i || pts[i - 1].need !== p.need)).map((p) => ({ t: p.t, need: p.need }));
    const cuts = pts.filter((p, i) => p.cut && (!i || !pts[i - 1].cut)).map((p) => p.t);
    people.push({ id, pts, first: pts[0].t, last: spans[spans.length - 1].t1, runs, mood, buzz, beads, needs, cuts });
  }
  return { t0: new Date(tonight.opened).getTime(), samples: times, people, step };
}
