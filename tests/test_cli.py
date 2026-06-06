from hyperliquid_trader_stats.cli import build_parser


def test_cli_parses_fetch_user_fills_options():
    parser = build_parser()

    args = parser.parse_args(
        ["fetch-user-fills", "--limit", "10", "--no-incremental"]
    )

    assert args.command == "fetch-user-fills"
    assert args.limit == 10
    assert args.incremental is False


def test_cli_exposes_expected_commands():
    parser = build_parser()
    subparser_action = next(
        action for action in parser._actions if action.dest == "command"
    )

    assert {
        "init-db",
        "fetch-leaderboard",
        "fetch-user-states",
        "fetch-user-fills",
        "compute-trades",
        "analyze-ls-rate",
    }.issubset(subparser_action.choices)
