import {correctionLabel, outcomeLabel, publishLabel, runLabel} from '../../constants/labels.js';
import {route} from '../../router/location.js';
import {esc, number, stamp, version} from '../../utils/format.js';

export const formError = '<p class="form-error" role="alert"></p>';
export const mark = '<span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>';

export function pageTitle(kicker, title, description, side = '') {
    return `<header class="page-heading"><div><p class="eyebrow">${kicker}</p><h1>${title}</h1><p class="page-summary">${description}</p></div>${side}</header>`;
}

export function badge(outcome, status) {
    if (outcome) return `<span class="badge tone-${outcome}">${outcomeLabel[outcome]}</span>`;
    if (status) return `<span class="badge tone-${status}">${runLabel[status]}</span>`;
    return '<span class="badge tone-pending">待验收</span>';
}

const publishTone = {
    published: 'accept', publishable: 'succeeded', draft: 'queued',
    stale: 'reject', superseded: 'pending', queued: 'queued', failed: 'failed',
};

export function publishBadge(state) {
    return `<span class="badge tone-${publishTone[state] ?? 'pending'}">${publishLabel[state] ?? state}</span>`;
}

export function runBadge(run) {
    return run.publish_state ? publishBadge(run.publish_state) : badge(run.outcome, run.status);
}

export function lotStrip(lot, samples) {
    return `<aside class="lot-strip"><div><span class="eyebrow">供货批号</span><strong>${esc(lot.code)}</strong></div>
        <div><span class="eyebrow">来料</span><b>${esc(lot.material)}</b><small>${esc(lot.supplier)}</small></div>
        <div><span class="eyebrow">到货重量</span><b>${number(lot.shipment_kg)} kg</b></div>
        <div><span class="eyebrow">现有干样</span><b>${samples.length} 份</b></div></aside>`;
}

export function empty(title, explanation, link = '', label = '') {
    return `<section class="empty"><h2>${title}</h2><p>${explanation}</p>${link ? `<a class="button secondary" href="${link}">${label}</a>` : ''}</section>`;
}

export function history(page, workspace, selected) {
    const runs = workspace.inspections;
    if (!runs.length) return '<p class="quiet inset">当前批号没有可查看的验收单。</p>';
    return `<ol class="run-history">${runs.map(run => `<li><a href="${route(page, workspace.lot.id, run.id)}"
        ${selected === run.id ? 'aria-current="true"' : ''}><strong>${version(run.version)}</strong>
        <span>${esc(run.parameters.threshold_pct)}% 超标线 · 尾部 ${esc(run.parameters.tail_pct)}%</span>
        ${runBadge(run)}</a></li>`).join('')}</ol>`;
}

export function correctionsTable(work, ruling = false) {
    const items = work.corrections ?? [];
    if (!items.length) return '<p class="quiet inset">还没有称重更正记录。</p>';
    const current = Object.fromEntries(work.samples.map(sample => [sample.code, sample]));
    const pendingByCode = {};
    for (const item of items) {
        if (item.status === 'pending') pendingByCode[item.sample_code] = (pendingByCode[item.sample_code] ?? 0) + 1;
    }
    return `<div class="table-scroll"><table id="correction-table"><thead><tr><th>更正单 / 样号</th><th>当前称重 g<br><small>干样 / 杂质</small></th>
        <th>更正称重 g<br><small>干样 / 杂质</small></th><th>状态</th><th>提交 / 裁定</th>${ruling ? '<th><span class="sr-only">裁定</span></th>' : ''}</tr></thead><tbody>
        ${items.map(item => {
            const now = current[item.sample_code];
            const conflict = item.status === 'pending' && pendingByCode[item.sample_code] > 1;
            return `<tr><td><strong class="record-code">${esc(item.ticket)}</strong><small>${esc(item.sample_code)}</small></td>
            <td class="mono">${item.status === 'pending' && now ? `${number(now.dry_g)} / ${number(now.impurity_g)}` : '—'}</td>
            <td class="mono">${number(item.dry_g)} / ${number(item.impurity_g)}</td>
            <td><span class="badge tone-${item.status === 'pending' ? 'queued' : item.status === 'adopted' ? 'accept' : 'reject'}">${correctionLabel[item.status]}</span>
            ${conflict ? '<span class="badge tone-retest">冲突</span>' : ''}</td>
            <td><small>${esc(item.submitter)} · ${stamp(item.submitted_at)}</small>${item.resolver ? `<br><small>${esc(item.resolver)} · ${stamp(item.resolved_at)}</small>` : ''}</td>
            ${ruling ? `<td>${item.status === 'pending' ? `<form class="ruling-form" data-correction="${item.id}">
                <button class="button mini primary" type="submit" name="verdict" value="adopted">采用</button>
                <button class="button mini secondary" type="submit" name="verdict" value="rejected">驳回</button></form>` : ''}</td>` : ''}</tr>`;
        }).join('')}</tbody></table></div>`;
}
