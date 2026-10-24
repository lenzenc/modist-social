import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import RealismPage from "./realism/RealismPage";
import SalesPage from "./sales/SalesPage";
import "./index.css";

// Pages share one app: the chat at "/", the sales dashboard at "/sales", the realism scorecard at "/realism" and the 3D floor at "/taproom".
// The floor is lazy so three.js stays out of the other pages' bundle.
const TaproomPage = lazy(() => import("./taproom/TaproomPage"));
// /watch compares three experimental ways to watch the room; /watch/<tower|taps|ledger> opens one full screen.
const Compare = lazy(() => import("./watch/Compare"));
const Tower = lazy(() => import("./watch/tower/Tower"));
const Taps = lazy(() => import("./watch/taps/Taps"));
const Ledger = lazy(() => import("./watch/ledger/Ledger"));
const path = location.pathname;
const ROUTES: [string, React.ComponentType][] = [
  ["/watch/tower", Tower],
  ["/watch/taps", Taps],
  ["/watch/ledger", Ledger],
  ["/watch", Compare],
  ["/sales", SalesPage],
  ["/realism", RealismPage],
  ["/taproom", TaproomPage],
];
const Page = ROUTES.find(([prefix]) => path.startsWith(prefix))?.[1] ?? App;

createRoot(document.getElementById("root")!, {
  onUncaughtError: (e) => console.error("[taproom-uncaught]", e instanceof Error ? `${e.message}\n${e.stack}` : e),
}).render(
  <StrictMode>
    <Suspense fallback={null}>
      <Page />
    </Suspense>
  </StrictMode>,
);
