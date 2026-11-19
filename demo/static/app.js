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
      el('path', { d: 'M-8,-6 L8,-6 L0,8 Z', fill: '#6b7690' }, g);
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
  el('text', { x: 396, y: 52, fill: '#66728f', 'font-size': 9, 'text-anchor': 'end' }, svg).textContent = '최근 2시간';
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
    ${sw ? `<div class="ops"><button class="g" ${closed ? 'disabled' : ''} data-op="close">투입</button><button class="r" ${!closed ? 'disabled' : ''} data-op="open">개방</button><button class="o" ${!closed ? 'disabled' : ''} data-op="trip">트립 모의</button></div><div id="confirm"></div>` : ''}
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
    ${pv.warnings.map((w) => `<div class="w">⚠ ${w}</div>`).join('')}
    <div class="row"><button class="go">실행</button><button class="no">취소</button></div></div>`;
  box.querySelector('.go').onclick = async () => {
    await api('/api/switch', { node: SEL, closed: PENDING.closed, trip: PENDING.op === 'trip' }); PENDING = null; await tick(); renderEq(true);
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
  const s = ST.scores; if (!s.length) { el('text', { x: 200, y: 40, fill: '#5d6884', 'font-size': 11, 'text-anchor': 'middle' }, svg).textContent = '이상 점수 대기 중'; return; }
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
    const pill = $('#scorePill'), al = ST.score !== null && ST.score > ST.thr;
    pill.textContent = ST.score === null ? '이상 점수 —' : `이상 점수 ${ST.score} / ${ST.thr}`; pill.classList.toggle('alarm', al);
    $('#topNow').innerHTML = ST.top_now.length ? ST.top_now.slice(0, 3).map((f) => `<b>${f.node}</b> ${f.score}`).join(' · ') : '';
    const live = ST.alarms.filter((a) => a.end === '진행 중').length; $('#nAl').textContent = live || '';
    $('#auto').checked = ST.auto;
    paint(); drawChart(); renderChat(); renderPanel(false);
    const ts = JSON.stringify([ST.sys_off, ST.sys_hot]); if (ts !== tabSig) { tabSig = ts; renderTabs(); }
  } catch (e) { console.log(e); }
}

async function init() {
  META = await api('/api/meta');
  const m = META.model, mb = $('#modelBadge');
  if (m) { mb.textContent = `경량 모델 ${m.size_kb.toFixed(0)}KB`; mb.classList.add('ok'); mb.title = `${m.name} · 1회 추론 ${m.latency_ms.toFixed(1)}ms`; }
  else { mb.textContent = '모델 없음'; mb.classList.add('bad'); }
  const ag = await api('/api/agent'), ab = $('#agentBadge');
  ab.textContent = ag.backend ? `에이전트(${ag.backend})` : '에이전트 꺼짐'; ab.classList.add(ag.backend ? 'ok' : 'bad');
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
init();
