(() => {
  const svg = document.querySelector('#swarm-map');
  if (!svg) return;

  const ns = 'http://www.w3.org/2000/svg';
  const picker = document.querySelector('.app-picker');
  const job = document.querySelector('#swarm-job');
  const result = document.querySelector('#swarm-result');
  const source = document.querySelector('#swarm-source');
  const open = document.querySelector('#swarm-open');
  const replay = document.querySelector('#swarm-replay');
  const colours = ['#2459d3', '#142033', '#6687bd'];
  let selected = 'puppytime-lost';
  let retained = null;

  const node = (tag, attrs = {}, text = '') => {
    const item = document.createElementNS(ns, tag);
    for (const [name, value] of Object.entries(attrs)) item.setAttribute(name, String(value));
    if (text) item.textContent = text;
    return item;
  };

  const shortPath = value => {
    try {
      const url = new URL(value);
      const path = url.pathname.split('/').filter(Boolean).pop() || 'home';
      return path.replace(/\.html$/, '') || 'home';
    } catch {
      return 'screen';
    }
  };

  function pointsFor(steps, index) {
    const lane = 105 + index * 88;
    const points = steps.map((step, stepIndex) => {
      const x = 78 + stepIndex * Math.min(105, 560 / Math.max(1, steps.length - 1));
      const statusShift = step.status === 'error_page' ? 34 : step.status === 'got_there' ? -28 : 0;
      return [x, lane + statusShift + (stepIndex % 2 ? 8 : -8)];
    });
    if (points.length === 1) points.push([points[0][0] + 80, points[0][1]]);
    return points;
  }

  function pathFor(steps, index) {
    const points = pointsFor(steps, index);
    return points.reduce((d, point, pointIndex) => {
      if (!pointIndex) return `M ${point[0]} ${point[1]}`;
      const previous = points[pointIndex - 1];
      const middle = (previous[0] + point[0]) / 2;
      return `${d} C ${middle} ${previous[1]}, ${middle} ${point[1]}, ${point[0]} ${point[1]}`;
    }, '');
  }

  function draw(data, animate = true) {
    retained = data;
    const visitors = data.tries?.[0] || [];
    svg.replaceChildren();
    svg.setAttribute('aria-label', `Recorded visitor paths through ${data.replay?.label || selected}`);

    svg.append(node('text', {x: 34, y: 38, class: 'map-label'}, 'START'));
    svg.append(node('text', {x: 655, y: 38, class: 'map-label'}, 'RESULT'));
    svg.append(node('line', {x1: 76, y1: 55, x2: 76, y2: 350, class: 'map-axis'}));
    svg.append(node('line', {x1: 686, y1: 55, x2: 686, y2: 350, class: 'map-axis'}));

    visitors.forEach((visitor, index) => {
      const colour = colours[index % colours.length];
      const steps = visitor.steps || [];
      const points = pointsFor(steps, index);
      const d = pathFor(steps, index);
      const lane = node('g', {'data-visitor': visitor.id || index});
      lane.append(node('path', {d, class: 'agent-path', stroke: colour}));
      steps.forEach((step, stepIndex) => {
        const [x, y] = points[stepIndex];
        lane.append(node('circle', {cx: x, cy: y, r: stepIndex === steps.length - 1 ? 7 : 3.5, fill: colour, class: 'step-dot'}));
        if (stepIndex === steps.length - 1 || step.status === 'error_page') {
          const anchor = x > 590 ? 'end' : 'middle';
          lane.append(node('text', {x: x > 590 ? x - 4 : x, y: y + 23, class: 'screen-label', 'text-anchor': anchor}, shortPath(step.url)));
        }
      });
      lane.append(node('text', {x: 84, y: 75 + index * 88, class: 'visitor-label', fill: colour}, visitor.name || visitor.id || `Visitor ${index + 1}`));
      if (animate && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
        const agent = node('circle', {r: 6, fill: colour, class: 'moving-agent', 'aria-hidden': 'true'});
        const motion = node('animateMotion', {dur: '2.4s', begin: `${index * 0.18}s`, path: d, fill: 'freeze', calcMode: 'spline', keySplines: '.23 1 .32 1'});
        agent.append(motion);
        lane.append(agent);
      }
      svg.append(lane);
    });

    job.textContent = `Job: ${data.job?.text || 'Task not recorded'}`;
    result.textContent = data.headline || 'The retained run has no summary.';
    source.textContent = `Source run: ${data.replay?.name || data.id || selected} · ${visitors.length} retained visitors · playback makes no model call.`;
    open.href = `/studio#replays/${selected}`;
  }

  async function load(name) {
    selected = name;
    picker.setAttribute('aria-busy', 'true');
    for (const button of picker.querySelectorAll('[data-replay]')) button.setAttribute('aria-pressed', String(button.dataset.replay === name));
    try {
      const response = await fetch(`/api/studio/replays/${encodeURIComponent(name)}`);
      if (!response.ok) throw new Error('Recorded run unavailable.');
      draw(await response.json());
    } catch (error) {
      job.textContent = 'The selected run could not be loaded.';
      result.textContent = error.message;
      source.textContent = 'No replacement or sample data was drawn.';
      svg.replaceChildren();
    } finally {
      picker.removeAttribute('aria-busy');
    }
  }

  async function loadOutside() {
    const cards = document.querySelector('#outside-results');
    const scope = document.querySelector('#outside-scope');
    const sourceLine = document.querySelector('#outside-source');
    try {
      const response = await fetch('/api/landing/outside-run');
      if (!response.ok) throw new Error('Outside rehearsal result unavailable.');
      const data = await response.json();
      if (data.status !== 'complete' || data.tools?.length !== 3) return;
      cards.replaceChildren();
      let attempted = 0;
      let passed = 0;
      data.tools.forEach((tool, index) => {
        attempted += tool.attempted;
        passed += tool.passed;
        const article = document.createElement('article');
        const rank = document.createElement('div');
        rank.className = 'tool-rank';
        const number = document.createElement('span');
        number.textContent = String(index + 1).padStart(2, '0');
        const name = document.createElement('strong');
        name.textContent = tool.name;
        rank.append(number, name);
        const task = document.createElement('p');
        task.textContent = tool.task;
        const score = document.createElement('div');
        score.className = 'score';
        const scoreValue = document.createElement('span');
        scoreValue.textContent = `${tool.passed}/${tool.attempted}`;
        const label = document.createElement('small');
        label.textContent = 'independent output checks';
        score.append(scoreValue, label);
        const outcome = document.createElement('p');
        outcome.className = 'outcome';
        outcome.textContent = `${tool.headline} ${tool.finding}`;
        const toolSource = document.createElement('a');
        toolSource.href = tool.source;
        toolSource.textContent = tool.version;
        article.append(rank, task, score, outcome, toolSource);
        cards.append(article);
      });
      document.querySelector('#outside-tools').textContent = String(data.tools.length);
      document.querySelector('#outside-attempts').textContent = String(attempted);
      document.querySelector('#outside-passes').textContent = `${passed}/${attempted}`;
      scope.textContent = data.scope;
      sourceLine.textContent = `Fresh run finished ${data.finished_at}. Model: ${data.model}. Provider: ${data.provider}.`;
    } catch (error) {
      scope.textContent = error.message;
    }
  }

  picker.addEventListener('click', event => {
    const button = event.target.closest('[data-replay]');
    if (button) load(button.dataset.replay);
  });
  replay.addEventListener('click', () => retained && draw(retained));
  load(selected);
  loadOutside();
})();
