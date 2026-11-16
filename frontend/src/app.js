import {api, post} from './api/client.js';
import {state} from './stores/session.js';
import {routes, page} from './router/index.js';
import {values, feedback} from './hooks/form.js';
import {esc} from './utils/html.js';
import * as readers from './pages/readers.js';
import * as entitlements from './pages/entitlements.js';
import * as features from './pages/features.js';
import * as map from './pages/map.js';
import * as outreach from './pages/outreach.js';

const root = document.querySelector('#app');
const pages = [readers, entitlements, features, map, outreach];

async function load() {
  const [readers_, segments_, outreaches_, batches_, versions_] = await Promise.all(
    ['/readers', '/segments', '/outreaches', '/batches', '/entitlements'].map(x => api(x))
  );
  state.readers = readers_;
  state.segments = segments_;
  state.outreaches = outreaches_;
  state.batches = batches_;
  state.versions = versions_;
  state.selected = state.segments.find(s => s.id === state.selected?.id) || state.segments[0] || null;
  if (state.versions[0]) {
    try {
      state.entitlement = await api('/entitlements/' + state.versions[0].version);
    } catch (e) {
      state.entitlement = null;
    }
  } else {
    state.entitlement = null;
  }
}

function login() {
  root.innerHTML = `<div class="login"><section class="cover"><div class="eyebrow">SHAN LAN / READER EDITION 007</div><h1>权益先于分群，<br>名单先于触达。</h1><p>山岚内容社 · 会员编辑部<br>从订阅订单修订生成完整权益版本，按自然周取样分群，再按发送日重算可达会员。<br>240位会员 / 三个行为维度 / 站内触达方案</p></section><section><div class="eyebrow">READER SEGMENTS</div><h2>登录会员编辑部</h2><form id="login"><label>工作邮箱<input name="email" type="email" value="analyst@demo.local" required></label><label>密码<input name="password" type="password" value="Demo123!" required></label><button class="primary">进入会员分群</button></form><p id="error" class="error"></p><p>演示：admin / analyst / viewer @demo.local<br>密码：Demo123!</p></section></div>`;
  document.querySelector('form').onsubmit = e => {
    e.preventDefault();
    run(async () => {
      let d = await post('/auth/login', values(e.target));
      localStorage.setItem('token', d.token);
      state.user = d.user;
      await load();
      render();
    });
  };
}

function render() {
  let n = Math.min(pages.length - 1, Math.max(0, page()));
  root.innerHTML = `<header><div class="brand">山岚 / 会员编辑部 <span class="eyebrow">READER SEGMENTS</span></div><div>${esc(state.user.email)} · ${esc(state.user.role)} <button id="logout">退出</button></div></header><div class="layout"><nav>${routes.map((r, i) => `<button data-nav="${i}" class="${i === n ? 'active' : ''}">0${i + 1} ${r}</button>`).join('')}<p class="eyebrow">EDITORIAL NOTES<br>2026 / SHAN LAN</p></nav><main><div class="intro"><div><div class="eyebrow">AUDIENCE RESEARCH / 0${n + 1}</div><h1>${routes[n]}</h1><p>以行为相似性制定内容建议，保留样本、特征与群组画像；每个群组与方案都能回到同一完整权益版本。</p></div><span class="tag">阅读行为 / 版本留痕</span></div><p id="error" class="error"></p>${pages[n].render()}</main></div>`;
  bind();
  if (state.user.role === 'viewer') document.querySelectorAll('form button').forEach(b => { b.disabled = true; b.textContent = '观察员只读'; });
}

async function run(fn) {
  try { await fn(); } catch (e) { feedback(e.message); }
}

