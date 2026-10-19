"""2026-10-19 editorial batch: explicit classification, reviewed additions, annotations.

Run before build_evidence. This edits source JSON only, never a business database.
Old source verification dates are retained unless that exact page was read.
"""
import json
import re
from pathlib import Path
from app.evidence_index import article_sections, digest

DATA = Path(__file__).resolve().parents[1] / 'data'
DATE = '2026-10-19'
CAT = 'https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/'
DOG = 'https://www.vet.cornell.edu/departments-centers-and-institutes/riney-canine-health-center/canine-health-topics/'
DENTAL_DOG = 'https://www.vet.cornell.edu/departments-centers-and-institutes/riney-canine-health-center/canine-health-information/dental-disease-and-home-dental-care'
CARRIER = 'https://catvets.com/wp-content/uploads/2024/12/FelineVMA_VisitingYourVet_Web.4.pdf'
CLEAN = 'https://www.cdc.gov/healthy-pets/about/cleaning-and-disinfecting-pet-supplies.html'
STORAGE = 'https://www.fda.gov/animal-veterinary/animal-health-literacy/tips-safe-handling-pet-food-and-treats'
LABEL = 'https://wsava.org/wp-content/uploads/2021/04/Selecting-a-pet-food-for-your-pet-updated-2021_WSAVA-Global-Nutrition-Toolkit.pdf'
FEEDING = 'https://www.aaha.org/resources/2021-aaha-nutrition-and-weight-management-guidelines/feeding-plans-for-healthy-appropriate-weight-cats-and-dogs/'
TRANSITION = 'https://www.aaha.org/resources/healthy-tails-how-to-choose-the-right-food-for-your-pet/'
NUTRITION = 'https://wsava.org/global-guidelines/global-nutrition-guidelines/'
HANDLING = 'https://catvets.com/resource/2019-respectful-handling-to-prevent-fear-and-pain-position-statement/'
NAILS = 'https://catfriendly.com/routine-care-grooming/nail-trimming/'
TRAVEL = 'https://www.fda.gov/animal-veterinary/animal-health-literacy/travel-training-you-and-your-pets'
EMERGENCY = 'https://www.cdc.gov/healthy-pets/emergency-preparedness/index.html'

