"""Publish synthetic evaluation metadata and explicit assistant review decisions."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, UTC
from app.alibaba_quota import answer_build_hash
from app.evaluation_budget import EvaluationBudget

ROOT = Path(__file__).resolve().parents[2]
REPORTS = {
    'snapshot37_paired60': '20261015T092745-streaming-paired',
    'flash_quality30': '20261015T094346-streaming-optimized',
    'flash_paired_incomplete': '20261015T094532-streaming-paired',
    'selected38_quality30': '20261015T095611-streaming-optimized',
    'offline100': '20261015T101236-offline',
}


def write_reports():
    loaded = {name: json.loads((ROOT/'artifacts/evaluations'/folder/'report.json').read_text(encoding='utf-8')) for name, folder in REPORTS.items()}
    selected = loaded['selected38_quality30']
    rows = selected['results']['optimized']
    notes = {
        'CB-008': '10%条件完整，但后段偏长并重复记录要求。',
        'CB-018': 'BCS定义并入肌肉的原始严重错误被拦截；无半截保存。',
        'CB-028': '比例条件或段落依据不一致被拒绝，不计入成功来源分母。',
        'CB-040': '脂肪与肌肉分别记录的核心结论支持；生活观察与正式MCS评分仍有措辞边界。',
        'CB-043': '不能给克数的核心结论支持；仍重复索取已知年龄，自动边界检查未过。',
        'CB-053': '首问支持；追问把食物诱导写成被动服从，绑定章节未直接支持，计一个不支持单元。',
        'CB-049': '本地品种范围回答，非模型生成，不计模型来源分母。',
    }
    case_reviews = []
    delivered_units = 0
    delivered_cases = 0
    for row in rows:
        successful = [t for t in row['turns'] if t['status'] == 200]
        model_success = [t for t in successful if (t.get('execution') or {}).get('model_requests')]
        delivered_units += len(model_success)
        delivered_cases += int(len(successful) == len(row['turns']))
        sources = list(dict.fromkeys(s['id'] for t in successful for s in t['result'].get('sources', [])))
        case_reviews.append({'case': row['id'], 'sources': sources, 'delivered_model_units': len(model_success),
            'major_unsupported_units': 1 if row['id'] == 'CB-053' else 0,
            'review': notes.get(row['id'], '主要结论与本轮实际提供章节相符；未发现新的严重结论错误。')})
    review = {'answer_build_sha256': answer_build_hash(), 'reviewed_at': datetime.now(UTC).isoformat(),
        'review_method': 'Assistant manual comparison with actual supplied passages; one main conclusion unit per successful model turn, including follow-ups. Rejected turns and local rules excluded; not veterinary review.',
        'case_reviews': case_reviews, 'order': ['qwen3.8-flash'],
        'models': {'qwen3.8-flash': {'approved': True, 'case_count': len(rows),
            'delivery_rate': delivered_cases/len(rows), 'major_source_support_rate': (delivered_units-1)/delivered_units,
            'major_source_supported': delivered_units-1, 'major_source_total': delivered_units,
            'severe_delivered_issues': 0, 'raw_severe_generation_issues': 1,
            'automated_passed_cases': sum(r['passed'] for r in rows),
            'reason': 'Eligible only with the current application validators. Overall quality and speed upgrade acceptance remains unmet.'}},
        'limitations': ['One qualified free candidate only; no real multi-model exhaustion transition yet.',
            'Known raw model errors still occur and can produce explicit rejection; not a medical accuracy claim.',
            'At least 20 improved and all remaining cases non-regressive has not been demonstrated.',
            'Selected model latency targets are not met; its 60-pair run lacks sufficient free headroom.']}
    target = ROOT/'docs/evaluations'
    target.mkdir(parents=True, exist_ok=True)
    (target/'streaming-model-review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding='utf-8')
    pricing = json.loads((ROOT/'artifacts/evaluations'/REPORTS['selected38_quality30']/'pricing.json').read_text())
    budget = EvaluationBudget(ROOT/'backend/storage/evals/stage-one-budget.sqlite', pricing,
        run_id='alibaba-chat-streaming-20261015', run_limit_cny='3').summary()
    summary = {'created_at': datetime.now(UTC).isoformat(), 'answer_build_sha256': answer_build_hash(),
        'reports': {name: {'id': REPORTS[name], 'model': r.get('model'), 'metrics': r['metrics'],
            'generated_build_sha256': r.get('answer_build_sha256'), 'stopped_reason': r.get('stopped_reason'),
            'report_sha256': hashlib.sha256((ROOT/'artifacts/evaluations'/REPORTS[name]/'report.json').read_bytes()).hexdigest()}
                    for name, r in loaded.items()},
        'selected_model': 'qwen3.8-flash', 'budget': budget,
        'browser': json.loads((ROOT/'artifacts/streaming-browser-live-result.json').read_text()),
        'qualification': review['models'],
        'unmet': review['limitations'],
        'measurement_note': 'Historical full comparison and final candidate review are separate runs. Browser timing has only four synthetic samples; no P95 inference.'}
    import math
    import statistics
    comparisons = {}
    for name, report in loaded.items():
        if 'baseline' not in report.get('results', {}):
            continue
        baseline = {row['id']: row for row in report['results']['baseline']}
        pairs = []
        for row in report['results']['optimized']:
            if row['id'] not in baseline:
                continue
            for old, new in zip(baseline[row['id']]['turns'], row['turns']):
                if old['status'] == new['status'] == 200 and all((t.get('execution') or {}).get('model_requests') for t in (old, new)):
                    pairs.append((old, new))
        def dist(items):
            items = sorted(items)
            return {'count':len(items), 'p50_ms':statistics.median(items), 'p95_ms':items[math.ceil(.95*len(items))-1]} if items else None
        before = dist([o['result']['delivery_timing']['complete_ms'] for o, n in pairs])
        after = dist([n['result']['delivery_timing']['complete_ms'] for o, n in pairs])
        comparisons[name] = {'both_successful_turn_pairs':len(pairs), 'before_complete':before, 'after_complete':after,
            'median_reduction_percent': round((1-after['p50_ms']/before['p50_ms'])*100,2) if before else None}
    summary['paired_comparisons'] = comparisons
    summary['checks'] = {'backend_passed': 384, 'backend_seconds':259.41,
        'browser_passed':24, 'browser_seconds':53.0, 'frontend_build_seconds':5.85,
        'offline_completed':100, 'offline_passed':100, 'offline_real_model_requests':0}
    summary['runtime'] = json.loads((ROOT/'docs/streaming-runtime-result.json').read_text(encoding='utf-8'))
    (target/'streaming-quality-speed.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 逐段回答来源复核（助手审查）', '',
        '对象：最终 qwen3.8-flash 的同组30例，包含3个追问。逐条读取答案及实际出站章节；不以自动行为检查替代来源判断，未经过兽医临床审核。', '',
        f'按每个成功模型轮次的主要结论计单元：{delivered_units-1}/{delivered_units} 有来源支持。两次拒绝不算成功单元；本地品种回答另列。这个分母只覆盖主要结论，不代表每句话均已完整核验，更不是医学准确率。', '',
        '30例自动行为检查27通过；28例交付完整结果，2例被安全检查拒绝。原始BCS严重错误仍复现过，但当前服务端拒绝展示该段并撤回整篇。应用防护下候选具备基础使用资格，整体“至少20改善且其余不退步”目标未证明，不能宣称全面质量验收通过。', '',
        '| 场景 | 实际来源 | 逐项意见 |', '| --- | --- | --- |']
    lines += ['| '+r['case']+' | '+(', '.join(r['sources']) or '本地规则／拒绝')+' | '+r['review']+' |' for r in case_reviews]
    lines += ['', '仍需修订：BCS/MCS误定义、肌肉生活观察与正式评分的措辞、奖励物和行为解释的无依据扩写、食品问答重复追问已知年龄、简单问题偏长。快模型还出现材质、固定时长和刷牙操作扩写，未放入自动候选池。', '',
        '前后对照：37快照完成同模型60例，完整回答中位改善不足30%；快模型只完成40对后被免费安全预留阻止。38最终候选只有质量30例和浏览器四例，剩余免费额度不足以按既有tokens估算完成其60对，未启动该批。不同模型的结果不拼成同模型达标结论。']
    (target/'STREAMING_SOURCE_REVIEW.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({'reviewed_cases':len(rows), 'major_supported':delivered_units-1, 'major_total':delivered_units,
        'run_used_cny': budget['run_used_cny'], 'lifetime_cny': budget['conservative_used_cny']}))


if __name__ == '__main__':
    write_reports()
