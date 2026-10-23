import { useStore } from "../../store";

/** The day's local headlines, which the store already loads but the Slack UI never shows. */
export function NewsTicker({ className = "", empty = "No headlines yet today." }: { className?: string; empty?: string }) {
  const news = useStore((s) => s.news);
  if (!news.length) return <div className={`truncate ${className}`}>{empty}</div>;
  return (
    <div className={`ticker ${className}`}>
      <span className="ticker-track">
        {news.map((n, i) => (
          <span key={i} className="mr-10">
            <span className="mr-2 opacity-50">◆</span>
            {n}
          </span>
        ))}
      </span>
    </div>
  );
}
