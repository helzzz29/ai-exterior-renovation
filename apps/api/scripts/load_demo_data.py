"""Seed initial admin and user directly into database."""

import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Ensure apps/api is in python path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from argon2 import PasswordHasher

try:
    from renocore.settings import get_settings

    DSN = get_settings().queue_dsn
except Exception:
    # Direct fallback from root .env
    env_file = Path(__file__).resolve().parents[3] / ".env"
    raw = ""
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                raw = line.partition("=")[2].strip()
                break
    raw = raw or os.getenv("DATABASE_URL", "")
    for prefix in (
        "postgresql+asyncpg://",
        "postgresql+psycopg2://",
        "postgresql+psycopg://",
        "postgres://",
    ):
        if raw.startswith(prefix):
            raw = "postgresql://" + raw[len(prefix) :]
            break
    DSN = raw

if not DSN:
    sys.exit("Error: DATABASE_URL could not be found in .env or environment.")

USERS = {
    "admin@example.com": "Admin@12345",
    "user@example.com": "User@12345",
    "user1@example.com": "User1@12345",
    "user2@example.com": "User2@12345",
}


def main():
    hasher = PasswordHasher()
    target = DSN.split("@")[-1] if "@" in DSN else DSN
    print(f"Connecting to database via {target}...")
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            for email, password in USERS.items():
                pw_hash = hasher.hash(password)
                user_id = str(uuid.uuid4())
                now = datetime.now(UTC)
                cur.execute(
                    """
                    INSERT INTO users (id, email, password_hash, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash;
                    """,
                    (user_id, email, pw_hash, now),
                )
            conn.commit()
            cur.execute("SELECT id, email, created_at FROM users;")
            print("Current users in database:")
            for row in cur.fetchall():
                print(f" - {row[1]} (id: {row[0]})")


if __name__ == "__main__":
    main()
