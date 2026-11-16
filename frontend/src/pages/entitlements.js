import {state} from '../stores/session.js';
import {esc} from '../utils/html.js';
import {badge} from '../components/common/status.js';
import {table} from '../components/common/table.js';
import {field} from '../components/common/fields.js';
import {BATCH_STATE_LABELS} from '../constants/enums.js';

function versionCountsRender(detail) {
  if (!detail) return '';
  return `<div class="metrics"><div><strong>${detail.members}</strong>有权益会员</div><div><strong>${detail.ranges}</strong>合并区间</div><div><strong>v${detail.version}</strong>当前查看</div></div>`;
}

function rangeText(ranges) {
  return (ranges || []).map(r => `${r.start}→${r.end}（${r.days}天）`).join('；') || '无有效区间';
}

export function render() {
  const version = state.versions[0];
  const detail = state.entitlement;
  return `<div class="split"><section class="panel">
    <h2>订阅订单修订与权益版本</h2>
    <p class="notice">每行记录订单、会员编号、有效起止日与修订号。同一订单只接纳修订号最大的记录，迟到旧修订只留痕不回退；退款截断对应订单，其他订单继续有效；重叠订阅合并后按自然日计天。</p>
    ${versionCountsRender(detail)}
    <h3>版本台账</h3>
    ${table(['版本', '批次', '会员', '区间', '校验和', '生成时间'], state.versions.map(v => ['v' + v.version, '#' + v.batch_id, v.members, v.ranges, (v.checksum || '').slice(0, 12), v.created]))}
    ${version ? `<p><button data-version="${version.version}">查看 v${version.version} 的会员区间</button></p>` : ''}
    ${detail ? `<details open><summary>v${detail.version} 会员有效区间（合并、截断后）</summary>${table(['会员编号', '区间', '天数', '来源订单'], (detail.ranges || []).map(r => [r.member_code, `${r.start}→${r.end}`, r.days, (r.orders || []).join(' / ')]))}</details>` : ''}
    <h3>订阅批次</h3>
    ${table(['批次', '状态', '总行', '接纳', '重复', '坏行', '被取代', '权益版本'], state.batches.map(b => ['#' + b.id + ' ' + (b.name || ''), BATCH_STATE_LABELS[b.state] || b.state, b.total_rows, b.accepted_rows, b.duplicate_rows, b.rejected_rows, b.superseded_rows, b.entitlement_version ? 'v' + b.entitlement_version : '—']))}
    ${state.batches.map(b => `<article class="rec"><h3>批次 #${b.id} ${badge(BATCH_STATE_LABELS[b.state] || b.state)}</h3>
      <p>提交 ${b.accepted_rows} 行，重复 ${b.duplicate_rows}，坏行 ${b.rejected_rows}，被更高修订取代 ${b.superseded_rows}。</p>
      ${b.rejected?.length ? `<details><summary>坏行与不可变冲突（${b.rejected.length}）</summary>${table(['行号', '原因'], b.rejected.map(r => [r.line, r.reason]))}</details>` : ''}
      ${b.events?.length ? `<details><summary>已记账明细（${b.events.length}）</summary>${table(['行', '订单', '会员', '修订', '生效', '失效', '退款', '最新'], b.events.map(e => [e.line, e.order_no, e.member_code, e.revision, e.effective_start, e.effective_end, e.refunded_on || '—', e.is_latest ? '是' : '被取代']))}</details>` : ''}
      ${b.state === 'pending' && state.user.role === 'admin' ? `<button data-verify="${b.id}">核验并生效</button>` : ''}
    </article>`).join('') || '<p>尚无订阅批次。用右侧文本框粘贴订单修订 JSON 数组。</p>'}
  </section><aside class="side"><h2>导入订单修订</h2>
    <form id="batch">
      ${field('批次名称', 'name', 'text', '')}
      <label>导入幂等键（重试请保持不变）<input name="import_key" type="text" placeholder="例如 2026-11-16-orders"></label>
      <label>订单修订（JSON 数组）<textarea name="rows" rows="12" required>[
 {"order_no":"ORD-101","member_code":"SL-241","revision":1,"effective_start":"2026-11-09","effective_end":"2026-12-31","refunded_on":null}
]</textarea></label>
      <p>坏行会被隔离并列出原因，正常行照常入账。核验生效后生成新的完整权益版本。</p>
      <button class="primary">提交待核验批次</button>
    </form>
  </aside></div>`;
}
