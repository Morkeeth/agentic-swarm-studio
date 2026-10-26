'use strict';
(() => {
  const node = (tag, text) => {const el = document.createElement(tag); el.textContent = text; return el;};
  let selected = null, lastSignature = null;
  const matches = (a, r) => a.id === r.id && a.url === r.url && a.task === r.task;
  const motion = document.querySelector('#mission-motion');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  let replay = null, playing = false, time = 0, lastFrame = null, lanes = [];
  const svg = (tag, attrs, text) => {
    const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    if (text) el.textContent = text;
    return el;
  };
  function paint(ms) {
    if (!replay) return;
    const events = [];
    lanes.forEach(({visitor, token, status, stall}) => {
      const steps = visitor.steps || [];
      const end = visitor.end_ms || 1;
      const checkStart = steps.find(s => s.action === 'done')?.start_ms ?? end;
      let x = 65;
      if (ms < 700) x = 65 + Math.min(1, ms / 700) * 155;
      else if (ms < checkStart) x = 220 + Math.max(0, (ms - 700) / Math.max(1, checkStart - 700)) * 120;
      else if (ms < end) x = 380;
      else x = 380 + Math.min(1, (ms - end) / 900) * 160;
      const stopped = !visitor.confirmed && ms >= end;
      if (stopped) x = 340;
      stall.setAttribute('visibility', stopped ? 'visible' : 'hidden');
      token.setAttribute('transform', `translate(${x},0)`);
      const step = steps.filter(s => s.start_ms <= ms).at(-1);
      status.textContent = ms >= end ? (visitor.confirmed ? 'Confirmed' : visitor.outcome === 'stuck' ? 'Got lost' : visitor.outcome) : step ? `${step.action}: ${step.target_text || step.title || ''}` : 'Task assigned';
      if (step) events.push(`${visitor.name}: ${step.say || step.claim?.why || step.action}`);
    });
    document.querySelector('#runway-event').textContent = ms >= replay.duration
      ? replay.headline + ' Source: puppytime-lost.' : (events.at(-1) || replay.task);
  }
  function frame(now) {
    if (playing && replay) {
      if (lastFrame !== null) time += now - lastFrame;
      if (time > replay.duration + 2500) time = 0;
      paint(time);
    }
    lastFrame = now;
    requestAnimationFrame(frame);
  }
  motion.addEventListener('click', () => {
    playing = !playing; motion.setAttribute('aria-pressed', String(playing));
    motion.textContent = playing ? 'Pause recorded run' : 'Play recorded run';
    if (reduced.matches && playing && replay) {time = replay.duration + 1000; paint(time); playing = false; motion.setAttribute('aria-pressed', 'false'); motion.textContent = 'Show recorded outcome';}
  });
  reduced.addEventListener('change', () => {if (reduced.matches) {playing = false; motion.setAttribute('aria-pressed', 'false'); motion.textContent = 'Show recorded outcome'; if(replay) paint(replay.duration + 1000);}});
  fetch('/api/studio/replays/puppytime-lost').then(r => {if(!r.ok) throw Error(); return r.json();}).then(r => {
    const visitors = r.tries[0];
    replay = {duration: Math.max(...visitors.map(v => v.end_ms)), task: r.job.text, headline: r.headline};
    const group = document.querySelector('#track-lanes');
    visitors.forEach((visitor, i) => {
      const y = 65 + i * 60;
      group.append(svg('path', {d: `M65 ${y} H540`, stroke: '#cdd8c2', 'stroke-width': 2, fill: 'none'}));
      const token = svg('g', {transform: 'translate(65,0)'});
      token.append(svg('circle', {cx: 0, cy: y, r: 14, fill: visitor.colour}), svg('text', {x: 0, y: y + 4, 'text-anchor':'middle', fill:'#fff', 'font-size':11}, visitor.phone ? 'P' : visitor.id.slice(0,1).toUpperCase()));
      const status = svg('text', {x:65, y:y+25, 'font-size':11, fill:'#53604d'});
      const stall = svg('text', {x: 362, y: y + 5, fill: '#a43e29', 'font-size': 20, visibility: 'hidden', 'aria-label': 'Visitor stalled'}, '×');
      group.append(token, status, stall); lanes.push({visitor, token, status, stall});
    });
    document.querySelector('#mission-caption').textContent = `Source: puppytime-lost / ${r.id}. ${visitors.length} recorded visitors. P = phone. Positions follow recorded step timing; Task and Keep transitions are schematic. Separate from the fresh-five batch below. No model call.`;
    paint(reduced.matches ? replay.duration + 1000 : 0);
    if (!reduced.matches) motion.click();
    requestAnimationFrame(frame);
  }).catch(() => {document.querySelector('#runway-event').textContent = 'Recorded run unavailable. Open the studio to inspect retained evidence.'; motion.disabled = true;});
  let currentPlan = null, currentHistory = {batches: [], runs: [], replays: []};
  let historyState = 'loading';
  const pending = {plan: false, history: false};
  async function getJSON(url) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(url, {cache: 'no-store', signal: controller.signal});
      if (!response.ok) throw new Error('Unavailable');
      return await response.json();
    } finally {clearTimeout(timer);}
  }
  function render(p, h) {
      const fresh = p.measured_batch;
      const signature = JSON.stringify([p, h.batches, fresh, historyState]);
      if (signature !== lastSignature) {
        lastSignature = signature;
        const batch = h.batches.find(b => p.apps.every(a => b.apps.some(r => matches(a, r))));
        const records = batch ? batch.apps : [];
        document.querySelector('#app-plan-source').textContent = `${p.apps.length} scoped apps. Source: ${p.source}. Queue source: ${batch ? 'batches/' + batch.id + '/queue.json' : 'no matching batch in this store'}.`;
        document.querySelector('#batch-summary').textContent = historyState !== 'ready'
          ? 'Local batch state unavailable or still loading. Historical app evidence remains available; previously shown queue states may be stale.' : batch
          ? `${records.filter(r => r.run_id).length} apps have a saved run ID in this batch. A run ID is not a confirmed completion.`
          : 'No matching batch in this local store. The measured historical launch failures are shown above.';
        const rows = document.querySelector('#app-plan-rows'); rows.replaceChildren();
        p.apps.forEach((app, index) => {
          const record = records.find(r => matches(app, r));
          const measured = fresh.apps.find(r => matches(app, r));
          const button = node('button', ''); button.type = 'button';
          button.append(node('span', app.id.toUpperCase()), node('strong', app.name), node('small', record ? record.status : measured ? 'Browser failed' : 'Not run'));
          button.dataset.status = record ? record.status : 'not-run';
          const select = () => {
            selected = app.id;
            for (const sibling of rows.children) sibling.setAttribute('aria-pressed', String(sibling === button));
            document.querySelector('#mission-name').textContent = app.name;
            document.querySelector('#mission-task').textContent = app.task;
            document.querySelector('#mission-url').textContent = new URL(app.url).hostname;
            document.querySelector('#mission-status').textContent = `Saved batch state: ${historyState !== 'ready' ? 'unavailable or loading' : record ? record.status : 'not run'}`;
            document.querySelector('#mission-kind').textContent = measured ? measured.kind : 'Scoped mission';
            const scene = document.querySelector('#mission-scene'); scene.replaceChildren();
            const symbols = {store: '▱', saas: '↗', booking: '▦', docs: '≡', vibe: '⌁'};
            scene.dataset.app = app.id;
            scene.append(node('span', symbols[app.id] || '↗'), node('strong', measured ? measured.kind : app.name));
            scene.append(node('p', measured ? `${measured.steps} browser steps / ${measured.confirmed} confirmed completions` : 'No measured result'));
            scene.append(node('p', measured ? measured.baseline.map(b => b.detail).join('. ') : 'Waiting for a real batch'));
            if (measured) scene.append(node('small', `Recorded ${measured.finished_at}. Browser never opened. No app verdict.`));
            document.querySelector('#fresh-five-source').textContent = `Historical source: ${fresh.source}. SHA-256 ${fresh.sha256}. This measured launch failure is separate from the current local queue.`;
            const link = document.querySelector('#mission-result'); link.hidden = !record?.run_id;
            if (record?.run_id) link.href = `/studio#runs/${encodeURIComponent(record.run_id)}`;
          };
          button.addEventListener('click', select); rows.append(button);
          if (selected === app.id || (!selected && index === 0)) select();
        });
      }
      const history = document.querySelector('#app-batch-history'); history.replaceChildren();
      for (const b of h.batches) {
        history.append(node('h4', `Batch ${b.id}`));
        for (const r of b.apps) {
          const line = node('p', `${r.name}: ${r.status}. `);
          if (r.run_id) {const link = node('a', 'Open saved result'); link.href = `/studio#runs/${encodeURIComponent(r.run_id)}`; line.append(link);}
          history.append(line);
        }
      }
      for (const r of [...h.runs, ...h.replays]) {
        const line = node('p', `${r.label || r.url || r.id}: ${(r.headline || r.status || 'recorded').replace(/[.!?]+$/, '')}. `);
        const link = node('a', 'Open record');
        link.href = `/studio#${r.label ? 'replays' : 'runs'}/${encodeURIComponent(r.id)}`;
        line.append(link); history.append(line);
      }
  }
  async function refreshPart(kind) {
    if (pending[kind]) return;
    pending[kind] = true;
    try {
      const value = await getJSON(kind === 'plan' ? '/api/landing/app-plan' : '/api/landing/batches');
      if (kind === 'plan') currentPlan = value;
      else {currentHistory = value; historyState = 'ready';}
      if (currentPlan) render(currentPlan, currentHistory);
    } catch (_) {
      lastSignature = null;
      if (kind === 'history') {
        historyState = 'unavailable';
        if (currentPlan) render(currentPlan, currentHistory);
      } else {
        document.querySelector('#app-plan-source').textContent = 'Plan unavailable or stale. Retrying locally; no coverage can be inferred.';
      }
    } finally {pending[kind] = false;}
  }
  function refresh() {return Promise.all([refreshPart('plan'), refreshPart('history')]);}
  refresh(); setInterval(refresh, 5000);
})();
