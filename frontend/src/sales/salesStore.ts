import { create } from "zustand";

export type Period = "day" | "week" | "month";
export type Tab = "drink" | "guest" | "tx";

export interface Totals {
  sales: number;
  tips: number;
  charged: number;
  drinks: number;
  transactions: number;
  guests: number;
  avg_ticket: number;
  happy_hour_drinks: number;
  discount: number;
}
export interface Bucket {
  key: string;
  label: string;
  sales: number;
  drinks: number;
  tips: number;
}
export interface DrinkRow {
  drink: string;
  qty: number;
  hh_qty: number;
  sales: number;
}
export interface PersonRow {
  id: string;
  name: string;
  drinks: number;
  sales: number;
  tips: number;
  tabs: number;
  per_drink: number;
  bought_for_others: number;
}
export interface Summary {
  range: { start: string; end: string; period: Period };
  totals: Totals;
  series: Bucket[];
  crowd: Record<string, number>;
  by_drink: DrinkRow[];
  by_person: PersonRow[];
}
export interface Tx {
  id: number;
  person_id: string;
  name: string;
  kind: "per_drink" | "tab";
  status: "open" | "closed";
  opened_at: string;
  closed_at: string | null;
  bartender: string;
  subtotal: number;
  tip_pct: number;
  tip: number;
  total: number;
  card: string;
  items: { drink: string; price: number; list_price: number; happy_hour: boolean; at: string; for: string | null }[];
}

interface State {
  period: Period;
  date: string;
  simNow: string;
  tab: Tab;
  drink: string;
  person: { id: string; name: string } | null;
  summary: Summary | null;
  txs: Tx[];
  openTabs: Tx[];
  first: string | null;
  connected: boolean;
  error: string;

  setPeriod: (p: Period) => void;
  setDate: (d: string) => void;
  step: (dir: -1 | 1) => void;
  goToday: () => void;
  setTab: (t: Tab) => void;
  pickDrink: (d: string) => void;
  pickPerson: (p: { id: string; name: string } | null) => void;
  clearDrink: () => void;
  load: () => Promise<void>;
  connect: () => () => void;
}

// Dates are sim calendar days, kept as YYYY-MM-DD strings and moved around at local noon to dodge DST edges.
const toDate = (s: string) => new Date(`${s}T12:00:00`);
export const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const getJson = async <T,>(path: string): Promise<T> => {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
};

let timer: ReturnType<typeof setTimeout> | undefined;

export const useSales = create<State>((set, get) => {
  const reload = () => void get().load();
  return {
    period: "day",
    date: iso(new Date()),
    simNow: "",
    tab: "drink",
    drink: "",
    person: null,
    summary: null,
    txs: [],
    openTabs: [],
    first: null,
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
      if (period === "day") d.setDate(d.getDate() + dir);
      else if (period === "week") d.setDate(d.getDate() + 7 * dir);
      else d.setMonth(d.getMonth() + dir, 1);
      get().setDate(iso(d));
    },
    goToday: () => {
      const { simNow } = get();
      if (simNow) get().setDate(simNow.slice(0, 10));
    },
    setTab: (tab) => set({ tab }),
    pickDrink: (drink) => {
      set({ drink, tab: "guest" });
      reload();
    },
    pickPerson: (person) => {
      set({ person, tab: person ? "drink" : get().tab });
      reload();
    },
    clearDrink: () => {
      set({ drink: "" });
      reload();
    },

    load: async () => {
      const { period, date, drink, person } = get();
      const q = new URLSearchParams({ period, date });
      if (drink) q.set("drink", drink);
      if (person) q.set("person_id", person.id);
      try {
        const [summary, txs, openTabs, days] = await Promise.all([
          getJson<Summary>(`/api/sales/summary?${q}`),
          getJson<Tx[]>(`/api/sales/transactions?${q}`),
          getJson<Tx[]>("/api/sales/open-tabs"),
          getJson<{ first: string | null; last: string | null }>("/api/sales/days"),
        ]);
        set({ summary, txs, openTabs, first: days.first, error: "" });
      } catch (e) {
        set({ error: e instanceof Error ? e.message : String(e) });
      }
    },

    connect: () => {
      let socket: WebSocket | null = null;
      let closed = false;
      let first = true;
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
          if (ev.type === "clock") {
            // The first clock event tells us what "today" is in the sim, so open on that day.
            if (first) {
              first = false;
              set({ simNow: ev.sim_now, date: ev.sim_now.slice(0, 10) });
              reload();
            } else if (ev.sim_now.slice(0, 10) !== get().simNow.slice(0, 10)) {
              set({ simNow: ev.sim_now });
              reload();
            } else {
              set({ simNow: ev.sim_now });
            }
          } else if (ev.type === "sale") {
            clearTimeout(timer);
            timer = setTimeout(reload, 600);
          }
        };
      };
      open();
      return () => {
        closed = true;
        socket?.close();
      };
    },
  };
});
