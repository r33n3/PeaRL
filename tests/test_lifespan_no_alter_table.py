"""Regression test: main.py lifespan must not contain raw ALTER TABLE blocks.

Schema changes must go through Alembic migrations (CLAUDE.md antipattern).
This test reads the source file and fails if any ALTER TABLE call is present
inside the lifespan function body.
"""
import re
from pathlib import Path


def test_lifespan_has_no_alter_table():
    main_src = (Path(__file__).parent.parent / "src/pearl/main.py").read_text()

    # Find the lifespan function body (from `async def lifespan` to `yield`)
    lifespan_match = re.search(
        r"async def lifespan.*?yield",
        main_src,
        re.DOTALL,
    )
    assert lifespan_match, "Could not find lifespan function in main.py"

    lifespan_body = lifespan_match.group(0)

    alter_table_calls = re.findall(r'ALTER TABLE', lifespan_body, re.IGNORECASE)
    assert not alter_table_calls, (
        f"Found {len(alter_table_calls)} ALTER TABLE call(s) in lifespan. "
        "Schema changes must use Alembic migrations, not lifespan hacks. "
        "See CLAUDE.md antipatterns."
    )
