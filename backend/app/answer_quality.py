"""Small, source-specific checks for contradictions observed in live reviews.

These are bounded heuristics, not a medical accuracy or semantic entailment judge.
"""
import re
from app.propositions import affirmative_schedules, clauses, negated, qualified


def factual_error(text, profile, ctx):
    """Deterministic checks for facts the application can actually establish."""
    analysis = getattr(ctx, 'analysis', {})
    nutrition = analysis.get('tool_results', {}).get('nutrition') or {}
    ready = nutrition.get('status') == 'ready'
    if nutrition and not ready:
        for part in clauses(text):
            precision = re.search(r'(?:准确|精确|精准).{0,15}(?:克数|喂食量|食量|方案)',part)
            predicates=list(re.finditer(r'算出|给出|得到|确定|计算|推算|生成|制定|产生|输出|保证|承诺',part[:precision.start()] if precision else ''))
            denied=precision and (negated(part,precision.start()) or (predicates and (
                negated(part,predicates[-1].start()) or any(
                    p.group() in ('保证','承诺') and negated(part,p.start())
                    and not re.search(r'却|仍然|反而',part[p.end():precision.start()]) for p in predicates))))
            if precision and not denied:
                return '营养评估未就绪，不能承诺少数资料就能产生精确个体食量'
    allowed = {'grams': [], 'kcal': []}
    def numeric_facts(value, key=''):
        if isinstance(value, dict):
            for name, child in value.items():
                numeric_facts(child, name)
        elif isinstance(value, list):
            for child in value:
                numeric_facts(child, key)
        elif type(value) in (int, float):
            if re.search(r'grams|gram|daily_g', key, re.I):
                allowed['grams'].append(float(value))
            if re.search(r'kcal|calor|^energy$', key, re.I):
                allowed['kcal'].append(float(value))
    numeric_facts(nutrition)
    numeric_facts(analysis.get('tool_results', {}).get('products', {}))
    quantities = re.finditer(r'\d+(?:\.\d+)?(?:\s*[—–~～至到-]\s*\d+(?:\.\d+)?)?\s*(?:千卡|kcal|克|(?<!k)g)(?![a-zA-Z])', text, re.I)
    for match in quantities:
        prefix = text[max(0, match.start()-18):match.start()]
        # A label denominator is a requested unit, not a feeding recommendation.
        if re.fullmatch(r'(?:100|1000)\s*(?:克|g|kcal|千卡)', match.group(), re.I) and re.search(r'(?:每|/)\s*$', prefix):
            continue
        values = [float(number) for number in re.findall(r'\d+(?:\.\d+)?', match.group())]
        kind = 'kcal' if re.search(r'kcal|千卡', match.group(), re.I) else 'grams'
        grounded = all(any(abs(number-known) <= .51 for known in allowed[kind]) for number in values)
        if ready and not grounded:
            return '食量或热量数值与本地计算不一致'
        if grounded and re.search(r'标签|包装|标示|你(?:提供|记录)|您(?:提供|记录)|实际摄入|当前记录', prefix):
            continue
        if not ready:
            # Repeating a reported intake is permitted only when the exact
            # quantity is in the user's current report and is labelled as such.
            current = getattr(ctx, 'current_text', '')
            reported = re.search(r'你(?:提供|记录)|您(?:提供|记录)|已记录|实际摄入|当前记录', prefix)
            if reported and match.group() in current:
                continue
            return '没有就绪的本地营养计算，不能生成食量或热量数值'
    if profile and profile.get('neutered') is not True:
        reported = getattr(ctx, 'current_text', '')
        if not re.search(r'已绝育|刚.{0,4}绝育|绝育手术后', reported):
            facts = analysis.get('answer_context', {})
            known = facts.get('known_fields', {}).get('neutered', {})
            user_confirmed = known.get('value') is True and known.get('source') in ('user_report', 'supplemental_context')
            conflict_report = any(r.get('field') == 'neutered' and r.get('value') is True
                                  for r in facts.get('reported_restrictions_and_conflicts', []))
            for clause in re.split(r'[。！？；;\n]', text):
                if re.search(r'已绝育|绝育后的(?:猫|狗|犬)|成年绝育(?:猫|狗|犬)', clause) and not re.search(r'如果|若|假如|是否|未知|未确认|尚未|不能确定|需(?:要)?确认', clause):
                    if user_confirmed or (conflict_report and re.search(r'你(?:说|提到|提供|报告)|用户(?:自述|报告)|本次报告|此前报告', clause)):
                        continue
                    return '把未知或相反的绝育状态写成了当前宠物事实'
    for clause in re.split(r'[，,。！？；;\n]', text):
        for match in re.finditer(r'肌肉(?:流失|损失|减少).{0,12}(?P<causal>导致|造成).{0,8}BCS(?:异常|升高|偏高)', clause, re.I):
            denied = negated(clause,match.start()) ^ negated(clause,match.start('causal'))
            if not denied:
                return '混淆肌肉状况与脂肪体况'
        if re.search(r'BCS|体况评分', text + getattr(ctx, 'current_text', ''), re.I):
            for match in re.finditer(r'(?:因)?肌肉(?:流失|损失|减少).{0,6}(?:导致|造成)(?:实际|当前|脂肪)?体况(?:变差|不佳|下降|恶化)', clause):
                prefix = clause[:match.start()]
                denied = re.search(r'(?:不是|并非|不能说|不应说|不能认为)$', prefix)
                uncertainty = re.search(r'不一定|不必然|不会|不能', match.group())
                double_negative = re.search(r'(?:不是不是|并非不是|不能不说|不是不能说)$', prefix)
                if double_negative or not (denied or uncertainty):
                    return '用肌肉减少解释脂肪体况变化'
    # Preserve an explicit scoring subject across an adjacent contrast. A
    # correct negative definition must not hide its contradictory alternative.
    for sentence in re.split(r'[。！？；;\n]',text):
        alternative = re.search(r'而是(?:用来|用于)?(?:评估|衡量|关注|反映|包含|包括).{0,24}肌肉',sentence)
        if alternative:
            subjects = list(re.finditer(r'BCS|MCS|体况评分|肌肉状况评分',sentence[:alternative.start()],re.I))
            if subjects and subjects[-1].group().upper() in ('BCS','体况评分') and not negated(sentence,subjects[-1].start()):
                return 'BCS只评估脂肪，不能把肌肉状况并入BCS定义'
    for clause in re.split(r'[，,。！？；;\n]', text):
        # Inspect the BCS proposition itself; a correct MCS definition later in
        # the sentence must not excuse a contradictory BCS definition.
        definition = re.search(r'(?:BCS|体况评分)(.*?)(?=MCS|肌肉状况评分|$)', clause, re.I)
        if definition:
            claim = definition[1]
            # "评估日期/填写者、肌肉状况" enumerates missing inputs;
            # its noun modifier is not a predicate defining the BCS object.
            predicate = re.search(r'(?:评估(?!日期|时间|者|人员|人|结果|记录)|衡量|关注|反映|包含|包括).{0,24}肌肉', claim)
            if predicate and not negated(claim,predicate.start()):
                return 'BCS只评估脂肪，不能把肌肉状况并入BCS定义'
            if re.search(r'(?:是|属于|反映).{0,6}整体健康', claim) and not re.search(r'不是|不属于|不代表|不能', claim):
                return '把BCS当作整体健康结论'
        if re.search(r'保证分析.{0,12}(?:中|内|里|包含|包括|涵盖).{0,15}(?:能量|热量|kcal|代谢能)', clause, re.I) and not re.search(r'不一定|未必|不能|分别|不同|不包含|不包括|不是', clause):
            return '把能量误写成保证分析中的必备项目'
    # A provider must not turn qualitative guidance into invented schedules.
    evidence = getattr(ctx, 'sent_evidence', {})
    supplied = ' '.join(passage for article in evidence.values() for passage in article.values())
    for timing in re.finditer(r'\d+(?:\s*[-—～至到]\s*\d+)?\s*(?:分钟|小时|周|个月|天)(?:一次|左右|后|内|以上|以下)?', text):
        value = re.sub(r'\s+', '', timing.group())
        age_prefix = text[max(0, timing.start()-14):timing.start()]
        known_age = (profile or {}).get('age_months')
        if known_age is None:
            known_age = analysis.get('answer_context', {}).get('known_fields', {}).get('age_months', {}).get('value')
        age_value = re.fullmatch(r'(\d+(?:\.\d+)?)个月', value)
        if age_value and known_age is not None and float(age_value[1]) == float(known_age):
            if re.match(r'大|龄', text[timing.end():]) or (re.search(r'年龄|月龄|已知|档案|猫|狗|犬', age_prefix)
                                                       and not re.search(r'每|隔|等待|再过|建议', age_prefix)):
                continue  # Known age is a profile fact, not a care schedule.
        if value not in re.sub(r'\s+', '', supplied):
            reported = re.search(r'你(?:提供|记录|提到)|您(?:提供|记录|提到)|已记录|实际观察|当前记录',age_prefix)
            if reported and value in re.sub(r'\s+','',getattr(ctx,'current_text','')):
                continue
            # Reporting the application's actual record windows is permitted.
            if value.rstrip('内') in ('7天', '30天') and re.search(r'记录|统计|复盘|窗口', text[max(0, timing.start()-12):timing.end()+12]):
                continue
            return '资料未提供具体时长或频率，不能编造固定安排'
    return None


