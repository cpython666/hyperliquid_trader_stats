# Hyperliquid Trader Stats

从 Hyperliquid 下载一批账户的成交记录，聚合完整交易，统计每个地址的胜率，并生成 CSV 与可视化 HTML 报告。

这个项目是从 `StarDreamAPI/scripts/hyperX` 相关逻辑拆出来的独立版本：

- 不依赖原项目的 FastAPI、MongoDB、scheduler。
- 使用本地 `data/` 目录保存地址库、fills、仓位状态和分析结果。
- 保留原来的核心思路：按 `coin + startPosition=0` 聚合完整交易，用净盈亏 `net_pnl > 0` 计算胜率。
- 输出 `summary.csv`、`trades.csv`、`per_asset.csv`、`population.json` 和 `dashboard.html`。

## 安装

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

如果要直接读写旧项目的 MongoDB：

```bash
pip install -e ".[dev,mongo]"
```

## 准备地址

建一个文本文件，例如 `addresses.txt`：

```text
0x0000000000000000000000000000000000000000
0x1111111111111111111111111111111111111111
```

也支持 CSV 第一列或 JSON list：

```json
[
  "0x0000000000000000000000000000000000000000",
  {"ethAddress": "0x1111111111111111111111111111111111111111"}
]
```

## 一键下载、统计、可视化

```bash
hyper-stats run --address-file addresses.txt --concurrency 3
```

如果已经用扫链命令生成了地址库，可以不传 `--address-file`：

```bash
hyper-stats run --limit-addresses 100 --concurrency 3
```

生成结果：

- `data/addresses.json`：扫链/排行榜发现的账户地址库
- `data/addresses.csv`：地址库 CSV 版本
- `data/addresses.txt`：地址库纯地址列表
- `data/fills/<address>.json`：原始成交记录缓存
- `data/states/<address>.json`：当前持仓状态缓存
- `data/results/<address>.json`：单地址分析结果
- `data/reports/summary.csv`：每个地址胜率排行
- `data/reports/trades.csv`：聚合后的完整交易明细
- `data/reports/per_asset.csv`：按币种统计
- `data/reports/dashboard.html`：可视化报告

打开报告：

```bash
open data/reports/dashboard.html
```

## 分步运行

### 使用旧 MongoDB

默认情况下项目只读写本地 `data/` 目录，不会连接 MongoDB。要使用 `StarDreamAPI` 之前的 MongoDB，需要显式选择 `--storage mongo`，并通过环境变量或命令行传入连接信息：

```bash
export MONGODB_URL="<your MongoDB connection string>"
export MONGODB_DB_NAME="<your MongoDB database name>"
```

初始化旧集合索引：

```bash
hyper-stats init-mongo --mongo-uri "$MONGODB_URL" --mongo-db "$MONGODB_DB_NAME"
```

从旧 MongoDB 地址集合读取账户并下载 fills：

```bash
hyper-stats fetch --storage mongo --limit-addresses 100 --concurrency 3
```

分析旧 MongoDB 中已有的 fills，并把结果写回旧格式集合：

```bash
hyper-stats analyze --storage mongo --limit-addresses 100
```

一键下载并分析：

```bash
hyper-stats run --storage mongo --limit-addresses 100 --concurrency 3
```

扫链写入旧 MongoDB 地址集合：

```bash
hyper-stats scan-blocks --storage mongo --block-count 1000 --concurrency 5
```

查看旧 MongoDB 地址集合：

```bash
hyper-stats addresses --storage mongo --limit-addresses 30
```

兼容的旧集合名：

- `web3_hyperliquid_hyper_x_addresses`
- `web3_hyperliquid_hyper_x_user_fills`
- `web3_hyperliquid_hyper_x_user_fills_summary`
- `web3_hyperliquid_hyper_x_completed_trades`
- `web3_hyperliquid_hyper_x_trade_summary`
- `web3_hyperliquid_hyper_x_analyze_result`

MongoDB 模式下写入字段会保留旧项目口径：

- 地址集合使用 `ethAddress`，并兼容旧的 `source`、`created_at`、`createdAt` 字段。
- fills 集合使用 `ethAddress + tid` 唯一键，成交原文写在 `fill` 字段，同时冗余 `coin`、`time`。
- fills summary 集合使用 `ethAddress`、`lastTime`、`updatedAt`。
- completed trades 集合使用 `ethAddress`、`completed_trades`、`completed_trade_pnl`、`duration_stats`、`stats_per_asset`、`total_trades`、`winning_trades`、`win_rate`、`win_rate_long`、`win_rate_short` 等旧字段。
- 新版完整分析结果会额外写入 `analysis_result_v2`，不会覆盖旧字段。

