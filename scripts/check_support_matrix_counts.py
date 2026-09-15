#!/usr/bin/env python3
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = REPO_ROOT / "SUPPORT_MATRIX.md"

def count_recipes() -> tuple[int, int]:
    golden_count = len(list(REPO_ROOT.rglob("expected/*.expected")))
    
    # Manual run templates
    flask_count = len(list((REPO_ROOT / "templates" / "flask" / "recipes").glob("*"))) if (REPO_ROOT / "templates" / "flask" / "recipes").exists() else len([d for d in (REPO_ROOT / "templates" / "flask").iterdir() if d.is_dir() and d.name != "tests" and not d.name.startswith(".")])
    fastapi_count = len(list((REPO_ROOT / "templates" / "api-service-fastapi" / "recipes").glob("*"))) if (REPO_ROOT / "templates" / "api-service-fastapi" / "recipes").exists() else 0
    streamlit_count = len(list((REPO_ROOT / "templates" / "dashboard").glob("*.py"))) if (REPO_ROOT / "templates" / "dashboard").exists() else 0
    django_count = 1 if (REPO_ROOT / "templates" / "django").exists() else 0
    celery_count = 1 if (REPO_ROOT / "templates" / "async-worker").exists() else 0
    
    manual_count = flask_count + fastapi_count + streamlit_count + django_count + celery_count
    return golden_count, manual_count

def main():
    golden_count, manual_count = count_recipes()
    total_recipes = golden_count + manual_count
    
    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    
    golden_pattern = re.compile(r'(\d+)\s+recipes that ship goldens')
    total_pattern = re.compile(r'cookbook ships \*\*(\d+)\s+recipes\*\*')
    ci_verified_pattern = re.compile(r'(\d+)\s+CI-verified on 11\.2')
    
    errors = []
    
    match = total_pattern.search(matrix)
    if not match or int(match.group(1)) != total_recipes:
        errors.append(f"Expected **{total_recipes} recipes** in text, found {match.group(1) if match else 'None'}")
        
    match = golden_pattern.search(matrix)
    if not match or int(match.group(1)) != golden_count:
        errors.append(f"Expected {golden_count} recipes that ship goldens in text, found {match.group(1) if match else 'None'}")
        
    match = ci_verified_pattern.search(matrix)
    if not match or int(match.group(1)) != golden_count:
        errors.append(f"Expected {golden_count} CI-verified in table footer, found {match.group(1) if match else 'None'}")

    if errors:
        print("SUPPORT_MATRIX.md counts are inconsistent:")
        for err in errors:
            print(f"  - {err}")
        return 1
        
    print("SUPPORT_MATRIX.md counts are verified.")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
