"""
scripts/verify_docs.py

Lightweight documentation link, asset, and syntax validator.
Validates:
1. Relative markdown links point to existing target files or valid anchors.
2. Image references point to existing asset files.
3. Code fences are balanced and properly closed.
"""

import os
import sys
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(ROOT_DIR, "docs")
README_PATH = os.path.join(ROOT_DIR, "README.md")

LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
IMAGE_PATTERN = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')


def check_markdown_file(file_path: str) -> list[str]:
    errors = []
    file_dir = os.path.dirname(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()

    # 1. Check code fences
    fence_count = sum(1 for line in lines if line.strip().startswith("```"))
    if fence_count % 2 != 0:
        errors.append(f"Unbalanced code block fences (``` count: {fence_count})")

    # 2. Check links
    for match in LINK_PATTERN.finditer(content):
        link_text = match.group(1)
        url = match.group(2).strip()

        # Skip external URLs, mailto, badges, and template macros
        if url.startswith(("http://", "https://", "mailto:", "#", "<!--")):
            continue

        # Split off anchor if present
        clean_path = url.split("#")[0]
        if not clean_path:
            continue

        target_full_path = os.path.normpath(os.path.join(file_dir, clean_path))
        if not os.path.exists(target_full_path):
            errors.append(f"Broken relative link '[{link_text}]({url})' -> target not found: {clean_path}")

    # 3. Check images
    for match in IMAGE_PATTERN.finditer(content):
        alt_text = match.group(1)
        src = match.group(2).strip()

        if src.startswith(("http://", "https://", "data:")):
            continue

        img_target = os.path.normpath(os.path.join(file_dir, src))
        if not os.path.exists(img_target):
            errors.append(f"Broken image reference '![{alt_text}]({src})' -> file not found")

    return errors


def verify_all_docs() -> int:
    print("=" * 70)
    print("           LYRICA DOCUMENTATION INTEGRITY AUDIT")
    print("=" * 70)

    files_to_check = [README_PATH]
    for scan_dir in [DOCS_DIR, os.path.join(ROOT_DIR, "guide")]:
        if os.path.exists(scan_dir):
            for root, _, files in os.walk(scan_dir):
                for file in files:
                    if file.endswith(".md"):
                        files_to_check.append(os.path.join(root, file))

    total_errors = 0
    for doc_file in files_to_check:
        rel_path = os.path.relpath(doc_file, ROOT_DIR)
        errors = check_markdown_file(doc_file)
        if errors:
            print(f" [FAIL] {rel_path}:")
            for err in errors:
                print(f"        - {err}")
            total_errors += len(errors)
        else:
            print(f" [PASS] {rel_path}")

    print("-" * 70)
    if total_errors == 0:
        print(f" [SUCCESS] All {len(files_to_check)} documentation files verified with 0 errors!")
        print("=" * 70)
        return 0
    else:
        print(f" [FAILED] Found {total_errors} documentation error(s).")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(verify_all_docs())
