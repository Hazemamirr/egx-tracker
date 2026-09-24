"""
Prints "changed" or "unchanged" depending on whether data/latest.json differs
from the committed version in anything other than its `updated_at` stamp.

The update workflow rewrites `updated_at` on every run, so committing on any
difference would add an empty commit twice a day on weekends, holidays, and
any run that fires before Yahoo publishes the session. This lets the workflow
commit only when the numbers actually moved.

Exits non-zero on any unexpected error, so the workflow fails loudly rather
than silently deciding there is nothing to commit.
"""

import json
import subprocess
import sys

PATH = "data/latest.json"


def committed_version():
    """The copy at HEAD, or None if the file is new."""
    result = subprocess.run(
        ["git", "show", f"HEAD:{PATH}"],
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")
        if "does not exist" in stderr or "exists on disk, but not in" in stderr:
            return None
        raise RuntimeError(f"git show failed: {stderr.strip()}")
    return json.loads(result.stdout.decode("utf-8"))


def comparable(payload):
    return {k: v for k, v in payload.items() if k != "updated_at"}


def main():
    with open(PATH, encoding="utf-8") as f:
        current = json.load(f)

    previous = committed_version()
    if previous is None:
        print("changed")
        return

    print("unchanged" if comparable(previous) == comparable(current) else "changed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"data_changed.py: {exc}", file=sys.stderr)
        sys.exit(2)
