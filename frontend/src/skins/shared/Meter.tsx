/** A horizontal bar. `value` runs 0..max. */
export function Meter({ value, max = 1, color = "var(--accent)", track = "var(--track)", height = 6, className = "", title }: {
  value: number;
  max?: number;
  color?: string;
  track?: string;
  height?: number;
  className?: string;
  title?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className={`w-full overflow-hidden rounded-full ${className}`} style={{ height, background: track }} title={title}>
      <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}
