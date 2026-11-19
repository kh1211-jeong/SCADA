// 수배전 감시·진단 화면
const $ = (s) => document.querySelector(s);
const NS = 'http://www.w3.org/2000/svg';
let META = null, SYS = '3F11', ST = null, SEL = null, PTAB = 'eq', PENDING = null, SPARK = null;
let view = { x: 0, y: 0, k: 1 }, prevOn = {};
const SWT = new Set(['GCB', 'MAIN', 'VCB_K', 'VCB_Q', 'VCB_FEEDER', 'VCB_STR', 'VCB_CAP', 'VCS_CAP', 'ACB', 'ACB_MAIN_EMG', 'XCB', 'TIE', 'DIS']);
const LV220 = new Set(['ACB', 'ACB_MAIN_EMG', 'XCB', 'STR', 'RETURN']);
const QK = { POWER: ['유효전력', 'kW'], VOLTAGE: ['전압', ''], CURRENT: ['전류', 'A'], PF: ['역률', '%'], TEMP: ['온도', '℃'], TEMP_C: ['철심온도', '℃'],
  TEMP_W: ['권선온도', '℃'], LOAD: ['부하율', '%'], TAP: ['탭', ''] };

const el = (tag, attrs = {}, parent) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (parent) parent.appendChild(e); return e; };
const short = (id) => id.replace(/^(VCB|ACB|LTR|BTR|GCB|MAIN|TIE|DIS|XCB|VCS|STR|SUBSTATION_RETURN)_/, '');
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const fmt = (v, u = '') => v === null || v === undefined ? '–' : `${Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1)}${u}`;
async function api(path, body) {
  const r = await fetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
  if (r.status === 401) { location.href = '/login'; return {}; }
  return r.json();
}
const nodeById = () => Object.fromEntries(META.diagrams[SYS].nodes.map((n) => [n.id, n]));
function vclass(n) {   // 전압 등급
  if (n.etype === 'BUS' || n.etype === 'GCB') return 'v154';
  if (n.etype === 'LTR' || LV220.has(n.etype) || ((n.etype === 'TIE' || n.etype === 'DIS') && n.level === 8)) return 'v220';
  return 'v66';
}

// ------------------------------------------------------------------ 계통도
function drawDiagram() {
  const svg = $('#sld'); svg.innerHTML = '';
  const d = META.diagrams[SYS], pos = nodeById();
  const root = el('g', { id: 'root' }, svg);
  const gE = el('g', {}, root), gH = el('g', {}, root), gN = el('g', {}, root);
  for (const e of d.edges) {
    const a = pos[e.src], b = pos[e.dst]; if (!a || !b) continue;
    const tree = e.etype === 'power' || e.etype === 'return';
    let p;
    if (tree) { const my = a.y + (b.y - a.y) * 0.55; p = `M${a.x},${a.y} L${a.x},${my} L${b.x},${my} L${b.x},${b.y}`; }
    else if (Math.abs(a.y - b.y) < 1) p = `M${a.x},${a.y} L${b.x},${b.y}`;
    else p = `M${a.x},${a.y} L${a.x},${b.y} L${b.x},${b.y}`;
    el('path', { d: p, class: 'edge' + (tree ? '' : ' tie'), 'data-a': e.src, 'data-b': e.dst, 'data-v': vclass(b) }, gE);
  }
  for (const n of d.nodes) {
    const g = el('g', { class: 'node', transform: `translate(${n.x},${n.y})`, 'data-id': n.id }, gN);
    el('circle', { r: 26, class: 'halo', 'data-halo': n.id, visibility: 'hidden', transform: `translate(${n.x},${n.y})` }, gH);
    el('rect', { x: -24, y: -24, width: 48, height: 48, rx: 6, class: 'hit' }, g);
    if (n.etype === 'BUS') {
      el('rect', { x: -80, y: -5, width: 160, height: 10, rx: 3, class: 'bus' }, g);
      el('text', { y: -13, class: 'nm' }, g).textContent = '154kV 모선';
    } else if (n.etype === 'BTR' || n.etype === 'LTR') {
      el('circle', { cy: -6, r: 9, class: 'xf', 'data-xf': 1 }, g); el('circle', { cy: 6, r: 9, class: 'xf', 'data-xf': 1 }, g);
      el('text', { x: 0, y: -20, class: 'nm' }, g).textContent = short(n.id);
    } else if (n.etype === 'STR') {
      el('circle', { r: 11, class: 'xf', 'data-xf': 1 }, g); el('text', { y: 4 }, g).textContent = 'PV';
    } else if (n.etype === 'RETURN') {
      el('path', { d: 'M-8,-6 L8,-6 L0,8 Z', fill: '#777777' }, g);
    } else if (SWT.has(n.etype)) {
      el('rect', { x: -11, y: -11, width: 22, height: 22, rx: 3, class: 'swbox' }, g);
      el('text', { x: 0, y: -16, class: 'nm' }, g).textContent = short(n.id);
      if (n.ext) {   // 다른 계통으로 이어지는 연계: 바깥쪽 화살표 + 상대 계통 이름
        const s = n.side;
        el('path', { d: `M${11 * s},0 L${34 * s},0 M${28 * s},-5 L${34 * s},0 L${28 * s},5`, class: 'extln' }, g);
        el('text', { x: 38 * s, y: 4, class: 'ext', 'text-anchor': s > 0 ? 'start' : 'end' }, g).textContent = n.ext + ' 계통';
      }
    }
    el('text', { y: 26, class: 'val', 'data-v1': n.id }, g);
    el('text', { y: 38, class: 'val', 'data-v2': n.id }, g);
    g.addEventListener('click', (ev) => { ev.stopPropagation(); select(n.id); });
  }
  el('rect', { id: 'selring', class: 'selring', x: -28, y: -28, width: 56, height: 56, rx: 8, visibility: 'hidden' }, root);
  fit(); if (ST) paint();
}
function fit() {
  const d = META.diagrams[SYS], wrap = $('#wrap');
  const xs = d.nodes.map((n) => n.x), ys = d.nodes.map((n) => n.y);
  const w = Math.max(...xs) + 150, h = Math.max(...ys) + 60;
  const k = Math.min(wrap.clientWidth / w, (wrap.clientHeight - 30) / h, 1.7);
  view = { k, x: (wrap.clientWidth - w * k) / 2, y: 8 }; applyView();
}
function applyView() { const r = $('#root'); if (r) r.setAttribute('transform', `translate(${view.x},${view.y}) scale(${view.k})`); }
function center(id) {
  const n = nodeById()[id]; if (!n) return; const wrap = $('#wrap');
  view.k = Math.max(view.k, 1.25); view.x = wrap.clientWidth / 2 - n.x * view.k; view.y = wrap.clientHeight / 2 - n.y * view.k; applyView();
}

