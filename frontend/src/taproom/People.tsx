import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Group } from "three";
import { useStore } from "../store";
import { doorFor, placeAll, type Spot, type Vec2 } from "./layout";

const LEAVE_MS = 2500;
/** Everyone present, plus anyone who left in the last couple of seconds still walking out the door. */
export function People() {
  const presence = useStore((s) => s.presence);
  const people = useStore((s) => s.people);
  const onShift = useStore((s) => s.clock?.on_shift);
  const [, tick] = useState(0);
  const leaving = useRef<Record<string, { until: number; from: Vec2 }>>({});
  const last = useRef<Record<string, Spot>>({});

  const spots = useMemo(
    () => placeAll(Object.values(presence), (id) => people[id]?.role === "bartender", onShift ?? []),
    [presence, people, onShift],
  );

  useEffect(() => {
    const now = Date.now();
    for (const id of Object.keys(last.current)) {
      if (!spots[id] && !leaving.current[id]) {
        leaving.current[id] = { until: now + LEAVE_MS, from: last.current[id].pos };
        setTimeout(() => tick((n) => n + 1), LEAVE_MS + 50);
      }
    }
    for (const id of Object.keys(spots)) delete leaving.current[id];
    last.current = spots;
  }, [spots]);

  const now = Date.now();
  const gone = Object.entries(leaving.current).filter(([, l]) => l.until > now);
  return (
    <>
      {Object.entries(spots).map(([id, s]) => (
        <Figure key={id} id={id} target={s.pos} sit={s.sit} />
      ))}
      {gone.map(([id, l]) => (
        <Figure key={id} id={id} target={doorFor(id)} sit={false} start={l.from} />
      ))}
    </>
  );
}

function Figure({ id, target, sit, start }: { id: string; target: Vec2; sit: boolean; start?: Vec2 }) {
  const person = useStore((s) => s.people[id]);
  const drink = useStore((s) => s.presence[id]?.drink);
  const active = useStore((s) => s.profileId === id || (s.openThread != null && s.presence[id]?.thread_id === s.openThread));
  const openProfile = useStore((s) => s.openProfile);
  const ref = useRef<Group>(null);
  const [hover, setHover] = useState(false);
  const born = useRef(start ?? doorFor(id));

  useFrame((_, dt) => {
    const g = ref.current;
    if (!g) return;
    const k = 1 - Math.exp(-dt * 2.2);
    g.position.x += (target[0] - g.position.x) * k;
    g.position.z += (target[1] - g.position.z) * k;
    g.position.y += ((sit ? 0.42 : 0) - g.position.y) * Math.min(1, dt * 8);
  });

  if (!person) return null;
  const bt = person.role === "bartender";
  return (
    <group ref={ref} position={[born.current[0], 0, born.current[1]]}>
      <group
        onClick={(e) => (e.stopPropagation(), void openProfile(id))}
        onPointerOver={(e) => (e.stopPropagation(), setHover(true), (document.body.style.cursor = "pointer"))}
        onPointerOut={() => (setHover(false), (document.body.style.cursor = ""))}
      >
        <mesh position={[0, 0.65, 0]}>
          <capsuleGeometry args={[0.26, 0.55, 4, 12]} />
          <meshStandardMaterial color={person.color} />
        </mesh>
        <mesh position={[0, 1.4, 0]}>
          <sphereGeometry args={[0.22, 16, 12]} />
          <meshStandardMaterial color="#f1cfae" />
        </mesh>
        {bt && (
          <mesh position={[0, 0.55, 0.2]}>
            <boxGeometry args={[0.4, 0.55, 0.1]} />
            <meshStandardMaterial color="#6b4423" />
          </mesh>
        )}
        {drink && (
          <mesh position={[0.34, 0.75, 0.15]}>
            <cylinderGeometry args={[0.09, 0.07, 0.22, 10]} />
            <meshStandardMaterial color="#e0a526" />
          </mesh>
        )}
      </group>
      {active && (
        <mesh position={[0, 0.03, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.42, 0.52, 24]} />
          <meshBasicMaterial color="#e0a526" />
        </mesh>
      )}
      {hover && (
        <Html position={[0, 1.9, 0]} center zIndexRange={[20, 0]} style={{ pointerEvents: "none" }}>
          <div className="whitespace-nowrap rounded bg-black/80 px-2 py-0.5 text-xs font-semibold text-white">
            {person.display}
          </div>
        </Html>
      )}
    </group>
  );
}
