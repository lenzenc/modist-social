import { Html } from "@react-three/drei";
import { useMemo } from "react";
import { useStore } from "../store";
import { placeAll, TABLES, type Vec2 } from "./layout";

/** One speech bubble per live conversation, anchored over its group. Click to open the transcript. */
export function Bubbles() {
  const threads = useStore((s) => s.threads);
  const presence = useStore((s) => s.presence);
  const people = useStore((s) => s.people);
  const typing = useStore((s) => s.typing);
  const onShift = useStore((s) => s.clock?.on_shift);
  const open = useStore((s) => s.openThread);
  const openThreadPane = useStore((s) => s.openThreadPane);

  const spots = useMemo(
    () => placeAll(Object.values(presence), (id) => people[id]?.role === "bartender", onShift ?? []),
    [presence, people, onShift],
  );

  // Anchor each live conversation over its group, then lift bubbles that would land on top of an earlier one.
  const anchors = Object.values(threads).flatMap((t) => {
    const ids = t.participants.filter((id) => presence[id] && (presence[id].thread_id === t.id || people[id]?.role === "bartender"));
    const at = ids.map((id) => spots[id]?.pos).filter((p): p is Vec2 => !!p);
    if (at.length === 0) return [];
    let [x, z] = [at.reduce((a, p) => a + p[0], 0) / at.length, at.reduce((a, p) => a + p[1], 0) / at.length];
    if (t.table != null && TABLES[t.channel]?.[t.table]) [x, z] = TABLES[t.channel][t.table];
    return [{ t, x, z, lift: 0 }];
  });
  anchors.sort((a, b) => a.x - b.x || a.z - b.z);
  anchors.forEach((a, i) => {
    a.lift = anchors.slice(0, i).filter((o) => Math.abs(o.x - a.x) < 3.2 && Math.abs(o.z - a.z) < 1.5).length * 0.75;
  });

  return (
    <>
      {anchors.map(({ t, x, z, lift }) => {
        const talking = (typing[t.id] ?? []).length > 0;
        const order = t.kind === "order";
        const text = t.last?.text ?? t.root_text;
        return (
          <Html key={t.id} position={[x, 2.1 + lift, z]} center zIndexRange={[10, 0]}>
            <button
              onClick={() => void openThreadPane(t.id)}
              className={`bubble-in w-max min-w-[7rem] max-w-[14rem] cursor-pointer rounded-xl border px-2.5 py-1.5 text-left text-xs shadow-md ${
                open === t.id ? "border-amber-500 bg-amber-50 text-black" : "border-[var(--border)] bg-[var(--canvas)] text-[var(--ink)]"
              }`}
            >
              {order ? "🍺 " : ""}
              <span className="line-clamp-2">{text}</span>
              {talking && (
                <span className="dots ml-1 text-[var(--muted)]">
                  <span>•</span>
                  <span>•</span>
                  <span>•</span>
                </span>
              )}
            </button>
          </Html>
        );
      })}
    </>
  );
}
