import type { Thread } from "../../types";

export const TOPIC_COLOR: Record<string, string> = {
  beer: "#c9902b",
  civic: "#5c7fb5",
  town: "#4e9a8c",
  gossip: "#b05a8a",
  sports: "#6e9a3f",
  life: "#8a7b6a",
  culture: "#8b6fb5",
  story: "#a8794a",
  event: "#c8361e",
  other: "#8f9ba6",
};

export const TOPIC_WORD: Record<string, string> = {
  beer: "Beer",
  civic: "City hall",
  town: "Around town",
  gossip: "Gossip",
  sports: "Sports",
  life: "Life",
  culture: "Culture",
  story: "Stories",
  event: "Tonight's news",
  other: "Small talk",
  order: "Ordering",
  staff: "Shop talk",
};

/** How a conversation is filed in the rack, like the colour of a flight strip. */
export type Strip = "chat" | "order" | "heated" | "staff";

export function stripOf(t: Thread): Strip {
  if (t.kind === "order") return "order";
  if (t.kind === "staff") return "staff";
  return (t.tension ?? 0) >= 0.6 || t.vibe === "tense" || t.on_event ? "heated" : "chat";
}

export const STRIP_FILL: Record<Strip, string> = {
  chat: "#efe3c2",
  order: "#cfe0f2",
  heated: "#f2cfd4",
  staff: "#d9dfe3",
};

/** The same colours, one step deeper, for outlines on the floor. */
export const STRIP_HULL: Record<Strip, string> = {
  chat: "#d9c58e",
  order: "#8fb6dc",
  heated: "#e58e9a",
  staff: "#a9b6c0",
};
