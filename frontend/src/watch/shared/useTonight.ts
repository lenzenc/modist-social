import { useEffect } from "react";
import { useStore } from "../../store";

/** Keep the store's connection, live conversations and night log fresh while a watch view is open. */
export function useWatch(tonightEveryMs = 0) {
  const connect = useStore((s) => s.connect);
  const connected = useStore((s) => s.connected);
  const watchLive = useStore((s) => s.watchLive);
  const loadTonight = useStore((s) => s.loadTonight);
  useEffect(() => connect(), [connect]);
  useEffect(() => {
    if (connected) void watchLive();
  }, [connected, watchLive]);
  useEffect(() => {
    if (!connected || !tonightEveryMs) return;
    void loadTonight();
    const id = setInterval(() => void loadTonight(), tonightEveryMs);
    return () => clearInterval(id);
  }, [connected, tonightEveryMs, loadTonight]);
}
