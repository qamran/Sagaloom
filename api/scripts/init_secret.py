"""Create api/.env and web/.env.local with a shared secret, only if missing.

Never prints the secret.
"""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_ENV = ROOT / "api" / ".env"
WEB_ENV = ROOT / "web" / ".env.local"


def main() -> None:
    secret = secrets.token_urlsafe(32)
    if API_ENV.exists():
        print(f"kept existing {API_ENV.relative_to(ROOT)}")
    else:
        API_ENV.write_text(f"API_SHARED_SECRET={secret}\n", encoding="utf-8")
        print(f"created {API_ENV.relative_to(ROOT)}")
    if WEB_ENV.exists():
        print(f"kept existing {WEB_ENV.relative_to(ROOT)}")
    elif not WEB_ENV.parent.exists():
        print("web/ does not exist yet; rerun after scaffolding it")
    else:
        WEB_ENV.write_text(
            f"API_SHARED_SECRET={secret}\nAPI_URL=http://localhost:8000\n", encoding="utf-8"
        )
        print(f"created {WEB_ENV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
