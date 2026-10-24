import { useMemo, useState } from "react";
import { useStore } from "../../store";
import { FloorPlan, threadPoints, type Hull, type Pin } from "../shared/FloorPlan";
import { batteryColor, batteryWord, buzzColor, moodColor, moodWord, NEED_WORD, ramp, BATTERY_STOPS, BUZZ_STOPS, MOOD_STOPS, tint } from "../shared/scales";
import { placeOf, type Live } from "../shared/useLive";
import type { Guest } from "../shared/useRoom";
import { stripOf, STRIP_HULL, TOPIC_COLOR, TOPIC_WORD } from "./topics";

export type Lens = "mood" | "buzz" | "energy" | "ties" | "topic";
const LENSES: [Lens, string][] = [["mood", "Mood"], ["buzz", "Buzz"], ["energy", "Energy"], ["ties", "Ties"], ["topic", "Topic"]];
const TIE_GOOD = "#2f8a57";
const TIE_BAD = "#c8361e";
const NONE = "#c3ccd3";

function Legend({ lens }: { lens: Lens }) {
  const swatches = (stops: string[], words: [string, string]) => (
    <div className="tw-legend">
      <span>{words[0]}</span>
      {[0, 0.25, 0.5, 0.75, 1].map((t) => <i key={t} style={{ background: ramp(stops, t) }} />)}
      <span>{words[1]}</span>
    </div>
  );
  if (lens === "mood") return swatches(MOOD_STOPS, ["down", "good"]);
  if (lens === "buzz") return swatches(BUZZ_STOPS, ["sober", "wasted"]);
  if (lens === "energy") return swatches([...BATTERY_STOPS].reverse(), ["fresh", "spent"]);
  if (lens === "ties") return <div className="tw-legend"><i style={{ background: TIE_GOOD }} /><span>gets on with</span><i style={{ background: TIE_BAD }} /><span>friction</span><span className="tw-legend-note">Pick someone to see their ties</span></div>;
  return (
    <div className="tw-legend tw-legend-topics">
      {["beer", "town", "sports", "life", "gossip", "civic", "event"].map((k) => <span key={k}><i style={{ background: TOPIC_COLOR[k] }} />{TOPIC_WORD[k]}</span>)}
    </div>
  );
}

