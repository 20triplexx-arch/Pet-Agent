"""Fail-closed Beijing peak tariffs; cache discounts never reduce reservations."""
import hashlib
import html
import re
import urllib.request
from datetime import datetime, UTC
from app.alibaba_models import family

TARIFFS = {
    'qwen3.6-flash': [(262144, 1.2, 7.2), (1000000, 4.8, 28.8)],
    'qwen3.7-plus': [(262144, 2, 8), (1000000, 6, 24)],
    'qwen3.5-flash': [(131072, .2, 2), (262144, .8, 8), (1000000, 1.2, 12)],
    'qwen3.7-max': [(1000000, 12, 36)],
}


def verified_price(model, page=None):
    group = family(model)
    if group not in TARIFFS:
        raise ValueError('This model has no reviewed tariff parser')
    url = 'https://help.aliyun.com/zh/model-studio/' + group.replace('.', '-')
    if page is None:
        page = urllib.request.urlopen(url, timeout=25).read().decode('utf-8')
    text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', page)).replace('\\n', ' '))
    if model not in text:
        raise ValueError('The official model page does not name the requested version')
    block = text[text.index('模型价格'):]
    block = block[block.index('华北'):]
    ends = [block.find(region) for region in ('新加坡', '德国', '美国', '日本', '中国香港') if block.find(region) >= 0]
    if not ends:
        raise ValueError('Could not isolate the Beijing tariff')
    block = block[:min(ends)]
    prices = [(float(i), float(o)) for i, o in re.findall(r'输入\s+([\d.]+)\s+每百万\s*tokens\s+输出\s+([\d.]+)\s+每百万\s*tokens', block)]
    expected = TARIFFS[group]
    if prices != [(i, o) for _, i, o in expected]:
        raise ValueError('Official tariff changed; do not infer a cheaper price')
    return {'currency':'CNY', 'provider':'alibaba', 'model':model, 'checked_at':datetime.now(UTC).isoformat(),
            'source':url, 'table_sha256':hashlib.sha256(block.encode()).hexdigest(),
            'tiers':[{'max_input_tokens':n, 'input_per_million':i, 'output_per_million':o} for n, i, o in expected]}
