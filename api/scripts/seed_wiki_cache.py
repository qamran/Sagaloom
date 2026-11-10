"""Copy the committed Wikipedia fixtures into a data directory's wiki cache.

The M2 demo runs offline: seeding `<data_dir>/cache/wiki/` lets `WikiClient` serve the three demo
pages and the Wikipedia licence without a network request. Safe to run again.

    cd api && uv run python scripts/seed_wiki_cache.py <data_dir>
"""

import shutil
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "wiki"


def seed(data_dir: Path) -> int:
    target = Path(data_dir) / "cache" / "wiki"
    target.mkdir(parents=True, exist_ok=True)
    files = sorted(FIXTURES.glob("*.v2.json"))
    for f in files:
        shutil.copyfile(f, target / f.name)
    return len(files)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: seed_wiki_cache.py <data_dir>")
    print(f"seeded {seed(Path(sys.argv[1]))} cache files into {Path(sys.argv[1]) / 'cache' / 'wiki'}")