def evidence_rules(article_ids):
    ids = set(article_ids)
    rules = []
    if ids & {'cat-grooming', 'cat-low-stress-care'}:
        rules.append('护理按当前参与意愿推进；紧张、回避或疼痛时停止。分别回答梳毛与剪甲的操作及边界，保留所引章节的练习环境与退避要求。不自行引入时间禁忌，不把恐惧与能否获得奖励混为一谈。')
    if ids & {'cat-scratching', 'supply-scratch'}:
        rules.append('抓挠资料支持位置、方向、材质、稳固性、替代选择及奖励；不添加猫薄荷、喷剂或喷雾等未由这些资料支持的产品建议。')
    if ids & {'nutrition-feeding', 'nutrition-energy'}:
        rules.append('零食比例10%只适用于健康、体况合适的成年猫狗；引用这个比例时，在同一段自然说全上述对象及前提。其他个体不套用，不将未知健康状况当作健康，不承诺精确食量。')
    if ids & {'nutrition-cat-bcs', 'nutrition-dog-bcs', 'nutrition-muscle'}:
        rules.append('概念题直接区分：BCS评估脂肪储备，MCS评估肌肉状况，二者分别记录；这是两个评估对象，不能合并为“BCS看脂肪与肌肉”或整体健康评分。脂肪较多仍可能同时肌肉损失，而不是肌肉损失导致BCS升高。日常起身、活动或触感变化只作为主人描述，不命名为MCS指标或据此判定肌肉损失。定义绑定BCS/肌肉章节，不标到喂食条目。')
    if ids & {'cat-dental', 'dog-dental', 'supply-dental'}:
        rules.append('只解释资料提供的口周接触、认识工具、按接受度推进及疼痛先评估。不添加漱口水、洁牙零食或具体刷牙部位等本次资料未给出的用品和操作推荐。')
    if ids & {'food-energy', 'nutrition-label', 'food-labels', 'nutrition-energy'}:
        rules.append('保证分析、营养适用声明和代谢能是不同标签项目；不说代谢能必定在保证分析内。每杯热量还需杯中实际克重。品牌名不能替代包装原文。年龄体重绝育等已知字段直接沿用当前档案，不再当成未知；还缺体况、肌肉、健康条件或标签时，不承诺补几项后就能精确给量。')
    if ids & {'dog-crate', 'dog-socialization'}:
        rules.append('只依据自愿接近、进入、能否舒适及整体反应推进，不把单次打哈欠当作放松证明。奖励目标行为与恐惧情绪分开，不补出只有完全放松才可获得奖励的条件。')
    if ids & {'cat-carrier', 'supply-carriers'}:
        rules.append('奖励追问只解释原文明示的自主接近、进入及按舒适反应推进；资料只说合适奖励时，保持该概括，不指定零食或玩具。不把食物诱导解释成被动服从、欺骗或恐惧强化。原文没有解释的机制不展开。')
    if 'cat-body-language' in ids:
        rules.append('咬手或尾巴变化时仅用原文支持的停止接触、给予空间及观察，不补出保持手部静止、强行固定或其他未提供的动作。人被咬伤的医疗意见与猫行为的兽医评估分别说明，不把人的伤口求助指向兽医。')
    if 'pet-travel' in ids:
        rules.append('健康文件不等于一律必须开具健康证明。证件须按实际运营方及目的地要求核实，不将清单升级为统一强制规定；资料未列出全国清单也不证明全国不存在统一要求。')
    if 'cat-clean' in ids:
        rules.append('排泄异常的风险说明适用于资料中的猫，不自行缩成仅公猫或某一品种；清洁问题只讲清洁与观察，不展开未询问的自动设备或购买维护清单。')
    return rules


