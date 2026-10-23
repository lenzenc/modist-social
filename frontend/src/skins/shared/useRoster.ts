import { useMemo } from "react";
import { useStore } from "../../store";
import { STOOLS, TABLES } from "../../taproom/layout";
import type { Person, Presence, Thread } from "../../types";

export const AREAS = [
  { id: "bar", title: "At the bar", seat: "stool", cap: STOOLS.length },
  { id: "inside-tables", title: "Inside tables", seat: "table", cap: 0 },
  { id: "patio", title: "Patio", seat: "table", cap: 0 },
] as const;

/** Seated = a stool at the bar, or a numbered table inside / on the patio. Everyone else is standing. */
export const seatOf = (pr: Presence | undefined): [string, number] | null => {
  if (pr?.location === "bar" && pr.stool != null) return ["bar", pr.stool];
  if (pr?.location && pr.location in TABLES && pr.table != null) return [pr.location, pr.table];
  return null;
};

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** "Stool 4", "Table 3", "Patio table 2", "At the counter", "Standing, bar". */
export function seatLabel(pr: Presence | undefined): string {
  if (!pr?.location) return "Out";
  const seat = seatOf(pr);
  if (seat) {
    if (seat[0] === "bar") return `Stool ${seat[1] + 1}`;
    return `${seat[0] === "patio" ? "Patio table" : "Table"} ${seat[1] + 1}`;
  }
  if (pr.location === "ordering") return "At the counter";
  if (pr.location === "door") return "At the door";
  return `Standing, ${pr.location.replace("-", " ")}`;
}

/** Where a conversation is happening, from its channel and who is in it. */
export function threadPlace(t: Thread, presence: Record<string, Presence>): string {
  if (t.kind === "staff" || t.channel === "staff") return "Behind the bar";
  if (t.kind === "order" || t.channel === "ordering") return "At the counter";
  if (t.channel === "door") return "At the door";
  if (t.table != null) return `${t.channel === "patio" ? "Patio table" : "Table"} ${t.table + 1}`;
  const stools = t.participants.map((id) => presence[id]).filter((p) => p?.location === "bar" && p.stool != null).map((p) => p!.stool! + 1).sort((a, b) => a - b);
  if (stools.length > 1) return `Stools ${stools[0]}–${stools[stools.length - 1]}`;
  if (stools.length === 1) return `Stool ${stools[0]}`;
  return cap(t.channel.replace("-", " "));
}

export const TIER_COLOR: Record<string, string> = { tipsy: "#f6b73c", drunk: "#f07c2a", wasted: "#e5484d" };

export interface Roster {
  here: Person[];
  bartenders: Person[];
  patrons: Person[];
  seatOf: (id: string) => [string, number] | null;
  inArea: (area: string) => Person[];
  standing: Person[];
  byLocation: Record<string, Person[]>;
}

/** Who is in the taproom and where, derived from people + presence. Shared by the Slack sidebar and every skin. */
export function useRoster(): Roster {
  const people = useStore((s) => s.people);
  const presence = useStore((s) => s.presence);
  return useMemo(() => {
    const here = Object.values(people).filter((p) => presence[p.id]);
    const bartenders = here.filter((p) => p.role === "bartender");
    const patrons = here.filter((p) => p.role === "patron").sort((a, b) => a.short.localeCompare(b.short));
    const seat = (id: string) => seatOf(presence[id]);
    const inArea = (area: string) =>
      patrons.filter((p) => seat(p.id)?.[0] === area).sort((a, b) => seat(a.id)![1] - seat(b.id)![1]);
    const standing = patrons.filter((p) => !seat(p.id));
    const byLocation: Record<string, Person[]> = {};
    for (const p of here) (byLocation[presence[p.id].location ?? "door"] ??= []).push(p);
    return { here, bartenders, patrons, seatOf: seat, inArea, standing, byLocation };
  }, [people, presence]);
}
