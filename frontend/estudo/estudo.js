/* Estudo automático: tudo vem de /api/arara/analyses/{id}. Nada é digitado à mão. */
(() => {
'use strict';
const $ = (s, r = document) => r.querySelector(s);
/* idioma (../arara-i18n.js): inglês por padrão; PT com ?lang=pt ou o seletor. tx(pt, en) */
const I18N = window.ARARA_I18N, EN = I18N.en, tx = I18N.tr, dados = I18N.dados;
const ORIG_PT = EN ? ' <i class="aside">(original text in Portuguese)</i>' : '';
/* frase da pipeline: em inglês pela tabela; o aviso só aparece se ela não estiver lá */
const leiaPT = (x) => { const t = dados(x); return esc(t) + (EN && t === x ? ORIG_PT : ''); };
const ENUM = { ganhando: 'gaining', perdendo: 'losing', 'estável': 'stable', abaixo: 'below', acima: 'above', normal: 'normal', 'atenção': 'attention', alerta: 'alert', alta: 'high', 'média': 'medium', baixa: 'low' };
const en_ = (v) => (EN && ENUM[v]) || v;
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v, d = 0) => v == null || isNaN(v) ? '–' : Number(v).toLocaleString(I18N.locale, { minimumFractionDigits: d, maximumFractionDigits: d });
const sg = (v, d = 1) => `${v >= 0 ? '+' : '−'}${fmt(Math.abs(v), d)}`;
const br = (s) => I18N.data(s);
const dm = (s) => I18N.dataCurta(s);
// rótulo radar x Sentinel-2 por data: "concordam" só com diferença de fração < 5 pontos (mesma regra da pipeline)
const leitura = (p) => {
  const pp = p.difference_pp ?? Math.round(Math.abs(p.sar_water_fraction - p.optical_water_fraction) * 1000) / 10;
  const ag = p.agreement || (p.optical_water_fraction < 0.005 && p.sar_water_fraction >= 0.05 ? 'optical_no_water' : pp >= 5 || p.level === 'strong' || p.level === 'moderate' ? 'diverge' : 'agree');
  const txt = ag === 'optical_no_water' ? tx('óptico sem água: o radar contou terra como água', 'optical sees no water: the radar counted land as water') : ag === 'diverge' ? tx(`divergem (${fmt(pp, 1)} pontos)`, `disagree (${fmt(pp, 1)} points)`) : tx('concordam', 'agree');
  return txt;      // só aparece na página sem água confiável, que não publica datas de vento
};
// relativo: funciona no servidor (/estudo/) e na vitrine estática em qualquer subpasta
const API = '../api/arara';
const STATIC = !!window.ARARA_STATIC || new URLSearchParams(location.search).has('static');
const files = (aid) => STATIC
  ? { json: `../data/analyses/${aid}/analysis.json`, png: (l) => `../data/analyses/${aid}/png/${l}.png`, sources: `../data/analyses/${aid}/sources.json`, csv: `../data/analyses/${aid}/metrics.csv`, metrics: `../data/analyses/${aid}/metrics.json` }
  : { json: `${API}/analyses/${aid}`, png: (l) => `${API}/analyses/${aid}/png/${l}.png`, sources: `${API}/analyses/${aid}/sources`, csv: `${API}/analyses/${aid}/metrics?format=csv`, metrics: `${API}/analyses/${aid}/metrics` };
const id = new URLSearchParams(location.search).get('id');
const main = $('#top'), ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/';
const MAT = { PROVISIONAL: tx('produto provisório', 'provisional product'), VALIDATED: tx('produto validado', 'validated product'), BETA: tx('produto beta', 'beta product'), LOCAL: tx('cenas locais', 'local scenes') };
if (EN) document.title = 'Study · Arara';
I18N.aplicarHtml();
I18N.botao($('#langsw'));
document.querySelectorAll('a[data-lang-link]').forEach(a => a.setAttribute('href', I18N.comLang(a.getAttribute('href'))));
const fail = (m) => { main.innerHTML = `<p class="state err">${esc(m)}</p>`; };
if (!id || !/^[0-9a-f]{8,64}$/.test(id)) { fail(tx('Estudo não informado. Abra um estudo pelo globo (painel da análise → "Abrir estudo completo").', 'No study given. Open a study from the globe (analysis panel → "Full study").')); return; }

fetch(files(id).json).then(async (r) => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(dados(j.reason) || (STATIC ? tx('estudo não incluído nesta vitrine', 'study not included in this showcase') : tx(`erro ${r.status}`, `error ${r.status}`))); return j; })
  .then((a) => {
    (a.quality === 'no_reliable_water' ? renderNoWater : render)(a);
    // análise refeita para a mesma área: esta continua acessível pelo id, com aviso e link para a atual
    if (a.superseded_by) main.insertAdjacentHTML('afterbegin', `<p class="superseded">${tx('Há uma versão mais recente deste estudo.', 'There is a newer version of this study.')} <a href="?id=${esc(a.superseded_by)}${STATIC ? '&static=1' : ''}&lang=${I18N.lang}">${tx('Abrir a versão atual', 'Open the current version')}</a>${tx('; esta fica guardada para conferência.', '; this one is kept for reference.')}</p>`);
  })
  .catch((e) => fail(tx('Não foi possível carregar este estudo: ', 'Could not load this study: ') + e.message + (STATIC ? '.' : tx('. Se ele tem mais de 7 dias, os derivados foram apagados; refaça a análise.', '. If it is older than the retention period, its files were deleted; run the analysis again.'))));

