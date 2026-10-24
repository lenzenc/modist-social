import { useStore } from "../../store";
import { fmtDayTime } from "../../util";
import { batteryColor, batteryWord, buzzColor, moodColor, moodWord, NEED_WORD } from "../shared/scales";

function Meter({ label, word, value, color }: { label: string; word: string; value: number; color: string }) {
  return (
    <div className="sl-meter">
      <span>{label}</span>
      <i><b style={{ width: `${Math.max(4, value * 100)}%`, background: color }} /></i>
      <em>{word}</em>
    </div>
  );
}

/** Who this is and how their night is going, sliding in over the wall. */
export function Slide({ id, onClose }: { id: string; onClose: () => void }) {
  const profile = useStore((s) => (s.profile?.id === id ? s.profile : null));
  const presence = useStore((s) => s.presence[id]);
  const openProfile = useStore((s) => s.openProfile);
  const person = useStore((s) => s.people[id]);
  const st = profile?.state;
  const mood = presence?.mood ?? st?.mood ?? 0;
  const buzz = presence?.buzz ?? st?.buzz ?? 0;
  const battery = presence?.battery ?? st?.battery ?? 1;

  return (
    <aside className="sl" role="dialog" aria-label={person?.display ?? "Profile"}>
      <button className="sl-close" onClick={onClose} aria-label="Close">×</button>
      <h2>{person?.display}</h2>
      <p className="sl-job">{profile?.persona.job ?? person?.job}{profile ? `, ${profile.persona.age}` : ""}</p>
      {!presence ? <p className="sl-away">Not in the taproom right now.{profile ? ` ${profile.visits} visits so far.` : ""}</p> : (
        <>
          <p className="sl-drink">{presence.drink ? `Drinking ${presence.drink}` : "No drink yet"}{st ? `, number ${st.drinks}` : ""}{presence.cut_off ? ", cut off" : ""}</p>
          <div className="sl-meters">
            <Meter label="Mood" word={moodWord(mood)} value={(mood + 1) / 2} color={moodColor(mood)} />
            <Meter label="Buzz" word={presence.tier ?? "sober"} value={buzz} color={buzzColor(buzz)} />
            <Meter label="Energy" word={batteryWord(battery)} value={battery} color={batteryColor(battery)} />
          </div>
          {presence.need && <p className="sl-need">Needs to {NEED_WORD[presence.need] ?? presence.need}.</p>}
          {st?.thought && <blockquote>{st.thought}</blockquote>}
        </>
      )}
      {profile && (
        <>
          <h3>Right now in their life</h3>
          <p>{profile.lately || profile.persona.life || "Nothing in particular."}</p>
          <h3>Knows here</h3>
          <ul className="sl-ties">
            {[...profile.relationships].sort((a, b) => b.familiarity - a.familiarity).slice(0, 5).map((r) => (
              <li key={r.id}>
                <button onClick={() => void openProfile(r.id)}>{r.name}</button>
                <span>{r.bond && r.bond !== "none" ? r.bond.replace("_", " ") : r.kind}</span>
                <i className={r.affinity >= 0 ? "good" : "bad"} style={{ width: `${Math.min(100, Math.abs(r.affinity))}%` }} />
              </li>
            ))}
          </ul>
          {profile.memories.length > 0 && (
            <>
              <h3>Remembers</h3>
              <ul className="sl-mem">
                {profile.memories.slice(0, 3).map((m, i) => <li key={i}><small>{fmtDayTime(m.sim_ts)}</small>{m.text}</li>)}
              </ul>
            </>
          )}
        </>
      )}
    </aside>
  );
}
