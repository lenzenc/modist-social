import { useEffect } from "react";
import { fmtDayTime } from "../util";
import { useRealism, type Band, type Counted, type MetricKey, type Period } from "./realismStore";

const PERIODS: Period[] = ["day", "week"];

const btn =
  "cursor-pointer rounded-md border border-[var(--border)] px-3 py-1 text-sm font-semibold hover:bg-black/[0.05]";

const METRICS: { key: MetricKey; label: string; hint: string }[] = [
  { key: "openers", label: "Fresh openers", hint: "Chats that don't start with an opener the room keeps using" },
  { key: "phrases", label: "Phrase variety", hint: "Lines free of 4-word phrases that keep recurring" },
  { key: "sameness", label: "Distinct voices", hint: "Phrases and rhythms that differ from person to person" },
  { key: "topics", label: "Topic variety", hint: "Spread of topics, and how much repeats the last few days" },
  { key: "endings", label: "Loose endings", hint: "Chats that trail off instead of closing on a tidy goodbye" },
];

const BAND_COLOR: Record<Band, string> = {
  green: "var(--ok)",
  amber: "#d99a1c",
  red: "#d0453a",
  none: "var(--muted)",
};

function Tile({ label, hint, value, band, active, onClick }: {
  label: string; hint: string; value: number | null; band: Band; active: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title={hint}
      className={`cursor-pointer rounded-lg border bg-[var(--panel)] px-4 py-3 text-left ${active ? "border-[var(--accent)]" : "border-[var(--border)]"}`}
    >
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className="mt-0.5 text-2xl font-bold" style={{ color: BAND_COLOR[band] }}>{value ?? "–"}</div>
      <div className="text-xs text-[var(--muted)]">{value === null ? "not enough talk yet" : "out of 100"}</div>
    </button>
  );
}

