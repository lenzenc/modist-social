import { useMemo } from "react";
import { useStore } from "../../store";
import { actionText } from "../shared/text";
import { fmtTime } from "../../util";
import { batteryColor, batteryWord, buzzColor, moodColor, moodWord, NEED_WORD, ZONE_LABEL } from "../shared/scales";
import type { Night, Pt } from "./model";

const W = 330;
const H = 96;

/** Mood, buzz and energy across the night for one person, on the same time axis as the sheet. */
function NightChart({ id, night, t0, t1 }: { id: string; night: Night; t0: number; t1: number }) {
  const person = night.people.find((x) => x.id === id);
  if (!person) return null;
  const x = (t: number) => ((t - t0) / (t1 - t0)) * (W - 8) + 4;
  const line = (f: (pt: Pt) => number) =>
    person.pts.filter((pt) => pt.t >= t0).map((pt, i) => `${i ? "L" : "M"}${x(pt.t).toFixed(1)},${(H - 8 - f(pt) * (H - 16)).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Mood, buzz and energy through the night" className="ld-chart">
      <line x1="4" x2={W - 4} y1={H / 2} y2={H / 2} className="mid" />
      <path d={line((pt) => (pt.mood + 1) / 2)} stroke={moodColor(0.8)} />
      <path d={line((pt) => pt.buzz)} stroke={buzzColor(0.8)} />
      <path d={line((pt) => pt.battery)} stroke={batteryColor(1)} />
    </svg>
  );
}

export function Detail({ night, t0, t1 }: { night: Night | null; t0: number; t1: number }) {
  const openThread = useStore((s) => s.openThread);
  const profileId = useStore((s) => s.profileId);
  const profile = useStore((s) => s.profile);
  const msgs = useStore((s) => (openThread != null ? s.threadMsgs[openThread] : undefined));
  const live = useStore((s) => (openThread != null ? s.threads[openThread] : undefined));
  const people = useStore((s) => s.people);
  const presence = useStore((s) => (profileId ? s.presence[profileId] : undefined));
  const openThreadPane = useStore((s) => s.openThreadPane);
  const openProfile = useStore((s) => s.openProfile);

  const speakers = useMemo(() => [...new Set((msgs ?? []).map((m) => m.speaker_id).filter(Boolean) as string[])], [msgs]);

  if (openThread != null) {
    return (
      <aside className="ld-detail">
        <button className="ld-x" onClick={() => void openThreadPane(null)} aria-label="Close">×</button>
        <h2>{speakers.map((id) => people[id]?.short).join(", ") || "Conversation"}</h2>
        <p className="sub">
          {msgs?.length ? `${fmtTime(msgs[0].sim_ts)} to ${fmtTime(msgs[msgs.length - 1].sim_ts)}` : ""}
          {live ? ", still talking" : ", finished"}
        </p>
        <div className="ld-lines">
          {(msgs ?? []).map((m) =>
            m.kind === "system" ? <p key={m.id} className="sys">{m.text}</p>
            : m.kind === "action" ? <p key={m.id} className="act">{actionText(m.text, people[m.speaker_id ?? ""]?.short)}</p>
            : <p key={m.id}><b style={{ color: `color-mix(in srgb, ${people[m.speaker_id ?? ""]?.color ?? "#555"} 70%, #000)` }}>{people[m.speaker_id ?? ""]?.short}</b> {m.text}</p>,
          )}
          {!msgs?.length && <p className="sys">No lines recorded.</p>}
        </div>
      </aside>
    );
  }

  if (profileId && profile?.id === profileId) {
    const st = profile.state;
    const mood = presence?.mood ?? st?.mood ?? 0;
    return (
      <aside className="ld-detail">
        <button className="ld-x" onClick={() => void openProfile(null)} aria-label="Close">×</button>
        <h2>{profile.display}</h2>
        <p className="sub">{profile.persona.job}, {profile.persona.age}. Visit {profile.visits}.</p>
        {night && <NightChart id={profileId} night={night} t0={t0} t1={t1} />}
        <p className="legend"><i style={{ background: moodColor(0.8) }} />mood <i style={{ background: buzzColor(0.8) }} />buzz <i style={{ background: batteryColor(1) }} />energy</p>
        {presence ? (
          <dl>
            <dt>Now</dt><dd>{ZONE_LABEL[presence.location ?? "ordering"] ?? presence.location}, feeling {moodWord(mood)}</dd>
            <dt>Drinking</dt><dd>{presence.drink || "nothing"}{st ? `, ${st.drinks} so far` : ""}</dd>
            <dt>Energy</dt><dd>{batteryWord(presence.battery ?? 1)}{presence.need ? `, needs to ${NEED_WORD[presence.need] ?? presence.need}` : ""}</dd>
            {st?.thought && (<><dt>Thinking</dt><dd className="thought">{st.thought}</dd></>)}
          </dl>
        ) : <p className="sub">Has left for the night.</p>}
        <h3>Knows here</h3>
        <ul>
          {[...profile.relationships].sort((a, b) => b.familiarity - a.familiarity).slice(0, 4).map((r) => (
            <li key={r.id}><button onClick={() => void openProfile(r.id)}>{r.name}</button> <span>{r.bond && r.bond !== "none" ? r.bond.replace("_", " ") : r.kind}</span></li>
          ))}
        </ul>
      </aside>
    );
  }

  return (
    <aside className="ld-detail hint">
      <h2>Reading the sheet</h2>
      <p>Each row is one person, with the night running left to right.</p>
      <p>A solid bar means they were in a conversation. A pale bar means they were on their own. Click a solid bar to read what was said.</p>
      <p>Round beads are drinks. A red mark above the bar is a need, like the restroom. The thin colour line under each bar is mood, and below it is buzz.</p>
      <p>Click a name to see how their night went.</p>
    </aside>
  );
}
