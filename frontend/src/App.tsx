import { useEffect } from "react";
import { Feed } from "./components/Feed";
import { Header } from "./components/Header";
import { RightPane } from "./components/RightPane";
import { Sidebar } from "./components/Sidebar";
import { StatsBar } from "./components/StatsBar";
import { useStore } from "./store";

export default function App() {
  const connect = useStore((s) => s.connect);
  const banner = useStore((s) => s.banner);
  const control = useStore((s) => s.control);

  useEffect(() => connect(), [connect]);

  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col">
        <Header />
        {banner && (
          <div className="flex items-center justify-between bg-amber-100 px-5 py-2 text-sm font-semibold text-amber-900">
            <span>{banner}</span>
            {/budget/i.test(banner) && (
              <button
                onClick={() => control({ action: "resume", extra_budget: 1 })}
                className="cursor-pointer rounded bg-amber-900 px-3 py-1 text-white"
              >
                Add $1 and resume
              </button>
            )}
          </div>
        )}
        <div className="flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            <Feed />
          </div>
          <RightPane />
        </div>
        <StatsBar />
      </main>
    </div>
  );
}
