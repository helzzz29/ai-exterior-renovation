"""Seed initial admin and user directly into database."""

import uuid
from datetime import UTC, datetime

import psycopg
from argon2 import PasswordHasher

from renocore.settings import get_settings

settings = get_settings()
DSN = settings.queue_dsn

USERS = {"admin@example.com": "Admin@12345", "user@example.com": "User@12345"}


def main():
    hasher = PasswordHasher()
    print(f"Connecting to database via {DSN.split('@')[-1]}...")
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
