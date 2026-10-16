"""Documented general-chat families, distinct from account quota and qualification.

Source: https://help.aliyun.com/zh/model-studio/qwen-structured-output
Discovery does not authorize a model for serving: every candidate still needs a
current-build source review and an account-specific free-only quota snapshot.
"""
import re

DEFAULT_MODELS = ('qwen3.7-plus', 'qwen3.6-flash', 'qwen3.5-flash', 'qwen-flash-2025-07-28',
                  'qwen3.8-flash', 'qwen3.7-flash-2026-07-15', 'qwen3.7-flash',
                  'qwen-flash', 'qwen-plus', 'qwen-plus-latest', 'qwen3.7-max', 'qwen-max')


def family(name):
    match = re.fullmatch(r'(qwen(?:3\.[5678])?-(?:flash|plus|max))(?:-(?:latest|preview|\d{4}(?:-\d{2}-\d{2})?))?', name)
    return match[1] if match else None


def supports_schema(name):
    return family(name) in {'qwen3.7-plus', 'qwen3.7-flash', 'qwen3.8-flash', 'qwen3.7-max', 'qwen3.8-max'}


def candidate(row):
    return isinstance(row, dict) and row.get('type') in (None, 'Text') and family(row.get('model', '')) is not None


def ordered_candidates(rows):
    names = list(dict.fromkeys(row['model'] for row in rows if candidate(row)))
    rank = {name: index for index, name in enumerate(DEFAULT_MODELS)}
    return sorted(names, key=lambda name: (rank.get(name, len(rank)), name))