# URL -> title, original locator, scope. These pages were opened in this batch.
CHECKED = {
    CLEAN: ('About Cleaning and Disinfecting Pet Supplies', 'Difference between cleaning and disinfecting; Using soapy water; Tips to clean and disinfect safely', '猫狗物品清洁、标签、安全接触；不移植美国消毒剂注册制度'),
    STORAGE: ('Tips for Safe Handling of Pet Food and Treats', 'Tips for Preparing Pet Food; Tips for Storing Pet Food', '食品储存、原袋、手部与食盆清洁分别处理'),
    LABEL: ('Guidelines on Selecting Pet Foods', 'p1: What to look for in a brand; What to look for on a label', '猫狗营养适用声明、每克或每份热量、厂家核对；非品牌认证'),
    FEEDING: ('Feeding Plans for Healthy, Appropriate Weight Cats and Dogs', 'opening recommendations; current intake steps 1–4', '健康、体况合适猫狗的喂食与饮食调整原则；原章节有明确前提'),
    TRANSITION: ('How to Choose the Right Food for Your Pet', 'Monitoring your pet’s health; Avoiding frequent diet changes', '猫狗逐步调整饮食及观察；不保证统一完成期限'),
    NUTRITION: ('Nutrition Guidelines', 'Body condition score tools; Muscle condition score charts; Diet History Form', 'BCS评估脂肪、MCS评估肌肉，分别记录'),
    CARRIER: ('Visiting Your Veterinarian', 'pp1–2: Positive Carrier Experiences; Choosing the Right Cat Carrier; Carrier Training in Six Simple Steps', '仅猫：自愿进入、分步适应、底部托举、不同猫独立运输箱'),
    HANDLING: ('2019 Respectful Handling of Cats to Minimize Fear and Pain', 'position statement paragraphs 1–3', '尊重式互动与恐惧疼痛；不是家庭临床保定教程'),
    NAILS: ('Trimming Your Cat’s Nails', 'Helpful Tips and Things to Know', '猫：安静环境、逐步练习、休息与请兽医示范'),
    TRAVEL: ('Travel Training for You and Your Pets', 'Before You Go; Traveling by Plane; Traveling by Car', '猫狗出行前沟通和实际承运要求；不是中国证件强制清单'),
    EMERGENCY: ('Be Prepared: Pet Safety in Emergencies', 'Prepare a pet disaster kit; Practice evacuating your pet', '猫狗身份、医疗记录、联系人与应急准备'),
    CAT+'feeding-your-cat': ('Feeding Your Cat', 'Choosing A Food; Other Considerations', '仅猫：阶段、标签和个体差异；不外推犬的具体换粮方法'),
    CAT+'choosing-and-caring-your-new-cat': ('Choosing and Caring for Your New Cat', 'Grooming; Food', '仅猫：梳毛、剪甲专业示范与逐步换粮'),
    CAT+'feline-dental-disease': ('Feline Dental Disease', 'Gingivitis: Clinical Signs/Diagnosis; Prevention and Treatment', '仅猫：猫用牙膏、渐进适应、疼痛与炎症先核对'),
    CAT+'feline-behavior-problems-aggression': ('Feline Behavior Problems: Aggression', 'Petting-Induced Aggression', '猫互动中的停止接触与给予空间，不推测病因'),
    DOG+'dog-crates-when-use-them-and-how-pick-one': ('Dog crates: When to use them and how to pick one', 'Are there situations when a crate shouldn’t be used?; How can you determine the right size crate?', '仅犬：站立转身躺卧与明显困扰不能强行留箱'),
    DOG+'anxious-behavior-how-help-your-dog-cope-unsettling-situations': ('Anxious behavior: How to help your dog cope with unsettling situations', 'Anxiety in dogs is seldom a simple diagnosis; Helping an anxious dog', '犬焦虑评估、环境管理与专业支持；不承诺治疗期限'),
    DENTAL_DOG: ('Dental disease and home dental care', 'What are the signs?; Home dental care; after professional care', '仅犬：家庭清洁与疼痛就医，专业处理后按兽医要求恢复'),
    'https://www.fda.gov/animal-veterinary/animal-health-literacy/complete-and-balanced-pet-food': ('Complete and Balanced Pet Food', 'nutritional adequacy statement and life stages', '美国标签声明的含义，不证明中国上市合规'),
}
for animal in ('Cat','Dog'):
    url=f'https://wsava.org/wp-content/uploads/2025/06/WSAVA_BCSCat_BCS{animal}_Nutrition_250612.pdf'
    CHECKED[url]=(f'Body Condition Score – {animal}', 'p1: ribs, waist, abdomen and score descriptions', f'{animal}脂肪体况观察；不能合并肌肉评分')

TOPICS = dict(zip(
    ['养宠前准备','新宠到家','饮食与体重','居住与清洁','互动与训练','生命阶段','误区与危险','健康与就医','品种照护','食物选购','用品选购'],
    ['preparation','arrival','nutrition-weight','environment-cleaning','interaction-training','life-stage','hazards','health-visit','breed-care','food-selection','supply-selection']))

# Explicit topic membership; each article also retains its original topic.
GROUPS = {
 'feeding': ('cat-food','dog-food','nutrition-feeding','feeding-followup'),
 'appetite': ('cat-appetite',),
 'vomiting': ('cat-vomiting',),
 'food-transition': ('food-transition',),
 'alone': ('dog-alone','dog-fear-support'),
 'carrier': ('cat-carrier','dog-crate','supply-carriers'),
 'cleaning': ('cat-clean','dog-clean','supply-cleaning','supply-bowls','food-storage'),
 'food-label': ('food-labels','food-adequacy','food-stage','food-energy','nutrition-label'),
 'grooming': ('cat-grooming','cat-low-stress-care','dog-grooming','supply-grooming'),
 'dental': ('cat-dental','dog-dental','supply-dental'),
 'body-muscle': ('nutrition-cat-bcs','nutrition-dog-bcs','nutrition-muscle'),
 'travel': ('pet-travel','visit-preparation','care-handoff'),
}
ALIASES = {
 'food-transition':['换粮','新粮','旧粮','混粮','转粮'],
 'alone':['独处','独自在家','分离','叫喊','拆家'],
 'carrier':['航空箱','运输箱','笼箱','进箱'],
 'cleaning':['清洁','清洗','消毒','食盆','砂盆'],
 'food-label':['标签','包装','保证分析','营养适用声明','代谢能'],
 'grooming':['梳毛','剪甲','剪指甲','护理','抗拒'],
 'dental':['刷牙','口腔','牙齿'],
 'body-muscle':['BCS','MCS','体况评分','肌肉状况'],
 'travel':['出行','健康文件','健康证明','交接'],
}

