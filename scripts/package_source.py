"""Package source and design context without local data, credentials or builds."""

import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    "node_modules", "storage", "dist", "test-results", "playwright-report",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".git",
    ".venv", ".venv313", "venv", ".tox", "htmlcov", "coverage",
}
ROOT_FILES = [
    ".impeccable/review/chat-stream-review.md",
    ".impeccable/review/chat-stream-detect.json",
    ".impeccable/review/chat-stream-desktop.png",
    ".impeccable/review/chat-stream-mobile.png",
    ".impeccable/review/chat-stream-live-desktop-brief.png",
    ".impeccable/review/chat-stream-live-mobile-brief.png",
    "README.md", "TEST_RESULTS.md", "UPSTREAM.md", "PRODUCT.md", "DESIGN.md",
    "LICENSE", ".env.example", ".gitignore", ".dockerignore", "Dockerfile",
    "compose.yaml", ".impeccable/design.json",
    ".impeccable/surfaces/local-model-limits.md",
    ".impeccable/review/local-limits-review.md",
    ".impeccable/review/local-limits-documentation.md",
    ".impeccable/review/local-limits-detect.json",
    ".impeccable/review/local-limits-desktop.png",
    ".impeccable/review/local-limits-mobile.png",
    ".impeccable/review/local-limits-bounded-desktop.png",
    ".impeccable/review/local-limits-bounded-mobile.png",
    ".impeccable/surfaces/hospital-combined.md",
    ".impeccable/review/hospital-combined-review.md",
    ".impeccable/review/hospital-combined-documentation.md",
    ".impeccable/review/hospital-combined-detect.json",
    ".impeccable/review/hospital-combined-desktop.png",
    ".impeccable/review/hospital-combined-mobile.png",
    ".impeccable/review/hospital-combined-user-1031.png",
    ".impeccable/review/hospital-combined-before-query-desktop.png",
    ".impeccable/review/hospital-combined-before-query-mobile.png",
    ".impeccable/review/hospital-combined-loading-desktop.png",
    ".impeccable/review/hospital-combined-loading-mobile.png",
    ".impeccable/review/hospital-combined-conflict-desktop.png",
    ".impeccable/review/hospital-combined-conflict-mobile.png",
    ".impeccable/review/hospital-combined-partial-desktop.png",
    ".impeccable/review/hospital-combined-partial-mobile.png",
    ".impeccable/review/hospital-combined-no-key-desktop.png",
    ".impeccable/review/hospital-combined-no-key-mobile.png",
    ".impeccable/surfaces/tianditu-integration.md",
    ".impeccable/review/tianditu-review.md",
    ".impeccable/review/tianditu-verdict.md",
    ".impeccable/review/tianditu-documentation.md",
    ".impeccable/review/tianditu-detect.json",
    ".impeccable/review/tianditu-desktop.png",
    ".impeccable/review/tianditu-mobile.png",
    ".impeccable/review/tianditu-user-1031.png",
    ".impeccable/review/tianditu-no-key-desktop.png",
    ".impeccable/review/tianditu-no-key-mobile.png",
    ".impeccable/review/tianditu-failure-desktop.png",
    ".impeccable/review/tianditu-failure-mobile.png",
    ".impeccable/review/tianditu-before-query-desktop.png",
    ".impeccable/review/tianditu-before-query-mobile.png",
    ".impeccable/review/tianditu-loading-desktop.png",
    ".impeccable/review/tianditu-loading-mobile.png",
    ".impeccable/surfaces/hospital-precision.md",
    ".impeccable/review/hospital-precision-review.md",
    ".impeccable/review/hospital-precision-verdict.md",
    ".impeccable/review/hospital-precision-documentation.md",
    ".impeccable/review/hospital-precision-detect.json",
    ".impeccable/review/hospital-precision-desktop.png",
    ".impeccable/review/hospital-precision-mobile.png",
    ".impeccable/review/hospital-precision-user-1031.png",
    ".impeccable/review/hospital-precision-street-desktop.png",
    ".impeccable/review/hospital-precision-street-mobile.png",
    ".impeccable/review/hospital-precision-blocked-desktop.png",
    ".impeccable/review/hospital-precision-blocked-mobile.png",
    ".impeccable/surfaces/hospital-search-upgrade.md",
    ".impeccable/review/hospital-search-review.md",
    ".impeccable/review/hospital-search-verdict.md",
    ".impeccable/review/hospital-search-documentation.md",
    ".impeccable/review/hospital-search-detect.json",
    ".impeccable/review/hospital-search-desktop.png",
    ".impeccable/review/hospital-search-mobile.png",
    ".impeccable/review/hospital-search-user-1031.png",
    ".impeccable/review/hospital-search-candidates-desktop.png",
    ".impeccable/review/hospital-search-candidates-mobile.png",
    ".impeccable/review/hospital-search-failure-desktop.png",
    ".impeccable/review/hospital-search-failure-mobile.png",
    ".impeccable/surfaces/hospital-navigation.md",
    ".impeccable/review/hospital-nav-review.md",
    ".impeccable/review/hospital-nav-verdict.md",
    ".impeccable/review/hospital-nav-documentation.md",
    ".impeccable/review/hospital-nav-detect.json",
    ".impeccable/review/hospital-nav-desktop.png",
    ".impeccable/review/hospital-nav-compact.png",
    ".impeccable/review/hospital-nav-mobile.png",
    ".impeccable/review/hospital-nav-more-mobile.png",
    ".impeccable/surfaces/chat-model-selection.md",
    ".impeccable/review/chat-model-review.md",
    ".impeccable/review/chat-model-documentation.md",
    ".impeccable/review/chat-model-detect.json",
    ".impeccable/review/chat-model-desktop.png",
    ".impeccable/review/chat-model-mobile.png",
    ".impeccable/review/chat-model-user-1031.png",
    ".impeccable/review/chat-model-depth-desktop.png",
    ".impeccable/review/chat-model-depth-mobile.png",
    ".impeccable/surfaces/care-review.md",
    ".impeccable/review/care-review-review.md",
    ".impeccable/review/care-review-documentation.md",
    ".impeccable/review/care-review-detect.json",
    ".impeccable/review/care-review-desktop.png",
    ".impeccable/review/care-review-mobile.png",
    ".impeccable/review/care-review-empty-desktop.png",
    ".impeccable/review/care-review-empty-mobile.png",
    ".impeccable/review/care-batch-desktop.png",
    ".impeccable/review/care-batch-mobile.png",
    ".impeccable/review/care-evidence-desktop.png",
    ".impeccable/review/care-evidence-mobile.png",
    ".impeccable/review/care-evidence-end-desktop.png",
    ".impeccable/review/care-evidence-end-mobile.png",
    ".impeccable/surfaces/deep-chat.md",
    ".impeccable/review/deep-chat-review.md",
    ".impeccable/review/deep-chat-verdict.md",
    ".impeccable/review/deep-chat-documentation.md",
    ".impeccable/review/deep-chat-detect.json",
    ".impeccable/review/deep-chat-answer-desktop.png",
    ".impeccable/review/deep-chat-answer-mobile.png",
    ".impeccable/review/deep-chat-supplement-desktop.png",
    ".impeccable/review/deep-chat-supplement-mobile.png",
    ".impeccable/review/deep-chat-table-desktop.png",
    ".impeccable/review/deep-chat-table-mobile.png",
    ".impeccable/surfaces/frontend-src-app-tsx.md",
    ".impeccable/surfaces/frontend-src-care-pages-tsx.md",
    ".impeccable/surfaces/knowledge-products.md",
    ".impeccable/review/knowledge-products-review.md",
    ".impeccable/review/knowledge-products-verdict.md",
    ".impeccable/review/knowledge-products-documentation.md",
    ".impeccable/review/knowledge-products-detect.json",
    ".impeccable/review/knowledge-products-desktop.png",
    ".impeccable/review/knowledge-products-mobile.png",
    ".impeccable/review/product-desktop.png",
    ".impeccable/review/product-mobile.png",
    ".impeccable/review/product-result-desktop.png",
    ".impeccable/review/product-result-mobile.png",
    ".impeccable/review/product-ocr-desktop.png",
    ".impeccable/review/product-ocr-mobile.png",
    ".impeccable/review/care-upgrade-review.md",
    ".impeccable/review/care-upgrade-documentation.md",
    ".impeccable/review/review.md", ".impeccable/review/verdict.md",
    ".impeccable/review/home-density-review.md",
    ".impeccable/review/pet-portraits-review.md",
    ".impeccable/review/knowledge-expansion-review.md",
    ".impeccable/review/knowledge-expanded-live-desktop.png",
    ".impeccable/review/knowledge-expanded-live-mobile.png",
    ".impeccable/review/knowledge-expanded-desktop.png",
    ".impeccable/review/knowledge-expanded-mobile.png",
    ".impeccable/review/pet-portraits-desktop.png",
    ".impeccable/review/pet-portraits-mobile.png",
    ".impeccable/review/pet-portraits-mobile-dog.png",
    ".impeccable/assets/pet-companions-original.png",
    ".impeccable/assets/pet-portrait-cat-original.png",
    ".impeccable/assets/pet-portrait-dog-original.png",
]


