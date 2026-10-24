import { useMemo, useState } from "react";
import { ZONE_LABEL, ZONES, batteryColor, buzzColor, moodColor, NEED_WORD, tint } from "../shared/scales";
import type { Guest } from "../shared/useRoom";

const worthALook = (g: Guest) => {
  const p = g.presence;
  return !g.bartender && (!!p.cut_off || p.tier === "drunk" || p.tier === "wasted" || (p.battery ?? 1) < 0.25 || (p.mood ?? 0) < -0.3);
};

const why = (g: Guest): string => {
  const p = g.presence;
  if (p.cut_off) return "cut off";
  if (p.tier === "wasted" || p.tier === "drunk") return p.tier;
  if (p.need) return NEED_WORD[p.need] ?? p.need;
  if ((p.mood ?? 0) < -0.3) return "irritable";
  if ((p.battery ?? 1) < 0.25) return "spent";
  if (p.busy) return "on phone";
  return "";
};

function Row({ g, selected, pinned, onSelect, onPin }: { g: Guest; selected: boolean; pinned: boolean; onSelect: () => void; onPin: () => void }) {
  const p = g.presence;
  const seat = p.stool != null ? `S${p.stool + 1}` : p.table != null ? `T${p.table + 1}` : "";
  const note = why(g);
  return (
    <li className={`tw-row${selected ? " is-selected" : ""}`}>
      <button className="tw-row-main" onClick={onSelect} aria-pressed={selected}>
        <span className="tw-chip" style={{ background: tint(g.person.color) }} aria-hidden>
          {g.person.display.replace(/"/g, "").split(/\s+/).slice(0, 2).map((w) => w[0]).join("")}
        </span>
        <span className="tw-name">{g.person.short}</span>
        <span className="tw-dot" style={{ background: moodColor(p.mood) }} title={`Mood ${(p.mood ?? 0).toFixed(2)}`} />
        <span className="tw-bars" aria-hidden>
          <i style={{ width: `${Math.max(6, (p.buzz ?? 0) * 100)}%`, background: buzzColor(p.buzz) }} />
          <i style={{ width: `${Math.max(6, (p.battery ?? 1) * 100)}%`, background: batteryColor(p.battery) }} />
        </span>
        <span className="tw-note">{note || seat}</span>
      </button>
      <button className={`tw-pin${pinned ? " on" : ""}`} onClick={onPin} aria-label={pinned ? `Unpin ${g.person.short}` : `Pin ${g.person.short}`} aria-pressed={pinned}>
        <svg viewBox="0 0 12 12" width="12" height="12"><path d="M6 1l1.5 3.3 3.5.4-2.6 2.4.7 3.5L6 8.8 2.9 10.6l.7-3.5L1 4.7l3.5-.4z" /></svg>
      </button>
    </li>
  );
}

export function Roster({ guests, selected, pinned, onSelect, onPin }: {
  guests: Guest[];
  selected: string | null;
  pinned: Set<string>;
  onSelect: (id: string) => void;
  onPin: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const [onlyLook, setOnlyLook] = useState(false);
  const look = useMemo(() => guests.filter(worthALook).length, [guests]);

  const groups = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const keep = guests.filter((g) => (!needle || g.person.display.toLowerCase().includes(needle)) && (!onlyLook || worthALook(g)));
    const by = (zone: string) =>
      keep
        .filter((g) => g.zone === zone)
        .sort((a, b) => Number(pinned.has(b.person.id)) - Number(pinned.has(a.person.id)) || a.person.short.localeCompare(b.person.short));
    return [...ZONES, "staff"].map((z) => ({ zone: z, list: by(z) })).filter((g) => g.list.length);
  }, [guests, q, onlyLook, pinned]);

  return (
    <aside className="tw-roster" aria-label="Who is here">
      <div className="tw-roster-head">
        <h2>Who is here <span>{guests.filter((g) => !g.bartender).length}</span></h2>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find someone" aria-label="Find someone" />
        <button className={`tw-toggle${onlyLook ? " on" : ""}`} onClick={() => setOnlyLook((v) => !v)} aria-pressed={onlyLook}>
          Worth a look <b>{look}</b>
        </button>
        <div className="tw-key" aria-hidden><span>mood</span><span>buzz / energy</span></div>
      </div>
      <div className="tw-roster-scroll">
        {groups.map(({ zone, list }) => (
          <section key={zone}>
            <h3>{ZONE_LABEL[zone]} <span>{list.length}</span></h3>
            <ul>
              {list.map((g) => (
                <Row key={g.person.id} g={g} selected={selected === g.person.id} pinned={pinned.has(g.person.id)} onSelect={() => onSelect(g.person.id)} onPin={() => onPin(g.person.id)} />
              ))}
            </ul>
          </section>
        ))}
        {!groups.length && <p className="tw-empty">{guests.length ? "No one matches." : "The taproom is empty. Doors open soon."}</p>}
      </div>
    </aside>
  );
}
