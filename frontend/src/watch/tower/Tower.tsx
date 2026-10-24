import "@fontsource/barlow-condensed/400.css";
import "@fontsource/barlow-condensed/500.css";
import "@fontsource/barlow-condensed/600.css";
import "@fontsource-variable/public-sans";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Controls } from "../../components/Controls";
import { useStore } from "../../store";
import { fmtDayTime } from "../../util";
import { useLive } from "../shared/useLive";
import { useRoom } from "../shared/useRoom";
import { useWatch } from "../shared/useTonight";
import { Floor } from "./Floor";
import { Rack } from "./Rack";
import { Roster } from "./Roster";
import { Timeline } from "./Timeline";
import "./tower.css";

const MAX_FOLLOW = 3;
const PINS_KEY = "tower.pins";

function loadPins(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(PINS_KEY) ?? "[]"));
  } catch {
    return new Set();
  }
}

function Mark() {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden className="tw-mark-svg">
      <circle cx="12" cy="12" r="10" fill="none" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="5.5" fill="none" strokeWidth="1.2" />
      <path d="M12 12 L19 7" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="12" r="1.6" />
    </svg>
  );
}

export default function Tower() {
  useWatch(10_000);
  const guests = useRoom();
  const live = useLive();
  const clock = useStore((s) => s.clock);
  const banner = useStore((s) => s.banner);
  const openProfile = useStore((s) => s.openProfile);

  const [selected, setSelected] = useState<string | null>(null);
  const [tracked, setTracked] = useState<string | null>(null);
  const [pinned, setPinned] = useState<Set<string>>(loadPins);
  const [followed, setFollowed] = useState<number[]>([]);
  const seeded = useRef(false);

  const follow = useCallback((id: number) => {
    setFollowed((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id].slice(-MAX_FOLLOW)));
  }, []);

  const select = useCallback((id: string | null) => {
    setSelected(id);
    void openProfile(id);
  }, [openProfile]);

  const track = useCallback((id: string | null) => {
    setTracked(id);
    if (id) select(id);
  }, [select]);

  const pin = useCallback((id: string) => {
    setPinned((cur) => {
      const next = new Set(cur);
      if (!next.delete(id)) next.add(id);
      try { localStorage.setItem(PINS_KEY, JSON.stringify([...next])); } catch { /* private window */ }
      return next;
    });
  }, []);

  // Start with the two liveliest chats so the dock is never empty on arrival.
  useEffect(() => {
    if (seeded.current) return;
    const chats = live.filter((l) => l.thread.kind === "chat" && l.msgs.length > 1).slice(0, 2);
    if (chats.length) {
      seeded.current = true;
      setFollowed(chats.map((l) => l.thread.id));
    }
  }, [live]);

  // Following a person also listens to whatever conversation they are in.
  const trackedThread = tracked ? guests.find((g) => g.person.id === tracked)?.presence.thread_id ?? null : null;
  useEffect(() => {
    if (trackedThread != null) setFollowed((cur) => (cur.includes(trackedThread) ? cur : [...cur, trackedThread].slice(-MAX_FOLLOW)));
  }, [trackedThread]);

  // A person who leaves can no longer be selected or followed.
  useEffect(() => {
    const here = new Set(guests.map((g) => g.person.id));
    if (selected && guests.length && !here.has(selected)) setSelected(null);
    if (tracked && guests.length && !here.has(tracked)) setTracked(null);
  }, [guests, selected, tracked]);

  const ended = useMemo(() => new Set(followed.filter((id) => !live.some((l) => l.thread.id === id))), [followed, live]);
  const heated = live.filter((l) => l.thread.tension && l.thread.tension >= 0.6).length;
  const patrons = guests.filter((g) => !g.bartender).length;

  return (
    <div className="tw">
      <header className="tw-top">
        <div className="tw-brand"><Mark /><b>Modist Tower</b></div>
        <div className="tw-clock">
          {clock ? <b>{fmtDayTime(clock.sim_now)}</b> : null}
          <span className={clock?.open ? "open" : ""}>{clock ? (clock.open ? "Open" : "Closed") : "Connecting"}</span>
          {clock?.occasion ? <span>{clock.occasion}</span> : null}
          <span>{patrons} guests</span>
          {heated > 0 && <span className="hot">{heated} heated</span>}
        </div>
        <div className="tw-controls"><Controls /></div>
      </header>
      {banner && <div className="tw-banner">{banner}</div>}
      <div className="tw-body">
        <Roster guests={guests} selected={selected} pinned={pinned} onSelect={(id) => select(id === selected ? null : id)} onPin={pin} />
        <main className="tw-center">
          <Floor guests={guests} live={live} selected={selected} tracked={tracked} pinned={pinned} followed={followed} onSelect={select} onTrack={track} onPin={pin} onFollow={follow} />
          <Timeline />
        </main>
        <Rack live={live} followed={followed} ended={ended} onToggle={follow} />
      </div>
    </div>
  );
}
