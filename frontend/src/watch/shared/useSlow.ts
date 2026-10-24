import { useEffect, useRef, useState } from "react";

/** A value that follows the live one but updates at most every `ms`, for views that are costly to redraw. */
export function useSlow<T>(live: T, ms: number): T {
  const [slow, setSlow] = useState(live);
  const latest = useRef(live);
  latest.current = live;
  useEffect(() => {
    const id = setInterval(() => setSlow(latest.current), ms);
    return () => clearInterval(id);
  }, [ms]);
  return slow;
}
