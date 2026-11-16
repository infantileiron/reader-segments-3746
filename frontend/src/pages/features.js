import {state} from '../stores/session.js';
import {esc} from '../utils/html.js';
import {field,select} from '../components/common/fields.js';
import {FEATURES} from '../constants/enums.js';

export function render() {
  const latest = state.versions[0];
  return `<div class="split"><section class="panel"><h2>分群之前，先确定观察周与资格依据</h2>
    <p class="notice">阅读篇数和比例量纲不同。后台先做z标准化，再以欧氏距离聚类；画像仍还原为原始单位。取样只纳入所选自然周整周（周一至周日）都有有效订阅权益的会员，并冻结当时的完整权益版本。</p>
    <div class="feature-notes"><h3>周阅读篇数</h3><p>反映内容使用频度，不等同付费意愿。</p><h3>完读率</h3><p>完整读完篇数 / 开始阅读篇数，原始范围0–1。</p><h3>夜读占比</h3><p>22:00–06:00阅读次数占比，原始范围0–1。</p></div>
    <h3>版本档案</h3>
    ${state.segments.map(s => `<button class="study" data-segment="${s.id}">#${s.id} ${esc(s.name)} · k=${s.k} · 周${esc(s.week_start || '—')} · 权益v${s.entitlement_version ?? '—'} · ${esc(s.state)}</button>`).join('') || '<p>尚无分群版本。右侧选择至少两个维度提交第一份。</p>'}
  </section><aside class="side"><h2>新建分群版本</h2>
    <form id="segment">
      ${field('版本名称', 'name', 'text', 'required value="11月会员阅读分群"')}
      ${select('群组数 k', 'k', [2, 3, 4, 5, 6].map(k => [k, k]))}
      <label>所选自然周（周一，留空取最近完整周）<input name="week_start" type="date"></label>
      ${select('权益版本', 'entitlement_version', [[latest?.version ?? '', latest ? 'v' + latest.version + '（最新）' : '暂无生效版本']])}
      <fieldset><legend>观察维度（至少2项）</legend>${Object.entries(FEATURES).map(([k, v]) => `<label class="check"><input type="checkbox" name="features" value="${k}" checked>${v}</label>`).join('')}</fieldset>
      <p>固定seed 3107；创建时冻结周界、权益版本与纳入/排除名单。常量列、样本不足和重复点不足会明确失败。</p>
      <button class="primary">提交后台分群</button>
    </form>
  </aside></div>`;
}
