"""Production plumbing that needs no database: Neon URLs, the S3 backend, the website route."""

import io

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app.config import Settings
from app.storage import S3Storage


def test_neon_url_is_accepted_as_given() -> None:
    s = Settings(
        database_url="postgresql://u:p@ep-x.ap-southeast-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    assert s.database_url == (
        "postgresql+asyncpg://u:p@ep-x.ap-southeast-1.aws.neon.tech/neondb?ssl=require"
    )
    assert (
        s.queue_dsn == "postgresql://u:p@ep-x.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    )


def test_local_url_unchanged() -> None:
    s = Settings(database_url="postgresql+asyncpg://reno:reno@localhost:5433/reno")
    assert s.database_url == "postgresql+asyncpg://reno:reno@localhost:5433/reno"
    assert s.queue_dsn == "postgresql://reno:reno@localhost:5433/reno"


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> None:  # noqa: N803
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket: str, Key: str) -> dict:  # noqa: N803
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, Bucket: str, Key: str) -> None:  # noqa: N803
        self.objects.pop((Bucket, Key), None)

    def head_object(self, Bucket: str, Key: str) -> dict:  # noqa: N803
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}


async def test_s3_storage_round_trip() -> None:
    fake = FakeS3()
    storage = S3Storage(fake, "photos")
    key = "p1/original/abc.jpg"
    assert not await storage.exists(key)
    await storage.put(key, b"jpeg")
    assert fake.objects == {("photos", key): b"jpeg"}
    assert await storage.exists(key)
    assert await storage.get(key) == b"jpeg"
    await storage.delete(key)
    assert not await storage.exists(key)


@pytest.mark.parametrize("bad", ["../x.jpg", "/abs/x.jpg", "x"])
async def test_s3_storage_rejects_unsafe_keys(bad: str) -> None:
    with pytest.raises(ValueError):
        await S3Storage(FakeS3(), "photos").put(bad, b"x")


def test_s3_from_settings_points_at_the_endpoint() -> None:
    s = Settings(
        storage_backend="s3",
        s3_endpoint_url="https://s3.eu-central-003.backblazeb2.com",
        s3_region="eu-central-003",
        s3_bucket="reno-photos",
        s3_access_key_id="id",
        s3_secret_access_key="secret",
    )
    storage = S3Storage.from_settings(s)
    assert storage.bucket == "reno-photos"
    assert storage.client.meta.endpoint_url == "https://s3.eu-central-003.backblazeb2.com"


def test_website_is_served_with_client_side_routes(tmp_path, monkeypatch) -> None:
    from app import main
    from app.config import get_settings

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app-123.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    monkeypatch.setattr(get_settings(), "web_dist", tmp_path)
    client = TestClient(main.create_app())  # no `with`: lifespan (database) not started

    r = client.get("/projects/abc/cost")
    assert r.status_code == 200 and "root" in r.text and r.headers["cache-control"] == "no-cache"
    r = client.get("/assets/app-123.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/api/health").json() == {"status": "ok"}
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert "root" in client.get("/../../etc/passwd").text  # never escapes the folder
