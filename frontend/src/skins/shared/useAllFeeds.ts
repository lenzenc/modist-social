import { useEffect, useMemo } from "react";
import { useStore } from "../../store";
import type { Msg, Thread } from "../../types";

/** Skins that show every channel at once ask the store to keep all feeds loaded, including across reconnects. */
export function useAllFeeds() {
  const setAllFeeds = useStore((s) => s.setAllFeeds);
  useEffect(() => {
    setAllFeeds(true);
    return () => setAllFeeds(false);
  }, [setAllFeeds]);
}

/** Live conversations, newest activity first. */
export function useLiveThreads(): Thread[] {
  const threads = useStore((s) => s.threads);
  return Object.values(threads).sort((a, b) => b.id - a.id);
}

/** The most recent messages across every channel, oldest first. */
export function useTail(n = 60): Msg[] {
  const feeds = useStore((s) => s.feeds);
  const threadMsgs = useStore((s) => s.threadMsgs);
  return useMemo(() => {
    const all: Msg[] = [];
    for (const f of Object.values(feeds)) all.push(...f.messages);
    for (const m of Object.values(threadMsgs)) all.push(...m);
    return all.sort((a, b) => a.id - b.id).slice(-n);
  }, [feeds, threadMsgs, n]);
}
