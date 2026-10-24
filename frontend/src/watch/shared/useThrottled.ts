import { useEffect, useState } from "react";
import { useStore } from "../../store";

type State = ReturnType<typeof useStore.getState>;

/**
 * Read from the store, but re-render at most every `ms`. At high sim speeds the socket delivers dozens of events a second;
 * these views are busy enough that drawing each one would freeze the tab.
 */
export function useThrottled<T>(selector: (s: State) => T, ms = 300): T {
  const [value, setValue] = useState(() => selector(useStore.getState()));
  useEffect(() => {
    let timer: number | undefined;
    let last = 0;
    const flush = () => {
      timer = undefined;
      last = Date.now();
      setValue(selector(useStore.getState()));
    };
    const unsubscribe = useStore.subscribe(() => {
      if (timer === undefined) timer = window.setTimeout(flush, Math.max(0, ms - (Date.now() - last)));
    });
    flush();
    return () => {
      unsubscribe();
      window.clearTimeout(timer);
    };
  }, [selector, ms]);
  return value;
}

export const selPresence = (s: State) => s.presence;
export const selThreads = (s: State) => s.threads;
export const selThreadMsgs = (s: State) => s.threadMsgs;
export const selTyping = (s: State) => s.typing;
