import type { Guest } from "../shared/useRoom";
import type { Thread } from "../../types";

const ROWS = 2;

/** A tiny map of where a conversation is: the bar's stools, or the tables with theirs lit. */
export function Where({ thread, members }: { thread: Thread; members: Guest[] }) {
  const stools = new Set(members.map((m) => m.presence.stool).filter((s): s is number => s != null));
  if (thread.channel === "bar") {
    return (
      <svg className="tp-where" viewBox="0 0 80 14" aria-label="Seats at the bar" role="img">
        <rect x="0" y="0" width="80" height="4" rx="1" className="bar" />
        {Array.from({ length: 20 }, (_, i) => (
          <circle key={i} cx={2 + i * 4} cy={9} r={1.5} className={stools.has(i) ? "on" : ""} />
        ))}
      </svg>
    );
  }
  const patio = thread.channel === "patio";
  const cols = patio ? 3 : 7;
  const w = cols * 11;
  return (
    <svg className="tp-where" viewBox={`0 0 ${w} ${ROWS * 8 + (patio ? 0 : 0)}`} aria-label="Table" role="img">
      {Array.from({ length: cols * ROWS }, (_, i) => {
        // Tables are numbered along rows in the sim (sorted by depth, then across).
        const x = (i % cols) * 11 + 1;
        const y = Math.floor(i / cols) * 8 + 1;
        const here = thread.table === i;
        return <rect key={i} x={x} y={y} width={9} height={6} rx={1} className={here ? "tbl on" : "tbl"} />;
      })}
    </svg>
  );
}
