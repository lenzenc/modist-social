import { useStore } from "../../store";

/** The amber strip the Slack UI shows when the director has something to say, with the budget top-up button. */
export function BudgetBanner({ className = "" }: { className?: string }) {
  const banner = useStore((s) => s.banner);
  const control = useStore((s) => s.control);
  if (!banner) return null;
  return (
    <div className={`flex items-center justify-between gap-3 bg-amber-400/15 px-4 py-1.5 text-sm font-semibold text-amber-200 ${className}`}>
      <span>{banner}</span>
      {/budget/i.test(banner) && (
        <button
          onClick={() => control({ action: "resume", extra_budget: 1 })}
          className="cursor-pointer rounded bg-amber-400 px-3 py-1 text-xs text-black"
        >
          Add $1 and resume
        </button>
      )}
    </div>
  );
}