def source_files():
    for relative in ROOT_FILES:
        path = ROOT / relative
        if path.is_file():
            yield path
    review = ROOT / ".impeccable" / "review" / "redesign"
    if review.is_dir():
        for path in sorted(review.iterdir()):
            if path.is_file() and path.suffix in {".md", ".json", ".png"}:
                yield path
    for directory in ("backend", "frontend", "scripts", "docs", ".github"):
        for parent, dirs, files in os.walk(ROOT / directory):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith("pytest-cache-files-")]
            for name in sorted(files):
                if (name.startswith(".env") or name == ".secret" or name.endswith((
                    ".pyc", ".tsbuildinfo", ".db", ".sqlite", ".sqlite3", ".log",
                    ".db-journal", ".db-shm", ".db-wal", ".key", ".pem",
                ))):
                    continue
                yield Path(parent) / name


def main():
    target = ROOT / "artifacts" / "chongban-mvp.zip"
    target.parent.mkdir(exist_ok=True)
    temporary = target.with_suffix(".tmp.zip")
    with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(set(source_files())):
            archive.write(path, path.relative_to(ROOT).as_posix())
    with ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Source archive integrity check failed")
        count = len(archive.namelist())
    temporary.replace(target)
    print(f"{target.name}: {count} files, {target.stat().st_size} bytes; integrity OK")


if __name__ == "__main__":
    main()
