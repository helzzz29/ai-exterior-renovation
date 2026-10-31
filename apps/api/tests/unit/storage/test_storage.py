import pytest

from app.storage import LocalStorage, new_key


async def test_put_get_delete(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    key = new_key("project-1/original", "jpg")
    assert key.startswith("project-1/original/") and key.endswith(".jpg")
    await storage.put(key, b"data")
    assert await storage.exists(key)
    assert await storage.get(key) == b"data"
    await storage.delete(key)
    assert not await storage.exists(key)
    await storage.delete(key)  # idempotent


def test_keys_never_use_user_input_unsafely() -> None:
    key = new_key("../../etc/pass wd", ".PNG")
    assert ".." not in key.split("/")[0] and " " not in key and key.endswith(".png")


@pytest.mark.parametrize("bad", ["../x.jpg", "/abs/x.jpg", "a/../../x.jpg", "x", "a\\b.jpg"])
async def test_rejects_unsafe_keys(tmp_path, bad: str) -> None:
    storage = LocalStorage(tmp_path)
    with pytest.raises(ValueError):
        await storage.put(bad, b"x")
