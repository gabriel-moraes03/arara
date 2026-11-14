/* Estudo automático: tudo vem de /api/arara/analyses/{id}. Nada é digitado à mão. */
(() => {
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v, d = 0) => v == null || isNaN(v) ? '–' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
const sg = (v, d = 1) => `${v >= 0 ? '+' : '−'}${fmt(Math.abs(v), d)}`;
const br = (s) => { const [y, m, d] = String(s).slice(0, 10).split('-'); return `${d}/${m}/${y}`; };
const dm = (s) => br(s).slice(0, 5);
const API = '/api/arara';
const id = new URLSearchParams(location.search).get('id');
const main = $('#top'), ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/';
const MAT = { PROVISIONAL: 'produto provisório', VALIDATED: 'produto validado', BETA: 'produto beta', LOCAL: 'cenas locais' };
const fail = (m) => { main.innerHTML = `<p class="state err">${esc(m)}</p>`; };
if (!id || !/^[0-9a-f]{8,64}$/.test(id)) { fail('Estudo não informado. Abra um estudo pelo globo (painel da análise → "Abrir estudo completo").'); return; }

fetch(`${API}/analyses/${id}`).then(async (r) => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.reason || `erro ${r.status}`); return j; })
  .then(render).catch((e) => fail('Não foi possível carregar este estudo: ' + e.message + '. Se ele tem mais de 7 dias, os derivados foram apagados; refaça a análise.'));

