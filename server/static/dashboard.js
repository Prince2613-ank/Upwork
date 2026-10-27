const $ = s => document.querySelector(s);
let schedule = {}, offset = 0, refreshBusy=false, browserMode='remote', activeTab='overview', analyticsAt=0, jobsKey='', knownJobs=null, freshUntil=new Map();
let displayContext=null, jobsAuto=true, launchEdited=false;
let reportRuns=[];
let browserWindowsVisible=false;
let speedDirty=false;
function renderWorkerSpeed(rate){
  if(!Number.isInteger(rate))return;
  schedule.jobs_per_minute=rate;
  if(!speedDirty)$('#worker-speed-rate').value=rate;
  $('#worker-speed-current').textContent=`Current: ${rate}/min each / ${rate*2}/min combined target`;
}
let overviewRunId=null;
const contextParams = () => new URLSearchParams({run_id:overviewRunId||'__no_current_run__'});
async function cleanLatestCollection(){
  while(refreshBusy) await new Promise(resolve=>setTimeout(resolve,50));
  const result=await api('/api/data/clean-latest','POST',{});
  jobsAuto=true;displayContext=null;overviewRunId=null;
  offset=0;knownJobs=null;jobsKey='';freshUntil.clear();
  $('#filter').reset();
  await refresh();await loadAnalytics();await loadSpeed();await loadJobs();
  message(`${result.deleted} jobs removed from Saved Jobs. HTML files are kept on Files.`);
}
function confirmClean(){
  const dialog=$('#clean-confirm');dialog.returnValue='';
  return new Promise(resolve=>{
    dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true});
    dialog.showModal();
  });
}
const csrf = () => decodeURIComponent(document.cookie.split('; ').find(c=>c.startsWith('flodata_csrf='))?.split('=')[1] || '');
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path, method='GET', body) {
  const r = await fetch(path, {method, signal:method==='GET'?AbortSignal.timeout(15000):undefined, headers:{'Content-Type':'application/json','X-Requested-With':'pipeline-dashboard','X-CSRF-Token':csrf()}, body: body === undefined ? undefined : JSON.stringify(body)});
  if(r.status===401){ window.location.replace('/login'); throw Error('Please sign in again.'); }
  const data = await r.json();
  if (!r.ok) throw Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
let messageTimer;
function message(text, error=false) {
  clearTimeout(messageTimer);
  const el=$('#message');el.hidden=false;el.textContent=text;el.className=error?'error':'success';
  messageTimer=setTimeout(()=>{el.textContent='';el.hidden=true;},5000);
}
function setConnection(connected){
  const el=$('#connection'),label=connected?'Connected':'Disconnected';
  el.className='sr-only';el.dataset.state=connected?'online':'offline';
  $('.topbar').dataset.connection=el.dataset.state;
  el.setAttribute('aria-label',label);el.title=label;el.querySelector('.sr-only').textContent=label;
}
async function act(fn) { try { await fn(); } catch(e) { message(e.message,true); } }
const reasonLabel = reason => ({ready:'Qualified',missing_description:'No description',incomplete_description:'Description incomplete',no_freelancer_reviews:'No written freelancer reviews',incomplete_reviews:'Review text incomplete',unverified_review_direction:'Review direction unverified',incomplete_history:'History pagination incomplete'}[reason] || reason);
const guidance = {
  queued:'Waiting for the worker service. Saved Upwork sessions will be reused.',
  running:'Fetching the selected window. You can leave this dashboard open for live updates.',
  cooldown:'Collection is paused for a cooldown. It will retry automatically after the displayed time.',
  needs_login:'Upwork login expired. Open the affected browser, log in, release remote control, then Resume.',
  needs_verification:'Upwork requires verification. Open the browser and resolve it manually, then Resume.',
  blocked:'Upwork restricted the account. Contact Upwork or resolve the restriction before resuming.',
  attention:'Automatic recovery was exhausted. Inspect the event details and remote browser.',
  paused:'Paused. Finish any remote browser work and release control before resuming.',
  completed:'Collection finished. Download the single filtered HTML report below.',
  partial:'A filtered HTML report is available, with unresolved collection gaps labelled in the file.',
  stopped:'Stopped. Saved records remain available; retry or compile a partial report if needed.'
};
const activeStatuses=['queued','running','cooldown','needs_login','needs_verification','blocked','attention','paused'];
function renderReportActions(){
  const run=reportRuns.find(r=>r.id===$('#report-run').value);
  if(!run){$('#report-actions').innerHTML='<small>No saved runs yet.</small>';return;}
  const commands=[];
  if((run.counts.failed||0)>0||run.status==='stopped')commands.push(['retry','Retry unfinished']);
  if(['paused','stopped','attention'].includes(run.status))commands.push(['compile','Prepare partial HTML']);
  if(run.report)commands.push(['deliver',run.delivery==='sent'?'Send to Chat again':'Send to Chat']);
  $('#report-actions').innerHTML=commands.map(([c,label])=>`<button data-run="${esc(run.id)}" data-command="${c}">${label}</button>`).join('')
    +(run.report?`<a class="download" href="/api/runs/${esc(run.id)}/export/html">Download single HTML report</a>`:'<small>No HTML report prepared for this collection yet.</small>');
}
function renderRunControls(data){
  // Display clearing must never hide controls for work that still exists on the server.
  const active=data.runs.find(r=>activeStatuses.includes(r.status));
  const controlled=active||(data.runs[0]?.status!=='cleaned'?data.runs[0]:null);
  $('#run-controls').hidden=!controlled;
  document.body.dataset.runState=controlled?.status||'idle';
  if(controlled){
    $('#controlled-run').innerHTML=`<span class="run-state ${esc(controlled.status)}">${esc(controlled.status)}</span>`;
    $('#controlled-run').removeAttribute('title');
    $('#control-guidance').textContent=guidance[controlled.status]||controlled.status;
    const actions=[];
    if(['running','queued'].includes(controlled.status)) actions.push(['pause','Pause']);
    if(['paused','attention','needs_login','needs_verification','blocked'].includes(controlled.status)) actions.push(['resume','Resume']);
    if(active) actions.push(['stop','Stop']);
    if(controlled.status==='stopped') actions.push(['retry','Resume unfinished']);
    $('#control-actions').innerHTML=actions.map(([command,label])=>`<button class="${command==='stop'?'danger':''}" data-run="${esc(controlled.id)}" data-command="${command}">${label}</button>`).join('');
  }else{$('#control-actions').replaceChildren();$('#controlled-run').textContent='';$('#control-guidance').textContent='';}
  const reason=active?'An existing collection is '+active.status+'. Use the navbar controls to resume it, or stop it before starting another window.':data.remote_control?'Release remote browser control before starting a collection.':'';
  const start=$('#launch button');start.disabled=!!reason;start.title=reason;
  $('#launch-availability').textContent='';
  $('#launch-availability').hidden=true;
}
async function refresh() {
  if(refreshBusy) return; refreshBusy=true;
  try {
    const data=await api('/api/status');
    if(!data.display_context) throw Error('Restart the dashboard API to load the daily analytics update. Collection data is preserved.');
    const context=data.display_context;
    renderWorkerSpeed(data.collection_speed);
    const changed=JSON.stringify(context)!==JSON.stringify(displayContext);
    displayContext=context;
    const currentRun=data.runs.find(r=>r.id===context.run_id);
    const latest=currentRun?.status!=='cleaned'?currentRun:null;
    overviewRunId=latest?.id||null;
    const visibleRuns=data.runs.filter(r=>r.status!=='cleaned');
    renderRunControls(data);
    const selectedReport=$('#report-run').value;
    reportRuns=data.runs;
    $('#report-run').innerHTML=reportRuns.map(r=>`<option value="${esc(r.id)}">${esc(r.start_date)} to ${esc(r.end_date)} / ${esc(r.status)} / ${esc(r.id.slice(0,6))}</option>`).join('');
    if(reportRuns.some(r=>r.id===selectedReport))$('#report-run').value=selectedReport;
    renderReportActions();
    if(changed){
      analyticsAt=0;
      if(jobsAuto){$('#filter').elements.start.value=context.start||'';$('#filter').elements.end.value=context.end||'';offset=0;knownJobs=null;jobsKey='';}
      if(!launchEdited){const day=new Date(context.day+'T12:00:00Z');day.setUTCDate(day.getUTCDate()-1);for(const x of $('#launch').querySelectorAll('input[type=date]'))x.value=day.toISOString().slice(0,10);}
    }
    const contextLabel=latest?`${latest.start_date} to ${latest.end_date} (${latest.timezone}) / current collection`:`${context.day} (${context.timezone}) / no collection started today`;
    $('#analytics-context').textContent=contextLabel;
    $('#jobs-context').textContent=jobsAuto?(currentRun?`${currentRun.start_date} to ${currentRun.end_date} (${currentRun.timezone}) / current collection`:`${context.day} / no collection started today`):'Historical data / selected filters';
    $('#collection-context').textContent=contextLabel;
    browserMode=data.browser_mode;
    browserWindowsVisible=!!data.browser_windows_visible;
    $('#toggle-browser-windows').hidden=browserMode!=='local_windows';
    $('#toggle-browser-windows').textContent=browserWindowsVisible?'Hide both browsers':'Show both browsers';
    $('#toggle-browser-windows').setAttribute('aria-pressed',String(browserWindowsVisible));
    $('#take-local-control').hidden=browserMode!=='local_windows';
    document.querySelectorAll('[data-browser]').forEach(el=>el.hidden=browserMode==='local_windows');
    $('#release-remote').hidden=!data.remote_control;
    setConnection(true);
    $('#remote-state').textContent=data.remote_control?'Manual control held. Release control to hide browsers.':browserMode==='local_windows'?(browserWindowsVisible?'Both browsers visible.':'Both browsers hidden / scraping in background.'):'Remote control released.';$('#remote-state').className='pill '+(data.remote_control?'bad':'ok');
    $('#workers').innerHTML=data.workers.map(w=>`<p><strong>Worker ${esc(w.id)}</strong> &middot; ${esc(w.action)} &middot; heartbeat ${Math.max(0,Math.round(Date.now()/1000-w.heartbeat))}s ago<br><small>${esc(w.url)}</small></p>`).join('') || '<p>Worker service has not connected yet.</p>';
    $('#chat-status').textContent=`Webhook: ${data.chat.webhook_configured?'configured':'missing'} / HTML credentials: ${data.chat.attachment_configured?'configured':'missing'}`;
    if(latest) {
      const count=latest.counts, quality=latest.quality||{}, collected=count.done||0, ready=quality.ready||0;
      const metrics=[['Status',latest.status],['Discovered',Object.values(count).reduce((a,b)=>a+b,0)],['Saved',collected],['Qualified',ready],['Excluded',collected-ready],['Pending',(count.pending||0)+(count.running||0)],['Skipped',count.unavailable||0],['Failed',count.failed||0]];
      $('#summary').innerHTML=metrics.map(([k,v])=>`<div class="metric"><small>${esc(k)}</small><strong class="${k==='Status'?'state-text '+esc(latest.status):''}">${esc(v)}</strong></div>`).join('');
      $('#run-guidance').textContent=guidance[latest.status]||latest.status;
      const total=Object.values(count).reduce((a,b)=>a+b,0);
      $('#progress').hidden=!total; $('#progress-bar').style.width=total?Math.round(100*((count.done||0)+(count.failed||0)+(count.unavailable||0)+(count.outside_window||0))/total)+'%':'0';
    }
    else {$('#summary').innerHTML='<p>No collection data. Select a date window above to begin.</p>';$('#run-guidance').textContent='';$('#progress').hidden=true;}
    $('#runs').innerHTML=visibleRuns.map(r=>{
      const release=r.release?`<p>${r.release.released} released / ${r.release.excluded} excluded / ${r.release.skipped||0} skipped. ${Object.entries(r.release.exclusion_reasons||{}).map(([k,v])=>`${esc(reasonLabel(k))}: ${v}`).join(' / ')}</p>`:'';
      return `<article><h3>${esc(r.start_date)} to ${esc(r.end_date)} <small>${esc(r.timezone)}</small></h3><p><strong>${esc(r.status)}</strong> &middot; ${esc(r.phase)} &middot; search page ${r.page}</p><p>${esc(r.error)}</p>${r.status==='cooldown'?`<p>Automatic retry after ${new Date(r.retry_at*1000).toLocaleString()}</p>`:''}${release}<p>Chat delivery: <strong>${esc(r.delivery)}</strong> ${esc(r.delivery_error)}</p><small>Prepared HTML reports are available on the Files page.</small></article>`;
    }).join('') || '<p>No collection history to show. Select dates above to start.</p>';
    const feed=latest?await api('/api/live-feed?run_id='+latest.id):[];
    $('#live-feed').innerHTML=feed.slice(0,4).map(item=>`<article><small>Worker ${esc(item.worker)} / ${esc(reasonLabel(item.release_check))}</small><h3>${esc(item.data.job_title)}</h3><p>${esc((item.data.client||{}).location)} &middot; ${item.data.client_recent_history?.filter(r=>r.feedback).length||0} written reviews</p><p>${esc(((item.data.job||{}).description||'No description').slice(0,240))}</p></article>`).join('') || '<p>Waiting for the first saved job in this run.</p>';
    if(activeTab==='files') await loadFiles();
    if(activeTab==='collection'&&offset===0) await loadJobs();
    if(activeTab==='overview'){ await loadSpeed(); await loadAnalytics(); }
  } catch(error){setConnection(false);throw error;}
  finally { refreshBusy=false; }
}
const field=(k,v)=>v?`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`:'';
async function loadJobs() {
  const params=new URLSearchParams(new FormData($('#filter'))); for(const [k,v] of [...params]) if(!v) params.delete(k); params.set('offset',offset); if(jobsAuto) params.set('run_id',displayContext?.run_id||'__no_current_run__');
  const rows=await api('/api/jobs?'+params);
  const key=offset+'|'+rows.map(r=>r.id+':'+r.last_seen+':'+r.release_check).join(',');
  if(key===jobsKey) return;
  jobsKey=key;
  const ids=new Set(rows.map(r=>r.id)), fresh=new Set();
  if(knownJobs&&offset===0) for(const id of ids) if(!knownJobs.has(id)) freshUntil.set(id,Date.now()+60000);
  if(offset===0) knownJobs=ids;
  for(const [id,until] of freshUntil) if(until>Date.now()) fresh.add(id);
  const expanded=new Set([...$('#jobs').querySelectorAll('details[open]')].map(e=>e.dataset.id));
  $('#jobs').innerHTML=rows.map(r=>{
    const d=r.data||{}, job=d.job||{}, c=d.client||{}, reviews=(d.client_recent_history||[]).filter(h=>h.feedback);
    const ok=r.release_check==='ready';
    return `<details data-id="${esc(r.id)}" ${expanded.has(r.id)?'open':''}><summary><strong>${esc(d.job_title||job.title||r.id)}</strong><span class="job-badges">${fresh.has(r.id)?'<span class="badge fresh">New</span>':''}<span class="badge qualification ${ok?'ready':'excluded'}" title="${esc(reasonLabel(r.release_check))}" aria-label="${ok?'Qualified':'Not qualified: '+esc(reasonLabel(r.release_check))}">${ok?'Qualified':'Not qualified'}</span></span><span class="meta">${esc(r.posted_date)} · ${esc(c.location||d.client_location||'Unknown location')} · ${esc(c.total_spent||'spend n/a')} · ${reviews.length} written reviews</span></summary>
      <div class="job-body"><dl>${field('Budget',job.budget||job.fixed_price)}${field('Experience',job.experience_level)}${field('Type',job.job_type)}${field('Skills',(job.skills||[]).join(', '))}${field('Rating',c.rating)}${field('Hire rate',c.hire_rate)}${field('Jobs posted',c.jobs_posted)}${field('Member since',c.member_since)}${field('Payment verified',c.payment_verified===true?'Yes':c.payment_verified===false?'No':'')}</dl>
      <div class="desc">${esc(job.description||d.description||'No description')}</div>
      ${reviews.length?`<h4 class="reviews-title">Freelancer reviews of this client (${reviews.length} of ${(d.client_recent_history||[]).length} contracts${d.history_expected?`, Upwork lists ${esc(d.history_expected)}`:''})</h4><div class="reviews">${reviews.map(h=>`<div class="review"><small>${esc(h.freelancer_name||'Freelancer')} · ${esc(h.rating||'')} · ${esc(h.job_title||'')}</small>${esc(h.feedback)}</div>`).join('')}</div>`:''}
      ${/^https:\/\/(www\.)?upwork\.com\//.test(d.job_url||'')?`<a href="${esc(d.job_url)}" target="_blank" rel="noopener noreferrer">Open on Upwork</a>`:''}</div></details>`;}).join('') || '<p class="empty">No saved jobs match this filter.</p>';
  $('#prev').disabled=offset===0; $('#next').disabled=rows.length<50;
  $('#page-label').textContent='Page '+(offset/50+1);
}
// ---- Overview charts: plain SVG sized by attributes (the strict CSP blocks inline styles) ----
const fmt=n=>Number(n).toLocaleString();
function hbars(el, pairs, cls='bar'){
  if(!pairs.length||!pairs.some(p=>p[1])){el.innerHTML='<p class="empty">No data in this range.</p>';return;}
  const max=Math.max(...pairs.map(p=>p[1])), W=el.clientWidth||400, H=el.clientHeight||pairs.length*28;
  const row=H/pairs.length,labelWidth=Math.min(145,Math.max(56,W*.3)),valueWidth=Math.max(30,fmt(max).length*7+10),barWidth=Math.max(10,W-labelWidth-valueWidth);
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Bar chart">${pairs.map(([label,n],i)=>{const w=Math.max(1,Math.round(barWidth*n/max)),y=i*row,barHeight=Math.min(16,row*.65),baseline=y+row*.65;
    return `<text x="0" y="${baseline}">${esc(String(label).slice(0,Math.floor(labelWidth/6)))}</text><rect class="${typeof cls==='function'?cls(label):cls}" x="${labelWidth}" y="${y+(row-barHeight)/2}" width="${w}" height="${barHeight}" rx="3"><title>${esc(label)}: ${fmt(n)}</title></rect><text class="val" x="${labelWidth+6+w}" y="${baseline}">${fmt(n)}</text>`;}).join('')}</svg>`;
}
function columns(el, points, label=p=>p.date.slice(5), tip=p=>`${p.date}: ${fmt(p.count)} jobs`, partial=false){
  if(!points.length){el.innerHTML='<p class="empty">No data in this range.</p>';return;}
  const max=Math.max(1,...points.map(p=>p.count)), W=el.clientWidth||640, H=Math.max(44,el.clientHeight||190), base=H-22, gap=2, bw=Math.max(1,(W-40)/points.length-gap);
  const every=Math.ceil(points.length/Math.max(2,Math.min(8,Math.floor((W-40)/68))));
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Jobs saved per minute"><line class="axis" x1="30" x2="${W}" y1="${base}" y2="${base}"/>${points.map((p,i)=>{const h=Math.round((base-18)*p.count/max),x=34+i*(bw+gap);
    return `<rect class="bar${partial&&i===points.length-1?' now':''}" x="${x}" y="${base-h}" width="${bw}" height="${h}" rx="2"><title>${esc(tip(p))}</title></rect>${i%every===0?`<text x="${x}" text-anchor="${x>W-70?'end':'start'}" y="${H-6}">${esc(label(p))}</text>`:''}`;}).join('')}</svg>`;
}
const clock=t=>new Date(t*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
async function loadSpeed(){
  const params=contextParams();params.set('minutes','15');
  const s=await api('/api/speed?'+params), cur=s.current_minute;
  const kpi=(k,v,sub='')=>`<div class="kpi"><small>${esc(k)}</small><strong>${esc(v)}</strong>${sub?`<small>${esc(sub)}</small>`:''}</div>`;
  $('#speed-kpis').innerHTML=kpi('Jobs / min (last 15 min)',s.jobs_per_min[15],`5 min: ${s.jobs_per_min[5]} ·`)
    +kpi('Reviews / min (last 15 min)',s.reviews_per_min[15],`5 min: ${s.reviews_per_min[5]} ·`)
    +kpi('This minute so far',cur.jobs,`${fmt(cur.reviews)} reviews · ${fmt(cur.qualified)} qualified`)
    +kpi('Saved in last 15 minutes',fmt(s.total_jobs),`${fmt(s.total_reviews)} reviews · ${fmt(s.total_qualified)} qualified · peak ${s.peak}/min`);
  columns($('#chart-speed'),s.per_minute.map(p=>({...p,count:p.jobs})),p=>clock(p.t),
    p=>`${clock(p.t)}: ${p.jobs} jobs, ${p.reviews} reviews, ${p.qualified} qualified`,true);
  $('#speed-updated').textContent='Live · updated '+new Date().toLocaleTimeString();
}
async function loadAnalytics(){
  const params=contextParams();
  const a=await api('/api/analytics?'+params); analyticsAt=Date.now();
  const kpi=(k,v,sub='')=>`<div class="kpi"><small>${esc(k)}</small><strong>${esc(v)}</strong>${sub?`<small>${esc(sub)}</small>`:''}</div>`;
  const pct=a.total?Math.round(100*a.release_ready/a.total)+'% of jobs':'';
  $('#kpis').innerHTML=kpi('Jobs saved',fmt(a.total))+kpi('Qualified',fmt(a.release_ready),pct)+kpi('Written reviews',fmt(a.written_reviews))+kpi('Payment verified',a.payment_verified_pct==null?'–':a.payment_verified_pct+'%')+kpi('Avg client hire rate',a.avg_hire_rate==null?'–':a.avg_hire_rate+'%');
  hbars($('#chart-countries'),a.countries);
}
async function loadFiles(){
  const rows=await api('/api/files');
  $('#files-count').textContent=rows.length+' HTML files';
  $('#files-list').innerHTML=rows.map(f=>`<article class="card file-card"><div class="file-symbol" aria-hidden="true">HTML</div><div class="file-details"><h3>${esc(f.name)}</h3><p class="muted">${esc(f.start?f.start+' to '+f.end:f.source)} / ${Math.max(1,Math.round(f.size/1024))} KB</p><small>Updated ${esc(new Date(f.updated_at*1000).toLocaleString())}${f.delivery?` / Google Chat: ${esc(f.delivery)}`:''}</small></div><a class="download" href="${esc(f.download_url)}">Download HTML</a></article>`).join('')||'<p class="empty">No HTML files found. Completed collection reports will appear here.</p>';
}
// ---- Tabs and saved-job filters ----
function showTab(name){
  if(name==='jobs')name='collection';
  activeTab=name;
  document.body.dataset.page=name;
  document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab===name)));
  document.querySelectorAll('.tab').forEach(t=>t.hidden=t.id!=='tab-'+name);
  try{history.replaceState(null,'','#'+name);}catch{}
  if(name==='files') act(loadFiles);
  if(name==='collection') act(loadJobs);
  if(name==='overview'){ act(loadAnalytics); act(loadSpeed); }
}
$('#tabs').onclick=e=>{const b=e.target.closest('[data-tab]'); if(b) showTab(b.dataset.tab);};
$('#report-run').onchange=renderReportActions;
$('#worker-speed-rate').oninput=()=>{speedDirty=true;};
$('#worker-speed').onsubmit=e=>{e.preventDefault();act(async()=>{
  const button=e.target.querySelector('button');button.disabled=true;
  try{
    const result=await api('/api/collection-speed','PUT',{jobs_per_minute:Number($('#worker-speed-rate').value)});
    speedDirty=false;renderWorkerSpeed(result.jobs_per_minute);
    $('#schedule').elements.jobs_per_minute.value=result.jobs_per_minute;
    message(`Speed applied: ${result.jobs_per_minute} jobs/minute per worker. Effective on the next fetch.`);
  }finally{button.disabled=false;}
});};
$('#launch').addEventListener('input',()=>{launchEdited=true;});
$('#launch').onsubmit=e=>{e.preventDefault();act(async()=>{const d=Object.fromEntries(new FormData(e.target));d.timezone=schedule.timezone||'UTC';await api('/api/runs','POST',d);jobsAuto=true;displayContext=null;$('#filter').elements.start.value=d.start_date;$('#filter').elements.end.value=d.end_date;offset=0;message('Collection queued. Saved sessions will be reused.');await refresh();});};
$('#schedule').onsubmit=e=>{e.preventDefault();act(async()=>{const f=e.target,d=Object.fromEntries(new FormData(f));d.enabled=f.elements.enabled.checked;d.deliver_to_chat=f.elements.deliver_to_chat.checked;for(const k of ['days','jobs_per_minute','search_delay_seconds'])d[k]=Number(d[k]);schedule=await api('/api/schedule','PUT',d);message('Settings saved.');});};
$('#filter').onsubmit=e=>{e.preventDefault();jobsAuto=false;$('#jobs-context').textContent='Historical data / selected filters';offset=0;knownJobs=null;jobsKey='';act(loadJobs);};
$('#prev').onclick=()=>{offset=Math.max(0,offset-50);act(loadJobs);};$('#next').onclick=()=>{offset+=50;act(loadJobs);};
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
  if(b.hasAttribute('data-clear-view'))act(async()=>{
    if(!await confirmClean())return;
    document.querySelectorAll('[data-clear-view]').forEach(el=>el.disabled=true);
    try {await cleanLatestCollection();}
    finally {document.querySelectorAll('[data-clear-view]').forEach(el=>el.disabled=false);}
  });
  if(b.id==='logout')act(async()=>{await api('/api/auth/logout','POST',{});window.location.replace('/login');});
  if(b.id==='toggle-browser-windows')act(async()=>{
    b.disabled=true;
    try{const result=await api('/api/browser/visibility','PUT',{visible:!browserWindowsVisible});browserWindowsVisible=result.visible;await refresh();}
    finally{b.disabled=false;}
  });
  if(b.id==='take-local-control')act(async()=>{await api('/api/browser/take-control','POST',{});message('Both browsers are visible for login. Release control when finished.');await refresh();});
  if(b.dataset.command)act(async()=>{await api(`/api/runs/${b.dataset.run}/${b.dataset.command}`,'POST',{});message('Command accepted.');await refresh();});
  if(b.dataset.browser)act(async()=>{await api('/api/browser/take-control','POST',{});if(browserMode==='local_windows'){message('The dedicated Upwork browser windows will open on this computer. Log in, then release remote control.');await refresh();return;}const w=b.dataset.browser.toLowerCase();const a=document.createElement('a');a.href=`/browser/${w}/vnc.html?autoconnect=true&resize=scale&path=browser/${w}/websockify`;a.target='_blank';a.rel='noopener noreferrer';a.click();await refresh();});
  if(b.id==='release-remote')act(async()=>{await api('/api/browser/release-control','POST',{});message('Control released. Both browsers are hidden.');await refresh();});
  if(b.dataset.restart)act(async()=>{await api(`/api/browser/${b.dataset.restart}/restart`,'POST',{});message('Browser restart requested.');});
});
act(async()=>{schedule=await api('/api/schedule');const form=$('#schedule');for(const [k,v] of Object.entries(schedule)){const input=form.elements[k];if(input)input.type==='checkbox'?input.checked=v:input.value=v;}
 const yesterday=new Date(Date.now()-86400000).toLocaleDateString('en-CA',{timeZone:schedule.timezone});for(const x of $('#launch').querySelectorAll('input[type=date]'))x.value=yesterday;
 await refresh();
 const initial=location.hash.slice(1)==='jobs'?'collection':location.hash.slice(1); showTab(document.querySelector('[data-tab="'+initial+'"]')?initial:'overview');});
setInterval(()=>act(refresh),5000);
window.addEventListener('offline',()=>setConnection(false));
window.addEventListener('online',()=>act(refresh));

let overviewResizeTimer;
window.addEventListener('resize',()=>{clearTimeout(overviewResizeTimer);overviewResizeTimer=setTimeout(()=>{if(activeTab==='overview')act(async()=>{await loadSpeed();await loadAnalytics();});},150);});
