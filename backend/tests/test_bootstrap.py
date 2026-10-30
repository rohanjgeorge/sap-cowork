from pathlib import Path


def test_layout_and_runtime():
    import sys
    import fastapi
    import pydantic

    assert sys.version_info[:2] == (3, 12)
    assert fastapi and pydantic
    root = Path(__file__).parents[2]
    for folder in ("backend/app", "backend/tests", "frontend", "cli", "templates", "test_fixtures"):
        assert (root / folder).is_dir()