function base(el, bounds) {
  const m = L.map(el, { zoomControl: false, worldCopyJump: true });
  L.control.zoom({ position: 'bottomright' }).addTo(m);
  L.tileLayer(ESRI + 'World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 18, attribution: 'Esri, Maxar, Earthstar Geographics' }).addTo(m);
  L.tileLayer(ESRI + 'Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', { maxZoom: 18, opacity: .9 }).addTo(m);
  m.fitBounds([[bounds.south, bounds.west], [bounds.north, bounds.east]]);
  return m;
}
const png = (a, l) => `${API}/analyses/${a.analysis_id}/png/${l}.png`;
const lb = (l) => [[l.bounds.south, l.bounds.west], [l.bounds.north, l.bounds.east]];

function render(a) {
  const S = a.dates, first = S[0], last = S[S.length - 1], c = a.comparison, g = a.group || {}, v = a.optical_validation || {}, P = a.patterns || {};
  const layers = a.layers || [], byId = (k) => layers.find(l => l.id === k), wl = layers.filter(l => l.type === 'water');
  const ref = byId('change') || wl[wl.length - 1] || layers[0], bnd = (ref || {}).bounds || { south: a.aoi.bbox[1], west: a.aoi.bbox[0], north: a.aoi.bbox[3], east: a.aoi.bbox[2] };
  const pct = first.water_km2 ? 100 * (last.water_km2 - first.water_km2) / first.water_km2 : null;
  document.title = `${a.name || 'Estudo'} · Arara`; $('#bar-info').textContent = `${MAT[g.maturity] || 'NISAR'} · trilha ${g.track ?? '–'} ${g.direction ?? ''} · frame ${g.frame ?? '–'}`;
  const csv = $('#csv'); csv.hidden = false; csv.href = `${API}/analyses/${a.analysis_id}/metrics?format=csv`;
  const wind = S.filter(p => p.suspeita_vento);
  const tr = P.trend && P.trend.status === 'ok' ? P.trend : null, an = P.anomaly && P.anomaly.status === 'ok' ? P.anomaly : null, fq = P.frequency && P.frequency.permanent_km2 != null ? P.frequency : null;
  const hot = (P.retraction_hotspots || []);
  const ins = a.insights || {}, antes = 'Esta análise é anterior aos padrões medidos; refaça a análise (estudar_lote.py --refazer) para calculá-los.';

  main.innerHTML = `
  <section class="hero auto">
    <div class="map hero-map" id="map-hero"></div>
    <div class="hero-text">
      <p class="kicker">Estudo automático · ${esc(a.sensor)}</p>
      <h1>${esc(a.name || 'Área analisada')}: ${fmt(last.water_km2, last.water_km2 < 100 ? 1 : 0)} km² de água</h1>
      <p class="dek">${S.length > 1 ? `Em ${S.length} passagens do NISAR, de ${br(first.date)} a ${br(last.date)}, a água ${pct < 0 ? 'diminuiu' : 'aumentou'} ${fmt(Math.abs(pct), 1)}% (${sg(last.water_km2 - first.water_km2, 1)} km²).` : `Uma passagem válida, em ${br(first.date)}.`} Cada número abaixo foi medido pelo radar sobre esta área e pode ser conferido nas cenas listadas no fim.</p>
      <div class="chips"><span class="chip ok">${esc(MAT[g.maturity] || 'NISAR')}</span>${a.experimental ? '<span class="chip warn">experimental</span>' : ''}${v.status === 'validated' ? `<span class="chip ok">validado com Sentinel-2 · IoU ${fmt(v.mean_iou, 2)}</span>` : '<span class="chip warn">sem validação óptica</span>'}${wind.length ? `<span class="chip warn">vento em ${wind.map(p => dm(p.date)).join(', ')}</span>` : ''}</div>
    </div>
  </section>

  <section class="sec"><div class="wrap wide"><div class="stats">
    <div class="stat"><span class="stat-v num">${fmt(last.water_km2, last.water_km2 < 100 ? 1 : 0)}<small>km²</small></span><p>de água em ${br(last.date)} (${fmt(last.water_pct, 1)}% da área analisada de ${fmt(a.aoi.area_km2, 0)} km²)</p></div>
    <div class="stat"><span class="stat-v num">${c ? sg(c.net_change_ha, 0) : '–'}<small>ha</small></span><p>saldo entre ${c ? `${br(c.before)} e ${br(c.after)}` : 'passagens'}: ${c ? `${fmt(c.expansion_ha, 0)} ha de água nova, ${fmt(c.retraction_ha, 0)} ha perdidos` : 'precisa de duas datas'}</p></div>
    <div class="stat"><span class="stat-v num">${v.status === 'validated' ? fmt(v.mean_iou, 2) : '–'}</span><p>${v.status === 'validated' ? `IoU médio contra o Sentinel-2 em ${v.n_dates_validated} de ${v.n_dates} datas` : esc(v.reason || 'sem validação óptica')}</p></div>
  </div></div></section>

  <section class="sec" id="padroes"><div class="wrap wide">
    <p class="kicker">O que a série mostra</p><h2>Padrões medidos</h2>
    <div class="cards">
      <div class="card"><h3>Tendência</h3>${tr ? `<div class="v">${sg(tr.km2_per_week, 2)}<small>km²/semana</small></div><p>${fmt(Math.abs(tr.pct_per_month), 1)}% ao mês, ${tr.direction}, desde ${br(tr.since)} (${tr.n_dates} datas, ${esc(tr.method)}). ${esc(tr.note)}.</p>` : `<p>${esc((P.trend || {}).reason || antes)}</p>`}</div>
      <div class="card ${an && an.level === 'alerta' ? 'alert' : an && an.level === 'atenção' ? 'warn' : ''}"><h3>Alerta da última passagem</h3>${an ? `<div class="v">${an.level}<small>${sg(an.pct_vs_normal, 1)}% vs normal</small></div><p>Em ${br(an.last_date)} havia ${fmt(an.last_km2, 2)} km², ${an.direction} do normal da série (${fmt(an.normal_km2, 2)} km²). ${esc(an.note || '')}</p>` : `<p>${esc((P.anomaly || {}).reason || antes)}</p>`}</div>
      <div class="card"><h3>Permanência da água</h3>${fq ? `<div class="v">${fmt(fq.permanent_km2, 1)}<small>km² permanente</small></div><p>${fmt(fq.seasonal_km2, 1)} km² sazonal e ${fmt(fq.occasional_km2, 1)} km² ocasional, em ${fq.n_dates} datas. Permanente: água em 90% ou mais das datas.</p>` : `<p>${esc((P.frequency || {}).reason || antes)}</p>`}</div>
      <div class="card"><h3>Trechos que mais secaram</h3>${hot.length ? `<ul class="top3">${hot.map((h, i) => `<li><button type="button" data-i="${i}">#${h.rank} · ${fmt(h.area_ha, 1)} ha<small>${fmt(h.lat, 4)}, ${fmt(h.lon, 4)}</small></button></li>`).join('')}</ul>` : `<p>${a.patterns ? 'Nenhum trecho contíguo perdeu água acima de 1 ha.' : antes}</p>`}</div>
    </div>
    <div class="legend2" id="lg-hero"></div>
    <div class="chips" id="hero-layers"></div>
  </div></section>

  <section class="sec" id="tempo"><div class="wrap wide">
    <p class="kicker">Linha do tempo</p><h2>A água em cada passagem</h2>
    <p>Cada data foi classificada com o mesmo limiar (${fmt(a.params.threshold_db, 2)} dB). Arraste para ver a água medida mudar.</p>
    <div class="map tlmap" id="map-time"></div>
    <div class="tlbar"><button class="btn btn-accent" id="play" type="button">▶ Reproduzir</button><input id="slider" type="range" min="0" max="${S.length - 1}" value="${S.length - 1}" aria-label="Data"><span class="tldate" id="tl-date"></span><span class="tldate" id="tl-area"></span></div>
  </div></section>

  ${c && byId(`hh_${first.date.replaceAll('-', '')}`) && byId(`hh_${last.date.replaceAll('-', '')}`) ? `
  <section class="sec" id="antes"><div class="split wrap wide">
    <div><p class="kicker">Antes × depois</p><h2>${dm(first.date)} e ${dm(last.date)}</h2>
      <p>Arraste a barra para comparar o retroespalhamento HH. Água calma aparece escura: o radar quase não recebe sinal de volta.</p>
      <div class="cmp" id="cmp" style="--ar:${(bnd.east - bnd.west) / (bnd.north - bnd.south) * Math.cos((bnd.north + bnd.south) / 2 * Math.PI / 180)}"><img alt="HH em ${br(last.date)}" src="${png(a, 'hh_' + last.date.replaceAll('-', ''))}"><img class="top" id="cmp-top" alt="HH em ${br(first.date)}" src="${png(a, 'hh_' + first.date.replaceAll('-', ''))}"><div class="cut" id="cmp-cut"></div><span class="tag" style="left:10px">${dm(first.date)}</span><span class="tag" style="right:10px">${dm(last.date)}</span><input type="range" id="cmp-r" min="0" max="100" value="50" aria-label="Comparar datas"></div></div>
    <div><p class="kicker">Medido</p><h2>O que mudou</h2>
      <div class="cards"><div class="card"><h3>Perdeu água</h3><div class="v">${fmt(c.retraction_ha, 0)}<small>ha</small></div></div><div class="card"><h3>Ganhou água</h3><div class="v">${fmt(c.expansion_ha, 0)}<small>ha</small></div></div><div class="card"><h3>Água nas duas datas</h3><div class="v">${fmt(c.stable_water_ha, 0)}<small>ha</small></div></div></div>
      ${P.event && P.event.before !== c.before ? `<p style="margin-top:18px"><b>Modo evento</b> (última passagem × anterior, ${br(P.event.before)} → ${br(P.event.after)}): ${sg(P.event.net_change_ha, 1)} ha${P.event.wind_caveat ? ', com suspeita de vento em uma das datas' : ''}. Ative a camada "Última passagem" no mapa de cima.</p>` : ''}
      <p class="aside">${c.wind_caveat ? 'Uma das duas datas tem suspeita de vento: parte desta diferença pode não ser real. ' : ''}O Arara mede a mudança; a causa fica na hipótese abaixo.</p></div>
  </div></section>` : ''}

  <section class="sec proof" id="prova"><div class="wrap wide">
    <p class="kicker">Conferência</p><h2>Série e validação</h2>
    <div class="svgwrap" id="chart"></div>
    <div class="legend2"><span><i style="background:var(--accent)"></i>medido pelo NISAR</span>${wind.length ? '<span><i style="background:transparent;border:2px solid var(--ochre)"></i>suspeita de vento</span>' : ''}${a.forecast && a.forecast.status === 'ok' ? '<span><i style="background:var(--accent-dim);border:1px dashed var(--accent)"></i>projeção experimental (p10–p90)</span>' : ''}</div>
    ${v.per_date ? `<table class="tbl"><thead><tr><th>Radar</th><th>Sentinel-2</th><th>IoU</th><th>F1</th><th>Precisão</th><th>Recall</th><th>Água radar km²</th><th>Água óptico km²</th></tr></thead><tbody>${v.per_date.map(p => p.status === 'validated' ? `<tr class="${p.suspeita_vento ? 'vento' : ''}"><td>${br(p.date)}</td><td>${br(p.optical_date)} (${p.days_apart} d)</td><td>${fmt(p.iou, 2)}</td><td>${fmt(p.f1, 2)}</td><td>${fmt(p.precision, 2)}</td><td>${fmt(p.recall, 2)}</td><td>${fmt(p.sar_water_km2, 2)}</td><td>${fmt(p.optical_water_km2, 2)}</td></tr>` : `<tr><td>${br(p.date)}</td><td colspan="7" style="text-align:left">não validada: ${esc(p.reason || '')}</td></tr>`).join('')}</tbody></table><p class="aside">O Sentinel-2 (MNDWI > 0, nuvem mascarada) é referência independente, não verdade de campo.</p>` : `<p>${esc(v.reason || 'Sem validação óptica.')}</p>`}
  </div></section>

  <section class="sec" id="hipotese"><div class="split wrap wide">
    <div><p class="kicker">Medido</p><h2>O que o radar viu</h2><p>${esc(ins.measured || '')}</p></div>
    <div><p class="kicker">Hipótese</p><h2>Causa provável${ins.confidence ? ` · confiança ${esc(ins.confidence)}` : ''}</h2><p>${esc(ins.hypothesis || 'O radar mede a mudança, não a causa. Nenhuma hipótese foi gerada.')}</p>${ins.check ? `<p class="aside">Para conferir: ${esc(ins.check)}.</p>` : ''}
      ${a.forecast && a.forecast.status === 'ok' ? `<p class="aside"><b>Projeção experimental:</b> ${a.forecast.points.map(p => `${dm(p.date)} ${fmt(p.water_km2, 2)} km² (${fmt(p.p10, 2)}–${fmt(p.p90, 2)})`).join(' · ')}. ${esc(a.forecast.note || '')}</p>` : ''}</div>
  </div></section>

  <section class="sec" id="limites"><div class="wrap">
    <p class="kicker">Limitações</p><h2>O que este estudo não garante</h2>
    <ol class="lim">
      ${a.experimental ? `<li><b>Experimental.</b> ${(a.experimental_reasons || []).map(esc).join('; ')}.</li>` : ''}
      ${wind.length ? `<li><b>Vento.</b> ${wind.map(p => br(p.date)).join(', ')} têm água mais clara que o normal da série; a área nessas datas tende a estar subestimada e não foi corrigida.</li>` : ''}
      ${(a.skipped_scenes || []).length ? `<li><b>Cenas descartadas.</b> ${a.skipped_scenes.map(s => `${br(s.date)} (${esc(s.reason)})`).join('; ')}.</li>` : ''}
      <li><b>Vegetação alagada e plantas aquáticas</b> não aparecem como água aberta em HH; solo muito liso e sombra de radar podem parecer água.</li>
      <li><b>Produto ${MAT[g.maturity] ? MAT[g.maturity].replace('produto ', '') : 'do NISAR'}.</b> Os valores podem mudar quando a NASA reprocessar; o CRID de cada cena está na tabela abaixo.</li>
      <li><b>Validação.</b> ${v.status === 'validated' ? 'O óptico pode estar a até 7 dias do radar e não enxerga água sob nuvem.' : 'Não houve validação óptica; não há conferência independente.'}</li>
      ${(a.warnings || []).map(w => `<li>${esc(w)}</li>`).join('')}
    </ol>
  </div></section>

  <section class="sec" id="fontes"><div class="wrap wide">
    <p class="kicker">Fontes</p><h2>Cenas e método</h2>
    <p>Canal HH, média 5×5 em dB, limiar único ${fmt(a.params.threshold_db, 2)} dB no vale água/terra, manchas &lt; 0,1 km² removidas. Versão ${esc(a.algorithm_version)}. Janelas brutas lidas por streaming e descartadas; ficam só os derivados.</p>
    <table class="tbl" id="scenes"><thead><tr><th>Data</th><th>CRID</th><th>Dado válido</th><th>Água km²</th><th>Granule</th></tr></thead><tbody>${S.map(p => `<tr class="${p.suspeita_vento ? 'vento' : ''}"><td>${br(p.date)}</td><td>${esc(p.crid || '–')}</td><td>${fmt(p.valid_fraction_aoi * 100, 0)}%</td><td>${fmt(p.water_km2, 2)}</td><td>${esc(p.granule)}</td></tr>`).join('')}</tbody></table>
    <p class="aside"><a class="link" href="${API}/analyses/${a.analysis_id}/sources" target="_blank" rel="noopener">sources.json (proveniência)</a> · <a class="link" href="${API}/analyses/${a.analysis_id}/metrics">metrics.json</a> · <a class="link" href="${API}/analyses/${a.analysis_id}/metrics?format=csv">metrics.csv</a></p>
  </div></section>`;

  /* ---- mapa de abertura com camadas selecionáveis ---- */
  const hero = base($('#map-hero'), bnd); let ov = null;
  L.geoJSON(a.aoi.geometry, { style: { color: '#f4b63f', weight: 2, fill: false, dashArray: '6 4' }, interactive: false }).addTo(hero);
  const opts = [{ l: wl[wl.length - 1], t: `Água ${wl.length ? dm(wl[wl.length - 1].date) : ''}` }, { l: byId('change_last'), t: 'Última passagem' }, { l: byId('change'), t: 'Mudança' }, { l: byId('frequency'), t: 'Permanência' }, { l: layers.filter(x => x.type === 'optical_water').pop(), t: 'Sentinel-2' }].filter(o => o.l);
  const KEY = { water: ['#2e86de', 'água medida'], change: ['#d93828', 'perdeu água · <span style="color:#1446d7">■</span> ganhou · <span style="color:#7ab2eb">■</span> nas duas datas'], frequency: ['#103ca0', 'permanente · <span style="color:#3b8fd9">■</span> sazonal · <span style="color:#7adcf0">■</span> ocasional'], optical_water: ['#40c4a0', 'água no Sentinel-2'] };
  const show = (o) => { if (ov) hero.removeLayer(ov); ov = o ? L.imageOverlay(png(a, o.l.id), lb(o.l), { opacity: .92 }).addTo(hero) : null;
    $('#hero-layers').querySelectorAll('button').forEach(b => b.style.borderColor = b.dataset.k === (o ? o.l.id : '') ? 'var(--accent)' : '');
    $('#lg-hero').innerHTML = o ? `<span><span style="color:${KEY[o.l.type][0]}">■</span> ${KEY[o.l.type][1]}</span>` : ''; };
  $('#hero-layers').innerHTML = opts.map(o => `<button class="chip" type="button" data-k="${o.l.id}">${esc(o.t)}</button>`).join('') + '<button class="chip" type="button" data-k="">Sem camada</button>';
  $('#hero-layers').querySelectorAll('button').forEach(b => b.addEventListener('click', () => show(opts.find(o => o.l.id === b.dataset.k) || null)));
  if (opts.length) show(opts[0]);
  document.querySelectorAll('.top3 button').forEach(b => b.addEventListener('click', () => { const h = hot[+b.dataset.i]; hero.flyToBounds([[h.bbox[1], h.bbox[0]], [h.bbox[3], h.bbox[2]]], { maxZoom: 16, padding: [40, 40] }); L.circleMarker([h.lat, h.lon], { radius: 10, color: '#e5482d', weight: 3, fill: false }).addTo(hero); window.scrollTo({ top: 0, behavior: 'smooth' }); }));

  /* ---- linha do tempo ---- */
  const tm = base($('#map-time'), bnd), ovs = S.map(p => { const l = byId('water_' + p.date.replaceAll('-', '')); return l ? L.imageOverlay(png(a, l.id), lb(l), { opacity: 0 }).addTo(tm) : null; });
  const setT = (i) => { ovs.forEach((o, k) => o && o.setOpacity(k === i ? .92 : 0)); $('#tl-date').textContent = br(S[i].date) + (S[i].suspeita_vento ? ' · vento' : ''); $('#tl-date').style.color = S[i].suspeita_vento ? 'var(--ochre-2)' : ''; $('#tl-area').textContent = `${fmt(S[i].water_km2, 2)} km²`; };
  const sl = $('#slider'); sl.addEventListener('input', () => setT(+sl.value)); setT(S.length - 1);
  let tmr = null; $('#play').addEventListener('click', () => { if (tmr) { clearInterval(tmr); tmr = null; $('#play').textContent = '▶ Reproduzir'; return; } sl.value = 0; setT(0); $('#play').textContent = '❚❚ Pausar'; tmr = setInterval(() => { if (+sl.value >= S.length - 1) { clearInterval(tmr); tmr = null; $('#play').textContent = '▶ Reproduzir'; return; } sl.value = +sl.value + 1; setT(+sl.value); }, 900); });

  /* ---- antes × depois ---- */
  const r = $('#cmp-r'); if (r) r.addEventListener('input', () => { $('#cmp-top').style.clipPath = `inset(0 ${100 - r.value}% 0 0)`; $('#cmp-cut').style.left = r.value + '%'; });

  /* ---- gráfico da série ---- */
  const F = a.forecast && a.forecast.status === 'ok' ? a.forecast.points : [], W = 1000, H = 300, Lm = 56, Rm = 14, T = 16, B = 30;
  const t = (d) => Date.parse(d + 'T00:00:00Z'), t0 = t(first.date), t1 = Math.max(t(last.date), F.length ? t(F[F.length - 1].date) : 0, t0 + 864e5);
  const vals = S.map(p => p.water_km2).concat(F.flatMap(p => [p.p10, p.p90])); let lo = Math.min(...vals), hi = Math.max(...vals); const pad = Math.max((hi - lo) * .15, hi * .01, .01); lo = Math.max(0, lo - pad); hi += pad;
  const X = (d) => Lm + (t(d) - t0) / (t1 - t0) * (W - Lm - Rm), Y = (q) => T + (hi - q) / (hi - lo) * (H - T - B), dec = hi - lo < 5 ? 2 : hi - lo < 50 ? 1 : 0;
  const grid = [0, 1, 2, 3].map(i => lo + (hi - lo) * i / 3).map(q => `<line x1="${Lm}" x2="${W - Rm}" y1="${Y(q)}" y2="${Y(q)}" stroke="rgba(255,255,255,.07)"/><text x="${Lm - 8}" y="${Y(q) + 4}" text-anchor="end" fill="#6e7f8c" font-size="12" font-family="IBM Plex Mono">${fmt(q, dec)}</text>`).join('');
  const line = S.map((p, i) => `${i ? 'L' : 'M'}${X(p.date).toFixed(1)},${Y(p.water_km2).toFixed(1)}`).join('');
  const dots = S.map(p => `<circle cx="${X(p.date)}" cy="${Y(p.water_km2)}" r="${p.suspeita_vento ? 6 : 4.5}" fill="${p.suspeita_vento ? '#04060c' : '#4fb6ee'}" ${p.suspeita_vento ? 'stroke="#f4b63f" stroke-width="2.5"' : ''}><title>${br(p.date)}: ${fmt(p.water_km2, 2)} km²</title></circle>`).join('');
  let fc = ''; if (F.length) { const pts = [{ date: last.date, water_km2: last.water_km2, p10: last.water_km2, p90: last.water_km2 }].concat(F); fc = `<path d="${pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.date)},${Y(p.p90)}`).join('')}${pts.slice().reverse().map(p => `L${X(p.date)},${Y(p.p10)}`).join('')}Z" fill="rgba(79,182,238,.14)"/><path d="${pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.date)},${Y(p.water_km2)}`).join('')}" fill="none" stroke="#4fb6ee" stroke-dasharray="6 5" stroke-width="2"/>`; }
  const xl = [first.date, last.date].concat(F.length ? [F[F.length - 1].date] : []).map((d, i, ar) => `<text x="${X(d)}" y="${H - 8}" text-anchor="${i === 0 ? 'start' : i === ar.length - 1 ? 'end' : 'middle'}" fill="#6e7f8c" font-size="12" font-family="IBM Plex Mono">${dm(d)}</text>`).join('');
  $('#chart').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Área de água em cada passagem (km²)">${grid}${xl}${fc}<path d="${line}" fill="none" stroke="#4fb6ee" stroke-width="2.5"/>${dots}</svg>`;
}
})();
