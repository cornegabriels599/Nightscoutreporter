import os
import time
from urllib.parse import urlparse

import psycopg2


def wait_for_db(timeout_seconds: int = 60) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")

    parsed = urlparse(database_url)
    start_time = time.time()
    while True:
        try:
            conn = psycopg2.connect(
                dbname=parsed.path.lstrip("/"),
                user=parsed.username,
                password=parsed.password,
                host=parsed.hostname,
                port=parsed.port or 5432,
                connect_timeout=3,
            )
            conn.close()
            return
        except Exception:
            if time.time() - start_time >= timeout_seconds:
                raise RuntimeError("Database not ready after waiting")
            time.sleep(1)


if __name__ == "__main__":
    wait_for_db()
