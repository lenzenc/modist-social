import { useEffect } from "react";
import { fmtDayTime, fmtTime } from "../util";
import { BarChart, usd } from "./charts";
import { useSales, type Period, type Tab, type Tx } from "./salesStore";

const PERIODS: Period[] = ["day", "week", "month"];

const btn =
  "cursor-pointer rounded-md border border-[var(--border)] px-3 py-1 text-sm font-semibold hover:bg-black/[0.05]";

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--panel)] px-4 py-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className="mt-0.5 text-2xl font-bold">{value}</div>
      {sub && <div className="text-xs text-[var(--muted)]">{sub}</div>}
    </div>
  );
}

function Chip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--accent)] px-3 py-1 text-xs font-semibold text-white">
      {label}
      <button onClick={onClear} className="cursor-pointer opacity-80 hover:opacity-100" aria-label={`Clear ${label}`}>
        ✕
      </button>
    </span>
  );
}

function TxRow({ t }: { t: Tx }) {
  return (
    <tr className="border-t border-[var(--border)] align-top">
      <td className="py-2 pr-3 whitespace-nowrap text-[var(--muted)]">{t.closed_at ? fmtTime(t.closed_at) : "open"}</td>
      <td className="py-2 pr-3 font-semibold">{t.name}</td>
      <td className="py-2 pr-3 whitespace-nowrap">{t.kind === "tab" ? "Tab" : "Per drink"}</td>
      <td className="py-2 pr-3">
        {t.items.map((i, n) => (
          <div key={n}>
            {i.drink} <span className="text-[var(--muted)]">{usd(i.price)}{i.happy_hour && " · HH"}</span>
          </div>
        ))}
      </td>
      <td className="py-2 pr-3 text-right tabular-nums">{usd(t.subtotal)}</td>
      <td className="py-2 pr-3 text-right tabular-nums">{t.status === "closed" ? `${usd(t.tip)} (${t.tip_pct}%)` : "–"}</td>
      <td className="py-2 pr-3 text-right font-semibold tabular-nums">{usd(t.total)}</td>
      <td className="py-2 whitespace-nowrap text-[var(--muted)]">{t.card}</td>
    </tr>
  );
}

