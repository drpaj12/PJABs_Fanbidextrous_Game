from src.utils.build_info import build_id


def test_build_id_returns_file_contents(tmp_path):
    f = tmp_path / "build_id.txt"
    f.write_text("game_web_mobile_20260620_010203\n", encoding="utf-8")
    assert build_id(f) == "game_web_mobile_20260620_010203"


def test_build_id_defaults_to_dev_when_missing(tmp_path):
    assert build_id(tmp_path / "nope.txt") == "dev"


def test_build_id_defaults_to_dev_when_empty(tmp_path):
    f = tmp_path / "build_id.txt"
    f.write_text("   \n", encoding="utf-8")
    assert build_id(f) == "dev"
