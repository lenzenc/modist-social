import { useStore } from "../store";
import { fmtDayTime } from "../util";
import { STOOLS, TABLES } from "../taproom/layout";
import { Avatar } from "./Avatar";

export function Sidebar() {
  const { channels, channel, selectChannel, unread, clock, people, presence, city, llmMode, connected } =
    useStore();

  const here = Object.values(people).filter((p) => presence[p.id]);
  const bartenders = here.filter((p) => p.role === "bartender");
  const patrons = here.filter((p) => p.role === "patron").sort((a, b) => a.short.localeCompare(b.short));

  // People in a channel: the staff channel counts bartenders, the door is just a log, the rest count patrons there.
  const headcount = (id: string) =>
    id === "staff" ? bartenders.length : id === "door" ? 0 : patrons.filter((p) => presence[p.id]?.location === id).length;

  // Seated = a stool at the bar, or a numbered table inside / on the patio. Everyone else is standing.
  const seatOf = (id: string): [string, number] | null => {
    const pr = presence[id];
    if (pr?.location === "bar" && pr.stool != null) return ["bar", pr.stool];
    if (pr?.location && pr.location in TABLES && pr.table != null) return [pr.location, pr.table];
    return null;
  };
  const inArea = (area: string) =>
    patrons
      .filter((p) => seatOf(p.id)?.[0] === area)
      .sort((a, b) => seatOf(a.id)![1] - seatOf(b.id)![1]);
  const standing = patrons.filter((p) => !seatOf(p.id));
  const areas = [
    { id: "bar", title: "At the bar", seat: "stool", cap: STOOLS.length },
    { id: "inside-tables", title: "Inside tables", seat: "table", cap: 0 },
    { id: "patio", title: "Patio", seat: "table", cap: 0 },
  ];

  return (
    <aside className="flex w-64 shrink-0 flex-col bg-[var(--sidebar)] text-[var(--sidebar-text)]">
      <div className="border-b border-white/10 px-4 py-3">
        <div className="flex items-center gap-2 text-lg font-bold text-white">
          <span>🍺</span> Modist Social
        </div>
        <div className="mt-0.5 text-xs opacity-70">{city}</div>
        {clock && (
          <div className="mt-2 flex items-center gap-2 text-sm text-white">
            <span
              className={`inline-block h-2 w-2 rounded-full ${clock.open ? "bg-[var(--ok)]" : "bg-neutral-500"}`}
              title={clock.open ? "Open" : "Closed"}
            />
            {fmtDayTime(clock.sim_now)}
            <span className="text-xs opacity-60">{clock.open ? "open" : "closed"}</span>
          </div>
        )}
      </div>

      <div className="scroll flex-1 py-2">
        <div className="px-4 pt-1 pb-1 text-xs font-semibold tracking-wide uppercase opacity-60">Channels</div>
        {channels.map((c) => (
          <button
            key={c.id}
            onClick={() => selectChannel(c.id)}
            className={`flex w-full cursor-pointer items-center justify-between px-4 py-1 text-left ${
              channel === c.id ? "bg-[var(--sidebar-active)] text-white" : "hover:bg-[var(--sidebar-hover)]"
            } ${unread[c.id] && channel !== c.id ? "font-bold text-white" : ""}`}
          >
            <span>
              <span className="mr-1 opacity-60">#</span>
              {c.id}
            </span>
            <span className="flex items-center gap-2">
              {headcount(c.id) > 0 && (
                <span className="text-[11px] opacity-60" title={`${headcount(c.id)} here`}>
                  👤 {headcount(c.id)}
                </span>
              )}
              {!!unread[c.id] && channel !== c.id && (
                <span className="inline-block h-2 w-2 rounded-full bg-[#cd2553]" title="New messages" />
              )}
            </span>
          </button>
        ))}

        <div className="px-4 pt-4 pb-1 text-xs font-semibold tracking-wide uppercase opacity-60">
          Behind the bar ({bartenders.length})
        </div>
        {bartenders.map((p) => (
          <PersonLine key={p.id} id={p.id} sub="bar" />
        ))}
        {!bartenders.length && <div className="px-4 py-1 text-sm opacity-50">Nobody on shift</div>}

        {areas.map((a) => {
          const seated = inArea(a.id);
          return (
            <div key={a.id}>
              <div className="px-4 pt-4 pb-1 text-xs font-semibold tracking-wide uppercase opacity-60">
                {a.title} ({seated.length}
                {a.cap ? `/${a.cap}` : ""})
              </div>
              {seated.map((p) => (
                <PersonLine
                  key={p.id}
                  id={p.id}
                  sub={[`${a.seat} ${seatOf(p.id)![1] + 1}`, presence[p.id]?.drink].filter(Boolean).join(" · ")}
                />
              ))}
              {!seated.length && <div className="px-4 py-1 text-sm opacity-50">Empty</div>}
            </div>
          );
        })}

        <div className="px-4 pt-4 pb-1 text-xs font-semibold tracking-wide uppercase opacity-60">
          Standing ({standing.length})
        </div>
        {standing.map((p) => (
          <PersonLine key={p.id} id={p.id} sub={[presence[p.id]?.location, presence[p.id]?.drink].filter(Boolean).join(" · ")} />
        ))}
        {!standing.length && <div className="px-4 py-1 text-sm opacity-50">Nobody standing</div>}
      </div>

      <div className="border-t border-white/10 px-4 py-2 text-xs opacity-70">
        <span className={`mr-1 inline-block h-2 w-2 rounded-full ${connected ? "bg-[var(--ok)]" : "bg-red-500"}`} />
        {connected ? "Live" : "Reconnecting…"} · {llmMode === "mock" ? "mock dialogue" : "Claude Haiku"}
      </div>
    </aside>
  );
}

function PersonLine({ id, sub }: { id: string; sub: string }) {
  const p = useStore((s) => s.people[id]);
  const openProfile = useStore((s) => s.openProfile);
  return (
    <button
      onClick={() => openProfile(id)}
      className="flex w-full cursor-pointer items-center gap-2 px-4 py-0.5 text-left hover:bg-[var(--sidebar-hover)]"
    >
      <Avatar id={id} size={20} />
      <span className="flex-1 truncate text-sm">
        {p.display}
        {p.walk_in && (p.visits ?? 0) <= 1 && (
          <span className="ml-1.5 rounded bg-white/15 px-1 text-[10px] font-semibold uppercase">new</span>
        )}
      </span>
      <span className="text-[11px] opacity-50">{sub}</span>
    </button>
  );
}
