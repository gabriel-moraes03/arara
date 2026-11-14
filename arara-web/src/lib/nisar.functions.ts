import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";

export type NisarScene = {
  id: string;
  start: string;
  track: number | null;
  frame: number | null;
  direction: string;
  polarization: string;
  url: string | null;
  footprint: number[][];
};

const Bbox = z.object({
  west: z.number().min(-180).max(180),
  south: z.number().min(-90).max(90),
  east: z.number().min(-180).max(180),
  north: z.number().min(-90).max(90),
});

export const searchNisarScenes = createServerFn({ method: "POST" })
  .inputValidator((d: unknown) => Bbox.parse(d))
  .handler(async ({ data }) => {
    const bbox = [data.west, data.south, data.east, data.north].map((n) => n.toFixed(4)).join(",");
    const url = `https://api.daac.asf.alaska.edu/services/search/param?dataset=NISAR&processingLevel=GCOV&bbox=${bbox}&maxResults=250&output=geojson`;
    const res = await fetch(url, { headers: { accept: "application/geo+json" } });
    if (!res.ok) return { scenes: [] as NisarScene[], error: `Catálogo da NASA respondeu ${res.status}` };
    const json = (await res.json()) as { features?: any[] };
    const scenes: NisarScene[] = (json.features ?? []).map((f) => {
      const p = f.properties ?? {};
      const id: string = p.fileID ?? p.sceneName ?? "";
      const parts = id.split("_");
      return {
        id,
        start: p.startTime ?? p.stopTime ?? "",
        track: p.pathNumber ?? null,
        frame: p.frameNumber ?? (parts[7] ? Number(parts[7]) : null),
        direction: p.flightDirection ?? "",
        polarization: parts[9] ?? "",
        url: p.url ?? null,
        footprint: f.geometry?.type === "Polygon" ? f.geometry.coordinates[0] : [],
      };
    });
    scenes.sort((a, b) => b.start.localeCompare(a.start));
    return { scenes, error: null as string | null };
  });
