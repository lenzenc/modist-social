import { create } from "zustand";
import type { Channel, Clock, GodAssessment, Msg, Person, Presence, Profile, Stats, Thread, WsEvent } from "./types";

interface Feed {
  threads: Thread[];
  messages: Msg[];
}

interface State {
  connected: boolean;
  llmMode: string;
  city: string;
  channels: Channel[];
  people: Record<string, Person>;
  presence: Record<string, Presence>;
  clock: Clock | null;
  stats: Stats | null;
  banner: string;
  news: string[];
  channel: string;
  feeds: Record<string, Feed>;
  threads: Record<number, Thread>;
  threadMsgs: Record<number, Msg[]>;
  typing: Record<number, string[]>;
  /** Per channel, the conversations (thread ids) with lines you haven't seen. */
  unread: Record<string, number[]>;
  openThread: number | null;
  profile: Profile | null;
  profileId: string | null;

  bootstrap: () => Promise<void>;
  selectChannel: (id: string) => Promise<void>;
  loadLiveThreads: () => Promise<void>;
  openThreadPane: (id: number | null) => Promise<void>;
  openProfile: (id: string | null) => Promise<void>;
  assessGod: (text: string) => Promise<GodAssessment>;
  setGod: (text: string, reach?: number, divisiveness?: number) => Promise<void>;
  clearGod: () => Promise<void>;
  control: (body: { action: string; speed?: number; crowd?: number; extra_budget?: number }) => Promise<void>;
  connect: () => void;
}

const api = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const r = await fetch(path, init);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
};

const mergeMsgs = (a: Msg[], b: Msg[]) => {
  const seen = new Set<number>();
  return [...a, ...b]
    .filter((m) => (seen.has(m.id) ? false : (seen.add(m.id), true)))
    .sort((x, y) => x.id - y.id);
};

let socket: WebSocket | null = null;

