import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import RealismPage from "./realism/RealismPage";
import SalesPage from "./sales/SalesPage";
import "./index.css";

// Four pages share one app: the chat at "/", the sales dashboard at "/sales", the realism scorecard at "/realism" and the 3D floor at "/taproom".
// The floor is lazy so three.js stays out of the other pages' bundle. The chat has alternate layouts, picked with "?ui=".
const TaproomPage = lazy(() => import("./taproom/TaproomPage"));
const SkinShell = lazy(() => import("./skins/SkinShell"));
const path = location.pathname;
const Page = path.startsWith("/sales")
  ? SalesPage
  : path.startsWith("/realism")
    ? RealismPage
    : path.startsWith("/taproom")
      ? TaproomPage
      : SkinShell;

createRoot(document.getElementById("root")!, {
  onUncaughtError: (e) => console.error("[taproom-uncaught]", e instanceof Error ? `${e.message}\n${e.stack}` : e),
}).render(
  <StrictMode>
    <Suspense fallback={null}>
      <Page />
    </Suspense>
  </StrictMode>,
);