function PersonCard({ guest, pinned, tracked, onClose, onPin, onTrack }: {
  guest: Guest;
  pinned: boolean;
  tracked: boolean;
  onClose: () => void;
  onPin: () => void;
  onTrack: () => void;
}) {
  const profile = useStore((s) => (s.profile?.id === guest.person.id ? s.profile : null));
  const p = guest.presence;
  const st = profile?.state;
  return (
    <div className="tw-card" role="dialog" aria-label={guest.person.display}>
      <div className="tw-card-top">
        <span className="tw-chip big" style={{ background: tint(guest.person.color) }}>{guest.person.display.replace(/"/g, "").split(/\s+/).slice(0, 2).map((w) => w[0]).join("")}</span>
        <div>
          <b>{guest.person.display}</b>
          <small>{guest.person.job}</small>
        </div>
        <button onClick={onClose} aria-label="Close">×</button>
      </div>
      <dl>
        <dt>Feels</dt><dd><i style={{ background: moodColor(p.mood) }} />{moodWord(p.mood)}</dd>
        <dt>Drinking</dt><dd>{p.drink || "nothing yet"}{st ? <em> · {st.drinks} so far{st.cut_off ? ", cut off" : ""}</em> : null}</dd>
        <dt>Buzz</dt><dd><i style={{ background: buzzColor(p.buzz) }} />{p.tier ?? "sober"}</dd>
        <dt>Energy</dt><dd><i style={{ background: batteryColor(p.battery) }} />{batteryWord(p.battery)}</dd>
        {p.need ? (<><dt>Needs</dt><dd>{NEED_WORD[p.need] ?? p.need}</dd></>) : null}
        <dt>Sitting</dt><dd>{guest.bartender ? "behind the bar" : p.stool != null ? `bar stool ${p.stool + 1}` : p.table != null ? `${p.location === "patio" ? "patio" : "table"} ${p.table + 1}` : p.waiting ? "waiting in line" : "standing"}</dd>
      </dl>
      {st?.thought ? <blockquote>{st.thought}</blockquote> : null}
      <div className="tw-card-actions">
        <button onClick={onTrack} aria-pressed={tracked}>{tracked ? "Stop following" : "Follow"}</button>
        <button onClick={onPin} aria-pressed={pinned}>{pinned ? "Unpin" : "Pin to roster"}</button>
      </div>
    </div>
  );
}

export function Floor({ guests, live, selected, tracked, pinned, followed, onSelect, onTrack, onPin, onFollow }: {
  guests: Guest[];
  live: Live[];
  selected: string | null;
  tracked: string | null;
  pinned: Set<string>;
  followed: number[];
  onSelect: (id: string | null) => void;
  onTrack: (id: string | null) => void;
  onPin: (id: string) => void;
  onFollow: (threadId: number) => void;
}) {
  const [lens, setLens] = useState<Lens>("mood");
  const profile = useStore((s) => s.profile);
  const sel = selected ? guests.find((g) => g.person.id === selected) ?? null : null;

  const topicOf = useMemo(() => {
    const m = new Map<number, string>();
    for (const l of live) m.set(l.thread.id, l.thread.topic ?? "other");
    return m;
  }, [live]);

  // Ties of the picked person: id -> affinity, from their profile.
  const ties = useMemo(() => {
    const m = new Map<string, { aff: number; fam: number }>();
    if (profile && profile.id === selected) for (const r of profile.relationships) m.set(r.id, { aff: r.affinity, fam: r.familiarity });
    return m;
  }, [profile, selected]);

  const pins: Pin[] = guests.map((g) => {
    const p = g.presence;
    let fill = NONE;
    let dim = false;
    if (lens === "mood") fill = moodColor(p.mood);
    else if (lens === "buzz") fill = buzzColor(p.buzz);
    else if (lens === "energy") fill = batteryColor(p.battery);
    else if (lens === "topic") fill = p.thread_id != null && topicOf.has(p.thread_id) ? TOPIC_COLOR[topicOf.get(p.thread_id)!] ?? NONE : NONE;
    else if (selected) {
      const t = ties.get(g.person.id);
      fill = g.person.id === selected ? "#14243a" : t ? (t.aff >= 0 ? TIE_GOOD : TIE_BAD) : NONE;
      dim = g.person.id !== selected && !t;
    }
    return { guest: g, fill, dim, selected: g.person.id === selected, ring: pinned.has(g.person.id) ? "#14243a" : undefined };
  });

  const hulls: Hull[] = live
    .map((l): Hull | null => {
      const points = threadPoints(l.thread, guests);
      if (!points.length || l.thread.kind === "order") return null;
      const strip = stripOf(l.thread);
      return {
        id: l.thread.id,
        points,
        color: lens === "topic" ? TOPIC_COLOR[l.thread.topic ?? "other"] ?? STRIP_HULL[strip] : STRIP_HULL[strip],
        pulse: strip === "heated",
        dim: followed.length > 0 && !followed.includes(l.thread.id),
        onClick: () => onFollow(l.thread.id),
      };
    })
    .filter((h): h is Hull => h !== null);

  const links = useMemo(() => {
    if (lens !== "ties" || !sel) return [];
    return guests
      .filter((g) => g.person.id !== sel.person.id && ties.has(g.person.id))
      .map((g) => {
        const t = ties.get(g.person.id)!;
        return { a: sel.spot.pos, b: g.spot.pos, color: t.aff >= 0 ? TIE_GOOD : TIE_BAD, width: 0.05 + (t.fam / 100) * 0.16 };
      });
  }, [lens, sel, guests, ties]);

  const trackedGuest = tracked ? guests.find((g) => g.person.id === tracked) : null;
  const subtitle = useMemo(() => {
    if (!trackedGuest || trackedGuest.presence.thread_id == null) return null;
    const l = live.find((x) => x.thread.id === trackedGuest.presence.thread_id);
    const last = l && [...l.msgs].reverse().find((m) => m.kind === "speech");
    return l && last ? { place: placeOf(l.thread), who: last.speaker_id, text: last.text } : null;
  }, [trackedGuest, live]);
  const people = useStore((s) => s.people);

  return (
    <section className="tw-floor" aria-label="Floor">
      <div className="tw-lenses" role="group" aria-label="Colour people by">
        {LENSES.map(([id, label]) => (
          <button key={id} className={lens === id ? "on" : ""} onClick={() => setLens(id)} aria-pressed={lens === id}>{label}</button>
        ))}
        <Legend lens={lens} />
      </div>
      <FloorPlan
        className="tw-plan"
        guests={pins}
        hulls={hulls}
        links={links}
        focus={trackedGuest?.spot.pos ?? null}
        onPerson={(id) => onSelect(id === selected ? null : id)}
        onPersonDouble={(id) => onTrack(id === tracked ? null : id)}
      />
      {sel && (
        <PersonCard
          guest={sel}
          pinned={pinned.has(sel.person.id)}
          tracked={tracked === sel.person.id}
          onClose={() => onSelect(null)}
          onPin={() => onPin(sel.person.id)}
          onTrack={() => onTrack(tracked === sel.person.id ? null : sel.person.id)}
        />
      )}
      {trackedGuest && (
        <div className="tw-follow" aria-live="polite">
          <span>Following {trackedGuest.person.short}</span>
          {subtitle ? <q>{subtitle.who ? `${people[subtitle.who]?.short ?? ""}: ` : ""}{subtitle.text}</q> : <em>{trackedGuest.presence.thread_id == null ? "not in a conversation" : "…"}</em>}
          <button onClick={() => onTrack(null)}>Stop</button>
        </div>
      )}
    </section>
  );
}
