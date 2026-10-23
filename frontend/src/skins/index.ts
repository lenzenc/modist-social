import type { ComponentType } from "react";
import App from "../App";

/** Alternate shells for the main page, picked with `?ui=<id>`. Every skin shares the store and socket; only the layout differs. */
export interface SkinDef {
  label: string;
  blurb: string;
  load: () => Promise<{ default: ComponentType }>;
}

export const SKINS: Record<string, SkinDef> = {
  slack: { label: "Slack", blurb: "Channels, threads and a profile pane", load: () => Promise.resolve({ default: App }) },
  tonight: { label: "Taproom Tonight", blurb: "The bar as a place: neon, chalkboard, live tables", load: () => import("./tonight") },
  floor: { label: "Floor Map", blurb: "A 2D plan of the room with conversations as halos", load: () => import("./floor") },
  storyboard: { label: "Storyboard", blurb: "Cinematic reading view with a cast strip", load: () => import("./storyboard") },
  control: { label: "Control Room", blurb: "The director's console: timeline, gauges, log", load: () => import("./control") },
};

export const DEFAULT_SKIN = "slack";
export const skinIds = Object.keys(SKINS);
