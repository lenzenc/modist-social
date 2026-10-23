/** A tiny line chart with no axes. */
export function Sparkline({ values, width = 120, height = 28, color = "var(--accent)", fill = true, className = "" }: {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  fill?: boolean;
  className?: string;
}) {
  const n = values.length;
  if (n < 2) return <svg width={width} height={height} className={className} />;
  const max = Math.max(1, ...values);
  const pts = values.map((v, i) => [(i / (n - 1)) * width, height - 2 - (v / max) * (height - 4)] as const);
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} className={className} viewBox={`0 0 ${width} ${height}`}>
      {fill && <path d={`${d} L${width},${height} L0,${height} Z`} fill={color} opacity={0.15} />}
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts[n - 1][0]} cy={pts[n - 1][1]} r={2} fill={color} />
    </svg>
  );
}