function paint() {
  const vals = ST.values, tripped = new Set(ST.ops.filter((o) => o.action.startsWith('트립')).map((o) => o.node));
  for (const n of META.diagrams[SYS].nodes) {
    const v = vals[n.id] || {}, g = document.querySelector(`.node[data-id="${n.id}"]`); if (!g) continue;
    const box = g.querySelector('.swbox');
    if (box) {
      const closed = v.closed === undefined ? true : v.closed === 1, tie = n.etype === 'TIE' || n.etype === 'XCB';
      box.setAttribute('class', 'swbox ' + (closed ? 'closed' : tripped.has(n.id) ? 'trip' : tie ? 'tieopen' : 'open'));
    }
    g.querySelectorAll('[data-xf]').forEach((c) => c.setAttribute('class', 'xf ' + (v.on ? vclass(n) : '')));
    let a = '', b = '', tv = false;
    if (v.POWER !== undefined) { a = fmt(v.POWER, 'kW'); b = `${fmt(v.CURRENT, 'A')} ${fmt(v.VOLTAGE, n.etype.startsWith('ACB') ? 'V' : 'kV')}`; }
    if (n.etype === 'BTR') { b = `탭${v.TAP ?? '–'} ${fmt(v.TEMP, '℃')}`; tv = true; }
    if (n.etype === 'LTR') { a = ''; b = `${fmt(v.LOAD, '%')} ${fmt(v.TEMP_W, '℃')}`; tv = true; }
    if (v.via && (n.etype === 'MAIN' || n.etype === 'TIE')) { a = `연계 공급 ← ${v.via.replace('BTR_', '')}`; tv = true; }
    const t1 = g.querySelector('[data-v1]'), t2 = g.querySelector('[data-v2]');
    t1.textContent = a; t2.textContent = b;
    t1.setAttribute('class', 'val' + (v.on ? '' : ' dead')); t2.setAttribute('class', 'val' + (tv ? ' tval' : '') + (v.on ? '' : ' dead'));
    const halo = document.querySelector(`[data-halo="${n.id}"]`), h = ST.hot[n.id];
    halo.setAttribute('visibility', h ? 'visible' : 'hidden'); if (h) halo.setAttribute('r', Math.min(40, 20 + h / 3));
  }
  document.querySelectorAll('.edge').forEach((p) => {
    const a = vals[p.dataset.a], b = vals[p.dataset.b], on = !!(a && b && a.on && b.on);
    const key = p.dataset.a + '>' + p.dataset.b;
    p.classList.remove('v154', 'v66', 'v220', 'viatie'); if (on) p.classList.add(p.dataset.v);
    if (on && a.via && b.via) p.classList.add('viatie');
    if (key in prevOn && prevOn[key] !== on) { p.classList.remove('flash'); void p.getBBox(); p.classList.add('flash'); setTimeout(() => p.classList.remove('flash'), 2100); }
    prevOn[key] = on;
  });
  // 모선 가로 구간은 여러 선로가 겹쳐 그려지므로, 가압 선로를 항상 무전압 선로 위에 둔다
  const gE = document.querySelector('.edge')?.parentNode;
  if (gE) [...gE.children].filter((p) => p.classList.contains('v154') || p.classList.contains('v66') || p.classList.contains('v220')).forEach((p) => gE.appendChild(p));
  const ring = $('#selring'), n = SEL && nodeById()[SEL];
  if (ring) { ring.setAttribute('visibility', n ? 'visible' : 'hidden'); if (n) ring.setAttribute('transform', `translate(${n.x},${n.y})`); }
}

