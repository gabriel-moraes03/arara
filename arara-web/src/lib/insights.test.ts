import { describe, it, expect } from "vitest";
import { computeInsights } from "./insights";
const s = (start: string, track = 24) => ({ id: start, start, track, frame: 99, direction: "DESCENDING", polarization: "DHDH", url: null, footprint: [] });
describe("computeInsights", () => {
  it("average revisit between distinct dates", () => {
    const r = computeInsights([s("2026-06-01T00:00:00Z"), s("2026-06-13T00:00:00Z"), s("2026-06-25T00:00:00Z")], new Date("2026-06-30T00:00:00Z"));
    expect(r.revisitDays).toBe(12);
    expect(r.daysSinceLast).toBe(5);
  });
  it("groups scenes by geometry", () => {
    const r = computeInsights([s("2026-06-01T00:00:00Z", 24), s("2026-06-02T00:00:00Z", 30), s("2026-06-13T00:00:00Z", 24)]);
    expect(r.geometries[0]).toEqual({ key: "Trilha 24 · desc · frame 99", count: 2 });
  });
});
