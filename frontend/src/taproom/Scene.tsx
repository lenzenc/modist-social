import { OrbitControls } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { useEffect } from "react";
import { Bubbles } from "./Bubbles";
import { BAR, CENTER, COUNTER, DOORS, PATIO, ROOM, STOOLS, TABLES, TABLE_SIZE } from "./layout";
import { People } from "./People";
import { useTheme } from "./theme";

const WOOD = "#8a5a33";
const WOOD_DARK = "#5c3b20";

function Box({ x, z, w, d, h, y = 0, color }: { x: number; z: number; w: number; d: number; h: number; y?: number; color: string }) {
  return (
    <mesh position={[x + w / 2, y + h / 2, z + d / 2]}>
      <boxGeometry args={[w, h, d]} />
      <meshStandardMaterial color={color} />
    </mesh>
  );
}

function Table({ x, z, patio }: { x: number; z: number; patio?: boolean }) {
  const [w, d] = TABLE_SIZE;
  const h = patio ? 0.8 : 1.05;
  return (
    <group position={[x, 0, z]}>
      <mesh position={[0, h, 0]}>
        <boxGeometry args={[w, 0.1, d]} />
        <meshStandardMaterial color={WOOD} />
      </mesh>
      <mesh position={[0, h / 2, 0]}>
        <cylinderGeometry args={[0.1, 0.1, h, 8]} />
        <meshStandardMaterial color={WOOD_DARK} />
      </mesh>
    </group>
  );
}

function Stool({ x, z }: { x: number; z: number }) {
  return (
    <group position={[x, 0, z]}>
      <mesh position={[0, 0.35, 0]}>
        <cylinderGeometry args={[0.06, 0.06, 0.7, 8]} />
        <meshStandardMaterial color={WOOD_DARK} />
      </mesh>
      <mesh position={[0, 0.72, 0]}>
        <cylinderGeometry args={[0.28, 0.28, 0.1, 16]} />
        <meshStandardMaterial color={WOOD} />
      </mesh>
    </group>
  );
}

function Room() {
  const t = useTheme();
  const floor = t.dark ? "#2b2f36" : "#e9e2d6";
  const wall = t.dark ? "#3a3f48" : "#cfc6b8";
  const patio = t.dark ? "#33383f" : "#d8d2c6";
  const T = 0.2;
  return (
    <group>
      <Box x={-T} z={-T} w={ROOM.w + T} d={ROOM.d + T} h={0.1} y={-0.1} color={floor} />
      {/* far walls stand tall; near walls stay low so the camera can see in */}
      <Box x={-T} z={-T} w={ROOM.w + T} d={T} h={2.2} color={wall} />
      <Box x={-T} z={0} w={T} d={ROOM.d} h={2.2} color={wall} />
      <Box x={0} z={ROOM.d} w={DOORS[0][0] - 0.8} d={T} h={0.3} color={wall} />
      <Box x={DOORS[0][0] + 0.8} z={ROOM.d} w={DOORS[1][0] - DOORS[0][0] - 1.6} d={T} h={0.3} color={wall} />
      <Box x={DOORS[1][0] + 0.8} z={ROOM.d} w={ROOM.w - DOORS[1][0] - 0.8} d={T} h={0.3} color={wall} />
      <Box x={ROOM.w} z={0} w={T} d={ROOM.d} h={0.3} color={wall} />
      {DOORS.map(([x, z]) => (
        <Box key={x} x={x - 0.8} z={z} w={1.6} d={0.08} h={0.04} color={t.accent} />
      ))}
      <Box x={PATIO.x} z={PATIO.z} w={PATIO.w} d={PATIO.d} h={0.06} y={-0.06} color={patio} />

      <Box x={BAR.x} z={BAR.z} w={BAR.w} d={BAR.d} h={1.05} color={WOOD} />
      <Box x={BAR.x} z={BAR.z} w={BAR.w} d={0.15} h={1.3} y={0} color={WOOD_DARK} />
      <Box x={COUNTER.x} z={COUNTER.z} w={COUNTER.w} d={COUNTER.d} h={1.05} color={WOOD_DARK} />
      {STOOLS.map(([x, z]) => <Stool key={x} x={x} z={z} />)}
      {TABLES["high-tops"].map(([x, z]) => <Table key={`h${x}-${z}`} x={x} z={z} />)}
      {TABLES.patio.map(([x, z]) => <Table key={`p${x}-${z}`} x={x} z={z} patio />)}
    </group>
  );
}

// Fit the whole plan in view whenever the canvas is resized.
function Fit() {
  const { camera, size } = useThree();
  useEffect(() => {
    camera.zoom = Math.max(10, Math.min(size.width / 27, size.height / 15.5));
    camera.updateProjectionMatrix();
  }, [camera, size]);
  return null;
}

const CAMERA = { position: [CENTER[0] + 24, 22, CENTER[1] + 24] as [number, number, number], zoom: 30, near: -100, far: 200 };

export function Scene() {
  const t = useTheme();
  return (
    <Canvas orthographic camera={CAMERA} style={{ background: t.canvas }}>
      <ambientLight intensity={1.1} />
      <directionalLight position={[10, 20, 6]} intensity={1.6} />
      <Fit />
      <OrbitControls makeDefault enableRotate={false} target={[CENTER[0], 0, CENTER[1]]} zoomToCursor />
      <Room />
      <People />
      <Bubbles />
    </Canvas>
  );
}
