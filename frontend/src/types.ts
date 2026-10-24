export interface Person {
  id: string;
  name: string;
  short: string;
  display: string;
  role: "patron" | "bartender";
  pronouns: string;
  color: string;
  job: string;
  /** Times they've come in, and whether they're one of the people generated as they walked in. */
  visits?: number;
  walk_in?: boolean;
}

export interface Presence {
  id: string;
  location: string | null;
  thread_id: number | null;
  seated?: boolean;
  drink?: string;
  stool?: number | null;
  table?: number | null;
  party?: number | null;
  /** sober | tipsy | drunk | wasted */
  tier?: string;
  waiting?: boolean;
  /** How they feel right now: mood -1..1, buzz 0..1, social battery 0..1, and a pending need ("" when none). */
  mood?: number;
  buzz?: number;
  battery?: number;
  need?: string;
  /** Doing something solo (phone, reading) and not up for a chat. */
  busy?: boolean;
  cut_off?: boolean;
  arrived_at?: string | null;
}

export interface Msg {
  id: number;
  thread_id: number | null;
  channel: string;
  speaker_id: string | null;
  kind: "speech" | "system" | "action";
  text: string;
  sim_ts: string;
}

export interface Thread {
  id: number;
  channel: string;
  kind: "chat" | "order" | "staff";
  started_at: string;
  ended_at: string | null;
  participants: string[];
  root_text: string;
  count: number;
  last: { speaker_id: string; text: string } | null;
  table?: number | null;
  /** lively | easy | flat | tense */
  vibe?: string;
  tension?: number;
  on_event?: boolean;
  outsider?: string;
  split_from?: number | null;
  /** beer | civic | town | gossip | sports | life | culture | story | event | other (or the thread kind for orders and staff) */
  topic?: string;
}

export interface Channel {
  id: string;
  desc: string;
}

/** How an event lands: both scales run 1-5; heat and fade run 0-1 and drop as the buzz dies down. */
export interface GodAssessment {
  reach: number;
  divisiveness: number;
  sides: [string, string];
  reason: string;
}

export interface GodState extends GodAssessment {
  text: string;
  heat: number;
  fade: number;
}

export interface Clock {
  sim_now: string;
  speed: number;
  effective_speed: number;
  crowd_level: number;
  god: GodState | null;
  paused: boolean;
  open: boolean;
  on_shift: string[];
  budget_paused: boolean;
  crowd: number;
  occasion?: string;
}

export interface Stats {
  calls: number;
  errors: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  cache_hit_pct: number;
  web_searches: number;
  spent_today: number;
  spent_total: number;
  budget: number;
}

export interface Profile extends Person {
  present: boolean;
  drink?: string;
  location: string | null;
  persona: {
    age: number;
    job: string;
    traits: string[];
    politics: string;
    drink: string;
    interests: string[];
    quirk: string;
    voice: string;
    life?: string;
    joined?: string;
    walkin?: boolean;
    takes?: string[];
    style?: string;
    beer?: string;
    big5?: { o: number; c: number; e: number; a: number; n: number };
  };
  relationships: {
    id: string;
    name: string;
    kind: string;
    familiarity: number;
    affinity: number;
    notes: string;
    color: string;
    bond: string;
    bond_since: string | null;
  }[];
  /** The last few times one of their relationships changed. */
  bond_changes: { with: string; from: string; to: string; why: string; sim_ts: string }[];
  memories: {
    sim_ts: string;
    text: string;
    about: string[];
    importance: number;
    kind: string;
    /** Who told them, for a rumor; null if they saw it themselves. */
    source: string | null;
    confidence: number | null;
    accuracy: number | null;
    hops: number | null;
  }[];
  /** How they feel right now; null when they're not in the taproom. */
  state: { reason: string; mood: number; buzz: number; battery: number; need: string; thought: string; drinks: number; tier: string; cut_off: boolean; on_water: boolean; slops: string[]; cap: number; spent: number } | null;
  /** How the shift is going for a bartender on the bar; null otherwise. */
  shift: { mood: number; energy: string; rough: string; served: number; wrong: number; spills: number; pours: number; poured: string[]; feeling: string; peeve: string; gripe: string } | null;
  /** What they like to drink and what they can spend; null for staff. */
  taste: { favorites: string[]; tired_of: string[]; budget: "tight" | "ok" | "flush"; owes: Record<string, number> } | null;
  lately: string;
  visits: number;
  /** Things that happened to them away from the taproom, newest first. */
  life: { text: string; cat: string; started_at: string; ends_at: string; active: boolean }[];
}

export type WsEvent =
  | ({ type: "clock" } & Clock)
  | { type: "presence"; people: Presence[] }
  | { type: "message"; message: Msg }
  | { type: "thread"; thread: Thread }
  | { type: "typing"; thread_id: number; person_id: string; on: boolean }
  | { type: "stats"; stats: Stats }
  | { type: "banner"; text: string }
  | { type: "relationships"; people: string[] }
  | { type: "person"; person: Person }
  | { type: "sale"; payment_id: number; person_id: string; status: string };

/** The night so far: where everyone was and how they felt every few sim minutes, plus the door log. */
export interface Tonight {
  opened: string | null;
  /** Each sample: [id, location, thread id, mood, buzz, battery, drinks so far, need, cut off] for everyone present. */
  samples: { t: string; p: [string, string | null, number | null, number, number, number, number, string, boolean][] }[];
  events: Msg[];
}