def has_disallowed_health_claim(text):
    # Do not let an assertion span punctuation into an unrelated disease word.
    # Negations must immediately qualify the diagnostic verb; a later positive
    # assertion is still checked independently.
    assertion = re.compile(r'(?:确诊|肯定是|一定是|诊断为)[^，,。！？；;\n]{0,16}(?:疾病|肾病|肝病|糖尿病|感染|中毒|炎|病)')
    negative = re.compile(r'(?:不|未|尚未|未能|没有|并非|并不|不能|无法|不应|不可|不宜)(?:据此|因此|就此|直接|仅凭这些|单凭这些|自行)?(?:作出|给出|判断|认定|说|称)?$')
    for clause in re.split(r'[，,。！？；;\n]', text):
        for match in assertion.finditer(clause):
            prefix = clause[:match.start()]
            if re.search(r'(?:既往|过去|历史|已知)(?:已)?$', prefix):
                continue
            double_negative = re.search(r'(?:不能不|不得不|不是不能|不是不|并非不能|并非不|不是不等于|并非不等于)(?:据此|直接)?(?:作出|给出|判断|认定|说|称)?$', prefix)
            denied=bool(negative.search(prefix)) or negated(clause,match.start())
            if double_negative or not denied:
                return True
    return bool(re.search(r'(?:服用|用药|注射|给药).{0,40}\d+(?:\.\d+)?\s*(?:mg|毫克|毫升|ml|片)', text, re.I))


