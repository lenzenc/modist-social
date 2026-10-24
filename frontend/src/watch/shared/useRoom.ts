import { useMemo } from "react";
import { useStore } from "../../store";
import { placeAll, type Spot } from "../../taproom/layout";
import type { Person, Presence } from "../../types";

export interface Guest {
  person: Person;
  presence: Presence;
  spot: Spot;
  bartender: boolean;
  /** "bar" | "inside-tables" | "patio" | "ordering" (bartenders count as behind the bar). */
  zone: string;
}

/** Everyone in the taproom right now: who they are, how they feel, and where the floor plan puts them. */
export function useRoom(): Guest[] {
  const people = useStore((s) => s.people);
  const presence = useStore((s) => s.presence);
  const onShift = useStore((s) => s.clock?.on_shift);
  return useMemo(() => {
    const list = Object.values(presence).filter((p) => people[p.id]);
    const spots = placeAll(list, (id) => people[id]?.role === "bartender", onShift ?? []);
    return list.map((p) => {
      const person = people[p.id];
      const bartender = person.role === "bartender";
      return { person, presence: p, spot: spots[p.id], bartender, zone: bartender ? "staff" : p.location ?? "ordering" };
    });
  }, [people, presence, onShift]);
}
