import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import SalesPage from "./sales/SalesPage";
import "./index.css";

// Three pages share one app: the chat at "/", the sales dashboard at "/sales" and the 3D floor at "/taproom".
// The floor is lazy so three.js stays out of the other pages' bundle.
const TaproomPage = lazy(() => import("./taproom/TaproomPage"));
const path = location.pathname;
const Page = path.startsWith("/sales") ? SalesPage : path.startsWith("/taproom") ? TaproomPage : App;

createRoot(document.getElementById("root")!, {
  onUncaughtError: (e) => console.error("[taproom-uncaught]", e instanceof Error ? `${e.message}\n${e.stack}` : e),
}).render(
  <StrictMode>
    <Suspense fallback={null}>
      <Page />
    </Suspense>
  </StrictMode>,
);
