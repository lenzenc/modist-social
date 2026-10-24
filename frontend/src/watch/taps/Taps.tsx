import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/source-serif-4";
import { useEffect, useMemo, useState } from "react";
import { Controls } from "../../components/Controls";
import { useStore } from "../../store";
import { actionText } from "../shared/text";
import { fmtDayTime } from "../../util";
import { onColor } from "../shared/scales";
import { useLive, placeOf, type Live } from "../shared/useLive";
import { useRoom } from "../shared/useRoom";
import { useWatch } from "../shared/useTonight";
import { Where } from "./Where";
import { Slide } from "./Slide";
import { bandOf, BANDS, TOPIC_LABEL } from "./srm";
import "./taps.css";

const STALE_SIM_MIN = 8;
const SHOWN = 14;
const STARS_KEY = "taps.stars";

const loadStars = (): Set<number> => {
  try {
    return new Set(JSON.parse(sessionStorage.getItem(STARS_KEY) ?? "[]"));
  } catch {
    return new Set();
  }
};

function Mark() {
  // A tap handle: a rounded lever on a stem.
  return (
    <svg viewBox="0 0 20 28" width="18" height="26" aria-hidden className="tp-mark">
      <rect x="3" y="1" width="14" height="15" rx="4" />
      <rect x="8.5" y="16" width="3" height="9" />
      <rect x="5" y="24" width="10" height="3" rx="1.5" />
    </svg>
  );
}

function Column({ l, stale, starred, onStar, onPerson }: {
  l: Live;
  stale: boolean;
  starred: boolean;
  onStar: () => void;
  onPerson: (id: string) => void;
}) {
  const people = useStore((s) => s.people);
  const guests = useRoom();
  const t = l.thread;
  const band = bandOf(t.topic);
  const members = guests.filter((g) => g.presence.thread_id === t.id);
  const here = members.length ? members : guests.filter((g) => t.participants.includes(g.person.id) && g.bartender);
  const lines = l.msgs.slice(-SHOWN);
  const guestsHere = t.participants.filter((id) => people[id]?.role !== "bartender");
  return (
    <article className={`tp-col${stale ? " stale" : ""}${t.vibe === "tense" ? " tense" : ""}`} style={{ ["--band" as string]: band.color, ["--on-band" as string]: onColor(band.color) }}>
      <header>
        <div className="tp-col-top">
          <h2>{TOPIC_LABEL[t.topic ?? "other"] ?? "Talking"}</h2>
          <button className={`tp-star${starred ? " on" : ""}`} onClick={onStar} aria-pressed={starred} aria-label={starred ? "Unstar this conversation" : "Star this conversation"}>
            <svg viewBox="0 0 12 12" width="14" height="14"><path d="M6 1l1.5 3.3 3.5.4-2.6 2.4.7 3.5L6 8.8 2.9 10.6l.7-3.5L1 4.7l3.5-.4z" /></svg>
          </button>
        </div>
        <p className="tp-who">
          {(guestsHere.length ? guestsHere : t.participants).map((id, i, a) => (
            <span key={id}>
              <button onClick={() => onPerson(id)}>{people[id]?.short ?? "?"}</button>
              {i < a.length - 1 ? ", " : ""}
            </span>
          ))}
        </p>
        <div className="tp-meta">
          <Where thread={t} members={here} />
          <span>{placeOf(t)}</span>
          <span className="vibe">{t.vibe}</span>
          <span className="count">{t.count}</span>
        </div>
      </header>
      <div className="tp-lines" aria-live="off">
        {lines.map((m) =>
          m.kind === "system" ? (
            <p key={m.id} className="sys">{m.text}</p>
          ) : m.kind === "action" ? (
            <p key={m.id} className="act">{actionText(m.text, people[m.speaker_id ?? ""]?.short)}</p>
          ) : (
            <p key={m.id} className="say">
              <button onClick={() => m.speaker_id && onPerson(m.speaker_id)} style={{ ["--who" as string]: people[m.speaker_id ?? ""]?.color ?? "#555" }}>
                {people[m.speaker_id ?? ""]?.short ?? "Modist"}
              </button>
              {m.text}
            </p>
          ),
        )}
        {!lines.length && <p className="sys">Just sat down. Nothing said yet.</p>}
      </div>
      <footer>{l.typing.length ? <span className="typing">{l.typing.map((id) => people[id]?.short).join(", ")} typing<i /><i /><i /></span> : <span>&nbsp;</span>}</footer>
    </article>
  );
}

