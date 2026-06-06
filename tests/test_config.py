import os

from hyperliquid_trader_stats.config import load_env_file


def test_load_env_file_reads_key_values_without_overriding_existing_values(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "MONGODB_URL='mongodb://example.invalid:27017'",
                'MONGODB_DB_NAME="example_db"',
                "EMPTY_LINE_AFTER=this",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MONGODB_DB_NAME", "existing_db")

    loaded = load_env_file(env_path)

    assert loaded is True
    assert os.environ["MONGODB_URL"] == "mongodb://example.invalid:27017"
    assert os.environ["MONGODB_DB_NAME"] == "existing_db"


def test_load_env_file_can_override_existing_values(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("MONGODB_DB_NAME=new_db\n", encoding="utf-8")
    monkeypatch.setenv("MONGODB_DB_NAME", "old_db")

    load_env_file(env_path, override=True)

    assert os.environ["MONGODB_DB_NAME"] == "new_db"
