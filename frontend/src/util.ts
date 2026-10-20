// Sim timestamps are naive ISO strings (no zone); Date() reads them as local time, which is what we want.
export const fmtTime = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

export const fmtDay = (iso: string) =>
  new Date(iso).toLocaleDateString([], { weekday: "short" });

export const fmtDayTime = (iso: string) => `${fmtDay(iso)} ${fmtTime(iso)}`;

export const initials = (name: string) =>
  name
    .replace(/"/g, "")
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();

export const money = (n: number) => `$${n.toFixed(n < 1 ? 3 : 2)}`;
export const kfmt = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n));

export const familiarityLabel = (f: number) =>
  f >= 75 ? "Close" : f >= 50 ? "Friend" : f >= 25 ? "Acquaintance" : "Met";
