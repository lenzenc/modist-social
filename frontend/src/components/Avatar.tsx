import { useStore } from "../store";
import { initials } from "../util";

export function Avatar({ id, size = 36, ring = false, round = false }: { id: string; size?: number; ring?: boolean; round?: boolean }) {
  const p = useStore((s) => s.people[id]);
  const openProfile = useStore((s) => s.openProfile);
  const shape = round ? "rounded-full" : "rounded-md";
  if (!p) return <div style={{ width: size, height: size }} className={`${shape} bg-neutral-400`} />;
  return (
    <button
      onClick={() => openProfile(id)}
      title={`${p.display} (${p.pronouns})`}
      style={{ width: size, height: size, background: p.color, fontSize: size * 0.4 }}
      className={`flex shrink-0 cursor-pointer items-center justify-center ${shape} font-bold text-white ${
        ring ? "ring-2 ring-[var(--canvas)]" : ""
      }`}
    >
      {initials(p.display)}
    </button>
  );
}

export function Name({ id }: { id: string | null }) {
  const p = useStore((s) => (id ? s.people[id] : undefined));
  const openProfile = useStore((s) => s.openProfile);
  if (!p) return <span className="font-bold">Modist</span>;
  return (
    <button onClick={() => openProfile(p.id)} className="cursor-pointer font-bold hover:underline">
      {p.display}
      {p.role === "bartender" && (
        <span className="ml-1.5 rounded bg-[var(--badge-bg,#fef3c7)] px-1 py-px align-middle text-[10px] font-semibold text-[var(--badge-ink,#92400e)]">
          BARTENDER
        </span>
      )}
    </button>
  );
}
