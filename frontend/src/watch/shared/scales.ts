// One set of scales for every watch view, so the same mood reads the same colour wherever you look.

type RGB = [number, number, number];

const hex = (h: string): RGB => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as RGB;
const toHex = (c: RGB) => "#" + c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
const clamp = (v: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));

/** Blend through a list of evenly spaced colour stops; t runs 0..1. */
export function ramp(stops: string[], t: number): string {
  const x = clamp(t) * (stops.length - 1);
  const i = Math.min(Math.floor(x), stops.length - 2);
  const a = hex(stops[i]);
  const b = hex(stops[i + 1]);
  const f = x - i;
  return toHex(a.map((v, k) => v + (b[k] - v) * f) as RGB);
}

/** Mood -1..1: cold slate-blue when low, neutral sand in the middle, amber-orange when high. */
export const MOOD_STOPS = ["#2f5f9e", "#7fa3c7", "#d8d3c4", "#eaa84b", "#d9692a"];
export const moodColor = (m = 0) => ramp(MOOD_STOPS, (clamp(m, -1, 1) + 1) / 2);

/** Buzz 0..1: clear to deep wine, with the drunk tiers sitting in the top half. */
export const BUZZ_STOPS = ["#e7e3d6", "#e8c46a", "#d9822b", "#a8322a", "#5a1424"];
export const buzzColor = (b = 0) => ramp(BUZZ_STOPS, b);

/** Social battery 1..0: full is a calm green, empty is grey. */
export const BATTERY_STOPS = ["#8c8f94", "#c9b25c", "#5f9a6b"];
export const batteryColor = (b = 1) => ramp(BATTERY_STOPS, b);

export const moodWord = (m = 0) => (m >= 0.4 ? "good" : m >= 0.1 ? "fine" : m > -0.25 ? "so-so" : m > -0.5 ? "irritable" : "down");
export const batteryWord = (b = 1) => (b > 0.66 ? "fresh" : b > 0.33 ? "fading" : "spent");

export const NEED_WORD: Record<string, string> = {
  restroom: "restroom",
  call: "phone call",
  air: "needs air",
  food: "wants food",
  smoke: "a smoke",
};

export const ZONE_LABEL: Record<string, string> = {
  ordering: "In line",
  bar: "At the bar",
  "inside-tables": "Inside tables",
  patio: "Patio",
  staff: "Behind the bar",
};
export const ZONES = ["ordering", "bar", "inside-tables", "patio"] as const;

/** Ink or white, whichever reads on this fill. */
export function onColor(fill: string): string {
  if (!fill.startsWith("#") || fill.length < 7) return "#14243a";
  const [r, g, b] = hex(fill).map((v) => v / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.55 ? "#14243a" : "#ffffff";
}

/** A pale wash of a person's own colour, for their initials chip. */
export const tint = (color: string, pct = 22) => `color-mix(in srgb, ${color} ${pct}%, white)`;
