import type { Bucket } from "./salesStore";

export const usd = (cents: number) =>
  `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** Sales bars with tips stacked on top; click a bar to drill into it. */
export function BarChart({ data, onPick }: { data: Bucket[]; onPick?: (b: Bucket) => void }) {
  const max = Math.max(1, ...data.map((b) => b.sales + b.tips));
  return (
    <div className="flex h-44 items-end gap-1.5">
      {data.map((b) => {
        const h = ((b.sales + b.tips) / max) * 100;
        const tipH = b.sales + b.tips ? (b.tips / (b.sales + b.tips)) * 100 : 0;
        return (
          <button
            key={b.key}
            disabled={!onPick}
            onClick={() => onPick?.(b)}
            title={`${b.label}: ${usd(b.sales)} sales, ${usd(b.tips)} tips, ${b.drinks} drinks`}
            className={`group flex h-full min-w-0 flex-1 flex-col justify-end text-center ${onPick ? "cursor-pointer" : ""}`}
          >
            <span className="mb-0.5 truncate text-[10px] text-[var(--muted)] opacity-0 group-hover:opacity-100">
              {usd(b.sales)}
            </span>
            <span
              className="flex w-full flex-col overflow-hidden rounded-t bg-[var(--accent)] transition-opacity group-hover:opacity-80"
              style={{ height: `${h}%`, minHeight: b.sales ? 3 : 0 }}
            >
              <span className="bg-[var(--ok)]" style={{ height: `${tipH}%` }} />
            </span>
            <span className="mt-1 truncate text-[10px] text-[var(--muted)]">{b.label}</span>
          </button>
        );
      })}
    </div>
  );
}
