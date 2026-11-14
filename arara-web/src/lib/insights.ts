import type { NisarScene } from "./nisar.functions";

export type Insights = {
  count: number;
  first: string | null;
  last: string | null;
  revisitDays: number | null;
  geometries: { key: string; count: number }[];
  daysSinceLast: number | null;
};

export function computeInsights(scenes: NisarScene[], now = new Date()): Insights {
  if (!scenes.length) return { count: 0, first: null, last: null, revisitDays: null, geometries: [], daysSinceLast: null };
  const dates = [...new Set(scenes.map((s) => s.start.slice(0, 10)))].sort();
  const groups = new Map<string, number>();
  for (const s of scenes) {
    const k = `Trilha ${s.track ?? "?"} · ${s.direction === "ASCENDING" ? "asc" : "desc"} · frame ${s.frame ?? "?"}`;
    groups.set(k, (groups.get(k) ?? 0) + 1);
  }
  const day = 86400000;
  const first = dates[0]!, last = dates[dates.length - 1]!;
  const span = (Date.parse(last) - Date.parse(first)) / day;
  return {
    count: scenes.length,
    first,
    last,
    revisitDays: dates.length > 1 ? Math.round((span / (dates.length - 1)) * 10) / 10 : null,
    geometries: [...groups].map(([key, count]) => ({ key, count })).sort((a, b) => b.count - a.count),
    daysSinceLast: Math.floor((now.getTime() - Date.parse(last)) / day),
  };
}