def unsupported_advice(text, article_ids):
    ids = set(article_ids)
    supplied = ' '.join(p for article in article_ids.values() for p in article.values()) if isinstance(article_ids, dict) else ''
    if isinstance(article_ids, dict):
        definitions_text=re.sub(r'BCS\s*[（(]\s*体况(?:评分)?\s*[）)]|体况评分\s*[（(]\s*BCS\s*[）)]','BCS',text,flags=re.I)
        definitions_text=re.sub(r'MCS\s*[（(]\s*肌肉(?:状况)?(?:评分)?\s*[）)]|肌肉(?:状况)?评分\s*[（(]\s*MCS\s*[）)]','MCS',definitions_text,flags=re.I)
        for concept, sources, definition in ((r'BCS|体况评分', {'nutrition-cat-bcs', 'nutrition-dog-bcs', 'nutrition-muscle'},r'脂肪'),
                                 (r'MCS|肌肉状况评分', {'nutrition-muscle'},r'肌肉减少|肌肉状况.{0,6}(?:关注|评估)|MCS.{0,10}(?:肌肉|评分)')):
            related=' '.join(value for aid,passages in article_ids.items() if aid in sources for value in passages.values())
            if not re.search(definition,related,re.I):
                # A missing field named "体况评分" is not a definition. Inspect
                # each proposition, including assertions after a legitimate ask.
                proposition = r'(?:' + concept + r')\s*(?:不|并非|并不|主要|通常|只|则)?(?:是(?!未知|空|缺失|尚未|未提供|未记录|待核对)|用于|用来|指|看|评估(?!日期|时间|者|人员|人|结果|记录|为)|衡量|关注|反映|包含|包括|通过|依据|根据|结合)'
                inverse = r'(?:评估|衡量|评分|反映)[^，,。！？；;\n]{0,20}(?:称为|就是|叫作|叫做|即|是)\s*(?:' + concept + ')'
                if re.search(proposition, definitions_text, re.I) or re.search(inverse, definitions_text, re.I):
                    return '评分定义未绑定实际提供的评分章节'
    if 'cat-body-language' in ids and '静止' not in supplied:
        for clause in re.split(r'[，,。！？；;\n]', text):
            if re.search(r'(?:保持|让|要|应|不要移动).{0,8}(?:静止|不动)|手(?:部)?.{0,6}(?:不动|不能动)', clause) and not re.search(r'不能要求|不要强求|不建议|无需', clause):
                return '咬手资料未支持保持静止的操作指令'
    if 'pet-travel' in ids:
        for clause in clauses(text):
            from app.propositions import unverified_nationwide_absence
            if unverified_nationwide_absence(clause):
                return '资料不足以断言全国不存在统一文件或证件规定'
            for claim in re.finditer(r'(?:必须|务必|需要|需|应当|应|要|准备|携带|开具|另开)[^。！？；;]{0,12}健康证明|健康证明[^。！？；;]{0,8}(?:必须|务必|一定要)(?:携带|开具|准备)',clause):
                if not negated(clause,claim.start()) and not qualified(clause):
                    return '把待核实的健康文件变成统一强制健康证明'
    if ids & {'cat-carrier', 'supply-carriers', 'dog-crate'}:
        for clause in re.split(r'[。！？；;\n]', text):
            if re.search(r'被动服从|强化恐惧|强化害怕|学会恐惧', clause) and not re.search(r'不能|不要|不代表|并非|不等于|不应|不宜', clause):
                return '奖励资料未支持对服从或恐惧学习机制的解释'
    if ids & {'nutrition-muscle', 'nutrition-cat-bcs', 'nutrition-dog-bcs'}:
        for clause in re.split(r'[。！？;；\n]', text):
            if re.search(r'起身|背部.{0,6}触感', clause):
                assertion = re.search(r'(?:应视为|视为|表明|说明|属于|是)(?:一种)?肌肉(?:损失|减少)(?:迹象|信号)', clause)
                if assertion and not re.search(r'(?:不能|不可|不应|不宜)(?:据此|直接)?$', clause[:assertion.start()]):
                    return '把生活观察直接当作肌肉减少迹象'
            if re.search(r'起身|背部触感', clause) and re.search(r'肌肉指标|肌肉损失信号|MCS评分标准', clause) and not re.search(r'不能|不代表|并非|不可', clause):
                return '把生活观察直接当作肌肉评分指标或肌肉损失结论'
            if re.search(r'MCS.{0,18}(?:需(?:要)?|通过|依据|根据|评估|判断|结合).{0,22}(?:起身|背部触感)', clause, re.I) and not re.search(r'不能|不代表|并非|不可|只是|仅是|仅作', clause):
                return '把生活观察当成正式MCS评估方法'
    if ids & {'cat-carrier', 'dog-crate'}:
        for material in ('零食', '玩具', '食物类奖励'):
            if material not in supplied and re.search(r'(?:优先使用|优先选择|建议.{0,8}选择|内部可放置|箱内放置).{0,25}' + material, text):
                return '运输箱资料未提供具体奖励物，不能补出用品建议'
    if ids & {'cat-grooming', 'cat-low-stress-care'}:
        for clause in clauses(text):
            for ban in re.finditer(r'(?:避免|不要|不应|不建议)(?:在)?(?:刚睡醒|饭后|(?:刚)?吃完饭)',clause):
                if not negated(clause,ban.start()):
                    return '护理时机被改写成资料没有规定的禁忌'
        if re.search(r'(?:仅|只)(?:在|有)?[^，,。；\n]{0,10}(?:放松|不害怕|平静)[^，,。；\n]{0,12}(?:奖励|零食)', text):
            return '把恐惧状态与能否获得奖励笼统绑定'
    if ids & {'cat-carrier','dog-crate','dog-alone','cat-grooming','cat-low-stress-care'}:
        for clause in clauses(text):
            for timing in re.finditer(r'每天|每日|每周|每月|每晚',clause):
                if timing.group() not in supplied and not negated(clause,timing.start()) and not re.search(r'不规定|不要求|不能规定|没有统一|不设统一',clause[:timing.start()]):
                    return '把按反应推进改写成来源未给出的固定频率'
    if 'cat-play' in ids:
        if affirmative_schedules(text)-affirmative_schedules(supplied):
            return '把按反应互动改写成来源未给出的次数或时长'
    if ids & {'cat-scratching', 'supply-scratch'}:
        for clause in re.split(r'[，,。！？；;\n]', text):
            for match in re.finditer(r'猫薄荷|喷剂|喷雾', clause):
                prefix = clause[:match.start()]
                # A refusal can cover a list; a subsequent positive alternative
                # starts a new recommendation even inside the same clause.
                prefix = re.split(r'改用|转而|而是|但可|但建议|而要', prefix)[-1]
                if not re.search(r'(?:不要|不推荐|不建议|无需|不必|不依赖|没有资料支持|避免|勿|不使用)[^，。]{0,40}$', prefix):
                    return '添加了抓挠资料没有支持的产品建议'
    if ids & {'nutrition-feeding', 'nutrition-energy'}:
        for paragraph in text.split('\n'):
            sentences = re.split(r'[。！？；;]', paragraph)
            for index, sentence in enumerate(sentences):
                if re.search(r'10\s*[%％]', sentence):
                    scope = sentence
                    following = sentences[index+1] if index+1 < len(sentences) else ''
                    if re.match(r'[^。！？；;\n]{0,12}(?:此|该|上述|以上|前述|这个).{0,8}(?:仅适用|适用于|限于|只适用|只针对)', following):
                        scope += following
                    denied = re.search(r'(?:不能|不要|不应).{0,6}(?:套用|推广|当作|作为)', sentence)
                    if not denied and not ('健康' in scope and re.search(r'成年|成猫|成犬', scope)
                                           and re.search(r'体况.{0,4}(?:合适|适宜|正常|良好)|理想体况', scope)):
                        return '零食比例缺少健康、体况合适的成年个体适用限定'
    return None
