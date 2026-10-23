import { useEffect, useRef, useState } from "react";
import { SKINS, skinIds } from "../index";
import { setSkin, useSkin } from "../useSkin";

/** A small floating switch so every layout is one click away during a demo. */
export function SkinPicker() {
  const id = useSkin();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  return (
    <div ref={ref} className="fixed right-4 bottom-12 z-50 text-[13px]" style={{ fontFamily: "ui-sans-serif, system-ui, sans-serif" }}>
      {open && (
        <div className="mb-2 w-64 overflow-hidden rounded-xl border border-white/10 bg-[#141416]/95 text-[#e8e8ea] shadow-2xl backdrop-blur">
          <div className="px-3 pt-2.5 pb-1 text-[10px] font-semibold tracking-[0.14em] text-white/45 uppercase">Layout</div>
          {skinIds.map((k) => (
            <button
              key={k}
              onClick={() => {
                setSkin(k);
                setOpen(false);
              }}
              className={`block w-full cursor-pointer px-3 py-2 text-left hover:bg-white/8 ${k === id ? "bg-white/10" : ""}`}
            >
              <div className="flex items-center gap-2 font-semibold">
                <span className={`inline-block h-1.5 w-1.5 rounded-full ${k === id ? "bg-emerald-400" : "bg-white/20"}`} />
                {SKINS[k].label}
              </div>
              <div className="pl-3.5 text-[11px] text-white/50">{SKINS[k].blurb}</div>
            </button>
          ))}
        </div>
      )}
      <button
        onClick={() => setOpen(!open)}
        title="Switch layout"
        className="flex cursor-pointer items-center gap-2 rounded-full border border-white/10 bg-[#141416]/90 px-3 py-1.5 font-semibold text-[#e8e8ea] shadow-lg backdrop-blur hover:bg-[#1f1f23]"
      >
        <span className="text-[11px] text-white/50">UI</span>
        {SKINS[id].label}
        <span className="text-[10px] text-white/50">▾</span>
      </button>
    </div>
  );
}
