/** Beer colour carries weight: pale for light talk, darker as the subject gets heavier. Topics share a band; the label names the topic. */
export interface Band { name: string; color: string }

const STRAW: Band = { name: "straw", color: "#f3d36b" };
const AMBER: Band = { name: "amber", color: "#d99a2b" };
const COPPER: Band = { name: "copper", color: "#b5561e" };
const BROWN: Band = { name: "brown", color: "#6b3417" };
const STOUT: Band = { name: "stout", color: "#2e1a10" };

export const BAND_OF: Record<string, Band> = {
  other: STRAW,
  story: STRAW,
  life: STRAW,
  beer: AMBER,
  town: COPPER,
  sports: COPPER,
  culture: COPPER,
  gossip: BROWN,
  civic: STOUT,
  event: STOUT,
};

export const BANDS = [STRAW, AMBER, COPPER, BROWN, STOUT];
export const bandOf = (topic?: string): Band => BAND_OF[topic ?? "other"] ?? STRAW;

export const TOPIC_LABEL: Record<string, string> = {
  other: "Small talk",
  story: "Telling stories",
  life: "Life stuff",
  beer: "Beer",
  town: "Around town",
  sports: "Sports",
  culture: "Music and movies",
  gossip: "Gossip",
  civic: "City hall",
  event: "Tonight's news",
};