export const useStore = create<State>((set, get) => ({
  connected: false,
  llmMode: "live",
  city: "",
  channels: [],
  people: {},
  presence: {},
  clock: null,
  stats: null,
  banner: "",
  news: [],
  channel: "door",
  feeds: {},
  threads: {},
  threadMsgs: {},
  typing: {},
  unread: {},
  openThread: null,
  profile: null,
  profileId: null,

  bootstrap: async () => {
    const b = await api<{
      channels: Channel[];
      people: (Person & { present: boolean; location: string | null; thread_id: number | null; seated?: boolean; drink?: string; tier?: string; stool?: number | null; table?: number | null; party?: number | null })[];
      clock: Clock;
      news: string[];
      stats: Stats;
      llm_mode: string;
      city: string;
      banner: string;
    }>("/api/bootstrap");
    const presence: Record<string, Presence> = {};
    for (const p of b.people) if (p.present) presence[p.id] = { id: p.id, location: p.location, thread_id: p.thread_id, seated: p.seated, drink: p.drink, tier: p.tier, stool: p.stool, table: p.table, party: p.party };
    set({
      channels: b.channels,
      people: Object.fromEntries(b.people.map((p) => [p.id, p])),
      presence,
      clock: b.clock,
      news: b.news,
      stats: b.stats,
      llmMode: b.llm_mode,
      city: b.city,
      banner: b.banner,
    });
    await get().selectChannel(get().channel);
  },

  selectChannel: async (id) => {
    set((s) => ({ channel: id, unread: { ...s.unread, [id]: [] } }));
    const feed = await api<Feed>(`/api/channels/${id}/feed`);
    set((s) => ({ feeds: { ...s.feeds, [id]: feed } }));
    // Pull transcripts for the threads we will preview inline.
    const recent = feed.threads.slice(-8);
    await Promise.all(
      recent.map(async (t) => {
        const msgs = await api<Msg[]>(`/api/threads/${t.id}/messages`);
        set((s) => ({ threadMsgs: { ...s.threadMsgs, [t.id]: mergeMsgs(s.threadMsgs[t.id] ?? [], msgs) } }));
      }),
    );
  },

  loadLiveThreads: async () => {
    // The chat view only tracks the open channel; the floor view needs every live conversation.
    const feeds = await Promise.all(
      ["bar", "inside-tables", "patio", "ordering", "staff"].map((c) => api<Feed>(`/api/channels/${c}/feed`)),
    );
    const live = feeds.flatMap((f) => f.threads).filter((t) => !t.ended_at);
    set((s) => ({ threads: { ...Object.fromEntries(live.map((t) => [t.id, t])), ...s.threads } }));
  },

  openThreadPane: async (id) => {
    set({ openThread: id, profile: id ? null : get().profile, profileId: id ? null : get().profileId });
    if (id == null) return;
    const msgs = await api<Msg[]>(`/api/threads/${id}/messages`);
    set((s) => ({ threadMsgs: { ...s.threadMsgs, [id]: mergeMsgs(s.threadMsgs[id] ?? [], msgs) } }));
  },

  openProfile: async (id) => {
    if (id == null) return set({ profile: null, profileId: null });
    set({ profileId: id, openThread: null });
    const profile = await api<Profile>(`/api/people/${id}`);
    if (get().profileId === id) set({ profile });
  },

  assessGod: (text) =>
    api<GodAssessment>("/api/sim/god/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }),

  setGod: async (text, reach, divisiveness) => {
    const clock = await api<Clock>("/api/sim/god", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, reach, divisiveness }),
    });
    set({ clock });
  },

  clearGod: async () => {
    const clock = await api<Clock>("/api/sim/god", { method: "DELETE" });
    set({ clock });
  },

  control: async (body) => {
    const clock = await api<Clock>("/api/sim/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    set({ clock });
  },

  connect: () => {
    const open = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${proto}://${location.host}/ws`);
      socket.onopen = () => {
        set({ connected: true });
        void get().bootstrap();
      };
      socket.onclose = () => {
        set({ connected: false });
        setTimeout(open, 2000);
      };
      socket.onmessage = (e) => handle(JSON.parse(e.data) as WsEvent);
    };

    const handle = (ev: WsEvent) => {
      switch (ev.type) {
        case "clock": {
          const { type: _t, ...clock } = ev;
          set({ clock });
          break;
        }
        case "presence":
          set({ presence: Object.fromEntries(ev.people.map((p) => [p.id, p])) });
          break;
        case "stats":
          set({ stats: ev.stats });
          break;
        case "banner":
          set({ banner: ev.text });
          break;
        case "typing":
          set((s) => {
            const cur = new Set(s.typing[ev.thread_id] ?? []);
            if (ev.on) cur.add(ev.person_id);
            else cur.delete(ev.person_id);
            return { typing: { ...s.typing, [ev.thread_id]: [...cur] } };
          });
          break;
        case "thread":
          set((s) => {
            const t = ev.thread;
            const feed = s.feeds[t.channel];
            const next: Partial<State> = {};
            if (t.ended_at) {
              const { [t.id]: _gone, ...rest } = s.threads;
              next.threads = rest;
            } else {
              next.threads = { ...s.threads, [t.id]: t };
            }
            if (feed) {
              const idx = feed.threads.findIndex((x) => x.id === t.id);
              const threads = idx >= 0 ? feed.threads.map((x) => (x.id === t.id ? t : x)) : [...feed.threads, t];
              next.feeds = { ...s.feeds, [t.channel]: { ...feed, threads } };
            }
            if (!s.threadMsgs[t.id]) next.threadMsgs = { ...s.threadMsgs, [t.id]: [] };
            return next;
          });
          break;
        case "message":
          set((s) => {
            const m = ev.message;
            const next: Partial<State> = {};
            if (m.thread_id != null) {
              const cur = s.threadMsgs[m.thread_id] ?? [];
              next.threadMsgs = { ...s.threadMsgs, [m.thread_id]: mergeMsgs(cur, [m]) };
            } else {
              const feed = s.feeds[m.channel] ?? { threads: [], messages: [] };
              next.feeds = { ...s.feeds, [m.channel]: { ...feed, messages: mergeMsgs(feed.messages, [m]).slice(-200) } };
            }
            // Only people talking count as unread, once per conversation; system notices (shift starts, arrivals) don't.
            if (m.channel !== s.channel && m.thread_id != null && m.kind !== "system") {
              const seen = s.unread[m.channel] ?? [];
              if (!seen.includes(m.thread_id)) next.unread = { ...s.unread, [m.channel]: [...seen, m.thread_id] };
            }
            return next;
          });
          break;
        case "person":
          set((s) => ({ people: { ...s.people, [ev.person.id]: { ...s.people[ev.person.id], ...ev.person } } }));
          break;
        case "relationships":
          if (get().profileId && ev.people.includes(get().profileId!)) void get().openProfile(get().profileId);
          break;
      }
    };
    open();
  },
}));
