"""Package source and design context without local data, credentials or builds."""

import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    "node_modules", "storage", "dist", "test-results", "playwright-report",
    "__pycache__", ".pytest_cache", ".git",
}
ROOT_FILES = [
    "README.md", "TEST_RESULTS.md", "UPSTREAM.md", "PRODUCT.md", "DESIGN.md",
    "LICENSE", ".env.example", ".gitignore", ".dockerignore", "Dockerfile",
    "compose.yaml", ".impeccable/design.json",
    ".impeccable/surfaces/frontend-src-app-tsx.md",
    ".impeccable/surfaces/frontend-src-care-pages-tsx.md",
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
    for directory in ("backend", "frontend", "scripts", "docs"):
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
        for path in sorted(source_files()):
            archive.write(path, path.relative_to(ROOT).as_posix())
    with ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Source archive integrity check failed")
        count = len(archive.namelist())
    temporary.replace(target)
    print(f"{target.name}: {count} files, {target.stat().st_size} bytes; integrity OK")


if __name__ == "__main__":
    main()
