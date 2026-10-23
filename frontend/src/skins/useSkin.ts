import { useSyncExternalStore } from "react";
import { DEFAULT_SKIN, SKINS } from "./index";

const KEY = "ui";
const listeners = new Set<() => void>();

const resolve = (): string => {
  const q = new URLSearchParams(location.search).get(KEY);
  return q && q in SKINS ? q : DEFAULT_SKIN;
};

// The attribute is set at module init, before the first paint, so a skin never flashes the Slack palette.
const apply = (id: string) => {
  if (id === DEFAULT_SKIN) delete document.documentElement.dataset.skin;
  else document.documentElement.dataset.skin = id;
};

let current = resolve();
apply(current);

export function setSkin(id: string) {
  if (!(id in SKINS) || id === current) return;
  current = id;
  apply(id);
  const u = new URL(location.href);
  if (id === DEFAULT_SKIN) u.searchParams.delete(KEY);
  else u.searchParams.set(KEY, id);
  history.replaceState(null, "", u);
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

export const useSkin = () => useSyncExternalStore(subscribe, () => current);
