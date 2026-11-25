import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKIP = {".git", ".venv", "venv", "node_modules", "docs", "docs-demo", "__pycache__", ".pytest_cache"}


def test_no_long_dashes_anywhere():
    bad = []
    for p in ROOT.rglob("*"):
        if p.is_dir() or any(part in SKIP or part.endswith(".egg-info") for part in p.parts):
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if chr(0x2014) in txt or chr(0x2013) in txt:
            bad.append(str(p.relative_to(ROOT)))
    assert not bad, bad


def test_no_secrets_tracked():
    gi = (ROOT / ".gitignore").read_text()
    assert "garmin_tokens.json" in gi and ".garminconnect/" in gi
