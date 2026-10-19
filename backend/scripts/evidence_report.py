"""Readable classification and source/gap inventories from the delivered manifest."""
import json
from pathlib import Path
import zipfile
from app.evidence_index import digest

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'backend/data'


def main():
    rows=[a for path in sorted(DATA.glob('knowledge*.json')) for a in json.loads(path.read_text(encoding='utf-8'))]
    annotation=json.loads((DATA/'evidence/annotations.json').read_text(encoding='utf-8'))
    index=json.loads((DATA/'evidence/index.json').read_text(encoding='utf-8'))
    batch=json.loads((DATA/'evidence/batch.json').read_text(encoding='utf-8'))
    previous={}
    archive=ROOT/'artifacts/evidence-rebuild/baseline.zip'
    if archive.exists():
        with zipfile.ZipFile(archive) as source:
            for name in source.namelist():
                if name.startswith('backend/data/knowledge') and name.endswith('.json'):
                    previous.update({a['id']:a for a in json.loads(source.read(name))})
    kinds={'care':'通用照护','breed':'品种','food':'食物','supplies':'用品'}
    species={'cat':'猫','dog':'狗'}
    lines=['# 95篇资料分类与编辑清单','','2026-10-20。每篇保留原ID；猫狗共用资料只保存一份。分类核对不等于专业审核。',
        '',f"本批：95篇，{len(index['chunks'])}个块；分类数量："+'、'.join(kinds[k]+str(v) for k,v in batch['classification_count'].items())+'。',
        '', '| 文章ID | 物种 | 主分类 | 原主题 | 子主题 | 本批处置 |', '|---|---|---|---|---|---|']
    for article in sorted(rows,key=lambda a:(a['content_kind'],a['id'])):
        aid=article['id'];old=previous.get(aid,{})
        changed=bool(old and article['body']!=old['body'])
        action='正文补充及来源核对' if changed else '分类及来源映射核对'
        if old and 'content_kind' not in old:
            action+='；默认分类改为显式分类'
        meta=annotation['articles'][aid]
        lines.append('|'+ '|'.join([aid,'、'.join(species[s] for s in article['species']),kinds[article['content_kind']],article['topic'],'、'.join(meta['subtopics']),action])+'|')
    lines+=['','原11个主题值保留；健康条件未知不补为健康，原文未明确的地域和阶段不扩展。',
            '块、来源、依赖和核对状态见 `backend/data/evidence/annotations.json`；派生正文与词项索引见同目录 `index.json`。']
    (ROOT/'docs/KNOWLEDGE_CLASSIFICATION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    lines=['# 本批补充资料与剩余来源缺口','','2026-10-20。摘要仍为 `editorial_summary_unreviewed`。',
       '',f"实质更新{len(batch['substantively_updated'])}篇；本次实际重新打开核对{batch['rechecked_source_count']}个来源；另有{batch['pending_source_count']}个历史来源未重新核对。",
       f"95篇全文及{batch.get('section_review_count',0)}个完整章节保存编辑核对记录、来源支持范围、证据性质与明确依赖；这是助手编辑审阅，未经兽医或独立专业审核。",
       '页面可读取范围另行标记；品种标准只用于外形身份，护理和健康内容绑定相应专业资料。原创流程和应用行为不冒充机构建议。',
       '', '| 更新文章 | 新增或重组的内容 |', '|---|---|']
    from scripts.reorganize_knowledge import ADDITIONS
    for aid,paragraphs in sorted(ADDITIONS.items()):
        lines.append('|'+aid+'|'+'；'.join(heading for heading,_ in paragraphs)+'|')
    lines += ['','护理和口腔旧文的可用步骤保留，并补充核对来源；没有为增加篇数另建重复文章。',
        '食品、用品中的厂家信息仍为声明或标签事实；预算、交接和记录格式明确属于编辑整理。',
        '', '## 已核对来源与定位','', '| 来源 | 本次定位与支持范围 |', '|---|---|']
    for source in sorted(annotation['sources'].values(),key=lambda s:s['url']):
        if source['verification_status']=='page_rechecked':
            lines.append(f"|[{source['title']}]({source['url']})|{source['locator']}；{source['supports']}|")
    lines += ['', '## 历史来源待复核清单','', '下表仅列本批仍未完成页面定位复核的来源；为空时表示没有该类结构性缺口，不代表临床正确率已获认证。',
              '', '| 来源 | 保留的核对日期 | 待完成项目 |','|---|---|---|']
    for source in sorted(annotation['sources'].values(),key=lambda s:s['url']):
        if source['verification_status']!='page_rechecked':
            lines.append(f"|[{source['organization']}]({source['url']})|{source['checked_at']}|原文可访问性、精确段落定位及逐结论支持范围复核|")
    if not batch['pending_source_count']:
        lines.append('|无|—|保留未经兽医审核状态；实际回答主要结论另行验收|')
    lines += ['', '完整章节核对清单见 `backend/data/evidence/section_reviews.json`；来源页与失效链接替换理由见 `source_reviews.json`。',
              '正文或来源定位改变后旧核对哈希失效，构建器拒绝沿用“已核对”标记；不通过脚本自动续签审阅。']
    lines += ['', '## 验收资料','', f"五类40题见 `backend/evals/evidence_cases.json`；{len(batch['substantively_updated'])}篇各六类问法共{len(batch['substantively_updated'])*6}题见 `evidence_article_cases.json`。",
        '这些是开发回归；新十组留出集单独冻结，不用于修复调参。旧十组留出集转为回归，原文件和历史结果保留。',
        '离线和真实质量、速度结果分别见 [实施与验收记录](EVIDENCE_REBUILD.md)。']
    (ROOT/'docs/KNOWLEDGE_GAPS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'classification_articles':len(rows),'source_records':len(annotation['sources']),
                      'manifest_sha256':index['manifest_sha256']},ensure_ascii=True))


if __name__=='__main__':
    main()