(function () {   // 이동 / 확대
  const svg = $('#sld'); let drag = null, moved = false;
  svg.addEventListener('mousedown', (e) => { drag = { x: e.clientX, y: e.clientY }; moved = false; });
  window.addEventListener('mousemove', (e) => { if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3) { moved = true; svg.classList.add('drag'); } view.x += dx; view.y += dy; drag = { x: e.clientX, y: e.clientY }; applyView(); });
  window.addEventListener('mouseup', () => { drag = null; svg.classList.remove('drag'); });
  svg.addEventListener('click', (e) => { if (moved) e.stopPropagation(); }, true);
  svg.addEventListener('wheel', (e) => {
    e.preventDefault(); const r = svg.getBoundingClientRect(), cx = e.clientX - r.left, cy = e.clientY - r.top;
    const k2 = Math.min(4, Math.max(0.2, view.k * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
    view.x = cx - (cx - view.x) / view.k * k2; view.y = cy - (cy - view.y) / view.k * k2; view.k = k2; applyView();
  }, { passive: false });
  $('#fitBtn').onclick = fit;
  window.addEventListener('resize', () => META && fit());
})();

// ------------------------------------------------------------------ 설비 선택·조작
function select(id) {
  SEL = id; PENDING = null; SPARK = null; setPTab('eq'); renderEq(true); loadSpark(); if (ST) paint();
}
function focusNode(id) {
  const s = META.node_system[id]; if (!s) return;
  if (s !== SYS) { SYS = s; renderTabs(); drawDiagram(); }
  center(id); select(id);
}
window.focusNode = focusNode;
async function loadSpark() {
  if (!SEL) return; const id = SEL; const r = await api(`/api/trend?node=${id}&minutes=120`); if (id !== SEL) return; SPARK = r; drawSpark();
}
function drawSpark() {
  const svg = $('#spark'); if (!svg || !SPARK) return; svg.innerHTML = '';
  const n = nodeById()[SEL] || { etype: '' };
  const keys = n.etype === 'LTR' ? ['LOAD', 'TEMP_W'] : n.etype === 'BTR' ? ['POWER', 'TEMP'] : ['POWER', 'VOLTAGE'];
  const cols = ['#7aa8ff', '#ffd29a'];
  keys.forEach((k, i) => {
    const ys = (SPARK.series[k] || []).map((x) => x ?? 0); if (!ys.length) return;
    const lo = Math.min(...ys), hi = Math.max(...ys), rg = hi - lo || 1;
    el('polyline', { points: ys.map((y, j) => `${(j / Math.max(1, ys.length - 1)) * 400},${50 - ((y - lo) / rg) * 44}`).join(' '), fill: 'none', stroke: cols[i], 'stroke-width': 1.3 }, svg);
    el('text', { x: 4 + i * 120, y: 11, fill: cols[i], 'font-size': 10 }, svg).textContent = `${QK[k][0]} ${fmt(ys[ys.length - 1], QK[k][1])}`;
  });
  el('text', { x: 396, y: 52, fill: '#7a7a7a', 'font-size': 9, 'text-anchor': 'end' }, svg).textContent = '최근 2시간';
}
function renderEq(full) {
  if (PTAB !== 'eq') return;
  const P = $('#panel');
  if (!SEL) { P.innerHTML = '<div class="empty">계통도에서 설비를 누르세요</div>'; return; }
  const n = nodeById()[SEL] || { id: SEL, type_ko: '', etype: '' }, v = (ST && ST.values[SEL]) || {};
  const kv = Object.entries(QK).filter(([k]) => v[k] !== undefined).map(([k, [nm, u]]) => `<div><span>${nm}</span><b>${v[k] ?? '–'}${u}</b></div>`).join('');
  const sig = `${SEL}|${v.closed}|${v.on}`;
  if (!full && $('#eqkv') && sig === renderEq.sig) { $('#eqkv').innerHTML = kv; return; }
  renderEq.sig = sig;
  const closed = v.closed === 1, sw = n.switch;
  const evs = Object.entries(META.event_types).filter(([, t]) => t.targets.includes(SEL));
  P.innerHTML = `<div class="eqh"><h3>${SEL}</h3>${stBadge(v)}</div>
    <div class="eqsub">${n.type_ko}${sw ? ' · ' + (closed ? '투입' : '개방') : ''}</div>
    <div class="kv" id="eqkv">${kv}</div>
    ${kv ? '<svg id="spark" viewBox="0 0 400 54" preserveAspectRatio="none"></svg>' : ''}
    ${sw ? `<div class="ops"><button class="g" ${closed ? 'disabled' : ''} data-op="close">투입</button><button class="r" ${!closed ? 'disabled' : ''} data-op="open">개방</button>${n.etype === 'DIS' ? '' : `<button class="o" ${!closed ? 'disabled' : ''} data-op="trip">트립 모의</button>`}</div><div id="confirm"></div>` : ''}
    ${evs.length ? `<div class="sec">이벤트 주입</div><div class="inj"><select id="evType">${evs.map(([k, t]) => `<option value="${k}">${t.name}</option>`).join('')}</select><input id="evMin" type="number" min="1" title="지속(분)"><button id="evGo">주입</button></div>` : ''}`;
  P.querySelectorAll('[data-op]').forEach((b) => b.onclick = () => prepare(b.dataset.op));
  const s = $('#evType');
  if (s) { const upd = () => { $('#evMin').value = META.event_types[s.value].minutes; }; s.onchange = upd; upd();
    $('#evGo').onclick = async () => { await api('/api/inject', { type: s.value, target: SEL, minutes: +$('#evMin').value }); tick(); }; }
  drawSpark(); renderConfirm();
}
const stBadge = (v) => `<span id="eqst" class="st ${v.on ? 'on' : 'offs'}">${v.on ? '가압' : '무전압'}</span>`;
async function prepare(op) {
  const closed = op === 'close' ? 1 : 0;
  const pv = await api(`/api/preview?node=${SEL}&closed=${closed}`);
  PENDING = { op, closed, pv }; renderConfirm(); $('#confirm').scrollIntoView({ block: 'nearest' });
}
function renderConfirm() {
  const box = $('#confirm'); if (!box) return;
  if (!PENDING) { box.innerHTML = ''; return; }
  const { op, pv } = PENDING, name = { close: '투입', open: '개방', trip: '트립 모의' }[op];
  const lost = pv.lost.length ? `정전 ${pv.lost.length}개 설비 · 부하 ${pv.n_load_lost}개 · 약 ${fmt(pv.lost_kw, 'kW')}` : '정전 설비 없음';
  const gain = pv.gained.length ? ` · 가압 ${pv.gained.length}개 설비` : '';
  box.innerHTML = `<div class="confirm"><b>${SEL} ${name}</b><div class="m">${lost}${gain}</div>
    ${(pv.backup || []).map((b) => `<div class="m">백업 ${b['변압기']}: 부하율 ${b['현재_%']}% → <b class="${b['예상_%'] > 100 ? 'bad' : ''}">${b['예상_%']}%</b></div>`).join('')}
    ${pv.warnings.map((w) => `<div class="w">⚠ ${w}</div>`).join('')}
    <div class="row">${pv.parallel ? '<button class="go fp">무정전 절체로 병렬 투입</button>' : '<button class="go">실행</button>'}<button class="no">취소</button></div>
    <div class="err" id="opErr"></div></div>`;
  box.querySelector('.go').onclick = async () => {
    const r = await api('/api/switch', { node: SEL, closed: PENDING.closed, trip: PENDING.op === 'trip', force_parallel: !!pv.parallel });
    if (r && r.error) { $('#opErr').textContent = r.error; return; }
    PENDING = null; await tick(); renderEq(true);
  };
  box.querySelector('.no').onclick = () => { PENDING = null; renderConfirm(); };
}

// ------------------------------------------------------------------ 오른쪽 패널
function setPTab(t) { PTAB = t; $('#ptabs').querySelectorAll('button').forEach((x) => x.classList.toggle('on', x.dataset.t === t)); renderPanel(true); }
function renderPanel(full) {
  if (PTAB === 'eq') return renderEq(full);
  const P = $('#panel');
  const item = (h, m, id) => `<div class="it" ${id ? `onclick="focusNode('${id}')"` : ''}><div class="h">${h}</div><div class="m">${m}</div></div>`;
  if (PTAB === 'alarms') P.innerHTML = ST.alarms.length ? ST.alarms.map((a) => item(
    `<span><span class="tag ${a.end === '진행 중' ? 'live' : 'done'}">${a.end === '진행 중' ? '진행' : '종료'}</span><b>${a.id}</b> ${a.start.slice(11)}${a.end === '진행 중' ? '' : '~' + a.end.slice(11)}</span><span>${a.peak_score}</span>`,
    a.top_nodes.join(' · '), a.top_nodes[0])).join('') : '<div class="empty">경보 없음</div>';
  else if (PTAB === 'ops') P.innerHTML = ST.ops.length ? ST.ops.map((o) => item(
    `<span>${o.action.startsWith('트립') ? '<span class="tag trip">트립</span>' : ''}<b>${o.node}</b> ${o.action.startsWith('트립') ? '' : o.action}</span><span>${o.time.slice(11)}</span>`, o.by, o.node)).join('') : '<div class="empty">개폐 기록 없음</div>';
  else P.innerHTML = ST.injected.length ? ST.injected.map((e) => item(
    `<span><b>${e.id}</b> ${e.name}</span><span>${e.start.slice(11)}</span>`, `${e.target} · ~${e.end.slice(11)}`, e.target.replace(/_(CURRENT|POWER|VOLTAGE|PF)$/, ''))).join('') : '<div class="empty">없음</div>';
}
function drawChart() {
  const svg = $('#chart'); svg.innerHTML = '';
  const s = ST.scores; if (!s.length) { el('text', { x: 200, y: 40, fill: '#6e6e6e', 'font-size': 11, 'text-anchor': 'middle' }, svg).textContent = '이상 점수 대기 중'; return; }
  const thr = ST.thr || 1, mx = Math.max(thr * 1.5, ...s.map((x) => x[1]));
  const X = (i) => (i / Math.max(179, s.length - 1)) * 400, Y = (v) => 66 - (Math.max(v, 0) / mx) * 62;
  el('line', { x1: 0, x2: 400, y1: Y(thr), y2: Y(thr), stroke: '#ff8a3d', 'stroke-dasharray': '4 3', 'stroke-width': 1 }, svg);
  el('polyline', { points: s.map((x, i) => `${X(i)},${Y(x[1])}`).join(' '), fill: 'none', stroke: '#7aa8ff', 'stroke-width': 1.4 }, svg);
}
let chatSig = '';
const EQRE = /\b(?:VCB|ACB|LTR|BTR|GCB|MAIN|TIE|DIS|XCB|VCS)_[0-9A-Z_]+\b/g;
function renderChat() {
  const sig = ST.chat.map((m) => m.id + (m.pending ? 'p' : 'd')).join(','); if (sig === chatSig) return; chatSig = sig;
  const box = $('#msgs'), atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  box.innerHTML = ST.chat.map((m) => {
    let body = esc(m.pending ? '진단 중' : m.text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '$1').replace(/^#+\s*/gm, '');
    body = body.replace(EQRE, (x) => META.node_system[x] ? `<a class="eq" onclick="focusNode('${x}')">${x}</a>` : x);
    const meta = m.role === 'agent' && !m.pending ? `<span class="meta">${m.time.slice(11)} · ${m.sec ?? ''}초</span>` : '';
    return `<div class="msg ${m.role}${m.pending ? ' pending' : ''}${m.error ? ' err' : ''}">${m.role === 'system' ? m.time.slice(11) + ' ' : ''}${body}${meta}</div>`;
  }).join('');
  if (atBottom) box.scrollTop = box.scrollHeight;
}
function renderTabs() {
  $('#tabs').innerHTML = META.systems.map((s) => {
    const off = ST ? ST.sys_off[s] : 0, hot = ST ? ST.sys_hot[s] : 0;
    return `<button data-s="${s}" class="${s === SYS ? 'on' : ''}">${s}${hot ? `<span class="dot hot">${hot}</span>` : ''}${off ? `<span class="dot off">${off}</span>` : ''}</button>`;
  }).join('');
  $('#tabs').querySelectorAll('button').forEach((b) => b.onclick = () => { SYS = b.dataset.s; prevOn = {}; renderTabs(); drawDiagram(); tick(); });
}

let tabSig = '';
async function tick() {
  try {
    ST = await api('/api/state?system=' + SYS);
    $('#simtime').textContent = ST.time;
    const pill = $('#scorePill'), al = ST.score !== null && ST.score > ST.thr, wr = !al && ST.score !== null && ST.score > 30;
    pill.innerHTML = ST.score === null ? '이상 점수 —' : `<span class="lv">${al ? '경보' : wr ? '상승' : '정상'}</span>이상 점수 ${ST.score.toFixed(1)} <span class="hint">/ 기준 ${Math.round(ST.thr)}</span>`;
    pill.classList.toggle('alarm', al); pill.classList.toggle('warn', wr);
    if (MODAL === 'score') renderScore();
    $('#topNow').innerHTML = ST.top_now.length ? ST.top_now.slice(0, 3).map((f) => `<b>${f.node}</b> ${f.score}`).join(' · ') : '';
    const live = ST.alarms.filter((a) => a.end === '진행 중').length; $('#nAl').textContent = live || '';
    $('#auto').checked = ST.auto;
    paint(); drawChart(); renderChat(); renderPanel(false);
    const ts = JSON.stringify([ST.sys_off, ST.sys_hot]); if (ts !== tabSig) { tabSig = ts; renderTabs(); }
  } catch (e) { console.log(e); }
}

async function init() {
  META = await api('/api/meta');
  const me = await api('/api/me');
  document.body.classList.toggle('notadmin', me.role !== 'admin');
  if (me.auth) $('#who').innerHTML = `${me.role === 'admin' ? '관리자(admin)' : '사용자(user)'} · <a href="/logout">로그아웃</a>`;
  refreshAgentBtn(); setInterval(refreshAgentBtn, 10000);
  renderTabs(); drawDiagram(); setPTab('eq'); tick(); setInterval(tick, 1000); setInterval(loadSpark, 5000);
}
$('#speed').querySelectorAll('button').forEach((b) => b.onclick = async () => {
  const v = +b.dataset.v; await api('/api/control', v ? { speed: v, paused: false } : { paused: true });
  $('#speed').querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
});
$('#auto').onchange = (e) => api('/api/control', { auto: e.target.checked });
$('#reset').onclick = () => api('/api/control', { reset: true });
$('#ptabs').querySelectorAll('button').forEach((b) => b.onclick = () => setPTab(b.dataset.t));
async function send(q) { if (!q) return; await api('/api/ask', { text: q }); tick(); }
$('#ask').onsubmit = (e) => { e.preventDefault(); const q = $('#q').value.trim(); $('#q').value = ''; send(q); };
$('#quick').querySelectorAll('button').forEach((b) => b.onclick = () => send(b.textContent));

// ------------------------------------------------------------------ 팝업: 에이전트 연결 / 이상 점수 추이
let MODAL = null, AG = null;
function openModal(kind, title) { MODAL = kind; $('#mTitle').textContent = title; $('#modal').hidden = false; }
function closeModal() { MODAL = null; $('#modal').hidden = true; }
$('#mClose').onclick = closeModal;
$('#modal').onclick = (e) => { if (e.target.id === 'modal') closeModal(); };
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

async function refreshAgentBtn() {
  AG = await api('/api/agent'); const b = $('#agentBtn');
  b.textContent = !AG.enabled ? '에이전트 해제됨' : AG.backend ? '에이전트 연결됨' : '에이전트 응답 없음';
  b.classList.toggle('ok', AG.enabled && !!AG.backend); b.classList.toggle('bad', !AG.enabled || !AG.backend);
  if (MODAL === 'agent') renderAgent();
}
$('#agentBtn').onclick = async () => { openModal('agent', '진단 에이전트 연결'); await refreshAgentBtn(); };
function renderAgent() {
  const a = AG, ok = (x) => `<span class="${x ? 'on-ok' : 'on-bad'}">${x ? '● 동작' : '● 꺼짐'}</span>`;
  const via = { goclaw: 'goclaw 게이트웨이 → LiteLLM → Gemini', litellm: 'LiteLLM 직접 → Gemini (goclaw 미사용)' }[a.backend] || '연결 안 됨';
  const m = a.model;
  $('#mBody').innerHTML = `
    <div class="btnrow"><b>상태</b> ${a.enabled ? '<span class="on-ok">연결됨</span>' : '<span class="on-bad">해제됨</span>'}
      ${a.enabled ? '<button class="btn neg" data-en="0">에이전트 빼기(연결 해제)</button>' : '<button class="btn pri" data-en="1">에이전트 붙이기(연결)</button>'}</div>
    <div class="hint">해제하면 자동 진단·채팅 질문·실시간 해설이 모두 멈추고, 이상 탐지 모델과 경보는 그대로 동작합니다.</div>
    <div class="btnrow"><b>호출 경로</b>
      ${[['auto', '자동(goclaw 우선)'], ['goclaw', 'goclaw만'], ['direct', 'LiteLLM 직접']].map(([k, t]) => `<button class="btn ${a.mode === k ? 'sel' : ''}" data-mode="${k}">${t}</button>`).join('')}</div>
    <table class="kvt">
      <tr><td>현재 경로</td><td>${via}</td></tr>
      <tr><td>goclaw 게이트웨이</td><td>${ok(a.goclaw.alive)} ${a.goclaw.url} · 에이전트 ${a.goclaw.agent}</td></tr>
      <tr><td>LiteLLM 프록시</td><td>${ok(a.litellm.alive)} ${a.litellm.url}</td></tr>
      <tr><td>언어 모델</td><td>${a.litellm.model}</td></tr>
      <tr><td>조회 도구 ${a.tools.length}종</td><td>${a.tools.join(', ')} <span class="hint">(읽기 전용, 제어 불가)</span></td></tr>
      <tr><td>자동 진단</td><td>${a.auto_diag ? '켜짐 — 경보 즉시, 차단기 조작 3분 뒤 진단' : '꺼짐'}</td></tr>
      <tr><td>응답 기록</td><td>성공 ${a.stats.n}회 · 실패 ${a.stats.fail}회${a.stats.last_sec ? ` · 최근 ${a.stats.last_sec}초 (${a.stats.last_via})` : ''}</td></tr>
      <tr><td>이상 탐지 모델</td><td>${m ? `${m.name} · ${m.size_kb}KB · 1회 추론 ${m.latency_ms}ms · 기준선 ${m.threshold}` : '없음'}</td></tr>
    </table>`;
  $('#mBody').querySelectorAll('[data-en]').forEach((b) => b.onclick = async () => { await api('/api/agent', { enabled: b.dataset.en === '1' }); refreshAgentBtn(); });
  $('#mBody').querySelectorAll('[data-mode]').forEach((b) => b.onclick = async () => { await api('/api/agent', { mode: b.dataset.mode }); refreshAgentBtn(); });
}

let SC = null, scBusy = false, scHover = null;
$('#scorePill').onclick = () => { openModal('score', '이상 점수 실시간 추이'); renderScore(true); };
document.querySelector('.score-card').style.cursor = 'pointer';
document.querySelector('.score-card').onclick = () => $('#scorePill').click();
async function renderScore(first) {
  if (scBusy) return; scBusy = true;
  try { SC = await api('/api/score?minutes=180'); } finally { scBusy = false; }
  if (first || !$('#bigChart')) {
    $('#mBody').innerHTML = `
      <div class="hint">이상 점수 = 가장 이상한 센서 5개가 평소보다 몇 배 예측을 빗나가는지(6분 평균). 평상시 10 이하, 기준선(정상 운전 상위 1%)을 3분 넘게 넘으면 경보.</div>
      <svg id="bigChart" viewBox="0 0 900 300" preserveAspectRatio="none"></svg>
      <div class="hint" id="hov">그래프 위에 마우스를 올리면 그 시각의 점수와 원인 설비가 보입니다. 세로 점선 = 차단기 조작.</div>
      <div class="sgrid">
        <div><div class="btnrow"><b>에이전트 실시간 해설</b><button class="btn" id="narBtn"></button><span class="hint" id="narSt"></span></div><div class="narr" id="narr"></div></div>
        <div><b>지금 점수를 올리는 설비</b><div class="toplist" id="topl"></div></div>
      </div>`;
    $('#narBtn').onclick = async () => { await api('/api/narrate', { on: !SC.narr.on }); renderScore(); };
    const svg = $('#bigChart');
    svg.onmousemove = (e) => { const r = svg.getBoundingClientRect(); scHover = Math.round(((e.clientX - r.left) / r.width) * 900); drawBig(); };
    svg.onmouseleave = () => { scHover = null; drawBig(); };
  }
  drawBig();
  const nr = SC.narr;
  $('#narBtn').textContent = nr.on ? '해설 끄기' : '해설 켜기'; $('#narBtn').className = 'btn ' + (nr.on ? 'neg' : 'pri');
  $('#narSt').textContent = !AG?.enabled ? '에이전트 연결 해제 상태' : nr.busy ? '해설 작성 중…' : nr.on ? '상태가 바뀌면 바로, 평소엔 90초마다 갱신 (이 창이 열려 있을 때만)' : '';
  const sig = nr.items.map((x) => x.time + x.text.length).join();
  if ($('#narr').dataset.sig !== sig) {
    $('#narr').dataset.sig = sig;
    $('#narr').innerHTML = nr.items.length ? nr.items.slice().reverse().map((x) => `<div class="it ${x.err ? 'err' : ''}"><div class="h">${x.time}${x.score !== null ? ` · 점수 ${x.score}` : ''}${x.sec ? ` · ${x.sec}초` : ''}</div>${esc(x.text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(EQRE, (m) => META.node_system[m] ? `<a class="eq" onclick="closeModal();focusNode('${m}')">${m}</a>` : m)}</div>`).join('') : '<div class="hint">해설 켜기를 누르면 에이전트가 점수 변화를 짧게 설명합니다.</div>';
  }
  $('#topl').innerHTML = SC.top_now.length ? SC.top_now.map((f) => `<div><a class="eq" onclick="closeModal();focusNode('${f.node}')">${f.node}</a><span class="hint">${f.kind}</span><b>${f.score}</b></div>`).join('') : '<div class="hint">평소보다 3배 넘게 빗나가는 설비 없음</div>';
}
function drawBig() {
  const svg = $('#bigChart'); if (!svg || !SC) return; svg.innerHTML = '';
  const v = SC.v, n = v.length, W = 900, Hh = 300, L = 46, B = 22; if (!n) return;
  const thr = SC.thr, mx = Math.max(thr * 1.3, ...v) * 1.05;
  const lg = (x) => Math.log10(1 + Math.max(x, 0)), X = (i) => L + (i / Math.max(n - 1, 1)) * (W - L - 8), Y = (x) => (Hh - B) - (lg(x) / lg(mx)) * (Hh - B - 10);
  for (const g of [1, 10, 100, 1000, 10000].filter((g) => g <= mx)) {
    el('line', { x1: L, x2: W, y1: Y(g), y2: Y(g), stroke: '#222', 'stroke-width': 1 }, svg);
    el('text', { x: L - 6, y: Y(g) + 4, fill: '#777', 'font-size': 11, 'text-anchor': 'end' }, svg).textContent = g;
  }
  if (SC.band) el('rect', { x: L, width: W - L, y: Y(SC.band[1]), height: Math.max(1, Y(SC.band[0]) - Y(SC.band[1])), fill: '#2fbf7122' }, svg);
  const idx = (t) => SC.t.indexOf(t);
  for (const a of SC.alarms) { const i0 = idx(a.start), i1 = a.end ? idx(a.end) : n - 1; if (i0 >= 0) el('rect', { x: X(i0), width: Math.max(2, X(i1 < 0 ? n - 1 : i1) - X(i0)), y: 0, height: Hh - B, fill: '#ff3b3b18' }, svg); }
  for (const o of SC.ops) { const i = idx(o.t); if (i >= 0) el('line', { x1: X(i), x2: X(i), y1: 0, y2: Hh - B, stroke: '#f2c14e66', 'stroke-dasharray': '3 3' }, svg); }
  el('line', { x1: L, x2: W, y1: Y(thr), y2: Y(thr), stroke: '#ff8a3d', 'stroke-dasharray': '6 4', 'stroke-width': 1.5 }, svg);
  el('text', { x: W - 6, y: Y(thr) - 5, fill: '#ff8a3d', 'font-size': 11, 'text-anchor': 'end' }, svg).textContent = `기준선 ${Math.round(thr)}`;
  el('polyline', { points: v.map((x, i) => `${X(i)},${Y(x)}`).join(' '), fill: 'none', stroke: '#e8e8e8', 'stroke-width': 1.6 }, svg);
  for (let k = 0; k < n; k += Math.ceil(n / 8)) el('text', { x: X(k), y: Hh - 6, fill: '#777', 'font-size': 11, 'text-anchor': 'middle' }, svg).textContent = SC.t[k];
  if (scHover !== null) {
    const i = Math.max(0, Math.min(n - 1, Math.round(((scHover - L) / (W - L - 8)) * (n - 1))));
    el('line', { x1: X(i), x2: X(i), y1: 0, y2: Hh - B, stroke: '#888' }, svg); el('circle', { cx: X(i), cy: Y(v[i]), r: 4, fill: '#fff' }, svg);
    const ops = SC.ops.filter((o) => o.t === SC.t[i]).map((o) => `${o.node} ${o.action}`).join(', ');
    $('#hov').innerHTML = `<b>${SC.t[i]}</b> 점수 <b>${v[i]}</b> ${v[i] > thr ? '<span class="chip a">경보 수준</span>' : v[i] > 30 ? '<span class="chip w">상승</span>' : '<span class="chip n">정상</span>'} · 원인 상위: ${(SC.top[i] || []).join(', ') || '없음'}${ops ? ' · 조작: ' + ops : ''}`;
  }
}

init();
