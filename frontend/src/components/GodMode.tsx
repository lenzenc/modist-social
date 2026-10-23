import { useState } from "react";
import { useStore } from "../store";
import type { GodAssessment } from "../types";

const REACH = ["Only fans care", "A few care", "Plenty care", "Most care", "Everyone's talking"];
const SPLIT = ["Everyone agrees", "Friendly rivalry", "Some disagree", "Sides form", "Picks sides, gets ugly"];

function Scale({ label, hints, value, onChange }: {
  label: string;
  hints: string[];
  value: number;
  onChange: (n: number) => void;
}) {
  return (
    <label className="mt-2 block text-xs">
      <span className="flex justify-between">
        <span className="font-semibold">{label}</span>
        <span className="text-[var(--muted)]">{hints[value - 1]}</span>
      </span>
      <input
        type="range"
        min={1}
        max={5}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-amber-500"
      />
    </label>
  );
}

export function GodMode() {
  const god = useStore((s) => s.clock?.god ?? null);
  const { setGod, clearGod, assessGod } = useStore();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [read, setRead] = useState<(GodAssessment & { text: string }) | null>(null);
  const [reach, setReach] = useState(3);
  const [split, setSplit] = useState(2);
  const [busy, setBusy] = useState(false);

  // A reading belongs to the text it was made from; editing the text discards it.
  const current = read && read.text === text.trim() ? read : null;

  const readRoom = async () => {
    const t = text.trim();
    if (!t) return;
    setBusy(true);
    try {
      const a = await assessGod(t);
      setRead({ ...a, text: t });
      setReach(a.reach);
      setSplit(a.divisiveness);
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    const t = text.trim();
    if (!t) return;
    setBusy(true);
    try {
      // Without a reading the server scores it; with one, the sliders are the user's final say.
      await (current ? setGod(t, reach, split) : setGod(t));
      setText("");
      setRead(null);
      setOpen(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        title={god?.text}
        style={god ? { backgroundColor: `rgb(245 158 11 / ${0.12 + 0.4 * god.heat})` } : undefined}
        className={`cursor-pointer rounded-md border px-3 py-1 text-sm font-semibold ${
          god ? "border-amber-500" : "border-[var(--border)] hover:bg-black/[0.05]"
        }`}
      >
        ⚡ God Mode{god && `: ${god.text.length > 24 ? god.text.slice(0, 24) + "…" : god.text}`}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 rounded-lg border border-[var(--border)] bg-[var(--bg,white)] p-3 shadow-lg">
          <div className="mb-1 text-sm font-semibold">What just happened in town?</div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={280}
            rows={3}
            placeholder="The stock market crashed today / the local team won the championship"
            className="w-full rounded-md border border-[var(--border)] bg-transparent p-2 text-sm"
          />
          {current ? (
            <>
              <Scale label="Reach" hints={REACH} value={reach} onChange={setReach} />
              <Scale label="Divisiveness" hints={SPLIT} value={split} onChange={setSplit} />
              <div className="mt-2 text-xs text-[var(--muted)]">
                Sides: {current.sides[0]} vs. {current.sides[1]}
                {current.reason && <div className="mt-1">{current.reason}</div>}
              </div>
            </>
          ) : (
            <div className="mt-2 text-xs text-[var(--muted)]">
              Read the room to see how far this reaches and how much it divides people, then adjust.
            </div>
          )}
          {god && (
            <div className="mt-2 text-xs text-[var(--muted)]">
              <div>Active: {god.text}</div>
              <div>
                Reach {god.reach}/5 · Divisiveness {god.divisiveness}/5 · {god.sides[0]} vs. {god.sides[1]}
              </div>
              <div className="mt-1 flex items-center gap-2">
                Heat
                <div className="h-1.5 flex-1 rounded bg-[var(--track)]">
                  <div className="h-full rounded bg-amber-500" style={{ width: `${Math.round(god.heat * 100)}%` }} />
                </div>
              </div>
            </div>
          )}
          <div className="mt-3 flex gap-2">
            <button
              onClick={readRoom}
              disabled={busy || !text.trim()}
              className="cursor-pointer rounded-md border border-[var(--border)] px-3 py-1 text-sm font-semibold disabled:opacity-50"
            >
              {busy && !current ? "Reading…" : "Read the room"}
            </button>
            <button
              onClick={submit}
              disabled={busy || !text.trim()}
              className="cursor-pointer rounded-md bg-amber-500 px-3 py-1 text-sm font-semibold text-black disabled:opacity-50"
            >
              Set the mood
            </button>
            {god && (
              <button
                onClick={async () => { await clearGod(); setOpen(false); }}
                className="cursor-pointer rounded-md border border-[var(--border)] px-3 py-1 text-sm font-semibold"
              >
                Turn off
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