注意：如果旧库某个地址没有 `state.assetPositions` 或 `effective_position_value`，分析仍会运行，但无法准确排除当前未平仓币种，相关多空仓位统计也可能为空。建议先跑一次 `fetch --storage mongo` 更新状态和 fills。

扫链发现账户，并写入本地地址库：

```bash
hyper-stats scan-blocks --block-count 1000 --concurrency 5
```

指定起始区块向前扫描：

```bash
hyper-stats scan-blocks --start-height 660876453 --block-count 30000 --concurrency 10
```

导入 Hyperliquid leaderboard 账户：

```bash
hyper-stats discover-leaderboard
```

导入 Hyperdash top-traders 账户：

```bash
hyper-stats discover-hyperdash-top-traders --top-traders-file /path/to/hyperdash_top_traders.json
```

如果不传 `--top-traders-file`，命令会尝试请求 `https://hyperdash.info/api/hyperdash/top-traders-cached`；这个接口可能被 Hyperdash 风控返回 403，因此更稳的方式是先保存 JSON 文件再导入。导入时会保留 `account_value`、`main_position`、`perp_*_pnl` 等元数据到地址库或 MongoDB 地址集合。

查看地址库：

```bash
hyper-stats addresses --limit-addresses 30
```

只下载：

```bash
hyper-stats fetch --address-file addresses.txt --incremental
```

只分析本地缓存：

```bash
hyper-stats analyze
```

直接传地址：

```bash
hyper-stats run --addresses 0xabc...,0xdef...
```

## 迁移覆盖

`StarDreamAPI/scripts/hyperX` 中已经迁入独立项目的核心能力：

- `fetch_and_store_addresses_from_block.py` / `fetch_and_store_addresses_from_block_requests.py`：对应 `hyper-stats scan-blocks`。
- `fetch_and_store_address.py`：对应 `hyper-stats discover-leaderboard`。
- `fetch_and_store_addresses_from_hyperdash_top_traders.py`：对应 `hyper-stats discover-hyperdash-top-traders`。
- `fetch_and_store_user_fills.py`、`fetch_and_store_user_state.py`、`hyper_x_utils.py` 中的 fills/state 核心逻辑：对应 `hyper-stats fetch`。
- `compute_complete_trades.py`：对应 `hyper-stats analyze` / `run` 中的完整交易聚合和胜率统计。
- `analyze_ls_rate.py` 的基础多空分布统计：对应报告中的 population/position distribution。
- `analyze_analyze_result.py` 的可视化目标：对应 `data/reports/dashboard.html`。
- 旧 MongoDB 集合读写：对应 `--storage mongo` 和 `init-mongo`。

暂未完整迁入的旧脚本/辅助能力：

- `add_addresses_from_vaults.py`：从旧 `web3_hyperliquid_vaults` followers 导入地址。
- `analyze_ls_rate_over_value_pro.py`：按入场价值区间的增强多空分析与历史快照。
- `analyze_analyze_result_pro.py` / `test/导出数据供TradingView使用.py`：增强图表和 TradingView 导出。
- `update_high_win_rate_user_state.py` / `run_fetch_states_and_analyze.py`：按高胜率筛选后周期性更新仓位的调度流程。
- demo、测试临时脚本、旧 PNG/XLSX 输出文件。

## 口径说明

- 扫链账户发现：请求 Hyperliquid explorer `blockDetails`，提取每笔 tx 里的 `user` 字段，校验为 `0x` + 40 位十六进制地址后写入地址库。
- 地址库：同一地址会 upsert，记录 `sources`、`first_seen_at`、`last_seen_at`、`seen_count` 和 `last_block_height`。
- 完整交易：同一个币种下，每次遇到 `startPosition=0` 视为新一轮交易分组。
- 当前仍有持仓的币种：默认会忽略该币种最后一笔聚合交易，避免把未完全结束的交易算进胜率。
- 胜率：`net_pnl = closed_pnl - fees`，`net_pnl > 0` 算赢。
- `win_rate_wilson_lower_bound`：Wilson 置信区间下界，用来减少“交易次数很少但胜率很高”的误导。

## 测试

```bash
pytest
```
