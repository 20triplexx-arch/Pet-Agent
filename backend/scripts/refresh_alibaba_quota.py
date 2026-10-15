"""Read verified free balances, optionally enabling free-only for eligible candidates."""
import argparse
import json
from app.alibaba_quota import refresh_quotas

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--enable-free-only', action='store_true')
    options = parser.parse_args()
    try:
        print(json.dumps({'models': refresh_quotas(enable_stop=options.enable_free_only)}, ensure_ascii=False))
    except Exception as error:
        # Never echo a subprocess command, credentials, console token or provider body.
        print(json.dumps({'error': type(error).__name__, 'message': '免费额度核验失败，请检查独立CLI网页授权、业务空间与配置。'}, ensure_ascii=False))
        raise SystemExit(1)
