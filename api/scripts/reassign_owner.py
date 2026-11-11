"""Give one Clerk user's worlds and costs to another Clerk user id.

Ownership is keyed on the Clerk user id, not the email. If an author's Clerk account is deleted
and made again (same email, new id), the new account cannot see the old worlds. This moves
them: every world in `worlds.json` owned by the old id, and every `prompt_log` record charged
to it (so the month's spend and the cost totals follow). Those are the only two places that
store the id as an owner; `users.sqlite` keeps one row per Clerk id, and the new account already
has its own row.

If the new account has already signed in, it keeps the Velmar copy it was given at sign-in and
gets the old worlds next to it. Worlds without an owner are left alone (the admin takes them).

Stop the API first: it holds the same files open. The data directory is the API's (`DATA_DIR`,
default `data`, read from api/.env), or `--data-dir`. Find both ids in the Clerk dashboard
(they start with `user_`).

    cd api && uv run python scripts/reassign_owner.py <old_clerk_id> <new_clerk_id>
"""

import argparse
import sys
from pathlib import Path

from sagaloom.promptlog import PromptLog
from sagaloom.store.worlds import WorldRegistry


def reassign(data_dir: Path, old_id: str, new_id: str) -> tuple[list[str], int]:
    """Moves `old_id`'s worlds and prompt records to `new_id`; returns (world ids, record count)."""
    old_id, new_id = old_id.strip(), new_id.strip()
    if not old_id or not new_id:
        raise ValueError("both Clerk user ids are needed")
    if old_id == new_id:
        raise ValueError("the two Clerk user ids must be different")
    data_dir = Path(data_dir)
    worlds = WorldRegistry(data_dir / "worlds.json").reassign_owner(old_id, new_id)
    records = PromptLog(data_dir / "prompts.sqlite").reassign_user(old_id, new_id)
    return worlds, records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("old_clerk_id")
    parser.add_argument("new_clerk_id")
    parser.add_argument("--data-dir", type=Path, help="the API's data directory (default: DATA_DIR)")
    args = parser.parse_args(argv)
    data_dir = args.data_dir
    if data_dir is None:
        from sagaloom.config import Settings

        data_dir = Path(Settings().data_dir)
    try:
        worlds, records = reassign(data_dir, args.old_clerk_id, args.new_clerk_id)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(f"moved {len(worlds)} world(s) and {records} prompt record(s) in {data_dir}")
    for world_id in worlds:
        print(f"  {world_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
