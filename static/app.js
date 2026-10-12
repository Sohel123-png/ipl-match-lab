const $ = (id) => document.getElementById(id);
let tossWinner = 'a';
let decision = 'bat';
let meta = null;

async function api(url, options = {}) {
  const response = await fetch(url, {headers: {'Content-Type': 'application/json'}, ...options});
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}
function pct(value) { return `${(Number(value) * 100).toFixed(1)}%`; }
function safeText(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function showToast(message) { const el = $('toast'); el.textContent = message; el.classList.add('show'); setTimeout(() => el.classList.remove('show'), 3000); }
function selectTab(name) {
  document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === `view-${name}`));
  const titles = {predict:'Match predictor', insights:'Season insights', report:'Model report'};
  $('pageTitle').textContent = titles[name] || 'Match predictor';
  if (name === 'insights' && !$('teamChart').dataset.loaded) loadInsights();
  if (name === 'report' && !$('reportChart').dataset.loaded) loadReport();
  window.scrollTo({top:0, behavior:'smooth'});
}
document.querySelectorAll('.nav-item').forEach(b => b.addEventListener('click', () => selectTab(b.dataset.tab)));
function wireSegmented(id, onPick, initial) {
  const wrap = $(id);
  wrap.querySelectorAll('button').forEach(btn => btn.addEventListener('click', () => {
    wrap.querySelectorAll('button').forEach(b => b.classList.toggle('selected', b === btn));
    onPick(btn.dataset.value);
  }));
  const selected = wrap.querySelector(`[data-value="${initial}"]`);
  if (selected) selected.classList.add('selected');
}
wireSegmented('tossChoices', v => tossWinner = v, 'a');
wireSegmented('decisionChoices', v => decision = v, 'bat');
function fillSelect(el, items, placeholder) {
  el.innerHTML = items.map((item, i) => `<option value="${safeText(item)}">${safeText(item)}</option>`).join('');
  if (placeholder && !items.length) el.innerHTML = '<option value="">No options available</option>';
}
async function init() {
  try {
    const [health, data] = await Promise.all([api('/api/health'), api('/api/meta')]);
    meta = data;
    fillSelect($('teamA'), data.teams);
    fillSelect($('teamB'), data.teams);
    fillSelect($('venue'), data.venues);
    $('teamA').value = data.teams.includes('Chennai Super Kings') ? 'Chennai Super Kings' : data.teams[0];
    $('teamB').value = data.teams.includes('Mumbai Indians') ? 'Mumbai Indians' : data.teams[Math.min(1, data.teams.length - 1)];
    $('heroMatches').textContent = Number(data.matches).toLocaleString('en-IN');
    $('systemStatus').textContent = `${Number(data.matches).toLocaleString('en-IN')} historical matches loaded`;
    $('modelStatus').textContent = health.status === 'ok' ? 'Operational' : 'Unavailable';
    $('insightsSeasons').textContent = `${data.seasons[0]}–${data.seasons[data.seasons.length - 1]} data`;
  } catch (error) {
    $('systemStatus').textContent = 'Model connection failed'; $('modelStatus').textContent = 'Offline';
    $('formError').textContent = error.message;
    showToast(`Could not connect to API: ${error.message}`);
  }
}
$('predictForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('formError').textContent = '';
  const teamA = $('teamA').value, teamB = $('teamB').value;
  if (teamA === teamB) { $('formError').textContent = 'Please select two different teams.'; return; }
  const button = $('predictBtn'); button.disabled = true; button.querySelector('span:first-child').textContent = 'Calculating…';
  try {
    const result = await api('/api/predict', {method:'POST', body:JSON.stringify({team_a:teamA,team_b:teamB,toss_winner:tossWinner === 'a' ? teamA : teamB,decision,venue:$('venue').value})});
    renderPrediction(result);
  } catch (error) {
    $('formError').textContent = error.message;
  } finally { button.disabled = false; button.querySelector('span:first-child').textContent = 'Generate prediction'; }
});
function renderPrediction(r) {
  $('resultPanel').innerHTML = `<div><div class="result-kicker">PREDICTION GENERATED</div><h3 class="result-heading">The numbers are in.</h3><p class="result-sub">${safeText(r.batting_first)} bats first · ${safeText(r.chasing)} chases</p>
    <div class="prob-row"><b>${safeText(r.batting_first)} <span style="color:#8b98aa;font-weight:400">· batting first</span></b><span>${pct(r.p_first)}</span></div><div class="prob-track"><div class="prob-fill" style="width:${Math.max(0,Math.min(100,r.p_first*100))}%"></div></div>
    <div class="prob-row"><b>${safeText(r.chasing)} <span style="color:#8b98aa;font-weight:400">· chasing</span></b><span style="color:var(--blue)">${pct(r.p_chase)}</span></div><div class="prob-track"><div class="prob-fill second" style="width:${Math.max(0,Math.min(100,r.p_chase*100))}%"></div></div>
    <div class="result-foot"><div class="mini-stat"><small>${safeText(r.batting_first)} · RECENT FORM</small><b>${pct(r.form_first)}</b></div><div class="mini-stat"><small>${safeText(r.chasing)} · RECENT FORM</small><b>${pct(r.form_chase)}</b></div></div>
    ${Math.abs(r.p_first-.5)<.1?'<div class="warning-list">This estimate is close to an even split. The model’s confidence has not been shown to reliably predict when it is correct.</div>':''}
    ${r.warnings?.length?`<div class="warning-list">${r.warnings.map(safeText).join('<br>')}</div>`:''}
    <p class="fine-print" style="text-align:left;margin-top:15px">${safeText(r.note)}</p></div>`;
  showToast('Prediction ready');
}
async function loadInsights() {
  $('teamChart').dataset.loaded = 'loading';
  try {
    const d = await api('/api/insights');
    $('metricMatches').textContent = Number(d.matches).toLocaleString('en-IN');
    $('metricChase').textContent = pct(d.chase_rate); $('metricToss').textContent = pct(d.toss_rate);
    $('chaseCI').textContent = `95% CI ${pct(d.chase_ci[0])}–${pct(d.chase_ci[1])} · p=${d.chase_p}`;
    $('tossCI').textContent = `95% CI ${pct(d.toss_ci[0])}–${pct(d.toss_ci[1])} · p=${d.toss_p}`;
    $('teamChart').innerHTML = d.teams.map(t => `<div class="bar-row"><span class="bar-name" title="${safeText(t.team)}">${safeText(t.team)}</span><div class="bar-track"><div class="bar-value" style="width:${Math.max(0,Math.min(100,t.win_rate*100))}%"></div></div><span class="bar-pct">${(t.win_rate*100).toFixed(1)}%</span></div>`).join('');
    const peak = Math.max(...d.chase_by_season.map(x => x.rate), 1);
    $('seasonChart').innerHTML = d.chase_by_season.map(x => `<div class="season-col"><span class="season-val">${x.rate.toFixed(0)}%</span><div class="season-bar" style="height:${Math.max(2,x.rate/peak*75)}%"></div><span class="season-label">${x.season}</span></div>`).join('');
    $('teamChart').dataset.loaded = 'true';
  } catch(e) { $('teamChart').dataset.loaded = ''; $('teamChart').innerHTML = `<p class="form-error">${safeText(e.message)}</p>`; }
}
async function loadReport() {
  $('reportChart').dataset.loaded = 'loading';
  try {
    const d = await api('/api/report');
    $('modelAccuracy').textContent = pct(d.model_accuracy); $('baselineAccuracy').textContent = pct(d.baseline_accuracy);
    const peak = 100;
    $('reportChart').innerHTML = `<div style="width:100%"><div class="legend"><span><i class="lime"></i>Model</span><span><i class="blue"></i>Baseline</span></div><div class="report-chart">${d.seasons.map(x=>`<div class="report-col"><div class="report-bars"><div class="report-bar model" title="Model ${pct(x.model)}" style="height:${Math.max(2,x.model*100/peak)}%"></div><div class="report-bar base" title="Baseline ${pct(x.baseline)}" style="height:${Math.max(2,x.baseline*100/peak)}%"></div></div><span class="season-label">${x.season}</span></div>`).join('')}</div></div>`;
    $('reportChart').dataset.loaded = 'true';
  } catch(e) { $('reportChart').dataset.loaded = ''; $('reportChart').innerHTML = `<p class="form-error">${safeText(e.message)}</p>`; }
}
init();
