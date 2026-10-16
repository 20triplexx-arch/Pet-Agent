"""Install a reviewed qualification manifest; never infer approval from latency."""
import argparse
import json
from pathlib import Path
from datetime import datetime, UTC
from app.alibaba_quota import answer_build_hash
from app.alibaba_models import family
from app.core.config import settings


def qualify(review):
    build = answer_build_hash()
    if review['answer_build_sha256'] != build:
        raise ValueError('Review does not match the current answer implementation')
    approved = {}
    for model in review['order']:
        item = review['models'][model]
        if not family(model) or not item.get('approved'):
            continue
        if not (item['case_count'] >= 30 and item['delivery_rate'] >= .9
                and item['major_source_support_rate'] >= .95 and item['severe_delivered_issues'] == 0):
            raise ValueError('Candidate has not passed the documented reliability and source gates')
        approved[model] = {**item, 'answer_build_sha256': build}
    target = Path(settings.DASHSCOPE_QUALIFIED_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    document = {'checked_at': datetime.now(UTC).isoformat(), 'order': list(approved), 'models': approved,
        'review_method': review['review_method'], 'limitations': review.get('limitations', [])}
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(target)
    print(json.dumps({'qualified_models': list(approved), 'build': build}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('review', type=Path)
    qualify(json.loads(parser.parse_args().review.read_text(encoding='utf-8')))
