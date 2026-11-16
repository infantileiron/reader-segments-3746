import {state} from '../stores/session.js';
import {esc} from '../utils/html.js';
import {badge} from '../components/common/status.js';
import {table} from '../components/common/table.js';
import {field,select} from '../components/common/fields.js';

function rangeText(ranges) {
  return (ranges || []).map(r => `${r.start}→${r.end}`).join('；') || '无有效订阅';
}

function basisBlock(basis, frozen) {
  if (!basis) return '';
  const counts = basis.counts || {};
  return `<details ${frozen ? 'open' : ''}><summary>${frozen ? '已冻结名单与依据' : '发送日可达依据'} · 发送日 ${esc(basis.send_date)} · 权益版本 v${esc(basis.entitlement_version)}（${counts.included ?? 0} 可达 / ${counts.excluded ?? 0} 排除）</summary>
    <p class="notice">${esc(basis.rule || '')}</p>
    ${table(['状态', '会员编号', '依据'], [
      ...(basis.included || []).map(r => ['可达/纳入', r.code, rangeText(r.ranges)]),
      ...(basis.excluded || []).map(r => ['排除', r.code, r.reason + (r.last_covered_end ? `（末次有效 ${r.last_covered_end}）` : '')]),
    ])}
    ${frozen ? '' : '<p>签核时会按同一完整权益版本重算并冻结名单；已签核名单不再变化。</p>'}
  </details>`;
}

export function render() {
  const successful = state.segments.filter(s => s.state === 'done');
  const today = new Date().toISOString().slice(0, 10);
  return `<div class="split"><section class="panel"><h2>内容建议，回到具体读者群</h2>
    <p class="notice">触达方案只在站内起草与签核，不自动外发。起草与签核都按发送日重算可达名单：当天有任一有效订阅区间即可达。签核后名单冻结，不再随订单修订漂移。</p>
    ${state.outreaches.map(o => `<article class="rec"><h3>${esc(o.title)} ${badge(o.status)}</h3>
      <p>分群版本 #${o.segment_id} · 群${o.cluster_id + 1} · 发送日 ${esc(o.send_date || '—')} · 权益版本 v${o.entitlement_version ?? '—'} · ${o.members.length}位可达</p>
      <p>${esc(o.note)}</p>
      <p class="member-line">${o.members.slice(0, 12).map(esc).join(' / ')}${o.members.length > 12 ? ' …' : ''}</p>
      ${basisBlock(o.entitlement_basis, o.status === 'approved')}
      ${o.status === 'approved' ? `<p class="eyebrow">签核 ${esc(o.approved_by || '')} · ${esc(o.approved_at || '')}</p>` : ''}
      ${state.user.role !== 'viewer' && o.status === 'draft' ? `<button data-outreach-refresh="${o.id}">按最新权益版本重算</button> ` : ''}
      ${state.user.role === 'admin' && o.status === 'draft' ? `<button data-approve="${o.id}">负责人签核</button> ` : ''}
      <button data-outreach-export="${o.id}">导出方案与成员</button></article>`).join('') || '<p>尚无触达方案。先完成分群，在这里写明内容主题、渠道假设与频次限制。</p>'}
  </section><aside class="side"><h2>起草触达方案</h2>
    <form id="outreach">${select('分群版本', 'segment_id', successful.map(s => [s.id, `#${s.id} ${s.name} · v${s.entitlement_version ?? '—'}`]))}
      ${select('群组号', 'cluster_id', [0, 1, 2, 3, 4, 5].map(n => [n, '群' + (n + 1)]))}
      <label>发送日<input name="send_date" type="date" value="${today}"></label>
      ${field('方案标题', 'title', 'text', 'required')}
      <label>内容主题、渠道与频次<textarea name="note" minlength="8" required rows="6"></textarea></label>
      <button class="primary">保存站内草案</button></form>
    <p>群组必须存在于所选版本。起草时按发送日与最新权益版本重算可达名单；签核时再按同一完整版本冻结。</p>
  </aside></div>`;
}
