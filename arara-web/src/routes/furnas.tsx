import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

export const Route = createFileRoute("/furnas")({
  head: () => ({
    meta: [
      { title: "Estudo de Furnas — Arara" },
      { name: "description", content: "Arara usa o radar NISAR (banda L) para medir mudanças na água em qualquer área do planeta. Validado em Furnas com erro médio de 1%." },
      { property: "og:title", content: "Arara — água vista pelo radar NISAR" },
      { property: "og:description", content: "Escolha uma área, o Arara mede onde a água avançou ou recuou com radar que enxerga através das nuvens." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

const stats = [
  { v: "1,0%", l: "erro médio vs. ANA nas datas calmas" },
  { v: "1.332 km²", l: "reservatório de Furnas monitorado" },
  { v: "9", l: "passagens NISAR, jun–out 2026" },
  { v: "−32,9 km²", l: "de água perdida em 108 dias" },
];

const steps = [
  ["01", "Escolha a área", "Busque um lugar ou desenhe um polígono de até 2.500 km² no globo."],
  ["02", "Catálogo ao vivo", "O Arara consulta o ASF DAAC e lê só a janela da sua área em cada cena GCOV."],
  ["03", "Classifica a água", "Canal HH em dB, média 5×5 e um limiar único por série no vale água/terra."],
  ["04", "Compara e confere", "Diferença entre datas, checagem com Sentinel-2 e datas com vento marcadas."],
];

function Compare() {
  const [pos, setPos] = useState(50);
  return (
    <div className="relative aspect-[4/3] w-full overflow-hidden rounded-xl border bg-card">
      <img src="/furnas/hh_20261013.jpg" alt="Radar HH de Furnas em 13/10/2026" className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 overflow-hidden" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
        <img src="/furnas/hh_20260627.jpg" alt="Radar HH de Furnas em 27/06/2026" className="h-full w-full object-cover" />
      </div>
      <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-primary" style={{ left: `${pos}%` }} />
      <span className="eyebrow absolute left-3 top-3 rounded bg-background/80 px-2 py-1">27 jun</span>
      <span className="eyebrow absolute right-3 top-3 rounded bg-background/80 px-2 py-1">13 out</span>
      <input aria-label="Comparar datas" type="range" min={0} max={100} value={pos} onChange={(e) => setPos(+e.target.value)}
        className="absolute bottom-4 left-1/2 w-2/3 -translate-x-1/2 accent-primary" />
    </div>
  );
}

function Index() {
  return (
    <main className="mx-auto max-w-6xl px-6">
      <nav className="flex items-center justify-between py-6">
        <span className="font-display text-xl font-extrabold tracking-tight">arara<span className="text-primary">.</span></span>
        <div className="flex gap-6 font-mono text-xs text-muted-foreground">
          <a href="#furnas" className="hover:text-foreground">Furnas</a>
          <a href="#metodo" className="hover:text-foreground">Método</a>
          <a href="https://github.com/gabriel-moraes03/arara" className="hover:text-foreground">GitHub</a>
        </div>
      </nav>

      <section className="grid items-center gap-12 py-16 md:grid-cols-[1.2fr_1fr] md:py-24">
        <div>
          <p className="eyebrow">NASA Space Apps 2026 · NISAR banda L</p>
          <h1 className="mt-5 font-display text-5xl font-extrabold leading-[0.95] tracking-tight md:text-7xl">
            Onde a água <span className="text-water">avançou</span> ou <span className="text-dry">recuou</span>.
          </h1>
          <p className="mt-6 max-w-lg text-lg text-muted-foreground">
            Radar que enxerga de dia, de noite e através das nuvens. Escolha uma área no planeta e o Arara mede a mudança na água — e diz quando não dá para medir.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <a href="#furnas" className="rounded-md bg-primary px-5 py-3 font-semibold text-primary-foreground transition hover:opacity-90">Ver o estudo de Furnas</a>
            <a href="#metodo" className="rounded-md border px-5 py-3 font-semibold transition hover:bg-secondary">Como funciona</a>
          </div>
        </div>
        <div className="relative mx-auto aspect-square w-full max-w-sm overflow-hidden rounded-full border">
          <img src="/furnas/cor_20260627.jpg" alt="Composição colorida HH/HV do NISAR sobre Furnas" className="h-full w-full object-cover" />
          <div className="radar-sweep absolute inset-0 rounded-full" />
          <div className="absolute inset-[25%] rounded-full border border-accent/30" />
        </div>
      </section>

      <section className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border md:grid-cols-4">
        {stats.map((s) => (
          <div key={s.l} className="bg-background p-6">
            <div className="font-display text-3xl font-extrabold text-signal">{s.v}</div>
            <div className="mt-1 text-sm text-muted-foreground">{s.l}</div>
          </div>
        ))}
      </section>

      <section id="furnas" className="py-24">
        <p className="eyebrow">Estudo validado</p>
        <h2 className="mt-3 font-display text-4xl font-extrabold tracking-tight">Furnas, Minas Gerais — 2026</h2>
        <p className="mt-3 max-w-2xl text-muted-foreground">
          A cota caiu 0,87 m entre julho e setembro. Arraste para comparar o retroespalhamento HH antes e depois: água calma aparece escura.
        </p>
        <div className="mt-10 grid gap-6 md:grid-cols-2">
          <Compare />
          <figure className="relative aspect-[4/3] overflow-hidden rounded-xl border bg-card">
            <img src="/furnas/hh_20261013.jpg" alt="" className="absolute inset-0 h-full w-full object-cover opacity-40" />
            <img src="/furnas/mudanca.png" alt="Mapa de mudança da água em Furnas" className="absolute inset-0 h-full w-full object-cover" />
            <figcaption className="absolute bottom-3 left-3 flex gap-4 rounded bg-background/85 px-3 py-2 font-mono text-xs">
              <span className="flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-full bg-dry" />secou 32,9 km²</span>
              <span className="flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-full bg-water" />água nova 13,0 km²</span>
            </figcaption>
          </figure>
        </div>
      </section>

      <section id="metodo" className="pb-24">
        <p className="eyebrow">Método</p>
        <h2 className="mt-3 font-display text-4xl font-extrabold tracking-tight">Tudo o que aparece é medido.</h2>
        <div className="mt-10 grid gap-4 md:grid-cols-4">
          {steps.map(([n, t, d]) => (
            <div key={n} className="rounded-xl border bg-card p-6">
              <div className="font-mono text-sm text-primary">{n}</div>
              <h3 className="mt-4 font-display text-xl font-semibold">{t}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{d}</p>
            </div>
          ))}
        </div>
        <p className="mt-8 max-w-2xl font-mono text-xs text-muted-foreground">
          Quando o dado real não pode ser obtido, a resposta é “indisponível”, com o motivo. Datas com suspeita de vento (07/09 e 01/10) ficam marcadas, sem correção.
        </p>
      </section>

      <footer className="flex flex-wrap justify-between gap-4 border-t py-8 font-mono text-xs text-muted-foreground">
        <span>Arara · MIT · Dados NISAR via ASF DAAC · Cota × área ANA/SNIRH</span>
        <span>NASA Space Apps Challenge 2026</span>
      </footer>
    </main>
  );
}
