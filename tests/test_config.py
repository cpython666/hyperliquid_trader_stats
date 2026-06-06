from pathlib import Path

from hyperliquid_trader_stats.config import PROJECT_ROOT


def test_project_root_points_to_repository_root():
    root = Path(PROJECT_ROOT)

    assert (root / "pyproject.toml").exists()
    assert (root / "src" / "hyperliquid_trader_stats").exists()