function base(el, bounds) {
  const m = L.map(el, { zoomControl: false, worldCopyJump: true });
  L.control.zoom({ position: 'bottomright' }).addTo(m);
  L.tileLayer(ESRI + 'World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 18, attribution: 'Esri, Maxar, Earthstar Geographics' }).addTo(m);
  L.tileLayer(ESRI + 'Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', { maxZoom: 18, opacity: .9 }).addTo(m);
  m.fitBounds([[bounds.south, bounds.west], [bounds.north, bounds.east]]);
  return m;
}
const png = (a, l) => files(a.analysis_id).png(l);
const lb = (l) => [[l.bounds.south, l.bounds.west], [l.bounds.north, l.bounds.east]];

function renderNoWater(a) {
  const S = a.dates, first = S[0], last = S[S.length - 1], g = a.group || {}, v = a.optical_validation || {}, f = files(a.analysis_id);
  const hh = (a.layers || []).filter(l => l.type === 'backscatter'), op = (a.layers || []).filter(l => l.type === 'optical_water');
  const bnd = (hh[0] || {}).bounds || { south: a.aoi.bbox[1], west: a.aoi.bbox[0], north: a.aoi.bbox[3], east: a.aoi.bbox[2] };
  const reasons = a.quality_reasons || [], dv = v.divergence;
  document.title = `${a.name || tx('Estudo', 'Study')} · Arara`; $('#bar-info').textContent = `${MAT[g.maturity] || 'NISAR'} · ${tx('trilha', 'track')} ${g.track ?? '–'} ${g.direction ?? ''} · frame ${g.frame ?? '–'}`;
  main.innerHTML = `
  <section class="hero auto">
    <div class="map hero-map" id="map-hero"></div>
    <div class="hero-text">
      <p class="kicker">${tx('Estudo automático', 'Automatic study')} · ${esc(a.sensor)}</p>
      <h1>${esc(a.name || tx('Área analisada', 'Analysed area'))}: ${tx('não foi possível separar água de terra nesta área', 'water could not be separated from land in this area')}</h1>
      <p class="dek">${tx(`O radar leu ${S.length} passagens do NISAR, de ${br(first.date)} a ${br(last.date)}, mas não encontrou um contraste nítido entre água e terra. Por isso este estudo não publica área de água, saldo, tendência, alerta, permanência, projeção nem datas de vento.`,
        `The radar read ${S.length} NISAR passes, from ${br(first.date)} to ${br(last.date)}, but found no sharp contrast between water and land. So this study publishes no water area, net change, trend, alert, permanence, projection or windy dates.`)}</p>
      <div class="chips"><span class="chip ok">${esc(MAT[g.maturity] || 'NISAR')}</span><span class="chip warn">${tx('sem água confiável', 'no reliable water')}</span>${dv && dv.level === 'strong' ? `<span class="chip warn">${tx(`Sentinel-2 não vê água em ${dv.n_strong} de ${dv.n_dates} datas`, `Sentinel-2 sees no water on ${dv.n_strong} of ${dv.n_dates} dates`)}</span>` : ''}</div>
    </div>
  </section>
  <section class="sec"><div class="wrap">
    <p class="kicker">${tx('Por quê', 'Why')}</p><h2>${tx('Motivos', 'Reasons')}</h2>
    <ol class="lim">${reasons.map(r => `<li>${esc(dados(r))}.</li>`).join('')}</ol>
    <p class="kicker" style="margin-top:28px">${tx('O que tentar', 'What to try')}</p>
    <p>${tx('Esta região precisa de outra área ou de outra geometria de radar para ser medida com confiança; ela fica sem medida em vez de mostrar um número errado.', 'This region needs a different area or radar geometry to be measured reliably; it stays unmeasured rather than showing a wrong number.')}</p>
    <p class="aside">${tx('As camadas abaixo são o retroespalhamento HH de cada data, para inspeção: água calma aparece escura.', 'The layers below are the HH backscatter of each date, for inspection: calm water looks dark.')} ${op.length ? tx('A camada Sentinel-2 mostra onde o óptico vê água (MNDWI > 0).', 'The Sentinel-2 layer shows where optical data sees water (MNDWI > 0).') : ''}</p>
    <div class="chips" id="hero-layers"></div>
  </div></section>
  ${dv && dv.per_date.length ? `<section class="sec proof"><div class="wrap wide">
    <p class="kicker">${tx('Conferência', 'Cross-check')}</p><h2>Radar × Sentinel-2</h2>
    <table class="tbl"><thead><tr><th>Radar</th><th>${tx('Fração escura no radar', 'Dark fraction in the radar')}</th><th>${tx('Fração de água no Sentinel-2', 'Water fraction in Sentinel-2')}</th><th>${tx('Leitura', 'Reading')}</th></tr></thead><tbody>${dv.per_date.map(p => `<tr><td>${br(p.date)}</td><td>${fmt(p.sar_water_fraction * 100, 1)}%</td><td>${fmt(p.optical_water_fraction * 100, 1)}%</td><td>${leitura(p)}</td></tr>`).join('')}</tbody></table>
    <p class="aside">${tx('O Sentinel-2 (MNDWI > 0, nuvem mascarada) é referência independente, não verdade de campo.', 'Sentinel-2 (MNDWI > 0, clouds masked) is an independent reference, not ground truth.')}</p>
  </div></section>` : ''}
  <section class="sec" id="fontes"><div class="wrap wide">
    <p class="kicker">${tx('Fontes', 'Sources')}</p><h2>${tx('Cenas usadas', 'Scenes used')}</h2>
    <table class="tbl"><thead><tr><th>${tx('Data', 'Date')}</th><th>CRID</th><th>${tx('Dado válido', 'Valid data')}</th><th>${tx('Blocos de margem', 'Shoreline blocks')}</th><th>Granule</th></tr></thead><tbody>${S.map(p => `<tr><td>${br(p.date)}</td><td>${esc(p.crid || '–')}</td><td>${fmt(p.valid_fraction_aoi * 100, 0)}%</td><td>${p.margin_blocks ?? '–'}</td><td>${esc(p.granule)}</td></tr>`).join('')}</tbody></table>
    <p class="aside">${(a.warnings || []).map(w => esc(dados(w))).join(' ')} <a class="link" href="${f.sources}" target="_blank" rel="noopener">sources.json (${tx('proveniência', 'provenance')})</a> · ${tx('versão', 'version')} ${esc(a.algorithm_version)}</p>
  </div></section>`;
  const hero = base($('#map-hero'), bnd); let ov = null;
  L.geoJSON(a.aoi.geometry, { style: { color: '#f4b63f', weight: 2, fill: false, dashArray: '6 4' }, interactive: false }).addTo(hero);
  const opts = hh.map(l => ({ l, t: `Radar HH ${dm(l.date)}` })).concat(op.slice(-1).map(l => ({ l, t: `Sentinel-2 ${dm(l.date)}` })));
  const show = (o) => { if (ov) hero.removeLayer(ov); ov = o ? L.imageOverlay(png(a, o.l.id), lb(o.l), { opacity: .92 }).addTo(hero) : null;
    $('#hero-layers').querySelectorAll('button').forEach(b => b.style.borderColor = b.dataset.k === (o ? o.l.id : '') ? 'var(--accent)' : ''); };
  $('#hero-layers').innerHTML = opts.map(o => `<button class="chip" type="button" data-k="${o.l.id}">${esc(o.t)}</button>`).join('') + `<button class="chip" type="button" data-k="">${tx('Sem camada', 'No layer')}</button>`;
  $('#hero-layers').querySelectorAll('button').forEach(b => b.addEventListener('click', () => show(opts.find(o => o.l.id === b.dataset.k) || null)));
  if (opts.length) show(opts[0]);
}

function render(a) {
  const S = a.dates, first = S[0], last = S[S.length - 1], c = a.comparison, g = a.group || {}, v = a.optical_validation || {}, P = a.patterns || {};
  const layers = a.layers || [], byId = (k) => layers.find(l => l.id === k), wl = layers.filter(l => l.type === 'water');
  const ref = byId('change') || wl[wl.length - 1] || layers[0], bnd = (ref || {}).bounds || { south: a.aoi.bbox[1], west: a.aoi.bbox[0], north: a.aoi.bbox[3], east: a.aoi.bbox[2] };
  const pct = first.water_km2 ? 100 * (last.water_km2 - first.water_km2) / first.water_km2 : null;
  document.title = `${a.name || tx('Estudo', 'Study')} · Arara`; $('#bar-info').textContent = `${MAT[g.maturity] || 'NISAR'} · ${tx('trilha', 'track')} ${g.track ?? '–'} ${g.direction ?? ''} · frame ${g.frame ?? '–'}`;
  const csv = $('#csv'); csv.hidden = false; csv.href = files(a.analysis_id).csv;
  const wind = S.filter(p => p.suspeita_vento);
  const tr = P.trend && P.trend.status === 'ok' ? P.trend : null, an = P.anomaly && P.anomaly.status === 'ok' ? P.anomaly : null, fq = P.frequency && P.frequency.permanent_km2 != null ? P.frequency : null;
  const hot = (P.retraction_hotspots || []);
  // o radar e o óptico devem concordar; quando não concordam, a série de radar não pode ser tomada como mudança real
  const vd = (v.per_date || []).filter(p => p.status === 'validated' && p.optical_water_km2 > 0);
  const div = v.divergence ? v.divergence.per_date.filter(p => p.level !== 'none') : vd.filter(p => Math.abs(p.sar_water_km2 - p.optical_water_km2) / p.optical_water_km2 > 0.3);
  const nvd = v.divergence ? v.divergence.n_dates : vd.length;
  const diverge = v.divergence ? v.divergence.level !== 'none' : vd.length >= 3 && (div.length >= 2 || (v.mean_iou != null && v.mean_iou < 0.7));
  const reasons = a.quality_reasons || a.experimental_reasons || [];
  const ins = a.insights || {}, antes = tx('Esta análise é anterior aos padrões medidos; refaça a análise (estudar_lote.py --refazer) para calculá-los.', 'This analysis predates the measured patterns; run it again (estudar_lote.py --refazer) to compute them.');

  main.innerHTML = `
  <section class="hero auto">
    <div class="map hero-map" id="map-hero"></div>
    <div class="hero-text">
      <p class="kicker">${tx('Estudo automático', 'Automatic study')} · ${esc(a.sensor)}</p>
      <h1>${esc(a.name || tx('Área analisada', 'Analysed area'))}: ${fmt(last.water_km2, last.water_km2 < 100 ? 1 : 0)} ${tx('km² de água', 'km² of water')}</h1>
      <p class="dek">${S.length > 1 ? tx(`Em ${S.length} passagens do NISAR, de ${br(first.date)} a ${br(last.date)}, a água ${pct < 0 ? 'diminuiu' : 'aumentou'} ${fmt(Math.abs(pct), 1)}% (${sg(last.water_km2 - first.water_km2, 1)} km²).`, `Over ${S.length} NISAR passes, from ${br(first.date)} to ${br(last.date)}, the water ${pct < 0 ? 'decreased' : 'increased'} ${fmt(Math.abs(pct), 1)}% (${sg(last.water_km2 - first.water_km2, 1)} km²).`) : tx(`Uma passagem válida, em ${br(first.date)}.`, `One valid pass, on ${br(first.date)}.`)} ${tx('Cada número abaixo foi medido pelo radar sobre esta área e pode ser conferido nas cenas listadas no fim.', 'Every number below was measured by the radar over this area and can be checked against the scenes listed at the end.')}</p>
      ${a.experimental ? `<p class="flag warn"><b>Experimental:</b> ${reasons.map(r => esc(dados(r))).join('; ')}. ${tx('Os números valem como indicação; não há projeção.', 'The numbers are indicative; there is no projection.')}</p>` : ''}
      <div class="chips"><span class="chip ok">${esc(MAT[g.maturity] || 'NISAR')}</span>${a.experimental ? '<span class="chip warn">experimental</span>' : ''}${v.status === 'validated' ? `<span class="chip ok">${tx('validado com Sentinel-2', 'validated with Sentinel-2')} · IoU ${fmt(v.mean_iou, 2)}</span>` : `<span class="chip warn">${tx('sem validação óptica', 'no optical validation')}</span>`}${diverge ? `<span class="chip warn">${tx(`radar diverge do óptico em ${div.length} de ${nvd} datas`, `radar disagrees with optical on ${div.length} of ${nvd} dates`)}</span>` : ''}${wind.length ? `<span class="chip warn">${tx('vento em', 'wind on')} ${wind.map(p => dm(p.date)).join(', ')}</span>` : ''}</div>
    </div>
  </section>

  <section class="sec"><div class="wrap wide"><div class="stats">
    <div class="stat"><span class="stat-v num">${fmt(last.water_km2, last.water_km2 < 100 ? 1 : 0)}<small>km²</small></span><p>${tx(`de água em ${br(last.date)} (${fmt(last.water_pct, 1)}% da área analisada de ${fmt(a.aoi.area_km2, 0)} km²)`, `of water on ${br(last.date)} (${fmt(last.water_pct, 1)}% of the ${fmt(a.aoi.area_km2, 0)} km² analysed area)`)}</p></div>
    <div class="stat"><span class="stat-v num">${c ? sg(c.net_change_ha, 0) : '–'}<small>ha</small></span><p>${c ? tx(`saldo entre ${br(c.before)} e ${br(c.after)}: ${fmt(c.expansion_ha, 0)} ha de água nova, ${fmt(c.retraction_ha, 0)} ha perdidos`, `net change between ${br(c.before)} and ${br(c.after)}: ${fmt(c.expansion_ha, 0)} ha of new water, ${fmt(c.retraction_ha, 0)} ha lost`) : tx('saldo entre passagens: precisa de duas datas', 'net change between passes: needs two dates')}</p></div>
    <div class="stat"><span class="stat-v num">${v.status === 'validated' ? fmt(v.mean_iou, 2) : '–'}</span><p>${v.status === 'validated' ? tx(`IoU médio contra o Sentinel-2 em ${v.n_dates_validated} de ${v.n_dates} datas`, `mean IoU against Sentinel-2 on ${v.n_dates_validated} of ${v.n_dates} dates`) : esc(dados(v.reason || 'sem validação óptica'))}</p></div>
  </div></div></section>

  <section class="sec" id="padroes"><div class="wrap wide">
    <p class="kicker">${tx('O que a série mostra', 'What the series shows')}</p><h2>${tx('Padrões medidos', 'Measured patterns')}</h2>
    ${diverge ? `<div class="card warn" style="margin-top:22px"><h3>${tx('Atenção: o radar não concorda com o Sentinel-2', 'Warning: the radar does not agree with Sentinel-2')}</h3><p>${tx(`Em ${div.length} de ${nvd} datas a área de água do radar difere mais de 30% da vista pelo Sentinel-2 (IoU médio ${fmt(v.mean_iou, 2)}). Isso costuma indicar solo muito úmido, irrigação ou vegetação sendo contados como água. <b>Não tome a tendência e a variação abaixo como mudança real do corpo d'água</b> antes de conferir a camada "Sentinel-2" e a tabela de validação.`,
      `On ${div.length} of ${nvd} dates the radar water area differs by more than 30% from what Sentinel-2 sees (mean IoU ${fmt(v.mean_iou, 2)}). This usually means very wet soil, irrigation or vegetation being counted as water. <b>Do not take the trend and change below as a real change of the water body</b> before checking the "Sentinel-2" layer and the validation table.`)}</p></div>` : ''}
    <div class="cards">
      <div class="card ${diverge ? 'warn' : ''}"><h3>${tx('Tendência', 'Trend')}${diverge ? tx(' · não confiável', ' · not reliable') : ''}</h3>${tr ? `<div class="v">${sg(tr.km2_per_week, 2)}<small>${tx('km²/semana', 'km²/week')}</small></div><p>${tx(`${fmt(Math.abs(tr.pct_per_month), 1)}% ao mês, ${tr.direction}, desde ${br(tr.since)} (${tr.n_dates} datas, ${esc(tr.method)})`, `${fmt(Math.abs(tr.pct_per_month), 1)}% per month, ${en_(tr.direction)}, since ${br(tr.since)} (${tr.n_dates} dates, ${esc(dados(tr.method))})`)}. ${esc(dados(tr.note))}.</p>` : `<p>${esc(dados((P.trend || {}).reason) || antes)}</p>`}</div>
      <div class="card ${an && an.level === 'alerta' ? 'alert' : an && an.level === 'atenção' ? 'warn' : ''}"><h3>${tx('Alerta da última passagem', 'Last-pass alert')}</h3>${an ? `<div class="v">${an.level === 'normal' ? tx('dentro da variação normal', 'within normal variation') : en_(an.level)}<small>${sg(an.pct_vs_normal, 1)}% vs normal</small></div><p>${tx(`Em ${br(an.last_date)} havia ${fmt(an.last_km2, 2)} km², ${an.direction} do normal da série (${fmt(an.normal_km2, 2)} km²)`, `On ${br(an.last_date)} there were ${fmt(an.last_km2, 2)} km², ${en_(an.direction)} the series normal (${fmt(an.normal_km2, 2)} km²)`)}${an.series_noise_km2 != null ? tx(`; a variação normal entre passagens é de ${fmt(an.series_noise_km2, 1)} km²`, `; the normal variation between passes is ${fmt(an.series_noise_km2, 1)} km²`) : ''}. ${esc(dados(an.note || ''))}</p>` : `<p>${esc(dados((P.anomaly || {}).reason) || antes)}</p>`}</div>
      <div class="card"><h3>${tx('Permanência da água', 'Water permanence')}</h3>${fq ? `<div class="v">${fmt(fq.permanent_km2, 1)}<small>${tx('km² permanente', 'km² permanent')}</small></div><p>${tx(`${fmt(fq.seasonal_km2, 1)} km² sazonal e ${fmt(fq.occasional_km2, 1)} km² ocasional, em ${fq.n_dates} datas`, `${fmt(fq.seasonal_km2, 1)} km² seasonal and ${fmt(fq.occasional_km2, 1)} km² occasional, over ${fq.n_dates} dates`)}${fq.n_wind_excluded ? tx(` (${fq.n_wind_excluded === 1 ? '1 data com suspeita de vento ficou' : fq.n_wind_excluded + ' datas com suspeita de vento ficaram'} fora)`, ` (${fq.n_wind_excluded === 1 ? '1 date with suspected wind was' : fq.n_wind_excluded + ' dates with suspected wind were'} left out)`) : ''}. ${tx('Permanente: água em 90% ou mais das datas.', 'Permanent: water on 90% or more of the dates.')}</p>` : `<p>${esc(dados((P.frequency || {}).reason) || antes)}</p>`}</div>
      <div class="card"><h3>${tx('Trechos que mais secaram', 'Stretches that dried the most')}</h3>${hot.length ? `<ul class="top3">${hot.map((h, i) => `<li><button type="button" data-i="${i}">#${h.rank} · ${fmt(h.area_ha, 1)} ha<small>${fmt(h.lat, 4)}, ${fmt(h.lon, 4)}</small></button></li>`).join('')}</ul>` : `<p>${a.patterns ? tx('Nenhum trecho contíguo perdeu água acima de 1 ha.', 'No contiguous stretch lost more than 1 ha of water.') : antes}</p>`}</div>
    </div>
    <div class="legend2" id="lg-hero"></div>
    <div class="chips" id="hero-layers"></div>
  </div></section>

  <section class="sec" id="tempo"><div class="wrap wide">
    <p class="kicker">${tx('Linha do tempo', 'Timeline')}</p><h2>${tx('A água em cada passagem', 'The water on each pass')}</h2>
    <p>${tx(`Cada data foi classificada com o mesmo limiar (${fmt(a.params.threshold_db, 2)} dB). Arraste para ver a água medida mudar.`, `Every date was classified with the same threshold (${fmt(a.params.threshold_db, 2)} dB). Drag to watch the measured water change.`)}</p>
    <div class="map tlmap" id="map-time"></div>
    <div class="tlbar"><button class="btn btn-accent" id="play" type="button">${tx('▶ Reproduzir', '▶ Play')}</button><input id="slider" type="range" min="0" max="${S.length - 1}" value="${S.length - 1}" aria-label="${tx('Data', 'Date')}"><span class="tldate" id="tl-date"></span><span class="tldate" id="tl-area"></span></div>
  </div></section>

  ${c && byId(`hh_${first.date.replaceAll('-', '')}`) && byId(`hh_${last.date.replaceAll('-', '')}`) ? `
  <section class="sec" id="antes"><div class="split wrap wide">
    <div><p class="kicker">${tx('Antes × depois', 'Before × after')}</p><h2>${dm(first.date)} ${tx('e', 'and')} ${dm(last.date)}</h2>
      <p>${tx('Arraste a barra para comparar o retroespalhamento HH. Água calma aparece escura: o radar quase não recebe sinal de volta.', 'Drag the bar to compare the HH backscatter. Calm water looks dark: the radar gets almost no signal back.')}</p>
      <div class="cmp" id="cmp" style="--ar:${(bnd.east - bnd.west) / (bnd.north - bnd.south) * Math.cos((bnd.north + bnd.south) / 2 * Math.PI / 180)}"><img alt="HH ${br(last.date)}" src="${png(a, 'hh_' + last.date.replaceAll('-', ''))}"><img class="top" id="cmp-top" alt="HH ${br(first.date)}" src="${png(a, 'hh_' + first.date.replaceAll('-', ''))}"><div class="cut" id="cmp-cut"></div><span class="tag" style="left:10px">${dm(first.date)}</span><span class="tag" style="right:10px">${dm(last.date)}</span><input type="range" id="cmp-r" min="0" max="100" value="50" aria-label="${tx('Comparar datas', 'Compare dates')}"></div></div>
    <div><p class="kicker">${tx('Medido', 'Measured')}</p><h2>${tx('O que mudou', 'What changed')}</h2>
      <div class="cards"><div class="card"><h3>${tx('Perdeu água', 'Lost water')}</h3><div class="v">${fmt(c.retraction_ha, 0)}<small>ha</small></div></div><div class="card"><h3>${tx('Ganhou água', 'Gained water')}</h3><div class="v">${fmt(c.expansion_ha, 0)}<small>ha</small></div></div><div class="card"><h3>${tx('Água nas duas datas', 'Water on both dates')}</h3><div class="v">${fmt(c.stable_water_ha, 0)}<small>ha</small></div></div></div>
      ${P.event && P.event.before !== c.before ? `<p style="margin-top:18px">${tx(`<b>Modo evento</b> (última passagem × anterior, ${br(P.event.before)} → ${br(P.event.after)}): ${sg(P.event.net_change_ha, 1)} ha${P.event.wind_caveat ? ', com suspeita de vento em uma das datas' : ''}. Ative a camada "Última passagem" no mapa de cima.`, `<b>Event mode</b> (last pass × previous, ${br(P.event.before)} → ${br(P.event.after)}): ${sg(P.event.net_change_ha, 1)} ha${P.event.wind_caveat ? ', with suspected wind on one of the dates' : ''}. Turn on the "Last pass" layer on the map above.`)}</p>` : ''}
      <p class="aside">${c.wind_caveat ? tx('Uma das duas datas tem suspeita de vento: parte desta diferença pode não ser real. ', 'One of the two dates has suspected wind: part of this difference may not be real. ') : ''}${tx('O Arara mede a mudança; a causa fica na hipótese abaixo.', 'Arara measures the change; the cause stays in the hypothesis below.')}</p></div>
  </div></section>` : ''}

  <section class="sec proof" id="prova"><div class="wrap wide">
    <p class="kicker">${tx('Conferência', 'Cross-check')}</p><h2>${tx('Série e validação', 'Series and validation')}</h2>
    <div class="svgwrap" id="chart"></div>
    <div class="legend2"><span><i style="background:var(--accent)"></i>${tx('medido pelo NISAR', 'measured by NISAR')}</span>${wind.length ? `<span><i style="background:transparent;border:2px solid var(--ochre)"></i>${tx('suspeita de vento', 'suspected wind')}</span>` : ''}${a.forecast && a.forecast.status === 'ok' ? `<span><i style="background:var(--accent-dim);border:1px dashed var(--accent)"></i>${tx('projeção experimental (p10–p90)', 'experimental projection (p10–p90)')}</span>` : ''}</div>
    ${v.per_date ? `<table class="tbl"><thead><tr><th>Radar</th><th>Sentinel-2</th><th>IoU</th><th>F1</th><th>${tx('Precisão', 'Precision')}</th><th>Recall</th><th>${tx('Água radar km²', 'Radar water km²')}</th><th>${tx('Água óptico km²', 'Optical water km²')}</th></tr></thead><tbody>${v.per_date.map(p => p.status === 'validated' ? `<tr class="${p.suspeita_vento ? 'vento' : ''}"><td>${br(p.date)}</td><td>${br(p.optical_date)} (${p.days_apart} d)</td><td>${fmt(p.iou, 2)}</td><td>${fmt(p.f1, 2)}</td><td>${fmt(p.precision, 2)}</td><td>${fmt(p.recall, 2)}</td><td>${fmt(p.sar_water_km2, 2)}</td><td>${fmt(p.optical_water_km2, 2)}</td></tr>` : `<tr><td>${br(p.date)}</td><td colspan="7" style="text-align:left">${tx('não validada:', 'not validated:')} ${esc(dados(p.reason || ''))}</td></tr>`).join('')}</tbody></table><p class="aside">${tx('O Sentinel-2 (MNDWI > 0, nuvem mascarada) é referência independente, não verdade de campo.', 'Sentinel-2 (MNDWI > 0, clouds masked) is an independent reference, not ground truth.')}</p>` : `<p>${esc(dados(v.reason || 'Sem validação óptica.'))}</p>`}
  </div></section>

  <section class="sec" id="hipotese"><div class="split wrap wide">
    <div><p class="kicker">${tx('Medido', 'Measured')}</p><h2>${tx('O que o radar viu', 'What the radar saw')}</h2><p>${ins.measured ? leiaPT(ins.measured) : ''}</p></div>
    <div><p class="kicker">${tx('Hipótese', 'Hypothesis')}</p><h2>${tx('Causa provável', 'Probable cause')}${ins.confidence ? ` · ${tx('confiança', 'confidence')} ${esc(en_(ins.confidence))}` : ''}</h2><p>${ins.hypothesis ? leiaPT(ins.hypothesis) : tx('O radar mede a mudança, não a causa. Nenhuma hipótese foi gerada.', 'The radar measures the change, not the cause. No hypothesis was generated.')}</p>${ins.check ? `<p class="aside">${tx('Para conferir:', 'To check:')} ${leiaPT(ins.check)}.</p>` : ''}
      ${a.forecast && a.forecast.status === 'ok' ? `<p class="aside"><b>${tx('Projeção experimental:', 'Experimental projection:')}</b> ${a.forecast.points.map(p => `${dm(p.date)} ${fmt(p.water_km2, 2)} km² (${fmt(p.p10, 2)}–${fmt(p.p90, 2)})`).join(' · ')}. ${esc(dados(a.forecast.note || ''))}</p>` : ''}</div>
  </div></section>

  <section class="sec" id="limites"><div class="wrap">
    <p class="kicker">${tx('Limitações', 'Limitations')}</p><h2>${tx('O que este estudo não garante', 'What this study does not guarantee')}</h2>
    <ol class="lim">
      ${a.experimental ? `<li><b>Experimental.</b> ${reasons.map(r => esc(dados(r))).join('; ')}.</li>` : ''}
      ${wind.length ? `<li>${tx(`<b>Vento.</b> ${wind.map(p => br(p.date)).join(', ')} têm água mais clara que o normal da série; a área nessas datas tende a estar subestimada e não foi corrigida.`, `<b>Wind.</b> ${wind.map(p => br(p.date)).join(', ')} have brighter water than the series normal; the area on those dates tends to be underestimated and was not corrected.`)}</li>` : ''}
      ${(a.skipped_scenes || []).length ? `<li><b>${tx('Cenas descartadas.', 'Discarded scenes.')}</b> ${a.skipped_scenes.map(s => `${br(s.date)} (${esc(dados(s.reason))})`).join('; ')}.</li>` : ''}
      <li>${tx('<b>Vegetação alagada e plantas aquáticas</b> não aparecem como água aberta em HH; solo muito liso e sombra de radar podem parecer água.', '<b>Flooded vegetation and aquatic plants</b> do not show up as open water in HH; very smooth soil and radar shadow can look like water.')}</li>
      <li><b>${tx(`Produto ${MAT[g.maturity] ? MAT[g.maturity].replace('produto ', '') : 'do NISAR'}.`, `${MAT[g.maturity] ? MAT[g.maturity].replace(' product', '').replace(/^./, ch => ch.toUpperCase()) : 'NISAR'} product.`)}</b> ${tx('Os valores podem mudar quando a NASA reprocessar; o CRID de cada cena está na tabela abaixo.', 'Values may change when NASA reprocesses the data; the CRID of every scene is in the table below.')}</li>
      ${diverge ? `<li>${tx(`<b>Divergência com o óptico.</b> O radar e o Sentinel-2 discordam em ${div.length} de ${nvd} datas; as áreas de água do radar nessas datas não devem ser usadas como medida do reservatório.`, `<b>Disagreement with optical.</b> The radar and Sentinel-2 disagree on ${div.length} of ${nvd} dates; the radar water areas on those dates should not be used as a measurement of the water body.`)}</li>` : ''}
      <li><b>${tx('Validação.', 'Validation.')}</b> ${v.status === 'validated' ? tx('O óptico pode estar a até 7 dias do radar e não enxerga água sob nuvem.', 'Optical data may be up to 7 days from the radar and cannot see water under clouds.') : tx('Não houve validação óptica; não há conferência independente.', 'There was no optical validation; there is no independent check.')}</li>
      ${(a.warnings || []).map(w => `<li>${esc(dados(w))}</li>`).join('')}
    </ol>
  </div></section>

  <section class="sec" id="fontes"><div class="wrap wide">
    <p class="kicker">${tx('Fontes', 'Sources')}</p><h2>${tx('Cenas e método', 'Scenes and method')}</h2>
    <p>${tx(`Canal HH, média 5×5 em dB, limiar único ${fmt(a.params.threshold_db, 2)} dB no vale água/terra, manchas &lt; 0,1 km² removidas. Versão ${esc(a.algorithm_version)}. Janelas brutas lidas por streaming e descartadas; ficam só os derivados.`, `HH channel, 5×5 mean in dB, a single ${fmt(a.params.threshold_db, 2)} dB threshold at the water/land valley, patches &lt; 0.1 km² removed. Version ${esc(a.algorithm_version)}. Raw windows are streamed and discarded; only the derived products are kept.`)}</p>
    <table class="tbl" id="scenes"><thead><tr><th>${tx('Data', 'Date')}</th><th>CRID</th><th>${tx('Dado válido', 'Valid data')}</th><th>${tx('Água km²', 'Water km²')}</th><th>Granule</th></tr></thead><tbody>${S.map(p => `<tr class="${p.suspeita_vento ? 'vento' : ''}"><td>${br(p.date)}</td><td>${esc(p.crid || '–')}</td><td>${fmt(p.valid_fraction_aoi * 100, 0)}%</td><td>${fmt(p.water_km2, 2)}</td><td>${esc(p.granule)}</td></tr>`).join('')}</tbody></table>
    <p class="aside"><a class="link" href="${files(a.analysis_id).sources}" target="_blank" rel="noopener">sources.json (${tx('proveniência', 'provenance')})</a> · <a class="link" href="${files(a.analysis_id).metrics}">metrics.json</a> · <a class="link" href="${files(a.analysis_id).csv}">metrics.csv</a></p>
  </div></section>`;

  /* ---- mapa de abertura com camadas selecionáveis ---- */
  const hero = base($('#map-hero'), bnd); let ov = null;
  L.geoJSON(a.aoi.geometry, { style: { color: '#f4b63f', weight: 2, fill: false, dashArray: '6 4' }, interactive: false }).addTo(hero);
  const opts = [{ l: wl[wl.length - 1], t: `${tx('Água', 'Water')} ${wl.length ? dm(wl[wl.length - 1].date) : ''}` }, { l: byId('change_last'), t: tx('Última passagem', 'Last pass') }, { l: byId('change'), t: tx('Mudança', 'Change') }, { l: byId('frequency'), t: tx('Permanência', 'Permanence') }, { l: layers.filter(x => x.type === 'optical_water').pop(), t: 'Sentinel-2' }].filter(o => o.l);
  const KEY = { water: ['#2e86de', tx('água medida', 'measured water')], change: ['#d93828', tx('perdeu água · <span style="color:#1446d7">■</span> ganhou · <span style="color:#7ab2eb">■</span> nas duas datas', 'lost water · <span style="color:#1446d7">■</span> gained · <span style="color:#7ab2eb">■</span> on both dates')], frequency: ['#103ca0', tx('permanente · <span style="color:#3b8fd9">■</span> sazonal · <span style="color:#7adcf0">■</span> ocasional', 'permanent · <span style="color:#3b8fd9">■</span> seasonal · <span style="color:#7adcf0">■</span> occasional')], optical_water: ['#40c4a0', tx('água no Sentinel-2', 'water in Sentinel-2')] };
  const show = (o) => { if (ov) hero.removeLayer(ov); ov = o ? L.imageOverlay(png(a, o.l.id), lb(o.l), { opacity: .92 }).addTo(hero) : null;
    $('#hero-layers').querySelectorAll('button').forEach(b => b.style.borderColor = b.dataset.k === (o ? o.l.id : '') ? 'var(--accent)' : '');
    $('#lg-hero').innerHTML = o ? `<span><span style="color:${KEY[o.l.type][0]}">■</span> ${KEY[o.l.type][1]}</span>` : ''; };
  $('#hero-layers').innerHTML = opts.map(o => `<button class="chip" type="button" data-k="${o.l.id}">${esc(o.t)}</button>`).join('') + `<button class="chip" type="button" data-k="">${tx('Sem camada', 'No layer')}</button>`;
  $('#hero-layers').querySelectorAll('button').forEach(b => b.addEventListener('click', () => show(opts.find(o => o.l.id === b.dataset.k) || null)));
  if (opts.length) show(opts[0]);
  document.querySelectorAll('.top3 button').forEach(b => b.addEventListener('click', () => { const h = hot[+b.dataset.i]; hero.flyToBounds([[h.bbox[1], h.bbox[0]], [h.bbox[3], h.bbox[2]]], { maxZoom: 16, padding: [40, 40] }); L.circleMarker([h.lat, h.lon], { radius: 10, color: '#e5482d', weight: 3, fill: false }).addTo(hero); window.scrollTo({ top: 0, behavior: 'smooth' }); }));

  /* ---- linha do tempo ---- */
  const tm = base($('#map-time'), bnd), ovs = S.map(p => { const l = byId('water_' + p.date.replaceAll('-', '')); return l ? L.imageOverlay(png(a, l.id), lb(l), { opacity: 0 }).addTo(tm) : null; });
  const setT = (i) => { ovs.forEach((o, k) => o && o.setOpacity(k === i ? .92 : 0)); $('#tl-date').textContent = br(S[i].date) + (S[i].suspeita_vento ? tx(' · vento', ' · wind') : ''); $('#tl-date').style.color = S[i].suspeita_vento ? 'var(--ochre-2)' : ''; $('#tl-area').textContent = `${fmt(S[i].water_km2, 2)} km²`; };
  const sl = $('#slider'); sl.addEventListener('input', () => setT(+sl.value)); setT(S.length - 1);
  const PLAY = tx('▶ Reproduzir', '▶ Play'), PAUSE = tx('❚❚ Pausar', '❚❚ Pause');
  let tmr = null; $('#play').addEventListener('click', () => { if (tmr) { clearInterval(tmr); tmr = null; $('#play').textContent = PLAY; return; } sl.value = 0; setT(0); $('#play').textContent = PAUSE; tmr = setInterval(() => { if (+sl.value >= S.length - 1) { clearInterval(tmr); tmr = null; $('#play').textContent = PLAY; return; } sl.value = +sl.value + 1; setT(+sl.value); }, 900); });

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
  $('#chart').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${tx('Área de água em cada passagem (km²)', 'Water area on each pass (km²)')}">${grid}${xl}${fc}<path d="${line}" fill="none" stroke="#4fb6ee" stroke-width="2.5"/>${dots}</svg>`;
}
})();
