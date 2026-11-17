"""Build the submission ZIP and verify it: python scripts/package.py"""
import sys
import zipfile
from pathlib import Path

# Replace the placeholders with the real registration numbers and section before submitting.
GROUP = "24I-XXXX_24I-YYYY_24I-ZZZZ_Section"

ROOT = Path(__file__).resolve().parent.parent
INCLUDE = ["README.md", "requirements.txt", "main.py", "pytest.ini", "smart_racing", "tests", "docs",
           "experiments", "report"]
EXCLUDE_PARTS = {".venv", ".git", "__pycache__", ".pytest_cache", ".claude", "graphify-out"}


def excluded(path: Path) -> bool:
    return bool(EXCLUDE_PARTS & set(path.parts)) or path.suffix in {".zip", ".pyc"}


def files():
    for name in INCLUDE:
        p = ROOT / name
        if not p.exists():
            sys.exit(f"missing: {name}")
        for f in sorted([p] if p.is_file() else p.rglob("*")):
            if f.is_file() and not excluded(f.relative_to(ROOT)):
                yield f


def main() -> None:
    out = ROOT / f"{GROUP}.zip"
    out.unlink(missing_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files():
            z.write(f, f"{GROUP}/{f.relative_to(ROOT).as_posix()}")
    with zipfile.ZipFile(out) as z:
        bad = z.testzip()
        names = z.namelist()
        leaked = [n for n in names if excluded(Path(n))]
    if bad or leaked:
        sys.exit(f"FAILED: corrupt={bad} excluded paths inside: {leaked[:5]}")
    print(f"{out.name}: {len(names)} files, {out.stat().st_size / 1e6:.2f} MB, no excluded paths")


if __name__ == "__main__":
    main()
