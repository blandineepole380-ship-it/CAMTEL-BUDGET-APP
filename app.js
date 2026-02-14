const $ = (id) => document.getElementById(id);

async function api(path, opts={}){
  const res = await fetch(path, {
    headers: { 'Content-Type':'application/json', ...(opts.headers||{}) },
    credentials: 'include',
    ...opts
  });
  const txt = await res.text();
  let data;
  try { data = txt ? JSON.parse(txt) : null; } catch { data = txt; }
  if(!res.ok) throw new Error((data && data.detail) ? data.detail : `HTTP ${res.status}`);
  return data;
}

function setYears(){
  const now = new Date().getFullYear();
  const years = [now-1, now, now+1];
  for(const y of years){
    const o1 = document.createElement('option'); o1.value=y; o1.textContent=y;
    const o2 = o1.cloneNode(true);
    $('yearSel').appendChild(o1);
    $('fYear').appendChild(o2);
  }
  $('yearSel').value = now;
  $('fYear').value = now;
}

let budgets = [];
let txs = [];

async function loadBudgets(year){
  budgets = [];
  try{
    const data = await api(`/api/budgets/${year}`, {method:'GET'});
    // Accept either {items:[...]} or plain array
    budgets = Array.isArray(data) ? data : (data.items || data.budgets || []);
  }catch(e){
    budgets = [];
  }
  renderBudgetList();
}

function renderBudgetList(){
  const q = ($('fBudgetSearch').value||'').toLowerCase();
  const dir = $('fDir').value;
  const sel = $('fBudget');
  sel.innerHTML = '';

  const list = budgets
    .filter(b => !dir || (b.direction||b.Direction||'').toUpperCase().includes(dir.toUpperCase()) || (b.dir||'').toUpperCase()===dir.toUpperCase())
    .filter(b => {
      const text = `${b.label||b.name||''} ${b.code||b.budget_line||''} ${b.title||''}`.toLowerCase();
      return !q || text.includes(q);
    })
    .slice(0, 200);

  for(const b of list){
    const code = b.code || b.budget_line || b.compte || '';
    const title = b.title || b.label || b.name || '';
    const opt = document.createElement('option');
    opt.value = code;
    opt.textContent = `${code} — ${title}`.trim();
    sel.appendChild(opt);
  }
}

function fmt(n){
  try{ return new Intl.NumberFormat('fr-FR').format(Number(n||0)); }catch{ return String(n||0); }
}

async function refreshTx(){
  const year = $('yearSel').value;
  const direction = ''; // keep simple
  txs = await api(`/api/transactions?year=${encodeURIComponent(year)}${direction?`&direction=${encodeURIComponent(direction)}`:''}`);
  renderTable();
}

function renderTable(){
  const tbody = $('txTable').querySelector('tbody');
  tbody.innerHTML='';
  const q = ($('search').value||'').toLowerCase();
  const doc = $('docFilter').value;

  const list = txs.filter(t => {
    const hay = `${t.code_ref||''} ${t.title||''}`.toLowerCase();
    if(q && !hay.includes(q)) return false;
    if(doc && t.doc !== doc) return false;
    return true;
  });

  for(const t of list){
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${t.code_ref||''}</td>
      <td>${t.direction}</td>
      <td>${t.doc}</td>
      <td>${t.budget_line}</td>
      <td>${fmt(t.amount)}</td>
      <td>${t.tx_date}</td>
      <td><button class="btn" data-del="${t.id}">Delete</button></td>
    `;
    tr.addEventListener('click', (ev)=>{
      if(ev.target?.dataset?.del) return;
      $('detailsBox').innerHTML = `
        <div><b>${t.title}</b></div>
        <div class="muted">${t.code_ref} • ${t.direction} • ${t.doc} • ${t.tx_date}</div>
        <hr/>
        <div><b>Budget line:</b> ${t.budget_line}</div>
        <div><b>Amount:</b> ${fmt(t.amount)} FCFA</div>
      `;
    });
    tbody.appendChild(tr);
  }

  tbody.querySelectorAll('button[data-del]').forEach(btn=>{
    btn.addEventListener('click', async (ev)=>{
      ev.stopPropagation();
      const id = btn.dataset.del;
      if(!confirm('Delete this transaction?')) return;
      try{
        await api(`/api/transactions/${id}`, {method:'DELETE'});
        await refreshTx();
      }catch(e){
        alert(e.message);
      }
    });
  });
}

async function ensureLoggedIn(){
  try{
    const me = await api('/api/me', {method:'GET'});
    $('loginPanel').hidden = true;
    $('appPanel').hidden = false;
    $('userbox').hidden = false;
    $('username').textContent = me.username;
    await loadBudgets($('yearSel').value);
    await refreshTx();
  }catch{
    $('loginPanel').hidden = false;
    $('appPanel').hidden = true;
    $('userbox').hidden = true;
  }
}

function openNew(){
  $('saveMsg').textContent='';
  $('fYear').value = $('yearSel').value;
  $('fDir').value = 'DRH';
  $('fDoc').value = 'NC';
  $('fDate').value = new Date().toISOString().slice(0,10);
  $('fBudgetSearch').value='';
  $('fBudget').innerHTML='';
  $('fCode').value='';
  $('fTitle').value='';
  $('fAmount').value='';
  renderBudgetList();
  $('txDialog').showModal();
}

async function saveTx(){
  $('saveMsg').textContent='';
  const payload = {
    year: Number($('fYear').value),
    direction: $('fDir').value,
    doc: $('fDoc').value,
    budget_line: $('fBudget').value,
    title: $('fTitle').value,
    tx_date: $('fDate').value,
    amount: Number($('fAmount').value||0),
    code_ref: $('fCode').value || null
  };
  if(!payload.budget_line){ $('saveMsg').textContent = 'Select a budget line.'; return; }
  try{
    await api('/api/transactions', {method:'POST', body: JSON.stringify(payload)});
    $('txDialog').close();
    await refreshTx();
  }catch(e){
    $('saveMsg').textContent = e.message;
  }
}

// Events
window.addEventListener('load', async ()=>{
  setYears();
  $('loginBtn').addEventListener('click', async ()=>{
    $('loginMsg').textContent='';
    try{
      await api('/api/login', {method:'POST', body: JSON.stringify({username: $('loginUser').value, password: $('loginPass').value})});
      await ensureLoggedIn();
    }catch(e){
      $('loginMsg').textContent = e.message;
    }
  });

  $('logoutBtn').addEventListener('click', async ()=>{
    await api('/api/logout', {method:'POST'});
    await ensureLoggedIn();
  });

  $('refreshBtn').addEventListener('click', async ()=>{
    await loadBudgets($('yearSel').value);
    await refreshTx();
  });
  $('yearSel').addEventListener('change', async ()=>{
    await loadBudgets($('yearSel').value);
    await refreshTx();
  });

  $('search').addEventListener('input', renderTable);
  $('docFilter').addEventListener('change', renderTable);

  $('newBtn').addEventListener('click', openNew);
  $('fBudgetSearch').addEventListener('input', renderBudgetList);
  $('fDir').addEventListener('change', renderBudgetList);
  $('saveBtn').addEventListener('click', (ev)=>{ ev.preventDefault(); saveTx(); });

  await ensureLoggedIn();
});
