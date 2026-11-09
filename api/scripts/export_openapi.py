"""Write the API's OpenAPI schema as deterministic JSON (the source of web/lib/api-types.gen.ts).

Usage: python scripts/export_openapi.py [OUT]   (default ../web/lib/openapi.json)

The app is built from fixed dummy settings, the way the tests build it: no .env is read, and
the throwaway data dir is deleted afterwards.
"""

import json
import sys
import tempfile
from pathlib import Path

from sagaloom.config import Settings
from sagaloom.web.app import create_app


def build_schema() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            _env_file=None, openrouter_api_key="sk-or-export", api_shared_secret="export", data_dir=Path(tmp)
        )
        return create_app(settings).openapi()


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "../web/lib/openapi.json")
    text = json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"
    with out.open("w", encoding="utf-8", newline="\n") as f:  # LF on Windows too
        f.write(text)


if __name__ == "__main__":
    main()