OBJECT_ALIASES = {
 'supply-bowls':['食盆','食碗','食水器具','狗碗','猫碗','洗碗机','机洗'],
 'supply-cleaning':['清洁用品','清洁剂','消毒','环境清洁'],
 'supply-carriers':['运输箱','航空箱','笼箱','犬箱','猫箱','可拆顶箱'],
 'supply-litter':['猫砂','砂盆'], 'supply-beds':['窝垫','睡垫'],
 'supply-scratch':['抓板','爬架'], 'supply-toys':['玩具','啃咬物'],
 'supply-harness':['胸背','牵引'], 'supply-grooming':['梳洗工具','梳子'],
 'supply-dental':['口腔用品','牙刷','牙膏'],
}
QUESTION_OVERRIDES = {
 'cat-food':{'先看完整性与阶段':['猫的喂食和饮水有哪些基础原则','猫日常食水怎样安排']},
 'cat-vomiting':{'记录比猜测原因更有用':['猫吐了之后怎样记录呕吐过程和变化']},
 'food-labels':{'把标签项目和证明能力分开':['食品标签能说明什么','厂家说法能证明什么','WSAVA认证吗','包装项目的区别','厂家说明和独立证据一样吗']},
 'supply-cleaning':{'先清洁，再决定是否消毒':['清洁是不是等于消毒','清洁剂没有标签能猜稀释吗','消毒液怎样选择使用']},
 'supply-bowls':{'食盆清洗与人的手部卫生分开':['狗碗用完怎么洗','人的洗手时长就是食盆消毒时长吗','没有器具标签能确定可以机洗吗']},
 'cat-carrier':{'从自主进入到移动的顺序':['猫怎样自主进入运输箱并适应关门','猫运输箱练习要统一分钟数吗']},
 'nutrition-label':{'按份热量仍需对应份量':['每杯热量怎样换成每克','没有杯中克重能算个体食量吗']},
 'nutrition-muscle':{'脂肪和肌肉分别记录':['BCS和MCS分别反映什么','肌肉流失是否导致BCS升高']},
}

