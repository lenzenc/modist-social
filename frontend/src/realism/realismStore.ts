import { create } from "zustand";

export type Period = "day" | "week";
export type MetricKey = "openers" | "phrases" | "sameness" | "topics" | "endings";
export type Band = "green" | "amber" | "red" | "none";

export interface Counted {
  text: string;
  count: number;
}
export interface PersonRow {
  id: string;
  name: string;
  lines: number;
  phrase: string;
  phrase_count: number;
  opener_repeat: number;
  blend: number | null;
}
export interface Summary {
  range: { start: string; end: string; period: Period };
  overall: number | null;
  metrics: Record<MetricKey, number | null>;
  bands: Record<MetricKey | "overall", Band>;
  lines: number;
  chats: number;
  detail: {
    openers: Counted[];
    greetings: Counted[];
    phrases: (Counted & { speakers: number })[];
    voice: number | null;
    topic_mix: Record<string, number>;
    topic_overlap?: number;
    tidy_share?: number;
  };
  people: PersonRow[];
  drunk: { rate: number | null; band: Band; visits: number; cut_offs: number; messes: number; rides: number };
  life: {
    rate: number | null;
    band: Band;
    visits: number;
    mentioned: number;
    events: { person: string; text: string; started: string; seen: boolean; came_up: boolean }[];
  };
  bonds: {
    changes: number;
    patron_days: number;
    rate: number | null;
    band: Band;
    list: { a: string; b: string; from: string; to: string; why: string; day: string }[];
  };
  series: ({ key: string; label: string; overall: number | null } & Record<MetricKey, number | null>)[];
}

interface State {
  period: Period;
  date: string;
  simNow: string;
  first: string | null;
  summary: Summary | null;
  metric: MetricKey | "overall";
  connected: boolean;
  error: string;

  setPeriod: (p: Period) => void;
  setDate: (d: string) => void;
  step: (dir: -1 | 1) => void;
  goToday: () => void;
  setMetric: (m: MetricKey | "overall") => void;
  load: () => Promise<void>;
  connect: () => () => void;
}

// Dates are sim calendar days as YYYY-MM-DD strings, moved around at local noon to dodge DST edges.
const toDate = (s: string) => new Date(`${s}T12:00:00`);
const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const getJson = async <T,>(path: string): Promise<T> => {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
};

const REFRESH_MS = 30_000;

export const useRealism = create<State>((set, get) => {
  const reload = () => void get().load();
  return {
    period: "day",
    date: iso(new Date()),
    simNow: "",
    first: null,
    summary: null,
    metric: "overall",
    connected: false,
    error: "",

    setPeriod: (period) => {
      set({ period });
      reload();
    },
    setDate: (date) => {
      if (!date) return;
      set({ date });
      reload();
    },
    step: (dir) => {
      const { period, date } = get();
      const d = toDate(date);
      d.setDate(d.getDate() + (period === "day" ? dir : 7 * dir));
      get().setDate(iso(d));
    },
    goToday: () => {
      const { simNow } = get();
      if (simNow) get().setDate(simNow.slice(0, 10));
    },
    setMetric: (metric) => set({ metric }),

    load: async () => {
      const { period, date } = get();
      try {
        const [summary, days] = await Promise.all([
          getJson<Summary>(`/api/realism/summary?${new URLSearchParams({ period, date })}`),
          getJson<{ first: string | null }>("/api/realism/days"),
        ]);
        set({ summary, first: days.first, error: "" });
      } catch (e) {
        set({ error: e instanceof Error ? e.message : String(e) });
      }
    },

    connect: () => {
      let socket: WebSocket | null = null;
      let closed = false;
      let first = true;
      const poll = setInterval(reload, REFRESH_MS);
      const open = () => {
        const proto = location.protocol === "https:" ? "wss" : "ws";
        socket = new WebSocket(`${proto}://${location.host}/ws`);
        socket.onopen = () => set({ connected: true });
        socket.onclose = () => {
          set({ connected: false });
          if (!closed) setTimeout(open, 2000);
        };
        socket.onmessage = (e) => {
          const ev = JSON.parse(e.data);
          if (ev.type !== "clock") return;
          // The first clock event says what "today" is in the sim, so open on that day.
          if (first) {
            first = false;
            set({ simNow: ev.sim_now, date: ev.sim_now.slice(0, 10) });
            reload();
          } else {
            set({ simNow: ev.sim_now });
          }
        };
      };
      open();
      return () => {
        closed = true;
        clearInterval(poll);
        socket?.close();
      };
    },
  };
});
