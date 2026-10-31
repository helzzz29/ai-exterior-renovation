"""Create invite-only accounts: a strong password per email, hashed for the server.

    uv run python scripts/make_accounts.py OUT_FILE email [email ...]

Writes OUT_FILE (keep it out of git: `*.local.*` is ignored) with each email + password and the
SEED_USERS value to paste into the host's settings. Only argon2 hashes go to the server.
"""

import json
import secrets
import string
import sys
from datetime import date
from pathlib import Path

from argon2 import PasswordHasher

# no look-alike characters (0/O, 1/l/I), so passwords are easy to read out and type
ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")


def new_password(groups: int = 4, size: int = 4) -> str:
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(size)) for _ in range(groups))


def main(out: Path, emails: list[str]) -> None:
    accounts = {e.strip().lower(): new_password() for e in emails if e.strip()}
    hasher = PasswordHasher()  # same defaults as app.auth
    seed = {email: hasher.hash(pw) for email, pw in accounts.items()}
    rows = "\n".join(f"| {email} | `{pw}` |" for email, pw in accounts.items())
    out.write_text(
        f"""# Renovation Planner: accounts (private, never commit)

Created {date.today().isoformat()}. Sign-up is closed; these are the only accounts.

| Email | Password |
|---|---|
{rows}

## SEED_USERS (paste into the host's environment settings)

Only password hashes. Re-run the script to change passwords, then replace this value
and redeploy: accounts are updated on start-up.

```
{json.dumps(seed, separators=(",", ":"))}
```
""",
        encoding="utf-8",
    )
    print(f"{len(accounts)} accounts written to {out}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), sys.argv[2:])