# Additions are short, independently written summaries and application checklists.
# Existing clinically useful passages remain; generic shopping templates do not.
ADDITIONS = {
 'cat-play': [('做一次可退出的互动','以下是一次互动的操作顺序，不规定每天的次数或时长；按猫当前的参与意愿和反应调整。\n1. 挑猫清醒、放松的时候开始，允许它先观察。\n2. 使用适合个体的玩具，引导跟踪和追逐，不直接拿手脚当猎物。\n3. 给猫接近、捕捉和休息的机会；兴趣下降或紧张时结束。\n4. 互动结束后检查并收好有线、细绳或可脱落部件的玩具，不能无人监督地留置危险物。')],
 'cat-multi': [('按反应推进，而不是按日历推进','介绍前先核对双方健康资料；原住猫有健康问题时，先和兽医讨论是否适合增加同伴。\n1. 新猫先在安全的独立区域安顿；让双方可以休息、进食和正常排泄，不强迫见面。\n2. 安顿后交换带气味的寝具，观察是否回避、低吼或变得紧张。\n3. 双方放松时，再尝试有可靠屏障的短暂视觉接触与分别互动。\n4. 只有先前步骤持续舒适，才考虑监督下更近的接触；保留退路和分开的资源，出现紧张立即退回较容易的阶段。')],
 'dog-play': [('一次活动前后检查','先核对已有健康问题及兽医活动限制；未知项保留未知，不能当成已经确认健康。新的运动项目或已有疾病的活动限制向兽医确认。\n1. 先看精神、步态及天气，选择能够安全返回的路线。\n2. 使用安全牵引，并给犬适合的探索与排泄机会。\n3. 穿插容易成功的简单互动，不以拉扯或惩罚让犬服从。\n4. 观察活动中及之后的恢复情况，有异常及时停止并寻求评估。')],
 'dog-alone': [('离开练习的前提与退出','独处练习先确认当前难度是狗能够接受的，而不是追求离开时间。把离家线索、独处反应和有人陪伴时的表现分别记录；出现持续不安就退回较容易的步骤。无法避免较长离开时，先落实替代照护，再与兽医讨论分离相关困扰；不把叫喊停止等同于情绪已经改善。应用记录窗口不构成治疗期限。')],
 'food-transition': [
  ('先区分适用对象和换粮原因','猫狗换粮都先核对新食品是否适合当前物种和阶段；有处方饮食、过敏或疾病限制时先联系原兽医。逐步调整是一般原则，不把健康个体资料中的时间建议当作所有个体的固定完成期限。'),
  ('分步换粮与停止条件','1. 保留旧新食品的具体配方和标签，先确认更换原因及已有专业要求。\n2. 按个体接受度和兽医建议逐步调整新旧食物，记录提供量与实际吃下量。\n3. 尽量保持其他饮食因素稳定，分别观察食欲、排泄、呕吐和精神。\n4. 出现拒食或不适时停止继续盲目推进，带着标签和时间线联系兽医；不通过让猫挨饿来迫使接受新粮。'),
 ],
 'supply-carriers': [
  ('是否需要与适用条件','先确定是运输、就诊还是休息用箱。犬的尺寸与留箱限制、猫的箱体及搬运方式分别核对，不能直接跨物种套用。运输前另向实际运营方核对规格和文件要求；箱体是否适用还需结合个体反应。'),
  ('犬的尺寸和使用限制','犬的笼箱应容许自然站立、转身和舒适躺卧。明显喘气、踱步、持续叫喊或逃脱挣扎时，不强迫它独自留在箱中；与兽医讨论其他安全安排。犬的尺寸和训练资料不能直接当作猫的出行依据。'),
  ('猫的箱体与移动方式','猫的运输箱要安全、便于进出及清洁；可拆顶结构方便在就诊时减少强行拖拽。多猫出行各用自己的箱。移动时从底部托稳，不能只提把手；猫的这些建议不自动套到犬的笼内独处安排。'),
 ],
 'dog-crate': [('尺寸、参与意愿和停止条件','犬应能在箱中自然站立、转身和舒适躺卧。先让它自愿接近、进入，以奖励式练习建立安全休息体验，再按反应增加难度。若出现明显持续叫喊、喘气、踱步或挣扎，不强迫它留箱独处，应降低难度并与兽医讨论替代照护。箱子不替代如厕、活动和陪伴。')],
 'cat-carrier': [('从自主进入到移动的顺序','先把箱子留在猫常活动的位置，放入有熟悉气味的垫物。让猫自主接近和进入，待它适应当前步骤后再尝试关门、延长停留和移动。搬动时从底部托稳，保持平稳。不要为了赶进度强行推进；持续害怕时提前向兽医讨论就诊安排。这里不设所有猫通用的练习分钟数。')],
 'supply-cleaning': [('先清洁，再决定是否消毒','清洁是去掉污物，消毒是额外处理病原的步骤，两者不同。先看物品材质和标签。耐水硬物可用清洁剂和水洗净、冲去残留并晾干；需要消毒时按产品标签的适用表面和接触时间操作，未达到允许接触条件前不让宠物接近。不得把美国注册标识当成中国要求。'),('清洁过程的接触安全','把猫狗与操作区域分开，不让它们舔到湿的消毒剂。不同清洁剂不要混合；用品完成标签要求的冲洗和干燥后再交还。猫的消毒用品需特别核对成分，不能仅凭“天然”“宠物友好”字样判断安全。')],
 'supply-bowls': [('食盆清洗与人的手部卫生分开','食盆和量具按实际使用及食品残留情况清洗，冲净清洁剂并干燥；可机洗与否看器具标签。处理食品前后的洗手要求属于人的手部卫生，不能把手部洗涤时长改成食盆必须浸泡的时长。湿粮剩余和干粮储存分别按食品标签处理。')],
 'food-storage': [('储存与卫生分别核对','干粮保留原袋和批次，收好袋口并放在干燥、凉爽、宠物接触不到的位置。湿粮开封后按标签及时处理剩余；需要冷藏时妥善覆盖。处理食品前后洗手，食盆与量具另行清洗，不能把人的洗手时长当作洗碗或消毒规定。过期或变质食品不继续喂。')],
 'food-labels': [('把标签项目和证明能力分开','营养适用声明回答是否为完整饮食及适用阶段，保证分析中的最低或最高值不等于精确实测值；代谢能与上述项目分别核对。厂家关于人员、质控和研究的答复属于待核实材料，不是WSAVA认证或独立疗效证明。美国标签规则不能自动当作中国上市要求。')],
 'nutrition-label': [('按份热量仍需对应份量','抄录包装能量数值、单位和对应的食品份量。每杯或每罐热量不能直接变成每克热量，除非对应克重也已明确。标签用于提供食品数据；个体食量还取决于营养评估是否就绪，补一项标签不等于可以精确算出该宠物的喂食量。')],
 'nutrition-muscle': [('脂肪和肌肉分别记录','BCS评估脂肪储备，MCS评估肌肉状况，二者不是一个整体健康评分。脂肪偏多与肌肉损失可以同时存在，不能说肌肉流失导致BCS升高。起身、活动或触感变化可以作为主人观察提交给兽医，不据此命名MCS指标或自行判定肌肉损失。')],
 'pet-travel': [('证件核对与实际承运要求','本篇是一般行前准备资料，未核实实际目的地及运营方的现行文件要求，不能据此确定整段行程的证件清单。先确定目的地、运输方式和实际运营方，再逐项询问身份、健康及其他文件要求，记录答复日期。整理健康文件不等于任何自驾或运输都必须另开健康证明；美国机构的清单不是中国统一法规。已有疾病、用药或饮食限制应提前与兽医沟通。')],
 'visit-preparation': [('记录与交接，不推断诊断','把观察到的变化、开始时间、已有病史与兽医限制分开写，带上可获得的医疗记录和联系人；不知道的内容保持未知。普通就医材料准备不能自动改写成疑似误食处置。急症优先联系兽医，不为凑齐清单延迟出发。')],
 'care-handoff': [('交接事实与执行权限','交接宠物身份、联系人、现用食品、已完成事项和兽医原建议；每项写清时间及来源。替代照护人核对自己实际接收了什么，缺失标记未知。应用清单只是整理方式，不生成新处方、不授权改治疗或改变原计划。')],
}

