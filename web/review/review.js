(() => {
  const $ = s => document.querySelector(s);
  const api = async (path, options) => { const response = await fetch(path, options); const body = await response.json(); if (!response.ok) throw new Error(body.error || String(response.status)); return body; };
  const text = (tag, cls, value) => { const node = document.createElement(tag); if (cls) node.className = cls; node.textContent = value; return node; };
  const item = (title, detail) => { const node = text('div', 'item', ''); node.append(text('b', '', title), text('span', '', detail)); return node; };
  const fill = (target, rows, empty) => { target.replaceChildren(); if (!rows.length) target.append(text('p', 'empty', empty)); else rows.forEach(row => target.append(row)); };

  function show(run, id) {
    $('#progress').hidden = true; $('#report').hidden = false;
    const opened = (run.baseline || []).some(x => x.label === 'The page loads' && x.status === 'passed');
    $('#headline').textContent = opened ? (run.headline || 'The visitors finished.') : 'The review could not start.';
    $('#scope').textContent = `${run.url} · ${(run.job || {}).text || ''}`;
    $('#replay').href = `/studio#runs/${id}`;
    const people = (run.tries || [[]])[0], journey = $('#journey'); journey.replaceChildren();
    people.forEach(person => {
      const stopped = person.outcome !== 'got_there'; const node = text('div', 'person' + (stopped ? ' left' : ''), '');
      const last = (person.steps || []).slice(-1)[0] || {};
      const outcome = !opened ? 'Visit did not start' : stopped ? `Left at ${new URL(last.url || run.url).pathname || '/'}` : 'Finished the job';
      node.append(text('b', '', person.name || person.id), text('span', '', outcome));
      journey.append(node);
    });
    fill($('#works'), (run.baseline || []).filter(x => x.status === 'passed').map(x => item(x.label, x.detail)), 'No basic check passed.');
    const confirmedBreaks = (run.findings || []).filter(x => x.kind === 'error_page');
    fill($('#breaks'), confirmedBreaks.map(x => item(x.title, `${x.what_happened} · ${x.page}`)), 'No page error was confirmed.');
    const candidates = (run.findings || []).filter(x => x.kind !== 'error_page');
    fill($('#missing'), candidates.map(x => item(x.title, `Candidate only. Check ${x.page}`)), 'No repeated missing-feature candidate.');
  }

  async function poll(id) {
    const run = await api(`/api/studio/runs/${id}`);
    if (run.status === 'failed') throw new Error(run.error || 'The run failed.');
    if (run.status !== 'complete') return setTimeout(() => poll(id).catch(fail), 1300);
    show(run, id); $('#run button').disabled = false;
  }
  function fail(error) { $('#setup').textContent = error.message; $('#progress').hidden = true; $('#run button').disabled = false; }
  $('#run').addEventListener('submit', async event => {
    event.preventDefault(); $('#run button').disabled = true; $('#report').hidden = true; $('#progress').hidden = false;
    $('#progress-copy').textContent = 'Starting the review. No visitor has moved yet.';
    try {
      const result = await api('/api/studio/runs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:$('#url').value, task:$('#task').value, visitors:5})});
      $('#progress-copy').textContent = 'The run started. Software visitors are moving through the app.';
      poll(result.id).catch(fail);
    } catch (error) { fail(error); }
  });
})();
