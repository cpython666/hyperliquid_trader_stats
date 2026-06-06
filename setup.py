from setuptools import find_packages, setup


setup(
    name="hyperliquid-trader-stats",
    version="0.1.0",
    description="Download Hyperliquid account fills, compute trader win rates, and render dashboards.",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.9",
    install_requires=[
        "aiohttp>=3.9",
        "pandas>=2.2",
        "plotly>=5.20",
    ],
    extras_require={
        "dev": ["pytest>=8.0"],
    },
    entry_points={
        "console_scripts": [
            "hyper-stats=hyperliquid_trader_stats.cli:main",
        ],
    },
)