export default function SalesPage() {
  const s = useSales();
  const { summary, period, date } = s;

  useEffect(() => {
    document.title = "Taproom Sales";
    void s.load();
    return s.connect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const t = summary?.totals;
  const range = summary?.range;
  const title = !range
    ? ""
    : period === "day"
      ? new Date(`${range.start}T12:00:00`).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric", year: "numeric" })
      : `${new Date(`${range.start}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric" })} – ${new Date(`${range.end}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}`;
  const filtered = Boolean(s.drink || s.person);
  const tabs: [Tab, string][] = [["drink", "By drink"], ["guest", "By guest"], ["tx", "Transactions"]];

  return (
    <div className="mx-auto flex min-h-full max-w-6xl flex-col gap-5 px-4 py-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-2xl font-bold">Taproom sales</div>
          <div className="text-sm text-[var(--muted)]">
            {title}
            {s.simNow && ` · taproom clock ${fmtDayTime(s.simNow)}`}
            {!s.connected && " · reconnecting…"}
          </div>
        </div>
        <a href="/" className={btn}>← Live taproom</a>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded-md border border-[var(--border)]">
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => s.setPeriod(p)}
              className={`cursor-pointer px-3 py-1 text-sm font-semibold capitalize ${p === period ? "bg-[var(--accent)] text-white" : "hover:bg-black/[0.05]"}`}
            >
              {p}
            </button>
          ))}
        </div>
        <button onClick={() => s.step(-1)} className={btn} aria-label="Previous">◀</button>
        <input
          type="date"
          value={date}
          min={s.first ?? undefined}
          onChange={(e) => s.setDate(e.target.value)}
          className="rounded-md border border-[var(--border)] bg-transparent px-2 py-1 text-sm"
        />
        <button onClick={() => s.step(1)} className={btn} aria-label="Next">▶</button>
        <button onClick={s.goToday} className={btn}>Today</button>
        {s.drink && <Chip label={`Drink: ${s.drink}`} onClear={s.clearDrink} />}
        {s.person && <Chip label={`Guest: ${s.person.name}`} onClear={() => s.pickPerson(null)} />}
      </div>

      {s.error && <div className="rounded bg-amber-100 px-3 py-2 text-sm font-semibold text-amber-900">Could not load sales: {s.error}</div>}

      {t && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Kpi label="Sales" value={usd(t.sales)} sub={t.discount ? `${usd(t.discount)} happy-hour discount` : undefined} />
          <Kpi label="Tips" value={filtered && s.drink ? "–" : usd(t.tips)} sub={t.sales && t.tips ? `${((t.tips / t.sales) * 100).toFixed(1)}% of sales` : undefined} />
          <Kpi label="Charged to cards" value={filtered && s.drink ? "–" : usd(t.charged)} sub={`${t.transactions} transactions`} />
          <Kpi label="Drinks" value={String(t.drinks)} sub={`${t.happy_hour_drinks} at happy-hour price`} />
          <Kpi label="Guests" value={String(t.guests)} />
          <Kpi label="Avg. transaction" value={t.avg_ticket ? usd(t.avg_ticket) : "–"} />
          <Kpi label="Avg. per guest" value={t.guests ? usd(Math.round(t.sales / t.guests)) : "–"} />
          <Kpi label="Open tabs" value={String(s.openTabs.length)} sub={s.openTabs.length ? usd(s.openTabs.reduce((a, x) => a + x.subtotal, 0)) + " running" : undefined} />
        </div>
      )}

      {summary && (
        <div className="rounded-lg border border-[var(--border)] p-4">
          <div className="mb-3 flex items-center justify-between text-sm">
            <span className="font-semibold">{period === "day" ? "Sales by hour" : "Sales by day"}</span>
            <span className="flex items-center gap-3 text-xs text-[var(--muted)]">
              <span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-[var(--accent)]" />sales</span>
              <span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-[var(--ok)]" />tips</span>
              {Object.entries(summary.crowd ?? {}).map(([d, v]) => (
                <span key={d} className="rounded bg-black/[0.06] px-1.5 py-0.5" title="Crowd setting used that day">
                  {period === "day" ? "" : d.slice(5) + " "}{v > 1 ? "busy" : "quiet"} crowd ×{v}
                </span>
              ))}
              {period !== "day" && <span>click a day to open it</span>}
            </span>
          </div>
          <BarChart
            data={summary.series}
            onPick={period === "day" ? undefined : (b) => { s.setPeriod("day"); s.setDate(b.key); }}
          />
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
        <div className="min-w-0 rounded-lg border border-[var(--border)]">
          <div className="flex gap-1 border-b border-[var(--border)] px-3 pt-2">
            {tabs.map(([k, label]) => (
              <button
                key={k}
                onClick={() => s.setTab(k)}
                className={`cursor-pointer border-b-2 px-3 py-1.5 text-sm font-semibold ${s.tab === k ? "border-[var(--accent)] text-[var(--accent)]" : "border-transparent text-[var(--muted)]"}`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="overflow-x-auto p-3">
            {s.tab === "drink" && (
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-[var(--muted)]">
                  <tr><th className="pb-2">Drink</th><th className="pb-2 text-right">Qty</th><th className="pb-2 text-right">Happy hour</th><th className="pb-2 text-right">Sales</th></tr>
                </thead>
                <tbody>
                  {summary?.by_drink.map((d) => (
                    <tr key={d.drink} onClick={() => s.pickDrink(d.drink)} className="cursor-pointer border-t border-[var(--border)] hover:bg-black/[0.04]">
                      <td className="py-1.5 pr-3 font-medium">{d.drink}</td>
                      <td className="py-1.5 text-right tabular-nums">{d.qty}</td>
                      <td className="py-1.5 text-right tabular-nums text-[var(--muted)]">{d.hh_qty || ""}</td>
                      <td className="py-1.5 text-right tabular-nums">{usd(d.sales)}</td>
                    </tr>
                  ))}
                  {summary && !summary.by_drink.length && <tr><td colSpan={4} className="py-6 text-center text-[var(--muted)]">No drinks sold in this period yet.</td></tr>}
                </tbody>
              </table>
            )}
            {s.tab === "guest" && (
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-[var(--muted)]">
                  <tr><th className="pb-2">Guest</th><th className="pb-2 text-right">Drinks</th><th className="pb-2 text-right">Sales</th><th className="pb-2 text-right">Tips</th><th className="pb-2 text-right">Paid</th></tr>
                </thead>
                <tbody>
                  {summary?.by_person.map((p) => (
                    <tr key={p.id} onClick={() => s.pickPerson({ id: p.id, name: p.name })} className="cursor-pointer border-t border-[var(--border)] hover:bg-black/[0.04]">
                      <td className="py-1.5 pr-3 font-medium">{p.name}</td>
                      <td className="py-1.5 text-right tabular-nums">{p.drinks}</td>
                      <td className="py-1.5 text-right tabular-nums">{usd(p.sales)}</td>
                      <td className="py-1.5 text-right tabular-nums">{usd(p.tips)}</td>
                      <td className="py-1.5 text-right text-xs text-[var(--muted)]">
                        {[p.tabs && `${p.tabs} tab${p.tabs > 1 ? "s" : ""}`, p.per_drink && `${p.per_drink} per drink`].filter(Boolean).join(", ")}
                      </td>
                    </tr>
                  ))}
                  {summary && !summary.by_person.length && <tr><td colSpan={5} className="py-6 text-center text-[var(--muted)]">Nobody has bought a drink in this period yet.</td></tr>}
                </tbody>
              </table>
            )}
            {s.tab === "tx" && (
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-[var(--muted)]">
                  <tr><th className="pb-2">Closed</th><th className="pb-2">Guest</th><th className="pb-2">Type</th><th className="pb-2">Drinks</th><th className="pb-2 text-right">Subtotal</th><th className="pb-2 text-right">Tip</th><th className="pb-2 text-right">Total</th><th className="pb-2">Card</th></tr>
                </thead>
                <tbody>
                  {s.txs.map((x) => <TxRow key={x.id} t={x} />)}
                  {!s.txs.length && <tr><td colSpan={8} className="py-6 text-center text-[var(--muted)]">No closed transactions in this period yet.</td></tr>}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-[var(--border)] p-3">
          <div className="mb-2 text-sm font-semibold">Open tabs right now</div>
          {s.openTabs.length === 0 && <div className="py-4 text-center text-sm text-[var(--muted)]">All tabs are closed.</div>}
          {s.openTabs.map((x) => (
            <div key={x.id} className="border-t border-[var(--border)] py-2 text-sm first:border-t-0">
              <div className="flex justify-between font-semibold"><span>{x.name}</span><span className="tabular-nums">{usd(x.subtotal)}</span></div>
              <div className="text-xs text-[var(--muted)]">
                since {fmtDayTime(x.opened_at)} · {x.items.length} drink{x.items.length === 1 ? "" : "s"}
              </div>
              <div className="text-xs text-[var(--muted)]">{x.items.map((i) => i.drink).join(", ")}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
