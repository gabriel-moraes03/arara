/* Arara · estudo Barra Grande + Machadinho. Todos os números vêm de data/serie.json e data/meta.json
   (pipeline/scripts/estudo_uruguai.py); os textos de i18n/ só recebem os valores. */
(() => {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const RES = ['barra_grande', 'machadinho'];
  const S = { lang: 'en', dict: {}, i: 0, timer: null, layers: {} };
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* sem armazenamento */ } },
  };
  const locale = () => (S.lang === 'pt' ? 'pt-BR' : 'en-GB');
  const fmt = (v, d = 1) => Number(v).toLocaleString(locale(), { minimumFractionDigits: d, maximumFractionDigits: d });
  const sgn = (v, d = 1) => (v > 0 ? '+' : v < 0 ? '−' : '') + fmt(Math.abs(v), d);
  const dt = (iso) => new Date(iso + 'T00:00:00Z');
  const day = (iso) => dt(iso).toLocaleDateString(locale(), { day: '2-digit', month: 'short', timeZone: 'UTC' }).replace(/\.$/, '');
  const dayLong = (iso) => dt(iso).toLocaleDateString(locale(), { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
  const key = (iso) => iso.replace(/-/g, '');
  const t = (k) => {
    const raw = S.dict[S.lang][k] ?? S.dict.en[k] ?? k;
    return raw.replace(/\{(\w+)\}/g, (_, v) => (S.V[v] ?? `{${v}}`));
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  async function load() {
    const get = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(`${u}: ${r.status}`); return r.json(); });
    const [serie, meta, gbg, gma, en, pt, sens] = await Promise.all([
      get('data/serie.json'), get('data/meta.json'), get('data/limite_barra_grande.geojson'),
      get('data/limite_machadinho.geojson'), get('i18n/en.json'), get('i18n/pt.json'), get('data/sensibilidade.json'),
    ]);
    Object.assign(S, { serie, meta, sens, geo: { barra_grande: gbg, machadinho: gma }, dict: { en, pt } });
    S.dates = serie.barra_grande.map((s) => s.data);
    const [r0, r1] = [meta.metricas.barra_grande.subida.de, meta.metricas.barra_grande.subida.para]
      .map((d) => `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}`);
    S.rise = [r0, r1];
  }

  /* variáveis dos textos, recalculadas a cada idioma (formatação local) */
  function buildVars() {
    const { serie, meta } = S, M = meta.metricas, V = {};
    const at = (k, d) => serie[k].find((s) => s.data === d);
    RES.forEach((k) => {
      const p = k === 'barra_grande' ? 'bg' : 'ma', a = at(k, S.rise[0]), b = at(k, S.rise[1]);
      const m = M[k].sem_vento || M[k].todas, c = meta.reservatorios[k].cobertura;
      Object.assign(V, {
        [`${p}_rise_m`]: fmt(b.cota_ana_m - a.cota_ana_m, 1), [`${p}_vol0`]: fmt(a.volume_util_pct, 0), [`${p}_vol1`]: fmt(b.volume_util_pct, 0),
        [`${p}_new`]: fmt(M[k].subida.delta_nisar_km2, 1), [`${p}_cav`]: fmt(M[k].subida.delta_cav_km2, 1),
        [`${p}_mae`]: fmt(m.erro_abs_medio_pct, 1), [`${p}_mae_km2`]: fmt(m.erro_abs_medio_km2, 1),
        [`${p}_r`]: fmt(m.r_cota_area, 2), [`${p}_ratio`]: fmt(m.razao_variacoes * 100, 0),
        [`${p}_valid`]: fmt(c.frac_valido_todas_datas * 100, 1), [`${p}_used`]: fmt(c.frac_usada * 100, 1),
        [`${p}_shadow`]: fmt(c.frac_encosta_sombra * 100, 1), [`${p}_layover`]: fmt(c.frac_encosta_layover * 100, 1),
        [`${p}_out`]: fmt(c.frac_fora_da_passagem * 100, 1), [`${p}_poly`]: fmt(c.area_poligono_km2, 1),
        [`s_${p}_5`]: fmt(S.sens.variantes['20m_5x5'][k].erro_abs_medio_pct, 1), [`s_${p}_3`]: fmt(S.sens.variantes['20m_3x3'][k].erro_abs_medio_pct, 1),
        [`${p}_bright`]: fmt(Math.max(...serie[k].map((s) => s.brilho_agua_hh_db)), 1),
      });
    });
    const days = Math.round((dt(S.rise[1]) - dt(S.rise[0])) / 864e5);
    Object.assign(V, {
      n: S.dates.length, d0: dayLong(S.dates[0]), d1: dayLong(S.dates[S.dates.length - 1]),
      r0: day(S.rise[0]), r1: day(S.rise[1]), days, limiar: fmt(meta.metodo.limiar_db, 1),
      track: meta.trilha, frame: meta.frame, crid: meta.crid.join(', '), px: fmt(meta.pixel_processado_m, 0),
      wind: [...new Set(RES.flatMap((k) => meta.reservatorios[k].datas_suspeita_vento))].map(day).join(', ') || S.dict[S.lang]['none'],
      erro_max: fmt(5, 0),
      bright_date: day(S.serie.barra_grande.reduce((a, b) => (b.brilho_agua_hh_db > a.brilho_agua_hh_db ? b : a)).data),
    });
    S.V = V;
  }

  function applyLang(lang) {
    S.lang = lang;
    document.documentElement.lang = S.dict[lang].lang;
    buildVars();
    document.title = t('doc.title');
    document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
    renderHero();
    renderTicks();
    renderTable();
    renderMetrics();
    renderSources();
    RES.forEach(renderChart);
    setDate(S.i, false);
  }

  function renderHero() {
    const st = S.meta.rotulo.status;
    $('#badge').innerHTML = `${esc(t(st === 'validado' ? 'badge.validated' : 'badge.experimental'))}<span>${esc(t('badge.reason'))}</span>`;
    const cards = [
      ['stat.bg.k', 'stat.bg.v', 'stat.bg.p'], ['stat.ma.k', 'stat.ma.v', 'stat.ma.p'], ['stat.err.k', 'stat.err.v', 'stat.err.p'],
    ];
    $('#stats').innerHTML = cards.map(([k, v, p]) => `<div class="stat"><span class="label">${esc(t(k))}</span><span class="big">${esc(t(v))}</span><p>${esc(t(p))}</p></div>`).join('');
  }

  /* ---------------- mapa e linha do tempo ---------------- */
  function buildMap() {
    const map = L.map('map', { zoomControl: true, attributionControl: true, scrollWheelZoom: false, zoomSnap: 0.25 });
    map.attributionControl.setPrefix(false);
    map.attributionControl.addAttribution('NISAR GCOV (NASA/ISRO, ASF DAAC) · ANA/SNIRH');
    L.control.scale({ imperial: false }).addTo(map);
    let all = null;
    RES.forEach((k) => {
      const b = L.latLngBounds(S.meta.reservatorios[k].imagem.bounds);
      all = all ? all.extend(b) : L.latLngBounds(b.getSouthWest(), b.getNorthEast());
      const hh = {}, agua = {};
      S.dates.forEach((d) => {
        hh[d] = L.imageOverlay(`data/hh_${k}_${key(d)}.jpg`, b, { opacity: 0, interactive: false }).addTo(map);
        agua[d] = L.imageOverlay(`data/agua_${k}_${key(d)}.png`, b, { opacity: 0, interactive: false }).addTo(map);
      });
      const rise = L.imageOverlay(`data/subida_${k}.png`, b, { opacity: 0, interactive: false }).addTo(map);
      const lim = L.geoJSON(S.geo[k], { style: { color: '#f4b63f', weight: 1, opacity: 0.7, fill: false }, interactive: false }).addTo(map);
      const c = b.getCenter();
      L.marker([b.getNorth(), c.lng], { interactive: false, icon: L.divIcon({ className: 'map-label', html: `UHE ${esc(S.meta.reservatorios[k].nome)}`, iconSize: null }) }).addTo(map);
      S.layers[k] = { hh, agua, rise, lim };
    });
    map.fitBounds(all, { padding: [10, 10] });
    S.map = map;
  }

  function renderTicks() {
    $('#ticks').innerHTML = S.dates.map((d) => `<span class="${S.rise.includes(d) ? 'rise' : ''}">${esc(day(d))}</span>`).join('');
  }

  function setDate(i, user = true) {
    S.i = i;
    const d = S.dates[i];
    $('#slider').value = i;
    $('#tl-date').textContent = dayLong(d);
    const showMask = $('#tl-mask').checked, showRise = $('#tl-rise').checked;
    RES.forEach((k) => {
      const L_ = S.layers[k];
      S.dates.forEach((x) => {
        L_.hh[x].setOpacity(x === d ? 1 : 0);
        L_.agua[x].setOpacity(x === d && showMask && !showRise ? 0.9 : 0);
      });
      L_.rise.setOpacity(showRise ? 1 : 0);
      const s = S.serie[k][i];
      $(`#res-${k}`).innerHTML = `<h3>UHE ${esc(S.meta.reservatorios[k].nome)}</h3><dl>
        <dt>${esc(t('time.level'))}</dt><dd>${fmt(s.cota_ana_m, 2)} m · ${fmt(s.volume_util_pct, 0)}%</dd>
        <dt>${esc(t('time.nisar'))}</dt><dd>${fmt(s.area_nisar_km2, 1)} km²</dd>
        <dt>${esc(t('time.expected'))}</dt><dd>${fmt(s.area_esperada_km2, 1)} km²</dd>
        <dt>${esc(t('time.diff'))}</dt><dd>${sgn(s.diferenca_km2)} km² (${sgn(s.diferenca_pct)}%)</dd></dl>`;
    });
    const wind = RES.some((k) => S.serie[k][i].suspeita_vento);
    $('#tl-flag').textContent = showRise ? t('time.flag.rise') : wind ? t('time.flag.wind') : (d === S.rise[1] ? t('time.flag.after') : '');
    document.querySelectorAll('.chart .cur').forEach((el) => el.setAttribute('transform', `translate(${S.X(dt(d))},0)`));
    document.querySelectorAll('#tbl tbody tr').forEach((tr, j) => tr.toggleAttribute('aria-current', j === i));
    if (user) stop();
  }

  function play() {
    if (S.timer) { stop(); return; }
    $('#tl-rise').checked = false;
    $('#play').textContent = t('time.pause');
    if (S.i >= S.dates.length - 1) setDate(0, false);
    S.timer = setInterval(() => {
      if (S.i >= S.dates.length - 1) { stop(); return; }
      setDate(S.i + 1, false);
    }, REDUCED ? 2200 : 1400);
  }
  function stop() {
    clearInterval(S.timer); S.timer = null;
    $('#play').textContent = t('time.play');
  }

  /* ---------------- gráfico NISAR × ANA (um por reservatório, mesma escala) ---------------- */
  function renderChart(k) {
    const W = 560, H = 300, m = { l: 44, r: 14, t: 14, b: 30 };
    const all = RES.flatMap((r) => S.serie[r].flatMap((s) => [s.area_nisar_km2, s.area_esperada_km2]));
    const lo = Math.floor(Math.min(...all) / 10) * 10, hi = Math.ceil(Math.max(...all) / 10) * 10;
    const t0 = dt(S.dates[0]).getTime(), t1 = dt(S.dates[S.dates.length - 1]).getTime();
    const X = (d) => m.l + ((d.getTime() - t0) / (t1 - t0)) * (W - m.l - m.r);
    const Y = (v) => H - m.b - ((v - lo) / (hi - lo)) * (H - m.t - m.b);
    S.X = X;
    const s = S.serie[k], path = (f) => s.map((p, j) => `${j ? 'L' : 'M'}${X(dt(p.data)).toFixed(1)},${Y(f(p)).toFixed(1)}`).join('');
    let g = '';
    for (let v = lo; v <= hi; v += 10) g += `<g class="grid"><line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/></g><g class="ax"><text x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">${v}</text></g>`;
    const months = [];
    for (let mo = dt(S.dates[0]).getUTCMonth() + 1; mo <= dt(S.dates[S.dates.length - 1]).getUTCMonth(); mo++) months.push(new Date(Date.UTC(2026, mo, 1)));
    g += months.map((d) => `<g class="ax"><line x1="${X(d)}" x2="${X(d)}" y1="${H - m.b}" y2="${H - m.b + 5}"/><text x="${X(d) + 3}" y="${H - m.b + 18}">${esc(d.toLocaleDateString(locale(), { month: 'short', timeZone: 'UTC' }).toUpperCase())}</text></g>`).join('');
    const band = `<rect x="${X(dt(S.rise[0]))}" y="${m.t}" width="${X(dt(S.rise[1])) - X(dt(S.rise[0]))}" height="${H - m.t - m.b}" fill="rgba(79,182,238,.14)"/>`;
    const dots = (f, cls) => s.map((p) => `<circle cx="${X(dt(p.data))}" cy="${Y(f(p))}" r="4.5" class="${cls}" stroke="#0a101a" stroke-width="2"/>`).join('');
    const hits = s.map((p, j) => {
      const x0 = j ? (X(dt(s[j - 1].data)) + X(dt(p.data))) / 2 : m.l, x1 = j < s.length - 1 ? (X(dt(p.data)) + X(dt(s[j + 1].data))) / 2 : W - m.r;
      return `<rect class="hit" data-j="${j}" x="${x0}" y="${m.t}" width="${x1 - x0}" height="${H - m.t - m.b}" fill="transparent"/>`;
    }).join('');
    const last = s[s.length - 1];
    const fig = $(`#chart-${k}`);
    fig.innerHTML = `<h3>UHE ${esc(S.meta.reservatorios[k].nome)}</h3><p class="sub">${esc(t('chart.unit'))}</p>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t('chart.title'))}">${band}${g}
        <path d="${path((p) => p.area_esperada_km2)}" fill="none" stroke="#c9d3db" stroke-width="2" stroke-dasharray="6 5"/>
        <path d="${path((p) => p.area_nisar_km2)}" fill="none" stroke="#4fb6ee" stroke-width="2"/>
        ${dots((p) => p.area_esperada_km2, 'c')}${dots((p) => p.area_nisar_km2, 'n')}
        <text x="${W - m.r}" y="${Y(last.area_esperada_km2) - 9}" text-anchor="end" fill="#a8b6c1" font-size="11" font-family="IBM Plex Mono, monospace">ANA ${fmt(last.area_esperada_km2, 1)}</text>
        <text x="${W - m.r}" y="${Y(last.area_nisar_km2) + 18}" text-anchor="end" fill="#a8b6c1" font-size="11" font-family="IBM Plex Mono, monospace">NISAR ${fmt(last.area_nisar_km2, 1)}</text>
        <g class="cur"><line x1="0" x2="0" y1="${m.t}" y2="${H - m.b}" stroke="#f4b63f" stroke-width="1" stroke-dasharray="2 3"/></g>
        ${hits}</svg><div class="tip"></div>`;
    fig.querySelectorAll('circle.c').forEach((c) => c.setAttribute('fill', '#c9d3db'));
    fig.querySelectorAll('circle.n').forEach((c) => c.setAttribute('fill', '#4fb6ee'));
    const tip = fig.querySelector('.tip'), svg = fig.querySelector('svg');
    fig.querySelectorAll('.hit').forEach((r) => {
      const p = s[+r.dataset.j];
      r.addEventListener('mouseenter', () => {
        tip.innerHTML = `<b>${esc(dayLong(p.data))}</b><br><span class="m">${esc(t('time.level'))}</span> ${fmt(p.cota_ana_m, 2)} m<br>NISAR ${fmt(p.area_nisar_km2, 1)} km²<br>ANA ${fmt(p.area_esperada_km2, 1)} km²<br><span class="m">Δ</span> ${sgn(p.diferenca_km2)} km²`;
        const sc = svg.getBoundingClientRect().width / W, x = X(dt(p.data)) * sc + 16;
        tip.style.left = `${Math.min(x + 10, fig.clientWidth - 170)}px`;
        tip.style.top = `${Y(p.area_nisar_km2) * sc + 40}px`;
        tip.style.opacity = 1;
      });
      r.addEventListener('mouseleave', () => { tip.style.opacity = 0; });
      r.addEventListener('click', () => setDate(+r.dataset.j));
      r.style.cursor = 'pointer';
    });
  }

  /* ---------------- tabela e métricas ---------------- */
  function renderTable() {
    const nm = (k) => S.meta.reservatorios[k].nome;
    const head = `<thead><tr><th></th>${RES.map((k) => `<th class="grp" colspan="5">UHE ${esc(nm(k))}</th>`).join('')}<th class="l"></th></tr>
      <tr><th>${esc(t('table.date'))}</th>${RES.map(() => ['table.level', 'table.vol', 'table.exp', 'table.nisar', 'table.diff'].map((c, j) => `<th class="${j ? '' : 'l'}">${esc(t(c))}</th>`).join('')).join('')}<th class="l">${esc(t('table.wind'))}</th></tr></thead>`;
    const rows = S.dates.map((d, i) => {
      const cells = RES.map((k) => {
        const s = S.serie[k][i];
        return `<td class="l">${fmt(s.cota_ana_m, 2)}</td><td>${fmt(s.volume_util_pct, 1)}</td><td>${fmt(s.area_esperada_km2, 1)}</td><td>${fmt(s.area_nisar_km2, 1)}</td><td class="${s.diferenca_km2 < 0 ? 'neg' : ''}">${sgn(s.diferenca_km2)} (${sgn(s.diferenca_pct)}%)</td>`;
      }).join('');
      const w = RES.some((k) => S.serie[k][i].suspeita_vento);
      const cls = d === S.rise[0] || d === S.rise[1] ? 'rise' : '';
      return `<tr class="${cls}"><td>${esc(dayLong(d))}</td>${cells}<td class="l">${esc(t(w ? 'yes' : 'no'))}</td></tr>`;
    }).join('');
    $('#tbl').innerHTML = head + `<tbody>${rows}</tbody>`;
  }

  function renderMetrics() {
    $('#metrics').innerHTML = RES.map((k) => {
      const m = S.meta.metricas[k].todas, c = S.meta.reservatorios[k].cobertura;
      const row = (a, b) => `<dt>${esc(t(a))}</dt><dd>${b}</dd>`;
      return `<div class="mcard"><h3>UHE ${esc(S.meta.reservatorios[k].nome)}</h3><dl>
        ${row('m.mae', `${fmt(m.erro_abs_medio_km2, 1)} km² (${fmt(m.erro_abs_medio_pct, 1)}%)`)}
        ${row('m.bias', `${sgn(m.vies_km2)} km²`)}
        ${row('m.noise', `${fmt(m.ruido_dp_km2, 1)} km²`)}
        ${row('m.r', fmt(m.r_cota_area, 2))}
        ${row('m.slope', `${fmt(m.inclinacao_nisar_km2_por_m, 2)} × ${fmt(m.inclinacao_cav_km2_por_m, 2)} km²/m`)}
        ${row('m.rd', fmt(m.r_variacoes, 2))}
        ${row('m.s20', `${fmt(S.sens.variantes['20m_5x5'][k].erro_abs_medio_pct, 1)}% (5×5) · ${fmt(S.sens.variantes['20m_3x3'][k].erro_abs_medio_pct, 1)}% (3×3)`)}
        ${row('m.cov', `${fmt(c.frac_valido_todas_datas * 100, 1)}% · ${t('m.used')} ${fmt(c.frac_usada * 100, 1)}%`)}
        </dl></div>`;
    }).join('');
  }

  function renderSources() {
    const M = S.meta;
    const items = [
      `${t('src.nisar')} ${M.colecao}, CRID ${M.crid.join(', ')}, ${t('src.geom')} ${M.trilha} ${M.direcao} / frame ${M.frame} / ${t('src.mode')} ${M.modo}. ` + M.cenas.map((c) => c.granuleId).map(esc).join(' · '),
      `${t('src.cav')} ${M.fontes.ana_cav}.`,
      `${RES.map((k) => M.reservatorios[k].fonte_poligono).join('; ')}.`,
      `${t('src.level')} ${M.fontes.ana_sar}.`,
      `${t('src.method')}`,
    ];
    $('#src').innerHTML = items.map((x) => `<li>${esc(x)}</li>`).join('');
  }

  async function init() {
    try { await load(); } catch (e) {
      document.querySelector('main').innerHTML = `<p class="err">Could not load study data (${esc(e.message)}).</p>`;
      return;
    }
    const q = new URLSearchParams(location.search).get('lang');
    const lang = q === 'pt' || q === 'en' ? q : store.get('tp-lang') || 'en';
    buildMap();
    S.i = S.dates.indexOf(S.rise[0]);
    applyLang(lang);
    $('#lang').addEventListener('click', () => { const l = S.lang === 'en' ? 'pt' : 'en'; store.set('tp-lang', l); applyLang(l); });
    $('#slider').addEventListener('input', (e) => setDate(+e.target.value));
    $('#play').addEventListener('click', play);
    $('#tl-mask').addEventListener('change', () => setDate(S.i, false));
    $('#tl-rise').addEventListener('change', () => setDate(S.i, false));
  }
  init();
})();
