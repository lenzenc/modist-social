import { useStore } from "../store";
import { GodMode } from "./GodMode";

const SPEEDS = [5, 15, 30, 60, 120, 240]
const CROWDS: [number, string][] = [[0.6, "Quiet"], [1, "Normal"], [1.6, "Busy"], [2.5, "Packed"]];

/** God Mode, pause, speed and crowd: shared by the chat header and the floor view. */
export function Controls() {
  const { control, clock } = useStore();
  if (!clock) return null;
  return (
    <>
      <GodMode />
      <button
        onClick={() => control({ action: clock.paused ? "resume" : "pause" })}
        className="cursor-pointer rounded-md border border-[var(--border)] px-3 py-1 text-sm font-semibold hover:bg-black/[0.05]"
      >
        {clock.paused ? "▶ Resume" : "⏸ Pause"}
      </button>
      <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
        Speed
        <select
          value={SPEEDS.includes(clock.speed) ? clock.speed : "custom"}
          onChange={(e) => control({ action: "speed", speed: Number(e.target.value) })}
          className="rounded-md border border-[var(--border)] bg-transparent px-2 py-1 text-[var(--ink)]"
        >
          {!SPEEDS.includes(clock.speed) && <option value="custom">{clock.speed}×</option>}
          {SPEEDS.map((s) => (
            <option key={s} value={s} className="text-black">
              {s}× ({s} sim min / min)
            </option>
          ))}
        </select>
        {clock.effective_speed < clock.speed - 0.5 && (
          <span className="text-xs" title="Conversations can't keep up with the chosen speed, so the clock is held back">
            held to {Math.round(clock.effective_speed)}×
          </span>
        )}
      </label>
      <label className="flex items-center gap-2 text-sm text-[var(--muted)]" title="How busy the room is: more guests arriving and more conversations. Sales follow.">
        Crowd
        <select
          value={clock.crowd_level}
          onChange={(e) => control({ action: "crowd", crowd: Number(e.target.value) })}
          className="rounded-md border border-[var(--border)] bg-transparent px-2 py-1 text-[var(--ink)]"
        >
          {CROWDS.map(([v, label]) => (
            <option key={v} value={v} className="text-black">{label}</option>
          ))}
        </select>
      </label>
    </>
  );
}