function CountList({ title, rows, empty }: { title: string; rows: (Counted & { speakers?: number })[]; empty: string }) {
  return (
    <div className="rounded-lg border border-[var(--border)] p-4">
      <div className="mb-2 text-sm font-semibold">{title}</div>
      {rows.length === 0 ? (
        <div className="text-sm text-[var(--muted)]">{empty}</div>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {rows.map((r) => (
              <tr key={r.text} className="border-t border-[var(--border)] first:border-0">
                <td className="py-1 pr-3">“{r.text}”</td>
                <td className="py-1 text-right whitespace-nowrap text-[var(--muted)]">
                  ×{r.count}{r.speakers ? ` · ${r.speakers} ${r.speakers === 1 ? "person" : "people"}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function RealismPage() {
  const s = useRealism();
  const { summary, period, date, metric } = s;

  useEffect(() => {
    s.load();
    return s.connect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const range = summary?.range;
  const title = !range
    ? ""
    : period === "day"
      ? new Date(`${range.start}T12:00:00`).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric", year: "numeric" })
      : `${new Date(`${range.start}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric" })} – ${new Date(`${range.end}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}`;
  const d = summary?.detail;
  const mix = Object.entries(d?.topic_mix ?? {}).sort((a, b) => b[1] - a[1]);
  const mixTotal = mix.reduce((a, [, n]) => a + n, 0);
  const label = metric === "overall" ? "Overall" : METRICS.find((m) => m.key === metric)!.label;

  return (
    <div className="mx-auto flex min-h-full max-w-6xl flex-col gap-5 px-4 py-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-2xl font-bold">Realism scorecard</div>
          <div className="text-sm text-[var(--muted)]">
            {title}
            {s.simNow && ` · taproom clock ${fmtDayTime(s.simNow)}`}
            {!s.connected && " · reconnecting…"}
            {summary && ` · ${summary.lines} lines in ${summary.chats} chats`}
          </div>
        </div>
        <a href="/" className={btn}>← Live taproom</a>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded-md border border-[var(--border)]">
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => s.setPeriod(p)}
              className={`cursor-pointer px-3 py-1 text-sm font-semibold capitalize ${p === period ? "bg-[var(--accent)] text-white" : "hover:bg-black/[0.05]"}`}
            >
              {p}
            </button>
          ))}
        </div>
        <button onClick={() => s.step(-1)} className={btn} aria-label="Previous">◀</button>
        <input
          type="date"
          value={date}
          min={s.first ?? undefined}
          onChange={(e) => s.setDate(e.target.value)}
          className="rounded-md border border-[var(--border)] bg-transparent px-2 py-1 text-sm"
        />
        <button onClick={() => s.step(1)} className={btn} aria-label="Next">▶</button>
        <button onClick={s.goToday} className={btn}>Today</button>
      </div>

      {s.error && <div className="rounded bg-amber-100 px-3 py-2 text-sm font-semibold text-amber-900">Could not load the scorecard: {s.error}</div>}

      {summary && d && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            <Tile label="Overall" hint="Average of the five scores" value={summary.overall} band={summary.bands.overall}
              active={metric === "overall"} onClick={() => s.setMetric("overall")} />
            {METRICS.map((m) => (
              <Tile key={m.key} label={m.label} hint={m.hint} value={summary.metrics[m.key]} band={summary.bands[m.key]}
                active={metric === m.key} onClick={() => s.setMetric(m.key)} />
            ))}
          </div>

          <div className="rounded-lg border border-[var(--border)] p-4">
            <div className="mb-2 flex items-baseline justify-between text-sm">
              <span className="font-semibold">Off-screen life</span>
              <span style={{ color: BAND_COLOR[summary.life.band] }} className="font-bold">
                {summary.life.rate === null ? "not enough visits yet" : `${summary.life.rate}% of visits mention it`}
              </span>
            </div>
            <div className="mb-2 text-xs text-[var(--muted)]">
              How often people bring up what has been happening to them away from here ({summary.life.mentioned} of{" "}
              {summary.life.visits} visits). About a third to four fifths is natural. Not part of the overall score.
            </div>
            {summary.life.events.length === 0 ? (
              <div className="text-sm text-[var(--muted)]">No off-screen events in this period.</div>
            ) : (
              <table className="w-full text-sm">
                <tbody>
                  {summary.life.events.map((e, i) => (
                    <tr key={i} className="border-t border-[var(--border)] first:border-0">
                      <td className="py-1 pr-3 font-semibold whitespace-nowrap">{e.person}</td>
                      <td className="py-1 pr-3">{e.text}</td>
                      <td className="py-1 text-right whitespace-nowrap text-[var(--muted)]">
                        {!e.seen ? "didn't visit" : e.came_up ? "came up" : "never mentioned"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="rounded-lg border border-[var(--border)] p-4">
            <div className="mb-2 flex items-baseline justify-between text-sm">
              <span className="font-semibold">Last call</span>
              <span style={{ color: BAND_COLOR[summary.drunk.band] }} className="font-bold">
                {summary.drunk.rate === null ? "not enough drunk visits yet" : `${summary.drunk.rate}% had consequences`}
              </span>
            </div>
            <div className="text-xs text-[var(--muted)]">
              How often a drunk night changes anything: a cut-off, a mess, a switch to water or a ride home ({summary.drunk.visits} drunk
              visits, {summary.drunk.cut_offs} cut off, {summary.drunk.messes} messes, {summary.drunk.rides} rides). Most should; if the
              drunk keep drinking and nothing happens, the room isn't taking it seriously. Not part of the overall score.
            </div>
          </div>

          <div className="rounded-lg border border-[var(--border)] p-4">
            <div className="mb-2 flex items-baseline justify-between text-sm">
              <span className="font-semibold">Relationships</span>
              <span style={{ color: BAND_COLOR[summary.bonds.band] }} className="font-bold">
                {summary.bonds.rate === null ? "not enough visits yet" : `${summary.bonds.changes} changes`}
              </span>
            </div>
            <div className="mb-2 text-xs text-[var(--muted)]">
              Friendships forming, rivalries, crushes, falling-outs and making up. None all week means the room never changes; a
              flood means a soap opera. Not part of the overall score.
            </div>
            {summary.bonds.list.length === 0 ? (
              <div className="text-sm text-[var(--muted)]">No relationship changes in this period.</div>
            ) : (
              <table className="w-full text-sm">
                <tbody>
                  {summary.bonds.list.map((c, i) => (
                    <tr key={i} className="border-t border-[var(--border)] first:border-0">
                      <td className="py-1 pr-3 font-semibold whitespace-nowrap">{c.a} &amp; {c.b}</td>
                      <td className="py-1 pr-3">{c.from.replace("_", " ")} → {c.to.replace("_", " ")}{c.why ? ` (${c.why})` : ""}</td>
                      <td className="py-1 text-right whitespace-nowrap text-[var(--muted)]">{c.day}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="rounded-lg border border-[var(--border)] p-4">
            <div className="mb-3 text-sm font-semibold">{label} by day</div>
            <div className="flex h-36 items-end gap-1.5">
              {summary.series.map((b) => {
                const v = b[metric];
                return (
                  <div key={b.key} title={`${b.label}: ${v ?? "not enough talk"}`} className="flex h-full min-w-0 flex-1 flex-col justify-end text-center">
                    <span className="mb-0.5 text-[10px] text-[var(--muted)]">{v ?? ""}</span>
                    <span className="w-full rounded-t bg-[var(--accent)]" style={{ height: `${v ?? 0}%`, minHeight: v ? 3 : 0 }} />
                    <span className="mt-1 truncate text-[10px] text-[var(--muted)]">{b.label}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <CountList title="Worn-out openers (chats)" rows={d.openers} empty="No opener has been used more than once." />
            <CountList title="Bartender greetings repeated" rows={d.greetings} empty="No greeting has been used more than once." />
            <CountList title="Recurring phrases" rows={d.phrases} empty="No phrase has come up three times." />
            <div className="rounded-lg border border-[var(--border)] p-4">
              <div className="mb-2 text-sm font-semibold">Topic mix</div>
              {mixTotal === 0 ? (
                <div className="text-sm text-[var(--muted)]">No chats to classify yet.</div>
              ) : (
                <div className="flex flex-col gap-1">
                  {mix.map(([k, n]) => (
                    <div key={k} className="flex items-center gap-2 text-sm">
                      <span className="w-16 capitalize text-[var(--muted)]">{k}</span>
                      <span className="h-3 rounded bg-[var(--accent)]" style={{ width: `${(n / mixTotal) * 100}%`, minWidth: 3 }} />
                      <span className="text-xs text-[var(--muted)]">{n}</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-3 text-xs text-[var(--muted)]">
                {d.topic_overlap !== undefined && `${Math.round(d.topic_overlap * 100)}% the same mix as the days before. `}
                {d.tidy_share !== undefined && `${Math.round(d.tidy_share * 100)}% of chats ended on a tidy goodbye. `}
                {d.voice !== null && `Voice distinctiveness ${d.voice}/100.`}
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-[var(--border)] p-4">
            <div className="mb-2 text-sm font-semibold">Who repeats themselves</div>
            {summary.people.length === 0 ? (
              <div className="text-sm text-[var(--muted)]">Nobody has spoken enough yet.</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-[var(--muted)]">
                    <th className="pb-1 pr-3">Guest</th><th className="pb-1 pr-3">Lines</th>
                    <th className="pb-1 pr-3">Favourite phrase</th><th className="pb-1 pr-3">Repeated openers</th>
                    <th className="pb-1">Blends into the room</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.people.map((p) => (
                    <tr key={p.id} className="border-t border-[var(--border)]">
                      <td className="py-1.5 pr-3 font-semibold">{p.name}</td>
                      <td className="py-1.5 pr-3">{p.lines}</td>
                      <td className="py-1.5 pr-3">{p.phrase ? `“${p.phrase}” ×${p.phrase_count}` : "–"}</td>
                      <td className="py-1.5 pr-3">{Math.round(p.opener_repeat * 100)}%</td>
                      <td className="py-1.5">{p.blend === null ? "–" : `${Math.round(p.blend * 100)}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
