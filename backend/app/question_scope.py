"""Conservative explicit animal subjects, separate from mentioned food/products.""" 
import re


def explicit_species(text):
    actors = re.findall(
        r'(?:我家|另一只|一只|这只|那只|新来的)(猫|狗|犬)'
        r'|(猫|狗|犬)(?:的)?(?:运输箱|航空箱|笼箱|箱|搬运|空间|尺寸|护理|刷牙|梳毛|BCS|MCS|体况)',
        text, re.I)
    names = {word for match in actors for word in match if word}
    if re.search(r'猫(?:和|与|及|、)?(?:狗|犬)|(?:狗|犬)(?:和|与|及|、)猫', text):
        names.update(('猫', '狗'))
    return {'cat' if name == '猫' else 'dog' for name in names}
