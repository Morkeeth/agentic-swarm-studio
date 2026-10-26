// Agentic Swarm Simulator studio. Reads one swarm result.json and draws it as a floor plan of screens.
// Rooms are the screens visitors reached. Each visitor has a row in every room; its squares are its steps there.
// Trails join the rooms in the order each visitor moved. A ring marks where a visitor stopped stuck.
(() => {
  const $ = s => document.querySelector(s);
  const NS = 'http://www.w3.org/2000/svg';
  const RW = 280, TH = 135, GAP = 120, PAD = 36, ROW = 20;
  const OUT = {got_there: 'Got there', reached_start: 'Reached the start', stuck: 'Stuck', left_app: 'Left the app', claimed: 'Said done, not confirmed',
               screen_only: 'Screen agreed, job not done', not_finished: 'Did not finish'};
  const state = {kind: null, id: null, result: null, T: Infinity, playing: false, live: false, poll: null, health: null};

  const el = (tag, attrs = {}, text) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const h = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const pathOf = u => { try { const x = new URL(u); return x.pathname.replace(/\/$/, '') || '/'; } catch { return u || '?'; } };
  const api = (p, o) => fetch(p, o).then(async r => { const t = r.headers.get('content-type') || ''; const b = t.includes('json') ? await r.json() : await r.text(); if (!r.ok) throw new Error(b.error || r.status); return b; });

  // ---- model of one result -------------------------------------------------------------
  function visitors(r) { return (r.tries && r.tries[0]) || (r.visitors_planned || []).map(v => ({...v, steps: [], status: 'waiting'})); }
  function endOf(r) {
    let m = 0;
    for (const v of visitors(r)) { m = Math.max(m, v.end_ms || 0); for (const s of v.steps) m = Math.max(m, (s.start_ms || 0) + (s.elapsed_ms || 0)); }
    return m || 1;
  }
  function model(r, T) {
    const rooms = new Map(), people = visitors(r);
    people.forEach((v, vi) => {
      v._seen = v.steps.filter(s => (s.start_ms || 0) <= T);
      v._seen.forEach(s => {
        const key = pathOf(s.url);
        if (!rooms.has(key)) rooms.set(key, {key, title: s.title, first: s.start_ms || 0, steps: [], shot: null, phoneShot: null, code: null, clicks: new Map()});
        const room = rooms.get(key);
        room.steps.push({...s, vi});
        if (s.http_status >= 400 && s.status !== 'error_page') room.code = s.http_status;   // an error click carries the status of the page it opened
        if (s.screenshot) { if (v.phone) room.phoneShot = s.screenshot; else room.shot = s.screenshot; }
        if (s.action === 'click' && s.target_text) room.clicks.set(s.target_text, (room.clicks.get(s.target_text) || 0) + 1);
      });
    });
    const order = [...rooms.values()].sort((a, b) => a.first - b.first);
    order.forEach((room, i) => { room.i = i; room.x = PAD + i * (RW + GAP); });
    return {rooms, order, people};
  }

  function progress() {
    const slots = [...document.querySelectorAll('#live-progress li')], people = state.result ? model(state.result, state.T).people : [];
    slots.forEach((slot, i) => {
      const v = people[i]; slot.className = '';
      slot.hidden = Boolean(state.result && !v);
      slot.style.display = slot.hidden ? 'none' : '';
      if (!v) { slot.querySelector('small').textContent = 'Waiting for a release'; return; }
      slot.querySelector('b').textContent = v.name || `Visitor ${i + 1}`;
      const seen = v._seen || [], last = seen[seen.length - 1], finished = v.status === 'complete' && seen.length === (v.steps || []).length;
      if (finished) {
        slot.classList.add('done');
        slot.querySelector('small').textContent = OUT[v.outcome] || v.outcome || 'Finished';
      } else if (seen.length) {
        slot.classList.add('moving');
        slot.querySelector('small').textContent = `${seen.length} screen${seen.length === 1 ? '' : 's'} · ${last.action || 'reading'}`;
      } else slot.querySelector('small').textContent = 'Opening the app';
    });
  }

  // ---- floor plan ----------------------------------------------------------------------
  function draw() {
    const r = state.result, svg = $('#plan');
    svg.replaceChildren();
    if (!r) return;
    const {rooms, order, people} = model(r, state.T);
    const heatRows = Math.max(1, ...order.map(o => o.clicks.size));
    const rowsTop = PAD + TH + 58, height = rowsTop + people.length * ROW + 18 + heatRows * 18 + PAD + 30;
    const width = Math.max(PAD * 2 + Math.max(1, order.length) * (RW + GAP) - GAP, 640);
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`); svg.setAttribute('width', width); svg.setAttribute('height', height);
    if (!order.length) { svg.appendChild(el('text', {x: PAD, y: 60, class: 'empty'}, r.status === 'failed' ? 'The run failed: ' + (r.error || '') : 'Visitors are opening the app.')); return; }
    const maxVisits = Math.max(...order.map(o => o.steps.length));
    const trails = el('g'), roomsG = el('g'), marks = el('g');
    for (const room of order) {
      const g = el('g', {class: 'room' + (room.code ? ' err' : ''), transform: `translate(${room.x},${PAD})`});
      g.appendChild(el('rect', {class: 'frame', x: 0, y: 0, width: RW, height: height - PAD * 2 - 10}));
      const shot = room.shot || room.phoneShot;
      if (shot) g.appendChild(el('image', {href: `${base()}/${shot}`, x: 3, y: 3, width: RW - 6, height: TH - 6, preserveAspectRatio: 'xMidYMin slice'}));
      g.appendChild(el('line', {x1: 0, x2: RW, y1: TH, y2: TH, stroke: '#1E1A17', 'stroke-width': 3}));
      g.appendChild(el('text', {x: 12, y: TH + 22, class: 't'}, (room.title || 'Untitled').slice(0, 30)));
      g.appendChild(el('text', {x: 12, y: TH + 38, class: 'p'}, room.key.slice(0, 40)));
      if (room.code) g.appendChild(el('text', {x: RW - 12, y: TH + 22, class: 'code', 'text-anchor': 'end'}, String(room.code)));
      // Heat: how often each control in this room was clicked, across all visitors.
      let hy = rowsTop - PAD + people.length * ROW + 14;
      const most = Math.max(1, ...room.clicks.values());
      for (const [label, n] of [...room.clicks.entries()].sort((a, b) => b[1] - a[1])) {
        g.appendChild(el('rect', {class: 'heat', x: 12, y: hy, height: 8, width: Math.max(4, (RW - 24) * n / most), opacity: .35 + .65 * room.steps.length / maxVisits}));
        g.appendChild(el('text', {x: 12, y: hy + 20, class: 'heatlabel'}, `${label.slice(0, 32)} ×${n}`));
        hy += 28;
      }
      roomsG.appendChild(g);
    }
    people.forEach((v, vi) => {
      const y = rowsTop + vi * ROW, colour = v.colour || '#1E1A17';
      const per = new Map();
      let prev = null, d = '';
      v._seen.forEach((s, si) => {
        const room = rooms.get(pathOf(s.url)), k = per.get(room.key) || 0; per.set(room.key, k + 1);
        const sx = room.x + 12 + k * 15;
        const cls = s.status === 'ok' ? 'fill' : s.status;
        const fill = cls === 'fill' ? colour : cls === 'error_page' ? '#FF7F5C' : cls === 'stuck' ? '#1E1A17' : cls === 'got_there' ? '#1F6B4E' : 'none';
        marks.appendChild(el('rect', {x: sx, y: y - 6, width: 11, height: 11, fill, stroke: fill === 'none' ? colour : fill, 'stroke-width': 2,
                                      'stroke-dasharray': s.status === 'thinking' ? '2 2' : 'none'}));
        if (prev && prev.room !== room) {
          const x1 = prev.x + 11, x2 = sx;
          if (room.x > prev.room.x) d += `M${x1},${y} C${x1 + 70},${y} ${x2 - 70},${y} ${x2},${y} `;
          else { const dip = height - PAD - 4 - vi * 5; d += `M${x1},${y} C${x1 + 40},${dip} ${x2 - 40},${dip} ${x2},${y} `; }
        }
        prev = {room, x: sx, s, si};
      });
      if (d) trails.appendChild(el('path', {class: 'trail', d, stroke: colour}));
      if (prev) {
        const dot = el('circle', {class: 'dot', r: 6, cx: 0, cy: 0, fill: colour, stroke: '#FFFDF9', 'stroke-width': 2});
        dot.style.transform = `translate(${prev.x + 22}px, ${y - 0.5}px)`;
        marks.appendChild(dot);
        const last = prev.s, done = v.status === 'complete' && v._seen.length === v.steps.length;
        if (done && (v.outcome === 'stuck' || v.outcome === 'not_finished' || v.outcome === 'claimed')) {
          marks.appendChild(el('circle', {class: 'knot', r: 11, cx: prev.x + 22, cy: y - .5, stroke: colour}));
          marks.appendChild(el('path', {d: `M${prev.x + 31},${y - 9} l6,-6 M${prev.x + 31},${y + 8} l6,6`, stroke: colour, 'stroke-width': 2}));
        }
        if (last.status === 'error_page' && last.hit) marks.appendChild(el('circle', {r: 4, cx: prev.x + 5, cy: y - .5, fill: '#FF7F5C'}));
      }
    });
    svg.append(trails, roomsG, marks);
  }

  // ---- roster, judge, test -------------------------------------------------------------
  function roster() {
    const r = state.result, list = $('#roster'); list.replaceChildren();
    if (!r) return;
    for (const v of model(r, state.T).people) {
      const li = h('li'); li.style.setProperty('--c', v.colour || '#1E1A17');
      li.title = v.goal || ''; li.appendChild(h('b', '', v.name));
      const steps = h('div', 'steps'); for (const s of v._seen) { const i = h('i', s.status); i.title = `${s.order}. ${s.action || 'looking'} ${s.target_text ? "'" + s.target_text + "'" : ''} : ${s.status}`; steps.appendChild(i); }
      li.appendChild(steps);
      const last = [...v._seen].reverse().find(s => s.say || s.wish);
      if (last) li.appendChild(h('q', '', (last.wish && last.status === 'stuck' ? last.wish : last.say).slice(0, 140)));
      li.appendChild(h('span', 'out', v.status === 'complete' ? (OUT[v.outcome] || v.outcome || '') : v._seen.length ? 'Moving' : 'Waiting'));
      list.appendChild(li);
    }
  }
  function judge() {
    const r = state.result, body = $('#judge'); body.replaceChildren();
    if (!r) return;
    const calls = ((r.spend || {}).calls || []).filter(c => /-judge$/.test(c.call));
    $('#judge-note').textContent = r.judge_model ? `Judge: ${r.judge_model}, given the screen image and its text. It ran ${calls.length} time${calls.length === 1 ? '' : 's'}: only when a visitor said it was done and quoted words that are on the page.` : 'No judge model in this run.';
    for (const v of visitors(r)) {
      const tr = h('tr'), name = h('td'); name.appendChild(document.createTextNode(v.name));
      const why = [...v.steps].reverse().map(s => (s.claim && s.claim.why) || (s.look && s.look.rejection_reason)).find(Boolean);
      if (why) name.appendChild(h('small', '', why.slice(0, 160)));
      tr.appendChild(name);
      for (const k of ['claimed', 'screen_confirmed', 'confirmed']) tr.appendChild(h('td', v[k] ? 'yes' : 'no', v.status !== 'complete' ? '...' : v[k] ? 'Yes' : 'No'));
      body.appendChild(tr);
    }
    const sp = r.spend;
    $('#spend').textContent = !sp ? '' : sp.billing_channel === 'ChatGPT subscription'
      ? `${sp.model_calls} Codex subscription decisions. Consumes subscription quota; no API dollar cost inferred.`
      : `${sp.model_calls} model calls on ${(sp.models || []).join(' and ') || r.model}. Listed-rate estimate ${Number.isFinite(sp.listed_rate_estimate_usd) ? 'USD ' + sp.listed_rate_estimate_usd.toFixed(5) : 'unavailable'}, held reservations USD ${(sp.held_reservation_usd || 0).toFixed(5)}. Not a provider invoice.`;
    const all = visitors(r), done = all.filter(v => v.confirmed).length;
    const interrupted = all.filter(v => v.outcome === 'not_finished').length;
    $('#headline').textContent = r.status === 'complete' ? `${done} of ${all.length} agents completed. ${all.filter(v => v.outcome === 'stuck').length} stuck${interrupted ? `, ${interrupted} interrupted` : ''}.` : (r.status === 'failed' ? 'The run failed.' : 'The swarm is running.');
    const DIAGNOSIS = {
      'swarm-2326': 'All five reached the guide at step 2, quoted a navigation label, then got lost. These are agent limits with a shared harness feedback defect. No app bug was proved. All five were given the same reading task in this run.',
      'rerun-2335': 'After the harness repair: 0 of 5 completed. Four ended stuck. The phone run was interrupted by a provider error. One visual judge call rejected the reading claim. The harness fix is local; it did not improve completion.',
      'broken-demo-0003': 'This is a real recorded run against a deliberately broken bundled demo. Its guide returns 404. This planted defect is separate from the working-guide runs.'};
    $('#diagnosis').textContent = (r.replay && r.replay.diagnosis) || DIAGNOSIS[state.id] || (r.headline || '');
    $('#run-url').textContent = (r.diagnostic ? `${r.diagnostic} Retained playback.  ` : '') + (r.replay ? `Recorded: ${r.replay.label}.  ` : '') + `${r.url}  ·  task: ${(r.job || {}).text || ''}`;
    $('#limits').textContent = (r.limitations || []).join(' ');
  }
  async function test() {
    const pre = $('#test'), link = $('#test-link'), note = $('#test-note');
    pre.textContent = ''; link.hidden = true;
    if (!state.result || state.result.status !== 'complete') { note.textContent = 'The test is written when the swarm finishes.'; return; }
    try {
      const src = await api(`${base()}/test.py`);
      const error = visitors(state.result).some(v => v.steps.some(s => s.status === 'error_page'));
      note.textContent = error ? 'A recorded click reached an HTTP error. This path check can reproduce that error. It checks page loading, not task success.' : 'No app error was confirmed in this run. This download checks the recorded navigation path only. A pass does not show that an agent completed its task.';
      pre.textContent = src; link.href = `${base()}/test.py`; link.hidden = false;
    } catch (e) { note.textContent = e.message; }
  }
  const base = () => `/api/studio/${state.kind}/${state.id}`;

  // ---- clock ---------------------------------------------------------------------------
  function setT(T) {
    state.T = T; const end = endOf(state.result);
    $('#scrub').value = Math.round(1000 * Math.min(T, end) / end);
    $('#time').textContent = `${(Math.min(T, end) / 1000).toFixed(1)} s`;
    draw(); roster(); progress();
  }
  function play() {
    if (!state.result) return;
    state.playing = !state.playing; $('#play').textContent = state.playing ? 'Pause recorded path' : 'Play recorded path';
    if (!state.playing) return;
    const end = endOf(state.result), span = 20000; let t0 = performance.now(), from = state.T >= end ? 0 : state.T;
    const tick = now => {
      if (!state.playing) return;
      const T = from + (now - t0) * end / span; setT(Math.min(T, end));
      if (T >= end) { state.playing = false; $('#play').textContent = 'Play recorded path'; return; }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  // ---- loading runs --------------------------------------------------------------------
  async function open(kind, id) {
    clearInterval(state.poll); state.playing = false; $('#play').textContent = 'Play recorded path';
    state.kind = kind; state.id = id;
    document.querySelectorAll('.runs button').forEach(b => b.setAttribute('aria-current', b.dataset.id === id));
    history.replaceState(null, '', `#${kind}/${id}`);
    const load = async () => {
      state.result = await api(base());
      const live = !['complete', 'failed'].includes(state.result.status);
      if (live || state.T === Infinity) setT(Infinity); else setT(state.T);
      judge();
      if (!live) { clearInterval(state.poll); test(); listRuns(); }
      return live;
    };
    state.T = Infinity;
    if (await load()) state.poll = setInterval(load, 1200);
    else if (kind === 'replays') { setT(0); play(); }
    explainBox();
  }
  // One live Nemotron Nano call through Nebius Token Factory, on recorded runs only.
  function explainBox() {
    const lc = state.health && state.health.live_call, box = $('#explain');
    box.hidden = !(lc && state.kind === 'replays'); $('#explain-text').textContent = '';
    if (!box.hidden) $('#explain-note').textContent = `Live call to ${lc.model} on ${lc.provider}. ${lc.calls_today} of ${lc.daily_calls} calls used today, USD ${lc.accounted_usd.toFixed(4)} of a USD ${lc.cap_usd} ceiling.`;
  }
  // A press always ends in an answer or a plain message, never an endless "Calling".
  function explainError(e, ms) {
    if (e.name === 'AbortError') return `No answer from Nemotron within ${Math.round(ms / 1000)} s. Recorded runs still play. Try again in a minute.`;
    if (e instanceof TypeError) return 'The request did not reach the server. Check your connection and try again.';
    if (e.message === '429') return 'Too many requests right now. Recorded runs still play. Try again in a minute.';
    if (/^\d+$/.test(e.message)) return `The server answered with error ${e.message}. Recorded runs still play. Try again in a minute.`;
    return e.message;
  }
  async function explain() {
    const go = $('#explain-go'); go.disabled = true; $('#explain-text').textContent = ''; $('#explain-note').textContent = 'Calling Nemotron...';
    const ms = Number($('#explain').dataset.timeoutMs) || 40000, ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), ms);
    try {
      const r = await api('/api/studio/explain', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({replay: state.id}), signal: ctl.signal});
      $('#explain-text').textContent = r.text;
      $('#explain-note').textContent = `Live answer from ${r.model} on ${r.provider}. Call ${r.call}: ${r.prompt_tokens} tokens in, ${r.completion_tokens} out, ${r.latency_ms} ms, USD ${r.estimated_usd.toFixed(6)} at listed rates. This is the model's reading of the record, not a verdict; the counts above come from the record.`;
      api('/api/studio/health').then(h => { state.health = h; }, () => {});
    } catch (e) { $('#explain-note').textContent = explainError(e, ms); }
    finally { clearTimeout(timer); go.disabled = false; }
  }
  async function listRuns() {
    const d = await api('/api/studio/runs'), ul = $('#runs'); ul.replaceChildren();
    const add = (kind, id, title, sub) => {
      const li = h('li'), b = h('button'); b.dataset.id = id; b.type = 'button';
      b.appendChild(document.createTextNode(title)); b.appendChild(h('small', '', sub)); b.onclick = () => open(kind, id);
      b.setAttribute('aria-current', id === state.id); li.appendChild(b); ul.appendChild(li);
    };
    for (const r of d.runs) add('runs', r.id, r.headline || r.status, `${pathOf(r.url)} · ${r.id}`);
    for (const x of d.replays) add('replays', x.id, x.label, x.headline || x.id);
    return d;
  }

  // ---- cases ---------------------------------------------------------------------------
  async function cases() {
    const d = await api('/api/studio/cases'), grid = $('#case-grid'); grid.replaceChildren();
    $('#case-limits').textContent = [d.score_comparability, ...(d.limitations || [])].filter(Boolean).join(' ');
    const best = Math.max(...d.cases.map(c => c.delta || 0));
    for (const c of d.cases) {
      const card = h('article', 'case' + (c.delta === best ? ' best' : ''));
      card.appendChild(h('span', 'id', c.id)); card.appendChild(h('h3', '', c.flow));
      for (const side of ['before', 'after']) {
        const s = c[side] || {}, row = h('div', 'row ' + side), dots = h('div', 'dots');
        row.appendChild(h('span', '', side === 'before' ? 'Before' : 'After'));
        const runs = s.runs || 1, passed = s.passed !== undefined ? s.passed : Math.round((s.judge_score || 0) * runs);
        for (let i = 0; i < runs; i++) dots.appendChild(h('i', i < passed ? 'pass' : ''));
        row.appendChild(dots); row.appendChild(h('b', '', `${passed}/${runs}`)); card.appendChild(row);
      }
      card.appendChild(h('p', '', `${c.fix || ''}. ${c.status[0].toUpperCase() + c.status.slice(1)}.` + (c.files && c.files.length ? ` Changed ${c.files.join(', ')}.` : '') + (c.judge ? ` Scored by ${c.judge}.` : ' Model verdict, kept apart from the checker scores.')));
      if (c.diff) {
        const det = h('details'), sum = h('summary', '', 'Show the fix'), pre = h('pre');
        det.append(sum, pre); det.ontoggle = async () => { if (det.open && !pre.textContent) pre.textContent = await api(`/api/studio/cases/${c.id}.diff`); };
        card.appendChild(det);
      }
      grid.appendChild(card);
    }
  }

  async function library() {
    const d = await api('/studio/evidence/library.json');
    for (const x of d.hn) { const li = h('li'), a = h('a', '', x.title); a.href = x.url; a.target = '_blank'; a.rel = 'noopener'; li.append(a, h('p', 'note', x.observation)); $('#hn-list').appendChild(li); }
  }

  // ---- wiring --------------------------------------------------------------------------
  function tabs(name) {
    document.querySelectorAll('.tabs button').forEach(b => b.setAttribute('aria-selected', b.dataset.tab === name));
    document.querySelectorAll('.view').forEach(v => { v.hidden = v.id !== name; });
    if (name === 'cases' && !$('#case-grid').children.length) cases();
    if (name === 'library' && !$('#hn-list').children.length) library();
  }
  document.addEventListener('DOMContentLoaded', async () => {
    document.querySelectorAll('.tabs button').forEach(b => { b.onclick = () => tabs(b.dataset.tab); });
    document.querySelectorAll('[data-demo]').forEach(b => { b.onclick = () => { $('#run [name=url]').value = location.origin + b.dataset.demo; }; });
    document.querySelectorAll('[data-replay]').forEach(b => { b.onclick = () => { open('replays', b.dataset.replay); document.querySelector('.stage-head').scrollIntoView({behavior: 'smooth'}); }; });
    $('#open-library').onclick = () => tabs('library');
    $('#play').onclick = play;
    $('#explain-go').onclick = explain;
    $('#scrub').oninput = e => { state.playing = false; $('#play').textContent = 'Play recorded path'; if (state.result) setT(endOf(state.result) * e.target.value / 1000); };
    state.health = await api('/api/studio/health');
    const form = $('#run'), go = form.querySelector('.go');
    if (!state.health.live_runs) {
      go.disabled = true; form.querySelectorAll('input,.demo-pick button').forEach(x => { x.disabled = true; });
      $('#run-note').textContent = 'Recorded mode on this server. No model will be called. Start locally with a Nebius Token Factory key to rehearse a new URL.';
    } else $('#run-note').textContent = `Crowd: ${state.health.crowd_model}. Judge: ${state.health.judge_model || 'none'}. Spending stop USD ${state.health.stop_usd}, USD ${state.health.accounted_usd.toFixed(4)} used so far.`;
    form.onsubmit = async e => {
      e.preventDefault(); go.disabled = true;
      try {
        const body = Object.fromEntries(new FormData(form)); body.visitors = Number(body.visitors);
        const r = await api('/api/studio/runs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        await listRuns(); open('runs', r.id); document.querySelector('.stage-head').scrollIntoView({behavior: 'smooth'});
      } catch (err) { $('#run-note').textContent = err.message; }
      finally { go.disabled = !state.health.live_runs; }
    };
    const d = await listRuns();
    const [kind, id] = location.hash.slice(1).split('/');
    if (kind === 'cases' || kind === 'library') tabs(kind);
    else if (kind && id) open(kind, id);
    else if (d.runs.length) open('runs', d.runs[0].id);
    else if (d.replays.length) open('replays', d.replays.some(x => x.id === 'broken-demo-0003') ? 'broken-demo-0003' : d.replays[0].id);
  });
})();