export default function Taps() {
  useWatch();
  const live = useLive();
  const clock = useStore((s) => s.clock);
  const banner = useStore((s) => s.banner);
  const openProfile = useStore((s) => s.openProfile);
  const profileId = useStore((s) => s.profileId);
  const people = useStore((s) => s.people);
  const [stars, setStars] = useState<Set<number>>(loadStars);
  const [onlyStars, setOnlyStars] = useState(false);

  const toggleStar = (id: number) =>
    setStars((cur) => {
      const next = new Set(cur);
      if (!next.delete(id)) next.add(id);
      try { sessionStorage.setItem(STARS_KEY, JSON.stringify([...next])); } catch { /* storage blocked */ }
      return next;
    });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && void openProfile(null);
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [openProfile]);

  const nowMs = clock ? new Date(clock.sim_now).getTime() : 0;
  const isStale = (l: Live) => {
    const last = l.msgs[l.msgs.length - 1];
    return !!last && nowMs - new Date(last.sim_ts).getTime() > STALE_SIM_MIN * 60_000;
  };

  const { chats, counter } = useMemo(() => {
    const chats = live.filter((l) => l.thread.kind === "chat");
    // Stable by when the chat began, so columns stay put while you read; quiet ones drift to the far end.
    chats.sort((a, b) => Number(isStale({ ...a })) - Number(isStale({ ...b })) || a.thread.id - b.thread.id);
    return { chats, counter: live.filter((l) => l.thread.kind !== "chat") };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, nowMs]);

  const shown = onlyStars ? chats.filter((l) => stars.has(l.thread.id)) : chats;
  const tense = chats.filter((l) => l.thread.vibe === "tense").length;

  return (
    <div className="tp">
      <header className="tp-top">
        <div className="tp-brand"><Mark /><b>Taps</b></div>
        <div className="tp-clock">
          {clock ? <b>{fmtDayTime(clock.sim_now)}</b> : null}
          <span>{clock ? (clock.open ? "open" : "closed") : "connecting"}</span>
          {clock?.occasion ? <span>{clock.occasion}</span> : null}
          <span>{chats.length} conversations</span>
          {tense > 0 && <span className="hot">{tense} tense</span>}
        </div>
        <button className={`tp-only${onlyStars ? " on" : ""}`} onClick={() => setOnlyStars((v) => !v)} aria-pressed={onlyStars} disabled={!stars.size && !onlyStars}>
          Only starred {stars.size ? `(${stars.size})` : ""}
        </button>
        <div className="tp-controls"><Controls /></div>
      </header>
      {banner && <div className="tp-banner">{banner}</div>}
      <div className="tp-key" aria-label="Colour key">
        {BANDS.map((b) => <span key={b.name}><i style={{ background: b.color }} />{b.name}</span>)}
        <em>paler is lighter talk, darker is heavier</em>
      </div>
      {counter.length > 0 && (
        <ul className="tp-counter" aria-label="At the counter">
          {counter.map((l) => (
            <li key={l.thread.id}><b>{l.thread.kind === "staff" ? "Shop talk" : "Counter"}</b> {l.msgs.length ? (people[l.msgs[l.msgs.length - 1].speaker_id ?? ""]?.short ?? "") + ": " + l.msgs[l.msgs.length - 1].text : l.thread.root_text}</li>
          ))}
        </ul>
      )}
      <main className="tp-wall">
        {shown.map((l) => (
          <Column key={l.thread.id} l={l} stale={isStale(l)} starred={stars.has(l.thread.id)} onStar={() => toggleStar(l.thread.id)} onPerson={(id) => void openProfile(id)} />
        ))}
        {!shown.length && (
          <p className="tp-empty">{onlyStars ? "Nothing starred is still talking." : clock?.open ? "No one is talking yet. The first guests are sitting down." : "Closed. The taps are quiet."}</p>
        )}
      </main>
      {profileId && <Slide id={profileId} onClose={() => void openProfile(null)} />}
    </div>
  );
}
