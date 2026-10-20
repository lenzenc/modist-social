import { useEffect } from "react";
import { Controls } from "../components/Controls";
import { RightPane } from "../components/RightPane";
import { StatsBar } from "../components/StatsBar";
import { useStore } from "../store";
import { Scene } from "./Scene";

export default function TaproomPage() {
  const connect = useStore((s) => s.connect);
  const loadLiveThreads = useStore((s) => s.loadLiveThreads);
  const connected = useStore((s) => s.connected);
  const banner = useStore((s) => s.banner);
  const control = useStore((s) => s.control);
  const clock = useStore((s) => s.clock);
  const crowd = useStore((s) => s.clock?.crowd ?? 0);

  useEffect(() => connect(), [connect]);
  useEffect(() => {
    if (connected) void loadLiveThreads();
  }, [connected, loadLiveThreads]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-2.5">
        <div>
          <div className="text-lg font-bold">Modist Social · floor</div>
          <div className="text-xs text-[var(--muted)]">
            {crowd} guests{clock && !clock.open ? " · closed" : ""} · click a speech bubble or a person
          </div>
        </div>
        <div className="flex items-center gap-3">
          <a href="/" className="rounded-md border border-[var(--border)] px-3 py-1 text-sm font-semibold hover:bg-black/[0.05]">
            Chat ↗
          </a>
          <Controls />
        </div>
      </div>
      {banner && (
        <div className="flex items-center justify-between bg-amber-100 px-5 py-2 text-sm font-semibold text-amber-900">
          <span>{banner}</span>
          {/budget/i.test(banner) && (
            <button
              onClick={() => control({ action: "resume", extra_budget: 1 })}
              className="cursor-pointer rounded bg-amber-900 px-3 py-1 text-white"
            >
              Add $1 and resume
            </button>
          )}
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1 overflow-hidden">
          <div className="absolute inset-0">
            <Scene />
          </div>
        </div>
        <RightPane />
      </div>
      <StatsBar />
    </div>
  );
}