function bind() {
  document.querySelectorAll('[data-nav]').forEach(b => b.onclick = () => location.hash = b.dataset.nav);
  document.querySelector('#logout').onclick = () => { localStorage.removeItem('token'); state.user = null; login(); };
  for (let [id, path] of [['reader', '/readers'], ['segment', '/segments'], ['outreach', '/outreaches']]) {
    let f = document.querySelector('#' + id);
    if (!f) continue;
    f.onsubmit = e => {
      e.preventDefault();
      run(async () => {
        let d = values(f);
        for (let k of ['weekly_reading', 'completion', 'night_share', 'k', 'segment_id', 'cluster_id']) if (k in d) d[k] = Number(d[k]);
        if (id === 'segment') {
          d.features = Array.from(f.querySelectorAll('[name=features]:checked')).map(c => c.value);
          if (d.week_start) {
            let day = new Date(d.week_start + 'T00:00:00Z');
            let shift = (day.getUTCDay() + 6) % 7;
            day.setUTCDate(day.getUTCDate() - shift);
            d.week_start = day.toISOString().slice(0, 10);
          } else delete d.week_start;
          d.entitlement_version = d.entitlement_version ? Number(d.entitlement_version) : null;
          if (!d.entitlement_version) delete d.entitlement_version;
        }
        if (id === 'outreach' && !d.send_date) delete d.send_date;
        if (id === 'segment' && !d.week_start) delete d.week_start;
        let record = d.record_id;
        delete d.record_id;
        let created = record ? await api(path + '/' + record, {method: 'PUT', body: JSON.stringify(d)}) : await post(path, d);
        if (id === 'segment') { state.selected = created; state.cluster = 0; }
        await load();
        if (id === 'segment') location.hash = '3';
        render();
      });
    };
  }
  const batchForm = document.querySelector('#batch');
  if (batchForm) {
    batchForm.onsubmit = e => {
      e.preventDefault();
      run(async () => {
        let d = values(batchForm);
        let rows;
        try { rows = JSON.parse(d.rows); } catch (err) { throw Error('订单修订不是合法 JSON：' + err.message); }
        if (!Array.isArray(rows)) throw Error('订单修订必须是 JSON 数组');
        let payload = {name: d.name || '', rows};
        if (d.import_key) payload.import_key = d.import_key;
        await post('/batches', payload);
        await load();
        render();
      });
    };
  }
  document.querySelectorAll('[data-verify]').forEach(b => b.onclick = () => run(async () => {
    await post('/batches/' + b.dataset.verify + '/verify', {});
    await load(); render();
  }));
  document.querySelectorAll('[data-version]').forEach(b => b.onclick = () => run(async () => {
    state.entitlement = await api('/entitlements/' + b.dataset.version);
    render();
  }));
  document.querySelectorAll('[data-segment]').forEach(b => b.onclick = () => run(async () => {
    state.selected = await api('/segments/' + b.dataset.segment);
    state.cluster = 0;
    location.hash = '3';
    render();
    window.scrollTo(0, 0);
  }));
  document.querySelectorAll('[data-cluster]').forEach(b => b.onclick = () => { state.cluster = Number(b.dataset.cluster); render(); });
  document.querySelectorAll('[data-approve]').forEach(b => b.onclick = () => run(async () => {
    await post('/outreaches/' + b.dataset.approve + '/approve', {});
    await load(); render();
  }));
  document.querySelectorAll('[data-outreach-refresh]').forEach(b => b.onclick = () => run(async () => {
    await post('/outreaches/' + b.dataset.outreachRefresh + '/refresh', {});
    await load(); render();
  }));
  let refresh = document.querySelector('#refresh');
  if (refresh) refresh.onclick = () => run(async () => { await load(); render(); });
  let download = document.querySelector('#download');
  if (download) download.onclick = () => run(() => downloadJSON('/segments/' + state.selected.id + '/export', 'reader-segments-' + state.selected.id));
  document.querySelectorAll('[data-outreach-export]').forEach(b => b.onclick = () => run(() => downloadJSON('/outreaches/' + b.dataset.outreachExport + '/export', 'reader-outreach-' + b.dataset.outreachExport)));
}

async function downloadJSON(path, name) {
  let d = await api(path);
  let u = URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], {type: 'application/json'}));
  let a = document.createElement('a');
  a.href = u;
  a.download = name + '.json';
  a.click();
  URL.revokeObjectURL(u);
}

window.onhashchange = () => { if (state.user) { render(); window.scrollTo(0, 0); } };
if (localStorage.getItem('token')) run(async () => {
  try { state.user = await api('/me'); await load(); render(); }
  catch (e) { localStorage.removeItem('token'); login(); feedback(e.message); }
});
else login();
