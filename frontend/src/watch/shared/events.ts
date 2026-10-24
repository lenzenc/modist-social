export type EventKind = "in" | "out" | "flag" | "alert";

/** What a door-log line means for the night's story: someone arriving or leaving, a milestone, or the God Mode event. */
export function eventKind(text: string): EventKind | null {
  if (/walks in|group of \d+ walks in|brought .* along/i.test(text)) return "in";
  if (/heads out|rideshare|drives .* home/i.test(text)) return "out";
  if (/Word around town|buzz has died/i.test(text)) return "alert";
  if (/open\.|closed\.|Last call|Happy hour|New on the board|kicked|booked|has the/i.test(text)) return "flag";
  return null;
}

/** The line without its leading emoji. */
export const plain = (text: string) => text.replace(/^[^\p{L}\p{N}]+/u, "");
