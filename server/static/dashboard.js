const $ = s => document.querySelector(s);
let schedule = {}, offset = 0;
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path, method='GET', body) {
  const r = await fetch(path, {method, headers:{'Content-Type':'application/json','X-Requested-With':'pipeline-dashboard'}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await r.json();
  if (!r.ok) throw Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
function message(text, error=false) { $('#message').textContent=text; $('#message').className=error?'error':'success'; }
async function act(fn) { try { await fn(); } catch(e) { message(e.message,true); } }
async function refresh() {
  const data=await api('/api/status');
  $('#connection').textContent='Dashboard connected';
  $('#remote-state').textContent=data.remote_control?'Remote control held — collection cannot start until released.':'Remote control released.';
  $('#workers').innerHTML=data.workers.map(w=>`<p><strong>${esc(w.id)}</strong> · ${esc(w.action)} · heartbeat ${Math.max(0,Math.round(Date.now()/1000-w.heartbeat))}s ago<br><small>${esc(w.url)}</small></p>`).join('') || '<p>Worker service has not connected yet.</p>';
  $('#chat-status').textContent=`Webhook: ${data.chat.webhook_configured?'configured':'missing'} · HTML attachment credentials: ${data.chat.attachment_configured?'configured':'missing'}`;
  $('#runs').innerHTML=data.runs.map(r=>`<article><h3>${esc(r.start_date)} → ${esc(r.end_date)} <small>${esc(r.timezone)}</small></h3><p><strong>${esc(r.status)}</strong> · ${esc(r.phase)} · search page ${r.page} · ${esc(JSON.stringify(r.counts))}</p><p>${esc(r.error)}</p>${r.status==='cooldown'?`<p>Retry after ${new Date(r.retry_at*1000).toLocaleString()}</p>`:''}<p>Chat delivery: ${esc(r.delivery)} ${esc(r.delivery_error)}</p><div class="actions">${['pause','resume','stop','retry','compile','deliver'].map(c=>`<button data-run="${r.id}" data-command="${c}">${esc(c)}</button>`).join('')}${r.report?['html','csv','json'].map(k=>`<a href="/api/runs/${r.id}/export/${k}">Download ${k.toUpperCase()}</a>`).join(''):''}</div></article>`).join('') || '<p>No collection runs yet. Connect both browsers, then start a date window.</p>';
  $('#events').textContent=data.events.map(e=>`${new Date(e.at*1000).toLocaleString()} [${e.kind}] ${e.message}`).join('\n');
}
async function loadJobs() {
  const params=new URLSearchParams(new FormData($('#filter'))); for(const [k,v] of [...params]) if(!v) params.delete(k); params.set('offset',offset);
  const rows=await api('/api/jobs?'+params);
  $('#jobs').innerHTML=rows.map(r=>`<details><summary>${esc(r.posted_date)} · ${esc(r.data.job_title)} · ${esc((r.data.client||{}).location)}</summary><pre>${esc(JSON.stringify(r.data,null,2))}</pre></details>`).join('') || '<p>No saved jobs match this filter.</p>';
  $('#prev').disabled=offset===0; $('#next').disabled=rows.length<50;
}
$('#launch').onsubmit=e=>{e.preventDefault();act(async()=>{const d=Object.fromEntries(new FormData(e.target));d.timezone=schedule.timezone||'Asia/Kolkata';await api('/api/runs','POST',d);message('Collection queued.');await refresh();});};
$('#schedule').onsubmit=e=>{e.preventDefault();act(async()=>{const f=e.target,d=Object.fromEntries(new FormData(f));d.enabled=f.elements.enabled.checked;d.deliver_to_chat=f.elements.deliver_to_chat.checked;for(const k of ['days','jobs_per_minute','search_delay_seconds'])d[k]=Number(d[k]);schedule=await api('/api/schedule','PUT',d);message('Settings saved.');});};
$('#filter').onsubmit=e=>{e.preventDefault();offset=0;act(loadJobs);};
$('#prev').onclick=()=>{offset=Math.max(0,offset-50);act(loadJobs);};$('#next').onclick=()=>{offset+=50;act(loadJobs);};
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
  if(b.dataset.command)act(async()=>{await api(`/api/runs/${b.dataset.run}/${b.dataset.command}`,'POST',{});message('Command accepted.');await refresh();});
  if(b.dataset.browser)act(async()=>{await api('/api/browser/take-control','POST',{});const w=b.dataset.browser.toLowerCase();const a=document.createElement('a');a.href=`/browser/${w}/vnc.html?autoconnect=true&resize=scale&path=browser/${w}/websockify`;a.target='_blank';a.rel='noopener noreferrer';a.click();await refresh();});
  if(b.id==='release-remote')act(async()=>{await api('/api/browser/release-control','POST',{});message('Remote sessions disconnected. You can resume collection.');await refresh();});
  if(b.dataset.restart)act(async()=>{await api(`/api/browser/${b.dataset.restart}/restart`,'POST',{});message('Browser restart requested.');});
});
act(async()=>{schedule=await api('/api/schedule');const form=$('#schedule');for(const [k,v] of Object.entries(schedule)){const input=form.elements[k];if(input)input.type==='checkbox'?input.checked=v:input.value=v;}
 const yesterday=new Date(Date.now()-86400000).toLocaleDateString('en-CA',{timeZone:schedule.timezone});for(const x of $('#launch').querySelectorAll('input[type=date]'))x.value=yesterday;
 await refresh();await loadJobs();});
setInterval(()=>act(refresh),5000);
