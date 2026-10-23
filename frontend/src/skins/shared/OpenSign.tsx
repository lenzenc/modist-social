import { useStore } from "../../store";

/** A neon OPEN / CLOSED sign driven by the sim clock. */
export function OpenSign({ className = "" }: { className?: string }) {
  const open = useStore((s) => s.clock?.open ?? false);
  return (
    <span className={`neon ${open ? "" : "off"} ${className}`} title={open ? "The taproom is open" : "Closed"}>
      {open ? "OPEN" : "CLOSED"}
    </span>
  );
}
