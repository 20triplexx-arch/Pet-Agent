"""Bounded Chinese proposition scoping for observed errors, not an NLP entailment model."""
import re


def clauses(text):
    # An unrelated denial before a contrast must not license the later assertion.
    return [part for part in re.split(r'[，,。！？?；;\n]|但是|然而|不过|但(?:是)?|而是|转而',text) if part.strip()]


def negated(clause, start):
    prefix = clause[:start].rstrip()
    if re.search(r'(?:不能不|不得不|不是不能|并非不能|不是不|并非不|不是不是|不能不说|不是不能说)(?:可以|能够|会|能|可|是|一律|都|总是|直接)*$',prefix):
        return False
    return bool(re.search(
        r'(?:不等于|不意味着|并不表示|不代表|不能认为|不能说|不应说|并非|不是|无需|不必|不要|不应|不能|无法|不会|未能|不可|不宜|未必|不一定|不|无)'
        r'(?:(?:仅凭|单凭)(?:现有|这些|上述)?(?:资料|信息|标签)|可以|能够|自驾|出行|运输|一律|都|总是|任何时候|必须|直接|仅凭这些|据此|自行|另行|另|再|就|会|可|能|是|认为|说|要求|包括|包含|评估|衡量|反映|涉及){0,5}$',prefix))


def affirmative_schedules(text):
    """Typed, bounded period/quantity claims; a denial is never positive evidence."""
    numbers = {'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
    def number(value):
        if value.isdigit():
            return int(value)
        if value in numbers:
            return numbers[value]
        if '十' in value:
            left, right = value.split('十',1)
            return numbers.get(left,1)*10 + numbers.get(right,0)
        return value
    pattern = re.compile(r'(?P<period>每天|每日|每周|每月|每晚)'
        r'(?:(?:可以|能够|可|能|应当|应该|建议|至少|至多|最多|不超过)|安排|进行|做|练习|玩耍|互动){0,4}'
        r'(?P<count>[一二两三四五六七八九十\d]+)(?P<unit>次|分钟|小时)(?P<tail>或多次|以上|以下)?')
    result=set()
    for clause in clauses(text):
        for match in pattern.finditer(clause):
            prefix=clause[:match.start()]
            if negated(clause,match.start()) or re.search(r'(?:不规定|不要求|不能规定|没有统一|不设统一)\s*$',prefix):
                continue
            claim=match.group()
            bound=('min' if re.search(r'至少|或多次|以上',claim) else
                   'max' if re.search(r'最多|至多|不超过|以下',claim) else 'exact')
            result.add(('每天' if match['period']=='每日' else match['period'],number(match['count']),match['unit'],bound))
    return result


def qualified(clause):
    return bool(re.search(r'是否|核实|核对|确认.{0,8}要求|如果|假如|若|按.{0,12}要求|取决于',clause))


def unverified_nationwide_absence(clause):
    """A document's silence cannot establish absence of nationwide requirements."""
    region=r'(?:全国|中国|国内)(?:范围内)?'
    absence=r'(?:没有(?!列出|提供|说明|覆盖|记载)|不存在|并无|尚无|未制定|未设|不设)'
    subject=r'(?:文件|证件|清单|要求|规定|标准|制度)'
    match=re.search(absence+r'[^。！？；]{0,10}'+region+r'[^。！？；]{0,12}'+subject+
                    '|'+region+r'[^。！？；]{0,10}'+absence+r'[^。！？；]{0,12}'+subject,clause)
    if not match:
        return False
    prefix=clause[:match.start()]
    if negated(clause,match.start()):
        return False
    if re.search(r'不是不能|并非不能|不能不|不是不',prefix):
        return True
    if re.search(r'(?:不能|不可|不足以|无法|不应|尚不能)(?:据此|就此)?(?:说|断言|认为|推断|证明)\s*$',prefix):
        return False
    if re.search(r'是否|有无|尚待核实|尚未证实|无法确认|仍待确认|吗[？?]?$',clause):
        return False
    return True
