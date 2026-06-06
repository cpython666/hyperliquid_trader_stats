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
