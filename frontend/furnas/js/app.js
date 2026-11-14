/* TerraPulse · app estático. Todos os números vêm de data/*.json. */
(() => {
  'use strict';

  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const MOBILE = matchMedia('(max-width: 900px)').matches;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const SVGNS = 'http://www.w3.org/2000/svg';
  const DAM = [-20.669, -46.318]; // UHE Furnas, eixo da barragem (aprox.)

  const S = { lang: 'en', dict: {}, V: {}, onLang: [], maps: {} };

  /* ---------------- utilidades ---------------- */
  const svg = (tag, attrs = {}, parent) => {
    const el = document.createElementNS(SVGNS, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(el);
    return el;
  };
  const locale = () => (S.lang === 'pt' ? 'pt-BR' : 'en-GB');
  const fmt = (v, d = 0) => new Intl.NumberFormat(locale(), { minimumFractionDigits: d, maximumFractionDigits: d })
    .format(v).replace('-', '−');
  const fmtS = (v, d = 0) => (v > 0 ? '+' : '') + fmt(v, d);
  const iso2key = (iso) => iso.replace(/-/g, '');
  const dt = (iso) => new Date(iso + 'T12:00:00Z');
  const fmtDate = (iso, year = false) => {
    const d = dt(iso), m = S.dict[S.lang].month[d.getUTCMonth()];
    return `${d.getUTCDate()} ${m}${year ? ' ' + d.getUTCFullYear() : ''}`;
  };
  const t = (key) => {
    const raw = S.dict[S.lang][key] ?? S.dict.en[key] ?? key;
    return typeof raw === 'string' ? raw.replace(/\{(\w+)\}/g, (_, k) => (k in S.V ? S.V[k] : `{${k}}`)) : raw;
  };
  const once = (el, cb, margin = '0px', threshold = 0.15) => {
    if (!('IntersectionObserver' in window)) return cb();
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) { io.disconnect(); cb(); }
    }, { rootMargin: margin, threshold });
    io.observe(el);
  };
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* sem armazenamento */ } },
  };
  function rollNumber(el, from, to, d, dur = 600) {
    if (REDUCED || from == null || isNaN(from)) { el.textContent = fmt(to, d); return; }
    const t0 = performance.now();
    cancelAnimationFrame(el._raf);
    const step = (now) => {
      const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = fmt(from + (to - from) * e, d);
      if (k < 1) el._raf = requestAnimationFrame(step);
    };
    el._raf = requestAnimationFrame(step);
  }

  /* ---------------- dados ---------------- */
  async function load() {
    const get = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(`${u}: ${r.status}`); return r.json(); });
    const [serie, meta, bounds, geo, en, pt] = await Promise.all([
      get('data/serie.json'), get('data/meta.json'), get('data/bounds.json'),
      get('data/limite_furnas.geojson'), get('i18n/en.json'), get('i18n/pt.json'),
    ]);
    Object.assign(S, { serie, meta, geo, dict: { en, pt } });
    S.B = L.latLngBounds(bounds.bounds);
    S.d0 = serie[0].data; S.d1 = serie[serie.length - 1].data;
    S.calm = serie.filter((s) => !s.suspeita_vento);
    S.wind = serie.filter((s) => s.suspeita_vento);
  }

  function buildVars() {
    const { serie, meta, calm, wind } = S, M = meta.metricas;
    const byVol = [...serie].sort((a, b) => a.volume_util_pct - b.volume_util_pct);
    const worst = wind.reduce((a, b) => (b.diferenca_km2 < a.diferenca_km2 ? b : a));
    const exc = calm.reduce((a, b) => (b.diferenca_km2 > a.diferenca_km2 ? b : a));
    const meanExp = serie.reduce((a, s) => a + s.area_esperada_km2, 0) / serie.length;
    const maxN = meta.cota_max_normal_m, last = serie[serie.length - 1];
    const pctDigits = Number.isInteger(M.erro_abs_medio_pct) ? 0 : (M.erro_abs_medio_pct * 10) % 10 === 0 ? 0 : 1;
    S.V = {
      n: serie.length, ncalm: M.n_datas_calmas,
      d0: fmtDate(S.d0, true), d1: fmtDate(S.d1, true), d0s: fmtDate(S.d0), d1s: fmtDate(S.d1),
      mae_pct: fmt(M.erro_abs_medio_pct, pctDigits), mae_km2: fmt(M.erro_abs_medio_km2, 0),
      areatyp: fmt(Math.round(meanExp / 10) * 10, 0),
      ruido: fmt(M.ruido_dp_km2, 0),
      slope: fmt(M.inclinacao_nisar_km2_por_m, 0), slopeana: fmt(M.inclinacao_ana_km2_por_m, 0),
      drop: fmt(M.queda_cota_m, 2), cmax: fmt(M.cota_max_m, 2), cmin: fmt(M.cota_min_m, 2),
      dmax: fmtDate(M.cota_max_data), dmin: fmtDate(M.cota_min_data),
      varexp: fmt(M.variacao_area_esperada_km2, 0),
      limiar: fmt(meta.metodo.limiar_db, 2), mancha: fmt(meta.metodo.mancha_minima_km2, 1),
      hv: fmt(meta.camadas.hv_volume_db, 0), px: meta.pixel_processado_m,
      w1: fmtDate(wind[0].data), w2: fmtDate(wind[1].data),
      b1: fmt(wind[0].brilho_agua_hh_db, 1), b2: fmt(wind[1].brilho_agua_hh_db, 1),
      bcalm: fmt(M.brilho_agua_calmas_db, 1),
      wworst: fmtDate(worst.data), worst: fmt(Math.abs(worst.diferenca_km2), 0),
      dexc: fmtDate(exc.data), exc: fmt(exc.diferenca_km2, 0),
      maxnormal: fmt(maxN, 1),
      net: fmtS(last.delta_nisar_km2, 0), netexp: fmtS(last.delta_esperado_km2, 0),
      vmax: fmt(byVol[byVol.length - 1].volume_util_pct, 1), dvmax: fmtDate(byVol[byVol.length - 1].data),
      vmin: fmt(byVol[0].volume_util_pct, 1), dvmin: fmtDate(byVol[0].data),
      vlast: fmt(last.volume_util_pct, 1), dlast: fmtDate(last.data),
      gapmin: fmt(Math.round((maxN - M.cota_max_m) * 100) / 100, 1), gapmax: fmt(Math.round((maxN - M.cota_min_m) * 100) / 100, 1),
      col: meta.colecao, funil: fmt(meta.cobertura.funil_frac * 100, 0),
      poly: fmt(meta.poligono.area_km2, 1),
    };
  }

  function applyLang(lang) {
    S.lang = lang;
    document.documentElement.lang = S.dict[lang].lang;
    buildVars();
    document.title = t('doc.title');
    $$('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
    $$('[data-i18n-aria]').forEach((el) => el.setAttribute('aria-label', t(el.dataset.i18nAria)));
    S.onLang.forEach((fn) => fn());
  }

  /* ---------------- mapas ---------------- */
  const url = {
    hh: (iso) => `data/hh_${iso2key(iso)}.jpg`,
    agua: (iso) => `data/agua_${iso2key(iso)}.png`,
    hv: () => `data/hv_${iso2key(S.d0)}.jpg`,
    cor: () => `data/cor_${iso2key(S.d0)}.jpg`,
  };

  // zoom em que a imagem preenche a moldura inteira (sem faixas vazias)
  function coverZoom(map) {
    const p1 = map.latLngToContainerPoint(S.B.getNorthWest()), p2 = map.latLngToContainerPoint(S.B.getSouthEast());
    const size = map.getSize();
    const z = map.getZoom() + Math.log2(Math.max(size.x / (p2.x - p1.x), size.y / (p2.y - p1.y)));
    return Math.ceil(z * 4) / 4;
  }

  // crédito das camadas: legenda em texto abaixo da moldura (legível, não cobre a imagem)
  function credit(el, host) {
    let target = host;
    if (!target) {
      const fig = el.closest('figure'), tl = el.closest('.tl');
      target = document.createElement('p');
      target.className = 'map-credit';
      if (fig) fig.appendChild(target); else if (tl) tl.after(target); else el.after(target);
    }
    const fill = () => { target.innerHTML = `<a class="link" href="https://leafletjs.com">Leaflet</a> · ${t('map.attrib')}`; };
    fill();
    S.onLang.push(fill);
  }

  function makeMap(el, { interactive = true, zoom = true, wheel = false, cover = false, creditHost = null } = {}) {
    const map = L.map(el, {
      zoomControl: zoom, attributionControl: false, zoomSnap: 0.25, zoomDelta: 0.5, preferCanvas: true,
      scrollWheelZoom: wheel, dragging: interactive && (!MOBILE || wheel), touchZoom: interactive,
      doubleClickZoom: interactive, boxZoom: false, keyboard: interactive, tap: false,
    });
    map.fitBounds(S.B, { animate: false });
    map.setMinZoom(map.getZoom() - 0.5);
    map.setMaxBounds(S.B.pad(0.25));
    if (cover) {
      map.setView(S.B.getCenter(), coverZoom(map), { animate: false });
      // o recorte sai do lado leste (borda da passagem), não do oeste, onde fica a barragem
      const west = map.latLngToContainerPoint(S.B.getNorthWest()).x;
      if (west < 0) map.panBy([west, 0], { animate: false });
    }
    map._home = map.getZoom();
    L.control.scale({ imperial: false, position: 'bottomleft', maxWidth: 120 }).addTo(map);
    credit(el, creditHost);
    // coordenadas no canto, à moda de instrumento
    const box = L.DomUtil.create('div', 'coords', map.getContainer());
    const show = (ll) => {
      const ns = ll.lat < 0 ? 'S' : 'N', ew = ll.lng < 0 ? 'W' : 'E';
      box.textContent = `${Math.abs(ll.lat).toFixed(4)}° ${ns}  ${Math.abs(ll.lng).toFixed(4)}° ${ew}`;
    };
    show(map.getCenter());
    map.on('mousemove', (e) => show(e.latlng));
    map.on('mouseout moveend', () => show(map.getCenter()));
    return map;
  }

  function outline(map, opts = {}) {
    // linha off-white de 1,6 px sobre halo escuro sutil: legível sobre água e sobre terra clara
    return L.layerGroup([
      L.geoJSON(S.geo, { interactive: false, renderer: opts.renderer,
        style: { color: '#05080a', weight: 4, opacity: 0.45, fill: false, lineJoin: 'round' } }),
      L.geoJSON(S.geo, { interactive: false, renderer: opts.renderer,
        style: { color: '#f4efe2', weight: 1.6, opacity: 0.95, fill: false, lineJoin: 'round' } }),
    ]).addTo(map);
  }

  function damLabel(map) {
    const mk = L.marker(DAM, { interactive: false, keyboard: false,
      icon: L.divIcon({ className: '', html: `<span class="map-label">${t('map.dam')}</span>`, iconSize: null, iconAnchor: [4, 6] }) }).addTo(map);
    S.onLang.push(() => mk.setIcon(L.divIcon({ className: '', html: `<span class="map-label">${t('map.dam')}</span>`, iconSize: null, iconAnchor: [4, 6] })));
  }

  const overlay = (map, u, opacity = 1, extra = {}) =>
    L.imageOverlay(u, S.B, { opacity, className: 'fade', interactive: false, ...extra }).addTo(map);

  /* sonda: HH/HV quantizados + classe, lidos por pixel */
  let sondaP = null;
  function sonda() {
    if (sondaP) return sondaP;
    sondaP = new Promise((res, rej) => {
      const img = new Image();
      img.onload = () => {
        const c = document.createElement('canvas');
        c.width = img.width; c.height = img.height;
        const ctx = c.getContext('2d', { willReadFrequently: true });
        ctx.drawImage(img, 0, 0);
        const data = ctx.getImageData(0, 0, c.width, c.height).data;
        const W = c.width, H = c.height;
        const my = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
        const n = S.B.getNorth(), s = S.B.getSouth(), w = S.B.getWest(), e = S.B.getEast();
        const q = S.meta.camadas.sonda;
        const at = (ll) => {
          const x = Math.floor(((ll.lng - w) / (e - w)) * W);
          const y = Math.floor(((my(n) - my(ll.lat)) / (my(n) - my(s))) * H);
          if (x < 0 || y < 0 || x >= W || y >= H) return null;
          const i = (y * W + x) * 4;
          if (!data[i + 2]) return null;
          return { hh: q.db_min + data[i] * q.db_por_nivel, hv: q.db_min + data[i + 1] * q.db_por_nivel, cls: data[i + 2] };
        };
        const mask = (cls) => {
          const out = ctx.createImageData(W, H);
          for (let i = 0; i < data.length; i += 4) {
            if (data[i + 2] === cls) { out.data[i] = 124; out.data[i + 1] = 242; out.data[i + 2] = 196; out.data[i + 3] = 255; }
          }
          const c2 = document.createElement('canvas');
          c2.width = W; c2.height = H;
          c2.getContext('2d').putImageData(out, 0, 0);
          return c2.toDataURL('image/png');
        };
        res({ at, mask });
      };
      img.onerror = rej;
      img.src = 'data/sonda.png';
    });
    return sondaP;
  }
  function probeText(v) {
    if (!v) return t('probe.none');
    const cls = { 1: t('probe.water'), 2: t('probe.volume'), 3: t('probe.field') }[v.cls] || '';
    return `<b>${t('probe.hh')}</b> ${fmt(v.hh, 1)} dB · <b>${t('probe.hv')}</b> ${fmt(v.hv, 1)} dB · <em>${cls}</em>`;
  }
  function attachProbe(map, el) {
    sonda().then((sd) => {
      const upd = (e) => { el.innerHTML = probeText(sd.at(e.latlng)); };
      map.on('mousemove click', upd);
    });
  }

  /* ---------------- 1 · abertura ---------------- */
  function initHero() {
    const el = $('#map-hero');
    const map = makeMap(el, { interactive: false, zoom: false, cover: true, creditHost: $('#hero-credit') });
    // a imagem cobre a tela toda; no desktop o lago fica à direita do título
    map.setMaxBounds(null);
    if (!MOBILE) map.panBy([-el.clientWidth * 0.14, 0], { animate: false });
    const ov = overlay(map, url.hh(S.d0));
    outline(map);
    const sweep = $('.sweep');
    let started = false;
    const go = () => { if (!started) { started = true; sweep.classList.add('go'); } };
    ov.on('load', go);
    setTimeout(go, 2500);
    const c = S.meta.cenas[0];
    const fill = () => {
      const lat = (v) => `${Math.abs(v).toFixed(2)}°S`;
      $('#hero-meta').innerHTML = [
        `ACQ <b>${c.zeroDopplerStartTime.slice(0, 19).replace('T', ' ')} UTC</b>`,
        `ORBIT ${c.absoluteOrbitNumber} · ${c.orbitPassDirection.toUpperCase()} · CRID ${c.compositeReleaseId}`,
        `<span class="nocase">γ⁰</span> HH · ${S.meta.pixel_original_m} m → ${S.meta.pixel_processado_m} m`,
        `${lat(S.B.getNorth())} – ${lat(S.B.getSouth())}`,
      ].join('<br>');
    };
    fill();
  }

  /* ---------------- diagrama "por que a água fica escura" ---------------- */
  function drawDiagram() {
    const host = $('#diagram');
    host.innerHTML = '';
    const s = svg('svg', { viewBox: '0 0 460 160', role: 'img' }, host);
    const fs = (13 * 460) / Math.min(460, host.clientWidth || 460);
    s.style.fontSize = `${fs}px`;
    // satélite
    svg('rect', { x: 24, y: 12, width: 24, height: 10, fill: 'none', stroke: '#aab1ad' }, s);
    svg('line', { x1: 10, y1: 17, x2: 24, y2: 17, stroke: '#aab1ad' }, s);
    svg('line', { x1: 48, y1: 17, x2: 62, y2: 17, stroke: '#aab1ad' }, s);
    svg('text', { x: 2, y: 34 + fs }, s).textContent = t('see.dia.sat');
    // água lisa e terreno rugoso
    svg('line', { x1: 110, y1: 150, x2: 236, y2: 150, stroke: '#3b82d6', 'stroke-width': 2 }, s);
    svg('path', { d: 'M296 150 l8 -6 l7 5 l9 -9 l6 7 l8 -4 l7 6 l9 -8 l7 6 l8 -5 l9 6 l6 -3 l8 5 l10 -4 l7 4 l9 -5 l6 5', fill: 'none', stroke: '#c97a34', 'stroke-width': 1.5 }, s);
    // pulso na água: reflexão especular, para longe
    svg('line', { x1: 40, y1: 24, x2: 172, y2: 148, stroke: '#7cf2c4', class: 'pulse' }, s);
    svg('line', { x1: 172, y1: 148, x2: 262, y2: 64, stroke: '#7cf2c4', class: 'pulse', opacity: 0.5 }, s);
    // pulso no terreno: espalha, parte volta
    svg('line', { x1: 40, y1: 24, x2: 372, y2: 142, stroke: '#7cf2c4', class: 'pulse' }, s);
    for (const [x2, y2] of [[408, 108], [420, 128], [352, 104], [390, 96]]) svg('line', { x1: 372, y1: 142, x2, y2, stroke: '#7cf2c4', opacity: 0.35 }, s);
    svg('line', { x1: 372, y1: 142, x2: 58, y2: 30, stroke: '#7cf2c4', 'stroke-width': 1.5, opacity: 0.85 }, s);
    svg('text', { x: 74, y: 4 + fs * 0.8 }, s).textContent = t('see.dia.pulse');
    const lab = document.createElement('div');
    lab.className = 'dia-labels';
    lab.innerHTML = `<span>${t('see.dia.water')}</span><span>${t('see.dia.land')}</span>`;
    host.appendChild(lab);
  }

  /* ---------------- 2 · o que o radar vê ---------------- */
  function initSee() {
    const map = makeMap($('#map-see'), { cover: true });
    const cor = overlay(map, url.cor());
    const hi = overlay(map, 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==', 0);
    outline(map);
    damLabel(map);
    attachProbe(map, $('#probe-see'));
    const cache = {};
    let pinned = null;
    const show = async (cls) => {
      if (!cls) { hi.setOpacity(0); cor.setOpacity(1); return; }
      const sd = await sonda();
      hi.setUrl(cache[cls] || (cache[cls] = sd.mask(cls)));
      hi.setOpacity(0.95); cor.setOpacity(0.28);
    };
    $$('#classes button').forEach((b) => {
      const cls = +b.dataset.class;
      b.addEventListener('mouseenter', () => show(cls));
      b.addEventListener('focus', () => show(cls));
      b.addEventListener('mouseleave', () => show(pinned));
      b.addEventListener('blur', () => show(pinned));
      b.addEventListener('click', () => {
        pinned = pinned === cls ? null : cls;
        $$('#classes button').forEach((x) => x.classList.toggle('on', +x.dataset.class === pinned));
        show(pinned);
      });
    });
  }

  /* ---------------- 3 · linha do tempo ---------------- */
  const TL = { i: 0, playing: false, timer: null, layers: [], area: null };
  function initTimeline() {
    const map = makeMap($('#map-time'), { cover: true });
    S.maps.time = map;
    TL.layers = S.serie.map((s, i) => ({
      hh: overlay(map, url.hh(s.data), i === 0 ? 1 : 0),
      agua: overlay(map, url.agua(s.data), 0),
    }));
    outline(map);
    damLabel(map);
    setDate(0, true);
    $('#tl-mask').addEventListener('change', () => setDate(TL.i, true));
  }
  function setDate(i, instant = false) {
    const prev = TL.i;
    TL.i = i;
    const s = S.serie[i], maskOn = $('#tl-mask').checked;
    TL.layers.forEach((l, k) => {
      l.hh.setOpacity(k === i ? 1 : 0);
      l.agua.setOpacity(k === i && maskOn ? 0.88 : 0);
    });
    $('#tl-date').textContent = fmtDate(s.data, true);
    const f = $('#tl-flag');
    f.classList.toggle('on', s.suspeita_vento);
    f.textContent = s.suspeita_vento ? t('time.flag') : t('time.calm');
    const a = $('#tl-area');
    rollNumber(a, instant ? null : S.serie[prev].area_nisar_km2, s.area_nisar_km2, 1);
    $('#tl-exp').textContent = `${fmt(s.area_esperada_km2, 1)} km²`;
    $('#tl-level').textContent = `${fmt(s.cota_ana_m, 2)} m`;
    $('#tl-signal').textContent = `${fmt(s.brilho_agua_hh_db, 1)} dB`;
    drawRuler();
  }
  function play(on) {
    TL.playing = on;
    const b = $('#tl-play');
    b.classList.toggle('on', on);
    b.querySelector('span').textContent = t(on ? 'time.pause' : 'time.play');
    clearInterval(TL.timer);
    if (!on) return;
    if (TL.i === S.serie.length - 1) setDate(0);
    TL.timer = setInterval(() => {
      if (TL.i >= S.serie.length - 1) { play(false); return; }
      setDate(TL.i + 1);
    }, REDUCED ? 2200 : 1500);
  }
  function drawRuler() {
    const host = $('#ruler');
    const W = Math.max(300, host.clientWidth || 800), H = 76, padL = 8, padR = 8, y0 = 42;
    const start = dt('2026-06-20'), end = dt('2026-10-20');
    const x = (d) => padL + ((d - start) / (end - start)) * (W - padL - padR);
    host.innerHTML = '';
    const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'group', 'aria-label': 'Timeline' }, host);
    svg('line', { x1: padL, x2: W - padR, y1: y0, y2: y0, class: 'axis' }, s);
    const dense = W > 640;
    for (let d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
      const first = d.getUTCDate() === 1;
      if (first) {
        svg('line', { x1: x(d), x2: x(d), y1: y0 - 12, y2: y0 + 12, class: 'major' }, s);
        svg('text', { x: x(d) + 4, y: y0 + 28 }, s).textContent = S.dict[S.lang].month[d.getUTCMonth()].toUpperCase();
      } else if (dense || d.getUTCDay() === 1) {
        svg('line', { x1: x(d), x2: x(d), y1: y0, y2: y0 + (d.getUTCDay() === 1 ? 6 : 3), class: 'minor' }, s);
      }
    }
    const cur = svg('path', { d: 'M-4 0 L4 0 L0 6 Z', class: 'cursor' }, s);
    cur.style.transform = `translate(${x(dt(S.serie[TL.i].data))}px, 19px)`;
    S.serie.forEach((p, i) => {
      const g = svg('g', { class: 'pass' + (i === TL.i ? ' on' : ''), tabindex: 0, role: 'button',
        'aria-label': fmtDate(p.data, true) + (p.suspeita_vento ? ' · ' + t('time.flag') : '') }, s);
      const px = x(dt(p.data));
      svg('rect', { x: px - 12, y: 0, width: 24, height: H, class: 'hit' }, g);
      svg('line', { x1: px, x2: px, y1: y0 - 14, y2: y0 + 1 }, g);
      if (p.suspeita_vento) svg('path', { d: `M${px - 5} ${y0 + 13} L${px + 5} ${y0 + 13} L${px} ${y0 + 5} Z`, class: 'flag' }, g);
      const lb = svg('text', { x: px, y: 13, 'text-anchor': i === 0 ? 'start' : i === S.serie.length - 1 ? 'end' : 'middle', class: 'lbl' }, g);
      lb.textContent = fmtDate(p.data);
      if (i === 0) lb.setAttribute('x', px + 8);
      if (i === S.serie.length - 1) lb.setAttribute('x', px - 8);
      const pick = () => { play(false); setDate(i); };
      g.addEventListener('click', pick);
      g.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); }
        if (e.key === 'ArrowRight' && i < S.serie.length - 1) { play(false); setDate(i + 1); $$('#ruler .pass')[i + 1].focus(); }
        if (e.key === 'ArrowLeft' && i > 0) { play(false); setDate(i - 1); $$('#ruler .pass')[i - 1].focus(); }
      });
    });
  }

  /* ---------------- 4 · antes x depois ---------------- */
  function initCompare() {
    const el = $('#map-cmp');
    const map = makeMap(el, { cover: true });
    map.createPane('after').style.zIndex = 420;
    map.createPane('chg').style.zIndex = 440;
    map.createPane('lines').style.zIndex = 460;
    const before = [overlay(map, url.hh(S.d0)), overlay(map, url.agua(S.d0), 0.85)];
    const after = [overlay(map, url.hh(S.d1), 1, { pane: 'after' }), overlay(map, url.agua(S.d1), 0.85, { pane: 'after' })];
    const chg = overlay(map, 'data/mudanca.png', 0, { pane: 'chg' });
    outline(map, { renderer: L.canvas({ pane: 'lines' }) });
    const pane = map.getPane('after'), sw = $('#swipe'), home = map._home;
    let pos = 0.5;
    const clip = () => {
      const nw = map.containerPointToLayerPoint([0, 0]);
      const se = map.containerPointToLayerPoint(map.getSize());
      const cx = nw.x + pos * map.getSize().x;
      pane.style.clip = `rect(${nw.y}px, ${se.x}px, ${se.y}px, ${cx}px)`;
      sw.style.left = `${pos * 100}%`;
    };
    map.on('move zoom resize viewreset zoomend', clip);
    clip();
    L.DomEvent.disableClickPropagation(sw);
    const handle = sw.querySelector('.swipe-handle');
    const drag = (e) => {
      const r = el.getBoundingClientRect();
      pos = Math.min(0.98, Math.max(0.02, (e.clientX - r.left) / r.width));
      clip();
    };
    handle.addEventListener('pointerdown', (e) => {
      e.preventDefault(); e.stopPropagation();
      handle.setPointerCapture(e.pointerId);
      map.dragging.disable();
      handle.addEventListener('pointermove', drag);
      const up = () => {
        handle.removeEventListener('pointermove', drag);
        handle.removeEventListener('pointerup', up);
        handle.removeEventListener('pointercancel', up);
        if (!MOBILE) map.dragging.enable();
      };
      handle.addEventListener('pointerup', up);
      handle.addEventListener('pointercancel', up);
    });
    handle.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') { pos = Math.max(0.02, pos - 0.05); clip(); }
      if (e.key === 'ArrowRight') { pos = Math.min(0.98, pos + 0.05); clip(); }
    });
    $('#cmp-change').addEventListener('change', (e) => {
      const on = e.target.checked;
      chg.setOpacity(on ? 1 : 0);
      before[1].setOpacity(on ? 0 : 0.85);
      after[1].setOpacity(on ? 0 : 0.85);
      // com a mudança ligada, aproxima da janela onde o lago mais recuou
      const opts = { animate: !REDUCED, duration: 1.2 };
      if (on) map.flyTo(S.meta.mudanca.foco_latlon, home + 2.25, opts);
      else map.flyTo(S.B.getCenter(), home, opts);
    });
  }
  function fillCompare() {
    const m = S.meta.mudanca, last = S.serie[S.serie.length - 1];
    $('#cmp-dried').textContent = fmt(m.secou_km2, 1);
    $('#cmp-new').textContent = fmt(m.agua_nova_km2, 1);
    $('#cmp-net').textContent = fmtS(last.delta_nisar_km2, 1);
    $('#cmp-l').textContent = '← ' + fmtDate(S.d0, true);
    $('#cmp-r').textContent = fmtDate(S.d1, true) + ' →';
  }

  /* ---------------- 5 · a prova (gráficos) ---------------- */
  const TT = $('#tooltip');
  function tip(e, html) {
    if (!html) { TT.classList.remove('on'); return; }
    TT.innerHTML = html;
    TT.classList.add('on');
    const pad = 14, r = TT.getBoundingClientRect();
    let x = e.clientX + pad, y = e.clientY + pad;
    if (x + r.width > innerWidth - 8) x = Math.max(8, e.clientX - r.width - pad);
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - pad;
    TT.style.left = x + 'px'; TT.style.top = y + 'px';
  }
  function tipHtml(s) {
    const row = (k, v, cls = '') => `<div class="row ${cls}"><span>${k}</span><b>${v}</b></div>`;
    return `<b>${fmtDate(s.data, true)}</b>` +
      row(t('tt.nisar'), `${fmt(s.area_nisar_km2, 1)} km²`) +
      row(t('tt.exp'), `${fmt(s.area_esperada_km2, 1)} km²`) +
      row(t('tt.diff'), `${fmtS(s.diferenca_km2, 1)} km² (${fmtS(s.diferenca_pct, 1)}%)`) +
      row(t('tt.level'), `${fmt(s.cota_ana_m, 2)} m`) +
      (s.suspeita_vento ? `<div class="f">▲ ${t('time.flag')}</div>` : '');
  }
  const niceTicks = (a, b, step) => { const out = []; for (let v = Math.ceil(a / step) * step; v <= b + 1e-9; v += step) out.push(+v.toFixed(6)); return out; };

  const CH = { drawn: { series: false, scatter: false } };
  function chartSeries(animate) {
    const fig = $('#chart-series'), host = fig.querySelector('.svg-host');
    const { serie } = S, M = S.meta.metricas, R = M.ruido_dp_km2;
    $('#leg-series').innerHTML =
      `<span><i class="k-dot"></i>${t('proof.c1.nisar')}</span><span><i class="k-hollow"></i>${t('proof.c1.wind')}</span>` +
      `<span><i class="k-line"></i>${t('proof.c1.exp')}</span><span><i class="k-band"></i>${t('proof.c1.band')}</span>`;
    const W = Math.max(300, host.clientWidth || 720), H = Math.round(Math.min(420, Math.max(300, W * 0.62))),
      m = { l: 52, r: 100, t: 14, b: 36 };
    const x0 = dt('2026-06-20'), x1 = dt('2026-10-20');
    const vals = serie.flatMap((s) => [s.area_nisar_km2, s.area_esperada_km2 - R, s.area_esperada_km2 + R]);
    const y0 = Math.floor((Math.min(...vals) - 10) / 25) * 25, y1 = Math.ceil((Math.max(...vals) + 10) / 25) * 25;
    const X = (d) => m.l + ((dt(d) - x0) / (x1 - x0)) * (W - m.l - m.r);
    const Y = (v) => m.t + ((y1 - v) / (y1 - y0)) * (H - m.t - m.b);
    host.innerHTML = '';
    const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': t('proof.c1.title') }, host);
    const g = svg('g', { class: 'grid' }, s);
    niceTicks(y0, y1, 25).forEach((v) => {
      svg('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) }, g);
      svg('text', { x: m.l - 8, y: Y(v) + 3.5, 'text-anchor': 'end' }, s).textContent = fmt(v, 0);
    });
    for (let mo = 6; mo <= 9; mo++) {
      const d = `2026-${String(mo + 1).padStart(2, '0')}-01`;
      svg('line', { x1: X(d), x2: X(d), y1: H - m.b, y2: H - m.b + 5, class: 'base' }, s);
      svg('text', { x: X(d) + 3, y: H - m.b + 18 }, s).textContent = S.dict[S.lang].month[mo].toUpperCase();
    }
    svg('line', { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: 'base' }, s);
    // faixa de ruído e linha esperada
    const top = serie.map((p) => `${X(p.data)},${Y(p.area_esperada_km2 + R)}`);
    const bot = serie.map((p) => `${X(p.data)},${Y(p.area_esperada_km2 - R)}`).reverse();
    const band = svg('path', { d: `M${top.join('L')}L${bot.join('L')}Z`, fill: 'rgba(170,177,173,.11)' }, s);
    const line = svg('path', { d: 'M' + serie.map((p) => `${X(p.data)},${Y(p.area_esperada_km2)}`).join('L'),
      fill: 'none', stroke: '#aab1ad', 'stroke-width': 2 }, s);
    const last = serie[serie.length - 1];
    // rótulos diretos da ponta direita: afastados verticalmente se ficarem a menos de 18 px
    let yN = Y(last.area_nisar_km2), yE = Y(last.area_esperada_km2);
    if (Math.abs(yN - yE) < 18) {
      const mid = (yN + yE) / 2, up = yN <= yE ? -1 : 1;
      yN = mid + up * 9; yE = mid - up * 9;
    }
    svg('text', { x: X(last.data) + 12, y: yE + 4.5, class: 'dlabel' }, s).textContent = t('proof.c1.explbl');
    // diferença: hastes finas entre esperado e NISAR
    const xh = svg('line', { y1: m.t, y2: H - m.b, class: 'xhair', opacity: 0 }, s);
    const pts = serie.map((p, i) => {
      const gg = svg('g', { class: 'pt' }, s);
      svg('line', { x1: X(p.data), x2: X(p.data), y1: Y(p.area_esperada_km2), y2: Y(p.area_nisar_km2),
        stroke: p.suspeita_vento ? '#c97a34' : '#7cf2c4', 'stroke-width': 1, opacity: 0.5 }, gg);
      svg('circle', { cx: X(p.data), cy: Y(p.area_nisar_km2), r: 5.5,
        fill: p.suspeita_vento ? '#0e1418' : '#7cf2c4', stroke: p.suspeita_vento ? '#c97a34' : '#0e1418', 'stroke-width': 2 }, gg);
      if (p.suspeita_vento) {
        const tx = svg('text', { x: X(p.data) + 9, y: Y(p.area_nisar_km2) + 4, class: 'dlabel flag' }, gg);
        tx.textContent = t('proof.c1.windlbl');
      }
      return gg;
    });
    svg('text', { x: X(last.data) + 12, y: yN + 4.5, class: 'dlabel' }, s).textContent = 'NISAR';
    // alvos de hover por data
    serie.forEach((p, i) => {
      const prevX = i ? (X(serie[i - 1].data) + X(p.data)) / 2 : m.l;
      const nextX = i < serie.length - 1 ? (X(serie[i + 1].data) + X(p.data)) / 2 : W - m.r;
      const hot = svg('rect', { x: prevX, y: m.t, width: nextX - prevX, height: H - m.t - m.b, class: 'hot' }, s);
      hot.addEventListener('mousemove', (e) => { xh.setAttribute('x1', X(p.data)); xh.setAttribute('x2', X(p.data)); xh.setAttribute('opacity', 1); tip(e, tipHtml(p)); });
      hot.addEventListener('mouseleave', (e) => { xh.setAttribute('opacity', 0); tip(e, null); });
      hot.addEventListener('click', (e) => tip(e, tipHtml(p)));
    });
    if (animate && !REDUCED) {
      const L0 = line.getTotalLength();
      line.style.strokeDasharray = L0; line.style.strokeDashoffset = L0;
      band.style.opacity = 0; band.style.transition = 'opacity .8s ease .9s';
      line.getBoundingClientRect();
      line.style.transition = 'stroke-dashoffset 1.3s cubic-bezier(.4,0,.2,1)';
      requestAnimationFrame(() => { line.style.strokeDashoffset = 0; band.style.opacity = 1; });
      pts.forEach((gg, i) => {
        gg.style.opacity = 0; gg.style.transform = 'translateY(6px)';
        setTimeout(() => { gg.style.opacity = 1; gg.style.transform = 'none'; }, 700 + i * 110);
      });
    }
  }

  function chartScatter(animate) {
    const fig = $('#chart-scatter'), host = fig.querySelector('.svg-host');
    const { serie, meta } = S, M = meta.metricas, curva = meta.curva_ana;
    $('#leg-scatter').innerHTML =
      `<span><i class="k-line"></i>${t('proof.c2.curve')}</span><span><i class="k-dash"></i>${t('proof.c2.fit')}</span>` +
      `<span><i class="k-hollow"></i>${t('time.flag')}</span>`;
    const W = Math.max(300, host.clientWidth || 480), H = Math.round(Math.min(420, Math.max(300, W * 0.8))),
      m = { l: 52, r: 18, t: 14, b: 44 };
    const cx0 = curva[0][0], cx1 = curva[curva.length - 1][0];
    const vals = serie.map((s) => s.area_nisar_km2).concat(curva.map((c) => c[1]));
    const y0 = Math.floor((Math.min(...vals) - 5) / 25) * 25, y1 = Math.ceil((Math.max(...vals) + 5) / 25) * 25;
    const X = (v) => m.l + ((v - cx0) / (cx1 - cx0)) * (W - m.l - m.r);
    const Y = (v) => m.t + ((y1 - v) / (y1 - y0)) * (H - m.t - m.b);
    host.innerHTML = '';
    const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': t('proof.c2.title') }, host);
    const g = svg('g', { class: 'grid' }, s);
    niceTicks(y0, y1, 25).forEach((v) => {
      svg('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) }, g);
      svg('text', { x: m.l - 8, y: Y(v) + 3.5, 'text-anchor': 'end' }, s).textContent = fmt(v, 0);
    });
    niceTicks(cx0, cx1, 0.25).forEach((v) => {
      svg('line', { x1: X(v), x2: X(v), y1: H - m.b, y2: H - m.b + 5, class: 'base' }, s);
      svg('text', { x: X(v), y: H - m.b + 18, 'text-anchor': 'middle' }, s).textContent = fmt(v, 2);
    });
    svg('text', { x: W - m.r, y: H - 4, 'text-anchor': 'end' }, s).textContent = `${t('tt.level')} (m)`;
    svg('line', { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: 'base' }, s);
    const cl = svg('path', { d: 'M' + curva.map((c) => `${X(c[0])},${Y(c[1])}`).join('L'), fill: 'none', stroke: '#aab1ad', 'stroke-width': 2 }, s);
    const calmC = S.calm.map((p) => p.cota_ana_m), a = Math.min(...calmC) - 0.05, b = Math.max(...calmC) + 0.05;
    // reta de mínimos quadrados nas datas calmas (a inclinação exibida vem de meta.json)
    const mc = calmC.reduce((u, v) => u + v, 0) / calmC.length;
    const ma = S.calm.reduce((u, p) => u + p.area_nisar_km2, 0) / S.calm.length;
    const sl = S.calm.reduce((u, p) => u + (p.cota_ana_m - mc) * (p.area_nisar_km2 - ma), 0) /
      S.calm.reduce((u, p) => u + (p.cota_ana_m - mc) ** 2, 0);
    const f = (c) => ma + sl * (c - mc);
    const fl = svg('line', { x1: X(a), y1: Y(f(a)), x2: X(b), y2: Y(f(b)), stroke: '#7cf2c4', 'stroke-width': 2, 'stroke-dasharray': '6 5' }, s);
    const pts = serie.map((p) => {
      const c = svg('circle', { cx: X(p.cota_ana_m), cy: Y(p.area_nisar_km2), r: 5.5, class: 'pt',
        fill: p.suspeita_vento ? '#0e1418' : '#7cf2c4', stroke: p.suspeita_vento ? '#c97a34' : '#0e1418', 'stroke-width': 2 }, s);
      const hot = svg('circle', { cx: X(p.cota_ana_m), cy: Y(p.area_nisar_km2), r: 14, class: 'hot' }, s);
      hot.addEventListener('mousemove', (e) => tip(e, tipHtml(p)));
      hot.addEventListener('mouseleave', (e) => tip(e, null));
      hot.addEventListener('click', (e) => tip(e, tipHtml(p)));
      return c;
    });
    if (animate && !REDUCED) {
      const L0 = cl.getTotalLength();
      cl.style.strokeDasharray = L0; cl.style.strokeDashoffset = L0;
      fl.style.opacity = 0;
      cl.getBoundingClientRect();
      cl.style.transition = 'stroke-dashoffset 1.1s ease';
      fl.style.transition = 'opacity .6s ease 1.6s';
      requestAnimationFrame(() => { cl.style.strokeDashoffset = 0; fl.style.opacity = 1; });
      pts.forEach((c, i) => { c.style.opacity = 0; setTimeout(() => { c.style.opacity = 1; }, 500 + i * 110); });
    }
  }

  function buildTable() {
    const cols = ['tt.date', 'tt.level', 'tt.storage', 'tt.exp', 'tt.nisar', 'tt.diff', 'tt.flag'];
    const rows = S.serie.map((s) => `<tr class="${s.suspeita_vento ? 'flag' : ''}"><td>${fmtDate(s.data, true)}</td>` +
      `<td>${fmt(s.cota_ana_m, 2)} m</td><td>${fmt(s.volume_util_pct, 2)}%</td><td>${fmt(s.area_esperada_km2, 1)}</td>` +
      `<td>${fmt(s.area_nisar_km2, 1)}</td><td>${fmtS(s.diferenca_km2, 1)}</td><td>${s.suspeita_vento ? t('time.flag') : ''}</td></tr>`).join('');
    $('#table-wrap').innerHTML = `<table><thead><tr>${cols.map((c) => `<th>${t(c)}${c === 'tt.exp' || c === 'tt.nisar' || c === 'tt.diff' ? ' (km²)' : ''}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table>`;
  }

  /* ---------------- 6 · polarizações ---------------- */
  function initPol() {
    const map = makeMap($('#map-pol'), { cover: true });
    const L3 = { hh: overlay(map, url.hh(S.d0)), hv: overlay(map, url.hv(), 0), cor: overlay(map, url.cor(), 0) };
    outline(map);
    S.polSet = (k) => Object.entries(L3).forEach(([n, l]) => l.setOpacity(n === k ? 1 : 0));
    S.polSet(S.pol || 'hh');
  }
  function setPol(k) {
    S.pol = k;
    $$('#pol-seg button').forEach((b) => b.setAttribute('aria-selected', b.dataset.pol === k));
    $$('.pol-text').forEach((p) => p.classList.toggle('on', p.dataset.polText === k));
    const lbl = { hh: 'HH', hv: 'HV', cor: 'HH · HV · HH−HV' }[k];
    $('#pol-cap').textContent = `NISAR · L-BAND · ${lbl} · ${fmtDate(S.d0, true).toUpperCase()} · ${S.meta.pixel_processado_m} m`;
    if (S.polSet) S.polSet(k);
  }

  /* ---------------- 7 · régua de cota ---------------- */
  function drawGauge(animate) {
    const host = $('#gauge .svg-host');
    const { serie, meta } = S, maxN = meta.cota_max_normal_m;
    const W = Math.max(300, host.clientWidth || 520), H = Math.round(Math.min(460, Math.max(340, W * 0.85))),
      m = { l: 44, r: 12, t: 22, b: 36 };
    const v0 = Math.floor(Math.min(...serie.map((s) => s.cota_ana_m)) - 2), v1 = Math.ceil(maxN + 1);
    const x0 = dt('2026-06-20'), x1 = dt('2026-10-20');
    const X = (d) => m.l + ((dt(d) - x0) / (x1 - x0)) * (W - m.l - m.r);
    const Y = (v) => m.t + ((v1 - v) / (v1 - v0)) * (H - m.t - m.b);
    host.innerHTML = '';
    const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': t('hum.g.title') }, host);
    const g = svg('g', { class: 'grid' }, s);
    for (let v = v0; v <= v1; v++) {
      svg('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) }, g);
      svg('text', { x: m.l - 8, y: Y(v) + 3.5, 'text-anchor': 'end' }, s).textContent = fmt(v, 0);
    }
    for (let mo = 6; mo <= 9; mo++) {
      const d = `2026-${String(mo + 1).padStart(2, '0')}-01`;
      svg('text', { x: X(d) + 3, y: H - m.b + 18 }, s).textContent = S.dict[S.lang].month[mo].toUpperCase();
      svg('line', { x1: X(d), x2: X(d), y1: H - m.b, y2: H - m.b + 5, class: 'base' }, s);
    }
    svg('line', { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: 'base' }, s);
    // faixa de margem exposta: entre a cota e o nível máximo normal
    const pts = serie.map((p) => `${X(p.data)},${Y(p.cota_ana_m)}`);
    const xa = X(serie[0].data), xb = X(serie[serie.length - 1].data);
    svg('path', { d: `M${pts.join('L')}L${xb},${Y(maxN)}L${xa},${Y(maxN)}Z`, fill: 'rgba(201,122,52,.16)' }, s);
    svg('path', { d: `M${pts.join('L')}L${xb},${Y(v0)}L${xa},${Y(v0)}Z`, fill: 'rgba(59,130,214,.22)' }, s);
    svg('line', { x1: m.l, x2: W - m.r, y1: Y(maxN), y2: Y(maxN), stroke: '#e8e3d7', 'stroke-width': 1, 'stroke-dasharray': '3 3' }, s);
    svg('text', { x: m.l + 6, y: Y(maxN) - 7, class: 'dlabel' }, s).textContent = t('hum.g.max');
    const ln = svg('path', { d: 'M' + pts.join('L'), fill: 'none', stroke: '#3b82d6', 'stroke-width': 2 }, s);
    serie.forEach((p) => {
      svg('circle', { cx: X(p.data), cy: Y(p.cota_ana_m), r: 4, fill: '#3b82d6', stroke: '#0e1418', 'stroke-width': 2 }, s);
      const hot = svg('circle', { cx: X(p.data), cy: Y(p.cota_ana_m), r: 12, class: 'hot' }, s);
      hot.addEventListener('mousemove', (e) => tip(e, tipHtml(p) + `<div class="row"><span>${t('tt.storage')}</span><b>${fmt(p.volume_util_pct, 1)}%</b></div>`));
      hot.addEventListener('mouseleave', (e) => tip(e, null));
    });
    const midY = (Y(maxN) + Y(S.meta.metricas.cota_max_m)) / 2;
    svg('text', { x: X('2026-08-20'), y: midY + 4, 'text-anchor': 'middle', class: 'dlabel', fill: '#d99a5a' }, s).textContent =
      `${S.V.gapmin}–${S.V.gapmax} m`;
    svg('text', { x: X('2026-08-20'), y: Y(S.meta.metricas.cota_min_m) + 26, 'text-anchor': 'middle', class: 'dlabel' }, s).textContent = t('hum.g.season');
    if (animate && !REDUCED) {
      const L0 = ln.getTotalLength();
      ln.style.strokeDasharray = L0; ln.style.strokeDashoffset = L0;
      ln.getBoundingClientRect();
      ln.style.transition = 'stroke-dashoffset 1.2s ease';
      requestAnimationFrame(() => { ln.style.strokeDashoffset = 0; });
    }
  }

  /* ---------------- 10 · fontes ---------------- */
  function fillConfig() {
    const C = window.TP_CONFIG || {};
    const team = (C.team || []).filter(Boolean);
    const dd = $('#team');
    dd.textContent = team.join(' · ');
    dd.classList.toggle('placeholder-team', !team.length || team.some((n) => n.startsWith('[')));
    const repo = C.github || '';
    $('#repo-link').href = repo || '#';
    $('#repo-note').hidden = Boolean(repo) && !/github\.com\/TEAM\//.test(repo);
  }

  function fillSources() {
    $('#scenes').innerHTML = S.meta.cenas.map((c) => `<li><span>${c.data}</span>${c.granuleId}</li>`).join('');
    $('#src-ana').href = S.meta.fontes.ana_boletins;
    $('#src-cav').href = S.meta.fontes.ana_cav;
    $('#code-limiar').textContent = String(S.meta.metodo.limiar_db);
  }

  /* ---------------- modo explorar ---------------- */
  const EX = { base: 'hh', i: 0, map: null };
  function initExplore() {
    const map = makeMap($('#map-ex'), { wheel: true, creditHost: $('#ex-credit') });
    EX.map = map;
    EX.hh = S.serie.map((s, i) => overlay(map, url.hh(s.data), i === 0 ? 1 : 0));
    EX.hv = overlay(map, url.hv(), 0);
    EX.cor = overlay(map, url.cor(), 0);
    EX.agua = S.serie.map((s, i) => overlay(map, url.agua(s.data), 0));
    EX.chg = overlay(map, 'data/mudanca.png', 0);
    map.createPane('lines').style.zIndex = 460;
    EX.out = outline(map, { renderer: L.canvas({ pane: 'lines' }) });
    damLabel(map);
    attachProbe(map, $('#probe-ex'));
    $$('#ex-base button').forEach((b) => b.addEventListener('click', () => { EX.base = b.dataset.base; if (EX.base !== 'hh') EX.i = 0; exUpdate(); }));
    ['#ex-mask', '#ex-change', '#ex-outline', '#ex-opacity'].forEach((s) => $(s).addEventListener('input', exUpdate));
    exDates();
    exUpdate();
  }
  function exDates() {
    $('#ex-dates').innerHTML = S.serie.map((s, i) =>
      `<button type="button" data-i="${i}" class="${s.suspeita_vento ? 'flag' : ''}" title="${s.suspeita_vento ? t('time.flag') : ''}">${fmtDate(s.data)}</button>`).join('');
    $$('#ex-dates button').forEach((b) => b.addEventListener('click', () => { EX.i = +b.dataset.i; exUpdate(); }));
    if (EX.map) exUpdate();
  }
  function exUpdate() {
    if (!EX.map) return;
    const op = $('#ex-opacity').value / 100;
    EX.hh.forEach((l, i) => l.setOpacity(EX.base === 'hh' && i === EX.i ? 1 : 0));
    EX.hv.setOpacity(EX.base === 'hv' ? 1 : 0);
    EX.cor.setOpacity(EX.base === 'cor' ? 1 : 0);
    EX.agua.forEach((l, i) => l.setOpacity($('#ex-mask').checked && i === EX.i ? op : 0));
    EX.chg.setOpacity($('#ex-change').checked ? op : 0);
    if ($('#ex-outline').checked) EX.out.addTo(EX.map); else EX.out.remove();
    $$('#ex-base button').forEach((b) => b.setAttribute('aria-pressed', b.dataset.base === EX.base));
    $$('#ex-dates button').forEach((b, i) => {
      b.setAttribute('aria-pressed', i === EX.i);
      b.disabled = EX.base !== 'hh' && i !== 0;
    });
  }
  function openExplore() {
    play(false);
    const ex = $('#explore');
    ex.hidden = false;
    document.body.style.overflow = 'hidden';
    if (!EX.map) initExplore(); else EX.map.invalidateSize();
    $('#close-explore').focus();
  }
  function closeExplore() {
    $('#explore').hidden = true;
    document.body.style.overflow = '';
    $('#open-explore').focus();
  }

  /* ---------------- partida ---------------- */
  async function boot() {
    try {
      await load();
    } catch (err) {
      document.body.insertAdjacentHTML('afterbegin', `<p style="padding:80px 24px;color:#d99a5a;font:14px monospace">Could not load data (${err.message}). Serve this folder over HTTP: python -m http.server</p>`);
      throw err;
    }
    const q = new URLSearchParams(location.search).get('lang');
    const lang = q === 'pt' || q === 'en' ? q : store.get('tp-lang') || 'en';
    S.onLang.push(() => {
      drawDiagram(); fillCompare(); setPol(S.pol || 'hh'); exDates();
      if (TL.layers.length) setDate(TL.i, true); else drawRuler();
      $('#tl-play span').textContent = t(TL.playing ? 'time.pause' : 'time.play');
      if (CH.drawn.series) chartSeries(false);
      if (CH.drawn.scatter) chartScatter(false);
      if (CH.drawn.gauge) drawGauge(false);
      if (!$('#table-wrap').hidden) buildTable();
      $('#toggle-table').textContent = t($('#table-wrap').hidden ? 'proof.table' : 'proof.table.hide');
    });
    applyLang(lang);
    fillSources();
    fillConfig();

    $('#lang').addEventListener('click', () => {
      const l = S.lang === 'en' ? 'pt' : 'en';
      store.set('tp-lang', l);
      applyLang(l);
    });

    initHero();
    const lazy = { see: initSee, time: initTimeline, cmp: initCompare, pol: initPol };
    $$('[data-lazy]').forEach((el) => once(el, lazy[el.dataset.lazy], '500px', 0));

    $$('.reveal').forEach((el) => once(el, () => el.classList.add('in'), '0px', 0.12));
    once($('#chart-series'), () => { CH.drawn.series = true; chartSeries(true); }, '0px', 0.35);
    once($('#chart-scatter'), () => { CH.drawn.scatter = true; chartScatter(true); }, '0px', 0.35);
    once($('#gauge'), () => { CH.drawn.gauge = true; drawGauge(true); }, '0px', 0.3);

    $('#tl-play').addEventListener('click', () => play(!TL.playing));
    $$('#pol-seg button').forEach((b) => b.addEventListener('click', () => setPol(b.dataset.pol)));
    $('#toggle-table').addEventListener('click', () => {
      const w = $('#table-wrap'), show = w.hidden;
      if (show) buildTable();
      w.hidden = !show;
      $('#toggle-table').setAttribute('aria-expanded', show);
      $('#toggle-table').textContent = t(show ? 'proof.table.hide' : 'proof.table');
    });
    $('#open-explore').addEventListener('click', openExplore);
    $('#close-explore').addEventListener('click', closeExplore);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#explore').hidden) closeExplore(); });
    document.addEventListener('scroll', () => TT.classList.remove('on'), { passive: true });

    let rz;
    addEventListener('resize', () => {
      clearTimeout(rz);
      rz = setTimeout(() => {
        drawRuler(); drawDiagram();
        if (CH.drawn.series) chartSeries(false);
        if (CH.drawn.scatter) chartScatter(false);
        if (CH.drawn.gauge) drawGauge(false);
      }, 150);
    });
  }

  boot();
})();
