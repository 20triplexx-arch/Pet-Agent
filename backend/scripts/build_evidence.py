"""Rebuild or verify the public evidence artifact; never imports the app/database."""
import argparse
import json
from pathlib import Path
from app.evidence_index import build_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'data'
    articles = [a for p in sorted(root.glob('knowledge*.json')) for a in json.loads(p.read_text(encoding='utf-8'))]
    annotation = json.loads((root/'evidence/annotations.json').read_text(encoding='utf-8'))
    path = root/'evidence/index.json'
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    index = build_index(articles, annotation, previous)
    if args.check:
        if previous != index:
            raise SystemExit('Evidence artifact is stale; run python -m scripts.build_evidence')
    else:
        path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'articles': len(articles), 'chunks': len(index['chunks']),
                      'manifest_sha256': index['manifest_sha256'], 'checked': args.check}))


if __name__ == '__main__':
    main()
