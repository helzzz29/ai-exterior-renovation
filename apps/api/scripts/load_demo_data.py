"""Seed initial admin and user directly into database."""

import os
import sys
import uuid
from datetime import UTC, datetime

import psycopg
from argon2 import PasswordHasher

DSN = os.getenv("DATABASE_URL")
if not DSN:
    sys.exit("Error: DATABASE_URL environment variable is required.")

# Convert asyncpg/postgres prefix to standard postgresql if needed
if DSN.startswith("postgresql+asyncpg://"):
    DSN = "postgresql://" + DSN[len("postgresql+asyncpg://") :]

USERS = {"admin@example.com": "Admin@12345", "user@example.com": "User@12345"}


def main():
    hasher = PasswordHasher()
    print("Connecting to database...")
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
