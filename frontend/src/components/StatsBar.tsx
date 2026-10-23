import { useStore } from "../store";
import { kfmt, money } from "../util";

export function StatsBar() {
  const stats = useStore((s) => s.stats);
  const clock = useStore((s) => s.clock);
  if (!stats) return null;
  const pct = Math.min(100, (stats.spent_today / stats.budget) * 100);
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-[var(--border)] bg-[var(--panel)] px-5 py-1.5 text-xs text-[var(--muted)]">
      <span>👥 {clock?.crowd ?? 0} guests</span>
      <span>💬 {kfmt(stats.calls)} calls</span>
      <span>
        tokens in {kfmt(stats.input_tokens + stats.cache_read_tokens + stats.cache_write_tokens)} · out{" "}
        {kfmt(stats.output_tokens)}
      </span>
      <span title="Share of input tokens served from the prompt cache">cache hit {stats.cache_hit_pct}%</span>
      <span>🔎 {stats.web_searches} searches</span>
      {stats.errors > 0 && <span className="text-red-500">{stats.errors} API errors</span>}
      <span className="ml-auto flex items-center gap-2">
        {money(stats.spent_today)} of ${stats.budget.toFixed(2)} today
        <span className="inline-block h-1.5 w-24 rounded-full bg-[var(--track)]">
          <span
            className={`block h-1.5 rounded-full ${pct > 85 ? "bg-red-500" : "bg-[var(--ok)]"}`}
            style={{ width: `${pct}%` }}
          />
        </span>
      </span>
    </div>
  );
}