EXTRA_REFS = {
 'food-transition':[FEEDING, TRANSITION, CAT+'choosing-and-caring-your-new-cat'],
 'supply-carriers':[CARRIER, DOG+'dog-crates-when-use-them-and-how-pick-one'],
 'dog-crate':[DOG+'dog-crates-when-use-them-and-how-pick-one'], 'cat-carrier':[CARRIER],
 'supply-cleaning':[CLEAN], 'supply-bowls':[CLEAN,STORAGE], 'food-storage':[STORAGE,CLEAN],
 'food-labels':[LABEL,'https://www.fda.gov/animal-veterinary/animal-health-literacy/complete-and-balanced-pet-food'],
 'nutrition-label':[LABEL], 'nutrition-muscle':[NUTRITION],
 'pet-travel':[TRAVEL], 'visit-preparation':[EMERGENCY], 'care-handoff':[EMERGENCY],
 'cat-grooming':[CAT+'choosing-and-caring-your-new-cat',HANDLING,NAILS],
 'cat-low-stress-care':[HANDLING,NAILS], 'cat-dental':[CAT+'feline-dental-disease'],
 'dog-dental':[DENTAL_DOG], 'supply-dental':[CAT+'feline-dental-disease',DENTAL_DOG],
 'dog-alone':[DOG+'anxious-behavior-how-help-your-dog-cope-unsettling-situations'],
 'dog-fear-support':[DOG+'anxious-behavior-how-help-your-dog-cope-unsettling-situations'],
}


