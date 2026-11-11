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
default `data`, read from api/.env), or `--data-dir`; it must hold `worlds.json`. Find both ids
in the Clerk dashboard (they start with `user_`). `--dry-run` shows what would move and changes
nothing.

    cd api && uv run python scripts/reassign_owner.py <old_clerk_id> <new_clerk_id> [--dry-run]

Exit codes: 0 done, 1 the old id owns nothing here, 2 bad arguments or no `worlds.json`.
"""

import argparse
import sys
from pathlib import Path

from sagaloom.promptlog import PromptLog
from sagaloom.store.worlds import WorldRegistry


def _ids(old_id: str, new_id: str) -> tuple[str, str]:
    old_id, new_id = old_id.strip(), new_id.strip()
    if not old_id or not new_id:
        raise ValueError("both Clerk user ids are needed")
    if old_id == new_id:
        raise ValueError("the two Clerk user ids must be different")
    return old_id, new_id


def _check_data_dir(data_dir: Path) -> None:
    """Refuse a folder that is not the API's data directory, before anything is opened there
    (opening the prompt log would create an empty `prompts.sqlite`)."""
    if not (data_dir / "worlds.json").is_file():
        raise ValueError(f"no worlds.json in {data_dir}: is this the API's data directory?")


def _log(data_dir: Path) -> PromptLog | None:
    """The prompt log, or None when the folder has none (it is not created)."""
    path = data_dir / "prompts.sqlite"
    return PromptLog(path) if path.is_file() else None


def plan(data_dir: Path, old_id: str) -> tuple[list[str], int]:
    """What `reassign` would move: (world ids, prompt-record count). Changes nothing."""
    data_dir = Path(data_dir)
    _check_data_dir(data_dir)
    worlds = [w.id for w in WorldRegistry(data_dir / "worlds.json").owned_by(old_id)]
    log = _log(data_dir)
    return worlds, log.count_for_user(old_id) if log is not None else 0


def reassign(data_dir: Path, old_id: str, new_id: str) -> tuple[list[str], int]:
    """Moves `old_id`'s worlds and prompt records to `new_id`; returns (world ids, record count)."""
    old_id, new_id = _ids(old_id, new_id)
    data_dir = Path(data_dir)
    _check_data_dir(data_dir)
    worlds = WorldRegistry(data_dir / "worlds.json").reassign_owner(old_id, new_id)
    log = _log(data_dir)
    records = log.reassign_user(old_id, new_id) if log is not None else 0
    return worlds, records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("old_clerk_id")
    parser.add_argument("new_clerk_id")
    parser.add_argument("--data-dir", type=Path, help="the API's data directory (default: DATA_DIR)")
    parser.add_argument("--dry-run", action="store_true", help="show what would move; change nothing")
    args = parser.parse_args(argv)
    data_dir = args.data_dir
    if data_dir is None:
        from sagaloom.config import Settings

        data_dir = Path(Settings().data_dir)
    try:
        old_id, new_id = _ids(args.old_clerk_id, args.new_clerk_id)
        worlds, records = plan(data_dir, old_id)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if not worlds and not records:
        print(f"warning: {old_id} owns no world and no prompt records in {data_dir}; nothing moved", file=sys.stderr)
        return 1
    if not args.dry_run:
        worlds, records = reassign(data_dir, old_id, new_id)
    verb = "would move" if args.dry_run else "moved"
    print(f"{verb} {len(worlds)} world(s) and {records} prompt record(s) from {old_id} to {new_id} in {data_dir}")
    for world_id in worlds:
        print(f"  {world_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
