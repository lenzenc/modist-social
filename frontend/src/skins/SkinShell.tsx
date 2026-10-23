import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from "react";
import { SKINS } from "./index";
import { SkinPicker } from "./shared/SkinPicker";
import { useSkin } from "./useSkin";

const cache: Record<string, LazyExoticComponent<ComponentType>> = {};
const component = (id: string) => (cache[id] ??= lazy(SKINS[id].load));

/** The main page: whichever skin the URL asks for, with the store shared across switches. */
export default function SkinShell() {
  const id = useSkin();
  const Skin = component(id);
  return (
    <>
      <Suspense fallback={null}>
        <Skin />
      </Suspense>
      <SkinPicker />
    </>
  );
}