def role(heading, text, first=False):
    if first:
        return ['scope']
    roles=[]
    if re.search(r'前提|适用|需要哪些资料|填写|资料缺口|深入分析前',heading): roles.append('prerequisites')
    if re.search(r'(?m)^\d+\. ',text) or re.search(r'步骤|分步|练习|顺序|使用|清洗|怎样.*(?:安排|执行|调整)|实际核对',heading): roles.append('action')
    if re.search(r'停止|边界|限制|风险|安全|求助|专业帮助|专业处理|不自行|就医|注意事项|退出',heading): roles.append('boundary')
    if re.search(r'观察|记录|衡量|进展',heading): roles.append('observation')
    return roles or ['explanation']


def main():
    directory=DATA/'evidence'
    directory.mkdir(exist_ok=True)
    sources, annotations, changes={}, {}, []
    for path in sorted(DATA.glob('knowledge*.json')):
        articles=json.loads(path.read_text(encoding='utf-8'))
        for article in articles:
            aid=article['id']
            original=digest(article)
            article['content_kind']=article.get('content_kind','care')
            if aid=='dog-home':
                article['life_stages']=['puppy']
            elif aid=='dog-socialization':
                article['life_stages']=['puppy']
            elif aid=='dog-adolescent':
                article['life_stages']=['adolescent']
            article.setdefault('breed_ids',[])
            passages=article_sections(article['body'])
            if aid=='food-transition':
                excluded={'需要记录什么','怎样比较和控制成本','深入分析前需要哪些资料'}
                passages=[p for p in passages if p['heading'] not in excluded]
            if aid in ADDITIONS:
                replacement={heading:text for heading,text in ADDITIONS[aid]}
                existing={p['heading'] for p in passages}
                passages=[{**p,'text':replacement.get(p['heading'],p['text'])} for p in passages]
                passages.extend({'heading':heading,'text':text} for heading,text in replacement.items() if heading not in existing)
                article['body']='\n\n'.join(p['text'] if i==0 and p['heading']==p['text'] else '## '+p['heading']+'\n'+p['text'] for i,p in enumerate(passages))
            # Existing primary source is included even when references used to be empty.
            refs={r['url']:r for r in article.get('references',[])}
            refs.setdefault(article['source_url'], {'organization':article['source_organization'],'url':article['source_url'],
                  'supports':'原资料所列的适用原则；逐块定位见独立来源清单',
                  'version':article['source_version'],'checked_at':article['ingested_at']})
            for url in EXTRA_REFS.get(aid,[]):
                title,locator,support=CHECKED[url]
                org=('Cornell 兽医学院' if 'cornell.edu' in url else 'FelineVMA' if 'catvets' in url or 'catfriendly' in url else
                     'CDC' if 'cdc.gov' in url else 'FDA' if 'fda.gov' in url else 'AAHA' if 'aaha.org' in url else 'WSAVA')
                refs[url]={'organization':org,'url':url,'supports':support,'version':title+'；原版本见独立来源记录','checked_at':DATE}
            article['references']=list(refs.values())
            if digest(article)!=original:
                article['updated_at']=DATE
                changes.append(aid)
            ref_ids=[]
            for url,ref in refs.items():
                sid='src-'+digest(url)[:16]
                ref_ids.append(sid)
                checked=CHECKED.get(url)
                sources.setdefault(sid, {'url':url,'organization':ref['organization'],
                    'title':checked[0] if checked else article['source_version'],
                    'published_at':None,'version':ref['version'],
                    'checked_at':DATE if checked else ref['checked_at'],
                    'verification_status':'page_rechecked' if checked else 'historical_not_rechecked',
                    'locator':checked[1] if checked else '原编辑版本：'+ref['version']+'；精确原文定位待复核',
                    'supports':checked[2] if checked else ref['supports'],
                    'reuse':'独立中文摘要和必要定位；不复制原文图片或整篇',
                })
            subtopics=[group for group,ids in GROUPS.items() if aid in ids]
            if not subtopics:
                subtopics=['breed-profile'] if article['content_kind']=='breed' else [TOPICS[article['topic']]]
            aliases=list(dict.fromkeys(alias for group in subtopics for alias in ALIASES.get(group,[])))
            meta={'species':article['species'],'content_kind':article['content_kind'],
                  'topic_id':TOPICS[article['topic']],'original_topic':article['topic'],'subtopics':subtopics,
                  'aliases':aliases,'breed_applicability':'specified' if article.get('breed_ids') else 'general',
                  'life_stages':{'state':'explicit_all' if 'all' in article['life_stages'] else 'specified','values':article['life_stages']},
                  'health_conditions':{'state':'unknown','values':[]},
                  'region':{'state':'source_specific','values':[]},
                  'data_destination':'public_knowledge','classification_checked_at':DATE,
                  'classification_reviewer':'editorial_code_review','sections':{}}
            passages=article_sections(article['body'])
            keys={p['heading']:('scope' if i==0 else digest(p['heading'])[:12]) for i,p in enumerate(passages)}
            # Dependencies are recorded, inspectable annotations, not runtime heading expansion.
            boundary=[p for p in passages if 'boundary' in role(p['heading'],p['text'])]
            for i,p in enumerate(passages):
                roles=role(p['heading'],p['text'],i==0)
                dependencies=[]
                if i and 'action' in roles:
                    dependencies=[keys[passages[0]['heading']]]
                    if boundary:
                        # Prefer the nearest preceding relevant stop/boundary, not every safety chapter.
                        stop=next((b for b in reversed(passages[:i]) if b in boundary),boundary[0])
                        if stop['heading']!=p['heading']:
                            dependencies.append(keys[stop['heading']])
                if aid=='dog-alone' and p['heading'] in ('怎么选择可以执行的练习','离开练习的前提与退出'):
                    dependencies.append(keys['练习应在可承受范围内'])
                if aid=='cat-appetite' and i:
                    dependencies.append(keys[passages[0]['heading']])
                mapped=ref_ids[:]
                species=article['species']
                if aid=='supply-carriers' and p['heading'].startswith(('犬的','猫的')):
                    cat=p['heading'].startswith('猫的')
                    species=['cat' if cat else 'dog']
                    mapped=['src-'+digest(CARRIER if cat else DOG+'dog-crates-when-use-them-and-how-pick-one')[:16]]
                meta['sections'][p['heading']]={'key':keys[p['heading']],'roles':roles,
                    'source_ids':mapped,'depends_on':list(dict.fromkeys(dependencies)),
                    'species':species,'evidence_nature':'editorial_summary_and_checklist',
                    'conditions':[],'questions':QUESTION_OVERRIDES.get(aid,{}).get(p['heading'],[article['title']+'：'+p['heading']+'？']),
                    'object_aliases':OBJECT_ALIASES.get(aid,[])}
            annotations[aid]=meta
        path.write_text(json.dumps(articles,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result={'schema_version':1,'batch':'20261019-evidence-rebuild','taxonomy_version':'classification-v1',
            'review_status':'editorial_summary_unreviewed','topics':TOPICS,
            'subtopics':{k:{'aliases':ALIASES.get(k,[])} for k in sorted({t for a in annotations.values() for t in a['subtopics']})},
            'sources':sources,'articles':annotations}
    (directory/'annotations.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (directory/'batch.json').write_text(json.dumps({'batch':result['batch'],'article_count':len(annotations),
        'classification_count':dict(__import__('collections').Counter(a['content_kind'] for a in annotations.values())),
        'substantively_updated':sorted(ADDITIONS),'changed_metadata':sorted(changes),
        'rechecked_source_count':sum(s['verification_status']=='page_rechecked' for s in sources.values()),
        'pending_source_count':sum(s['verification_status']=='historical_not_rechecked' for s in sources.values()),
        'limitations':['分类核对不等于兽医审核','历史来源未全部重新打开；逐源状态保留','切分、检索和真实回答另行验收']},
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Separate reviewed page records survive reproducible editorial rebuilds.
    if (directory/'source_reviews.json').exists():
        from scripts.apply_source_reviews import main as apply_page_reviews
        apply_page_reviews()
    if (directory/'section_reviews.json').exists():
        from scripts.apply_section_reviews import main as apply_reviewed_sections
        apply_reviewed_sections()
    print(json.dumps({'classified':len(annotations),'substantively_updated':len(ADDITIONS),'sources':len(sources)}))


if __name__=='__main__':
    main()
