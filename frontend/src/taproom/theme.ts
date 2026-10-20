import { useEffect, useState } from "react";

const read = () => {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string) => css.getPropertyValue(name).trim();
  return { canvas: v("--canvas"), panel: v("--panel"), border: v("--border"), ink: v("--ink"), accent: v("--accent") };
};

/** The page's CSS colour tokens as strings three.js can use; re-read when the OS flips light/dark. */
export function useTheme() {
  const [theme, setTheme] = useState(read);
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const on = () => setTheme(read());
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return { ...theme, dark: matchMedia("(prefers-color-scheme: dark)").matches };
}
