/* Arara · idioma do site (globo e estudo; furnas/ e uruguai/ usam a mesma chave 'tp-lang').
   Inglês sempre por padrão, independente do navegador. Só vira português com ?lang=pt ou com o clique
   em PT, e a escolha fica em localStorage (com try/catch: sem armazenamento, vale só a URL).
   Também traduz para o inglês as frases fixas que vêm prontas, em português, nos resultados das análises.
   O que não estiver na tabela continua em português. */
(function () {
  'use strict';
  var KEY = 'tp-lang';
  var stored = null;
  try { stored = localStorage.getItem(KEY); } catch (e) { /* sem armazenamento */ }
  var q = new URLSearchParams(location.search).get('lang');
  var lang = q === 'pt' || q === 'en' ? q : (stored === 'pt' ? 'pt' : 'en');
  if (q === 'pt' || q === 'en') { try { localStorage.setItem(KEY, q); } catch (e) { /* ok */ } }
  var en = lang === 'en';
  document.documentElement.lang = en ? 'en' : 'pt-BR';

  /* ---------- frases fixas da pipeline (PT exato -> EN) ---------- */
  var EXATAS = {
    'cena completa, sem vento': 'full scene, no wind',
    'cena completa, sem vento, coerente com o Sentinel-2': 'full scene, no wind, consistent with Sentinel-2',
    'vento: a água desta passagem pode estar subestimada': 'wind: water on this pass may be underestimated',
    'o Sentinel-2 vê uma área de água diferente nesta data': 'Sentinel-2 sees a different water area on this date',
    'análise experimental': 'experimental analysis',
    'sem modelo de terreno (HAND): cheia sem corte de áreas altas': 'no terrain model (HAND): flood water not cut on high ground',
    'o radar não separou água de terra nesta área': 'the radar did not separate water from land in this area',
    'referência = passagem mais seca do período: uma cheia que durou o período inteiro não aparece':
      'reference = driest pass of the period: a flood that lasted the whole period does not show up',
    'vegetação alagada é possível, não confirmada: solo encharcado e mudança de cultura também clareiam o HH':
      'flooded vegetation is possible, not confirmed: wet soil and crop changes also brighten HH',
    'população do município inteiro (Censo 2022, IBGE), não o número de pessoas atingidas':
      'population of the whole municipality (2022 Census, IBGE), not the number of people affected',
    'população indisponível agora (API do IBGE)': 'population unavailable right now (IBGE API)',
    'cruzamento com municípios desligado no pedido': 'municipality cross-check turned off for this request',
    'área fora do Brasil: sem malha municipal do IBGE': 'area outside Brazil: no IBGE municipal boundaries',
    "desenhe uma área menor em volta do corpo d'água, com margem de terra dos dois lados, ou escolha outra geometria (trilha/frame) no catálogo":
      'use a smaller area around the water body, with land on both banks, or another geometry (track/frame) from the catalog',
    'desenhe uma área com um rio ou lago largo e terra dos dois lados': 'use an area with a wide river or lake and land on both banks',
    'GPM IMERG Late Run diário V07 (GPM_3IMERGDL), NASA GES DISC': 'GPM IMERG Late Run daily V07 (GPM_3IMERGDL), NASA GES DISC',
    'média das células de 0,1° que cobrem a área': 'mean of the 0.1° cells covering the area',
    'IMERG Late é estimativa por satélite (sem ajuste de pluviômetro do produto Final)':
      'IMERG Late is a satellite estimate (without the rain-gauge adjustment of the Final product)',
    'célula de ~11 km: chuva local forte pode ficar diluída': '~11 km cells: heavy local rain may be diluted',
    'chuva desligada no pedido': 'rainfall turned off for this request',
    'o GES DISC recusou o acesso: autorize o aplicativo "NASA GESDISC DATA ARCHIVE" em urs.earthdata.nasa.gov (Applications > Authorized Apps) na conta Earthdata do servidor':
      'GES DISC refused access: the server\'s Earthdata account must authorize the "NASA GESDISC DATA ARCHIVE" application at urs.earthdata.nasa.gov (Applications > Authorized Apps)',
    'o servidor de chuva do GES DISC (OPeNDAP, gpm1.gesdisc.eosdis.nasa.gov) não responde agora; a próxima atualização tenta de novo':
      'the GES DISC rainfall server (OPeNDAP, gpm1.gesdisc.eosdis.nasa.gov) is not responding right now; the next update will try again',
    'Sentinel-2 indisponível (falha de rede ou do serviço)': 'Sentinel-2 unavailable (network or service failure)',
    'validação óptica desligada no pedido': 'optical validation turned off for this request',
    'sem pixels comparáveis': 'no comparable pixels',
    'datas do óptico diferem do radar em até 7 dias': 'optical dates differ from the radar by up to 7 days',
    'o radar vê água sob nuvem; o óptico não': 'the radar sees water under clouds; optical does not',
    'vegetação alagada: o radar em L pode não ver como água aberta o que o MNDWI vê, e vice-versa':
      'flooded vegetation: L-band radar may not see as open water what MNDWI sees, and vice versa',
    'projeção diferente das demais cenas': 'projection differs from the other scenes',
    'não executada': 'not run',
    'datas com suspeita de vento ficam fora do ajuste': 'dates with suspected wind are left out of the fit',
    'A última data tem suspeita de vento: a área pode estar subestimada.': 'The last date has suspected wind: the area may be underestimated.',
    'Experimental: continuação estatística da série, sem chuva nem operação de reservatório. A faixa é p10–p90 dos erros que a mesma regra teve nas passagens anteriores.':
      'Experimental: statistical continuation of the series, without rainfall or reservoir operation. The band is p10–p90 of the errors the same rule had on earlier passes.',
    'poucas datas anteriores sem suspeita de vento': 'too few earlier dates without suspected wind',
    'persistência amortecida': 'damped persistence',
    'Sem validação óptica.': 'No optical validation.',
    'sem validação óptica': 'no optical validation',
  };
  /* frases com números (PT -> EN) */
  var MODELOS = [
    [/^só (\d+)% da área com dado válido$/, 'only $1% of the area has valid data'],
    [/^só (\d+)% da área com dado válido \(mínimo (\d+)%\)$/, 'only $1% of the area has valid data (minimum $2%)'],
    [/^o radar não achou margem água\/terra nítida \(só (\d+) blocos de margem, mínimo (\d+)\): não há lago ou rio largo o bastante na área para calibrar o limiar$/,
      'the radar found no sharp water/land shoreline (only $1 shoreline blocks, minimum $2): there is no lake or river wide enough in the area to calibrate the threshold'],
    [/^o limiar água\/terra saiu em (-?[\d.]+) dB, fora da faixa da água calma \((-?\d+) a (-?\d+) dB\): o que ficou escuro é terra lisa, não água$/,
      'the water/land threshold came out at $1 dB, outside the calm-water range ($2 to $3 dB): what looks dark is smooth land, not water'],
    [/^em (\d+) de (\d+) datas a água ficou fora de ([\d.,]+%) a ([\d.,]+%) da área$/, 'on $1 of $2 dates the water was outside $3 to $4 of the area'],
    [/^o Sentinel-2 não vê água onde o radar vê \(em (\d+) de (\d+) datas comparadas\): o radar está contando terra como água$/,
      'Sentinel-2 sees no water where the radar does (on $1 of $2 compared dates): the radar is counting land as water'],
    [/^o radar diverge do Sentinel-2 em (\d+) de (\d+) datas sem vento \(IoU médio ([\d.]+)\)$/, 'the radar disagrees with Sentinel-2 on $1 of $2 windless dates (mean IoU $3)'],
    [/^o radar diverge do Sentinel-2 em (\d+) de (\d+) datas sem vento$/, 'the radar disagrees with Sentinel-2 on $1 of $2 windless dates'],
    [/^menos de (\d+) passagens: vegetação alagada não avaliada$/, 'fewer than $1 passes: flooded vegetation not assessed'],
    [/^HAND desligado no pedido: sem corte por terreno, terra lisa em áreas altas pode aparecer como água$/,
      'HAND turned off for this request: no terrain cut, smooth land on high ground may show up as water'],
    [/^HAND indisponível \((\w+)\): sem corte por terreno, terra lisa em áreas altas pode aparecer como água$/,
      'HAND unavailable ($1): no terrain cut, smooth land on high ground may show up as water'],
    [/^HAND indisponível \((\w+)\); o modo cheia rodou sem corte por terreno$/, 'HAND unavailable ($1); flood mode ran without a terrain cut'],
    [/^GPM IMERG indisponível agora \((\w+)\)$/, 'GPM IMERG unavailable right now ($1)'],
    [/^malhas do IBGE indisponíveis \((\w+)\)$/, 'IBGE boundaries unavailable ($1)'],
    [/^nenhuma cena Sentinel-2 a ±(\d+) dias de (\S+)$/, 'no Sentinel-2 scene within ±$1 days of $2'],
    [/^Sentinel-2 com nuvem: a melhor cena a ±(\d+) dias de (\S+) \((\S+)\) tem só (\d+)% da área sem nuvem$/,
      'Sentinel-2 cloudy: the best scene within ±$1 days of $2 ($3) has only $4% of the area cloud-free'],
    [/^Sentinel-2 com nuvem: (.*)$/, 'Sentinel-2 cloudy: $1'],
    [/^tendência precisa de (\d+) datas sem suspeita de vento \(há (\d+)\)$/, 'trend needs $1 dates without suspected wind (there are $2)'],
    [/^alerta precisa de (\d+) datas$/, 'the alert needs $1 dates'],
    [/^frequência de água precisa de (\d+) datas sem suspeita de vento \(há (\d+)\)$/, 'water frequency needs $1 dates without suspected wind (there are $2)'],
    [/^projeção precisa de pelo menos (\d+) datas sem suspeita de vento \(há (\d+)\)$/, 'the projection needs at least $1 dates without suspected wind (there are $2)'],
    [/^análise experimental: sem projeção \((.*)\)$/, 'experimental analysis: no projection ($1)'],
  ];
  /* frase da pipeline em inglês; o que não está na tabela fica como veio (português) */
  function dados(s) {
    if (!en || s == null) return s;
    var t = String(s).trim();
    if (Object.prototype.hasOwnProperty.call(EXATAS, t)) return EXATAS[t];
    for (var i = 0; i < MODELOS.length; i++) if (MODELOS[i][0].test(t)) return t.replace(MODELOS[i][0], MODELOS[i][1]);
    return s;
  }
  /* troca o idioma: guarda e recarrega com ?lang= (os parâmetros extras, como ?regiao=, são mantidos) */
  function setLang(l, extra) {
    try { localStorage.setItem(KEY, l); } catch (e) { /* ok */ }
    var p = new URLSearchParams(location.search);
    p.set('lang', l);
    Object.keys(extra || {}).forEach(function (k) { if (extra[k] == null) p.delete(k); else p.set(k, extra[k]); });
    location.replace(location.pathname + '?' + p.toString() + location.hash);
  }
  /* link para outra página do Arara levando o idioma */
  function comLang(href) {
    var u = new URL(href, location.href);
    u.searchParams.set('lang', lang);
    return u.origin === location.origin ? u.pathname + u.search + u.hash : u.href;
  }
  /* textos fixos do HTML: data-en (innerHTML), data-en-placeholder, data-en-aria, data-en-title */
  function aplicarHtml(raiz) {
    if (!en) return;
    var r = raiz || document;
    r.querySelectorAll('[data-en]').forEach(function (el) { el.innerHTML = el.getAttribute('data-en'); });
    r.querySelectorAll('[data-en-placeholder]').forEach(function (el) { el.setAttribute('placeholder', el.getAttribute('data-en-placeholder')); });
    r.querySelectorAll('[data-en-aria]').forEach(function (el) { el.setAttribute('aria-label', el.getAttribute('data-en-aria')); });
    r.querySelectorAll('[data-en-title]').forEach(function (el) { el.setAttribute('title', el.getAttribute('data-en-title')); });
  }
  /* seletor EN | PT */
  function botao(el, extra) {
    if (!el) return;
    el.innerHTML = '<button type="button" data-l="en" aria-pressed="' + en + '">EN</button><button type="button" data-l="pt" aria-pressed="' + !en + '">PT</button>';
    el.setAttribute('aria-label', en ? 'Language' : 'Idioma');
    el.querySelectorAll('button').forEach(function (b) {
      b.addEventListener('click', function () { if (b.getAttribute('data-l') !== lang) setLang(b.getAttribute('data-l'), typeof extra === 'function' ? extra() : extra); });
    });
  }
  var MES_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  window.ARARA_I18N = {
    lang: lang, en: en, locale: en ? 'en-US' : 'pt-BR',
    tr: function (pt, eng) { return en ? eng : pt; },
    dados: dados, setLang: setLang, comLang: comLang, aplicarHtml: aplicarHtml, botao: botao,
    /* AAAA-MM-DD -> "3 Oct 2026" | "03/10/2026" e curto "3 Oct" | "03/10" */
    data: function (s) { var p = String(s).slice(0, 10).split('-'); return en ? (+p[2]) + ' ' + MES_EN[+p[1] - 1] + ' ' + p[0] : p[2] + '/' + p[1] + '/' + p[0]; },
    dataCurta: function (s) { var p = String(s).slice(0, 10).split('-'); return en ? (+p[2]) + ' ' + MES_EN[+p[1] - 1] : p[2] + '/' + p[1]; },
  };
})();
