import { createFileRoute, Link } from "@tanstack/react-router";
import { ClientOnly } from "@tanstack/react-router";
import { lazy, Suspense, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { searchNisarScenes, type NisarScene } from "@/lib/nisar.functions";
import { computeInsights } from "@/lib/insights";
import type { Bounds } from "@/components/WorldMap";

const WorldMap = lazy(() => import("@/components/WorldMap"));

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Arara — Mapa hídrico mundial com radar NISAR" },
      { name: "description", content: "Selecione qualquer área do planeta e veja as passagens do radar NISAR e as mudanças na água." },
      { property: "og:title", content: "Arara — Mapa hídrico mundial com NISAR" },
      { property: "og:description", content: "Selecione uma área no mapa-múndi e o Arara puxa os dados do NISAR ao vivo." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

const hotspots: { name: string; note: string; b: Bounds }[] = [
  { name: "Furnas, BR", note: "reservatório", b: { west: -46.4, south: -21.2, east: -45.6, north: -20.6 } },
  { name: "Pantanal, BR", note: "área alagada", b: { west: -57.6, south: -18.6, east: -56.6, north: -17.8 } },
  { name: "Rio Negro, BR", note: "seca amazônica", b: { west: -60.6, south: -3.3, east: -59.8, north: -2.7 } },
  { name: "Lago Chade", note: "lago encolhendo", b: { west: 13.8, south: 12.8, east: 14.8, north: 13.7 } },
  { name: "Lake Mead, EUA", note: "reservatório", b: { west: -114.9, south: 35.9, east: -114.0, north: 36.5 } },
  { name: "Mar de Aral", note: "lago encolhendo", b: { west: 58.6, south: 44.6, east: 59.9, north: 45.6 } },
];

const ARARA_API = import.meta.env["VITE_ARARA_API_URL"] as string | undefined;
const fmt = (d: string | null) => (d ? new Date(d).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" }) : "—");

function Index() {
  const [selecting, setSelecting] = useState(false);
  const [bounds, setBounds] = useState<Bounds | null>(null);
  const [place, setPlace] = useState<string | null>(null);
  const search = useMutation({ mutationFn: (b: Bounds) => searchNisarScenes({ data: b }) });
  const scenes: NisarScene[] = search.data?.scenes ?? [];
  const ins = useMemo(() => computeInsights(scenes), [scenes]);

  const pick = (b: Bounds, name: string | null) => {
    setSelecting(false); setBounds(b); setPlace(name); search.mutate(b);
  };
  const km2 = bounds ? Math.round(Math.abs(bounds.east - bounds.west) * 111 * Math.cos(((bounds.north + bounds.south) / 2) * Math.PI / 180) * Math.abs(bounds.north - bounds.south) * 111) : 0;

  return (
    <div className="flex h-screen flex-col md:flex-row">
      <aside className="z-10 flex w-full flex-col gap-6 overflow-y-auto border-r bg-background p-6 md:w-[400px]">
        <div className="flex items-center justify-between">
          <span className="font-display text-xl font-extrabold tracking-tight">arara<span className="text-primary">.</span></span>
          <Link to="/furnas" className="font-mono text-xs text-muted-foreground hover:text-foreground">Estudo de Furnas →</Link>
        </div>
        <div>
          <p className="eyebrow">Mapa hídrico mundial · NISAR</p>
          <h1 className="mt-2 font-display text-3xl font-extrabold leading-tight tracking-tight">Escolha qualquer lugar do planeta.</h1>
          <p className="mt-2 text-sm text-muted-foreground">O Arara consulta o catálogo da NASA ao vivo e mostra cada passagem do radar sobre a área.</p>
        </div>

        <button onClick={() => setSelecting((s) => !s)}
          className={`rounded-md px-4 py-3 font-semibold transition ${selecting ? "bg-accent text-accent-foreground" : "bg-primary text-primary-foreground hover:opacity-90"}`}>
          {selecting ? "Arraste no mapa para desenhar…" : "Selecionar área no mapa"}
        </button>

        <div>
          <p className="eyebrow mb-3">Pontos críticos de água</p>
          <div className="grid grid-cols-2 gap-2">
            {hotspots.map((h) => (
              <button key={h.name} onClick={() => pick(h.b, h.name)}
                className={`rounded-md border p-3 text-left transition hover:bg-secondary ${place === h.name ? "border-primary" : ""}`}>
                <div className="text-sm font-semibold">{h.name}</div>
                <div className="font-mono text-[11px] text-muted-foreground">{h.note}</div>
              </button>
            ))}
          </div>
        </div>

        {bounds && (
          <section className="rounded-xl border bg-card p-5">
            <p className="eyebrow">{place ?? "Área selecionada"} · ~{km2.toLocaleString("pt-BR")} km²</p>
            {search.isPending && <p className="mt-4 animate-pulse text-sm text-muted-foreground">Consultando o catálogo NISAR…</p>}
            {search.data?.error && <p className="mt-4 text-sm text-destructive">{search.data.error}</p>}
            {search.isError && <p className="mt-4 text-sm text-destructive">Não foi possível consultar o catálogo agora.</p>}
            {search.isSuccess && !search.data.error && (ins.count === 0 ? (
              <p className="mt-4 text-sm text-muted-foreground">Nenhuma passagem NISAR cobre esta área ainda. Tente uma área próxima ou maior.</p>
            ) : (
              <>
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <Stat v={String(ins.count)} l="cenas de radar" />
                  <Stat v={ins.revisitDays ? `${ins.revisitDays} d` : "—"} l="revisita média" />
                  <Stat v={fmt(ins.last)} l={`última passagem${ins.daysSinceLast != null ? ` · há ${ins.daysSinceLast} d` : ""}`} />
                  <Stat v={fmt(ins.first)} l="primeira passagem" />
                </div>
                <p className="eyebrow mt-6 mb-2">Geometrias de observação</p>
                <ul className="space-y-1 font-mono text-xs">
                  {ins.geometries.slice(0, 4).map((g) => (
                    <li key={g.key} className="flex justify-between"><span>{g.key}</span><span className="text-signal">{g.count}</span></li>
                  ))}
                </ul>
                <p className="eyebrow mt-6 mb-2">Passagens recentes</p>
                <ul className="max-h-40 space-y-1 overflow-y-auto font-mono text-xs text-muted-foreground">
                  {scenes.slice(0, 12).map((s) => (
                    <li key={s.id} className="flex justify-between"><span>{s.start.slice(0, 10)}</span><span>{s.polarization} · T{s.track}</span></li>
                  ))}
                </ul>
                <Analyze bounds={bounds} name={place} />
              </>
            ))}
          </section>
        )}
      </aside>
      <div className="relative flex-1">
        <ClientOnly fallback={<div className="h-full w-full bg-card" />}>
          <Suspense fallback={<div className="h-full w-full bg-card" />}>
            <WorldMap selecting={selecting} bounds={bounds} scenes={scenes} onSelect={(b) => pick(b, null)} />
          </Suspense>
        </ClientOnly>
      </div>
    </div>
  );
}

function Stat({ v, l }: { v: string; l: string }) {
  return <div><div className="font-display text-xl font-extrabold text-signal">{v}</div><div className="text-xs text-muted-foreground">{l}</div></div>;
}

function Analyze({ bounds, name }: { bounds: Bounds; name: string | null }) {
  const [status, setStatus] = useState<string | null>(null);
  const run = async () => {
    if (!ARARA_API) return;
    setStatus("Enviando…");
    try {
      const end = new Date().toISOString().slice(0, 10);
      const start = new Date(Date.now() - 120 * 86400000).toISOString().slice(0, 10);
      const r = await fetch(`${ARARA_API}/api/arara/analysis`, { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: name ?? "Área", bbox: [bounds.west, bounds.south, bounds.east, bounds.north], start, end }) });
      const job = await r.json();
      const id = job.id ?? job.job_id;
      const poll = async (): Promise<void> => {
        const j = await (await fetch(`${ARARA_API}/api/arara/jobs/${id}`)).json();
        setStatus(`Análise: ${j.status}`);
        if (!["completed", "failed", "unavailable"].includes(j.status)) setTimeout(poll, 3000);
      };
      poll();
    } catch { setStatus("O servidor de análise não respondeu."); }
  };
  return (
    <div className="mt-6 border-t pt-5">
      <button onClick={run} disabled={!ARARA_API} className="w-full rounded-md border border-primary px-4 py-2.5 font-semibold text-primary transition hover:bg-primary hover:text-primary-foreground disabled:opacity-50">
        Analisar água nesta área
      </button>
      <p className="mt-2 text-xs text-muted-foreground">
        {status ?? (ARARA_API ? "Classifica a água em cada data e compara antes × depois." : "A medição da água precisa do servidor de análise do Arara conectado.")}
      </p>
    </div>
  );
}
