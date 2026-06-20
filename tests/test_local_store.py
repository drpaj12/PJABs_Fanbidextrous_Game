from src.sync.local_store import LocalStore


def test_set_then_get_roundtrips_on_desktop(tmp_path):
    store = LocalStore(file_path=tmp_path / "store.json")
    assert store.get("k") is None
    store.set("k", "v")
    assert store.get("k") == "v"


def test_persists_across_instances(tmp_path):
    path = tmp_path / "store.json"
    LocalStore(file_path=path).set("a", "1")
    assert LocalStore(file_path=path).get("a") == "1"


def test_overwrites_key(tmp_path):
    store = LocalStore(file_path=tmp_path / "store.json")
    store.set("a", "1")
    store.set("a", "2")
    assert store.get("a") == "2"


def test_corrupt_file_reads_as_empty(tmp_path):
    path = tmp_path / "store.json"
    path.write_text("not json", encoding="utf-8")
    store = LocalStore(file_path=path)
    assert store.get("a") is None
    store.set("a", "1")          # recovers by overwriting
    assert store.get("a") == "1"
