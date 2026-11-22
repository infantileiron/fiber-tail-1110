export const roleLabel = {analyst: '称重分析', reviewer: '收料复核', observer: '仓务观察'};
export const outcomeLabel = {accept: '接收', retest: '复检', reject: '退货'};
export const runLabel = {queued: '排队中', succeeded: '已出报告', failed: '样本不足'};
export const correctionLabel = {pending: '待裁定', adopted: '已采用', rejected: '已驳回'};
export const publishLabel = {
    published: '已发布', publishable: '可发布', draft: '草稿·待裁定',
    stale: '称重已更正', superseded: '已有更新版本', queued: '排队中', failed: '样本不足',
};
export const publishHint = {
    draft: '存在待裁定的称重更正，本版按当前称重计算，仅作草稿。裁定采用后按原参数自动重算，算完的最新版才能发布。',
    stale: '称重台账已更正，本版快照不再有效，请按有效称重重新诊断后再发布。',
    superseded: '该版本仅可追溯，请切换到最新版本复核发布。',
    queued: '最新版本正在后台计算，算完后才能发布。',
    failed: '最新版本计算失败，请检查干样后重新提交诊断。',
};
export const actions = {
    lot_created: '登记供货批次', sample_recorded: '记录干样', inspection_queued: '提交诊断',
    inspection_completed: '完成诊断', inspection_failed: '诊断失败', decision_published: '发布验收决定',
    correction_submitted: '提交称重更正', correction_adopted: '裁定采用更正', correction_rejected: '裁定驳回更正',
};
export const parameterFields = [
    ['threshold_pct', '单样超标线', '杂质率严格高于此线计入超标重量', 3, 0],
    ['tail_pct', '尾部干样份额', '从杂质率最高处逆向累计干样重量', 15, 0.01],
    ['exceed_cap_pct', '超标份额上限', '超标干样重量占总干样重量的上限', 20, 0],
    ['tail_cap_pct', '尾部均值上限', '尾部重量加权平均杂质率的上限', 8, 0],
];
