import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { NisarScene } from "@/lib/nisar.functions";

export type Bounds = { west: number; south: number; east: number; north: number };

export default function WorldMap({ selecting, bounds, scenes, onSelect }: {
  selecting: boolean; bounds: Bounds | null; scenes: NisarScene[]; onSelect: (b: Bounds) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const rect = useRef<L.Rectangle | null>(null);
  const fp = useRef<L.LayerGroup | null>(null);
  const sel = useRef(selecting); sel.current = selecting;
  const cb = useRef(onSelect); cb.current = onSelect;

  useEffect(() => {
    const m = L.map(el.current!, { worldCopyJump: true, zoomControl: false }).setView([0, -20], 2);
    L.control.zoom({ position: "bottomright" }).addTo(m);
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { attribution: "Esri", maxZoom: 18 }).addTo(m);
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", { attribution: "" }).addTo(m);
    fp.current = L.layerGroup().addTo(m);
    let start: L.LatLng | null = null;
    m.on("mousedown", (e: L.LeafletMouseEvent) => { if (sel.current) { start = e.latlng; m.dragging.disable(); } });
    m.on("mousemove", (e: L.LeafletMouseEvent) => {
      if (!start) return;
      const b = L.latLngBounds(start, e.latlng);
      if (rect.current) rect.current.setBounds(b); else rect.current = L.rectangle(b, { color: "#ff7a3d", weight: 2, fillOpacity: 0.08 }).addTo(m);
    });
    m.on("mouseup", (e: L.LeafletMouseEvent) => {
      if (!start) return;
      const b = L.latLngBounds(start, e.latlng); start = null; m.dragging.enable();
      cb.current({ west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() });
    });
    map.current = m;
    return () => { m.remove(); };
  }, []);

  useEffect(() => { el.current!.style.cursor = selecting ? "crosshair" : ""; }, [selecting]);

  useEffect(() => {
    const m = map.current; if (!m || !bounds) return;
    const b = L.latLngBounds([bounds.south, bounds.west], [bounds.north, bounds.east]);
    if (rect.current) rect.current.setBounds(b); else rect.current = L.rectangle(b, { color: "#ff7a3d", weight: 2, fillOpacity: 0.08 }).addTo(m);
    m.flyToBounds(b.pad(1.2), { duration: 0.8 });
  }, [bounds]);

  useEffect(() => {
    const g = fp.current; if (!g) return; g.clearLayers();
    scenes.slice(0, 60).forEach((s) => {
      if (s.footprint.length) L.polygon(s.footprint.map(([x, y]) => [y, x] as [number, number]), { color: "#5ad1f0", weight: 1, opacity: 0.35, fillOpacity: 0 })
        .bindTooltip(`${s.start.slice(0, 10)} · trilha ${s.track}`).addTo(g);
    });
  }, [scenes]);

  return <div ref={el} className="h-full w-full" />;
}
