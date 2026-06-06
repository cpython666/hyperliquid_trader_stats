## 集合介绍
### web3_hyperliquid_hyper_x_addresses
地址表 记录所有用户地址
![web3_hyperliquid_hyper_x_addresses.png](/imgs/web3_hyperliquid_hyper_x_addresses.png)


| 字段        | 类型   | 描述                 |
|------------|--------|----------------------|
| ethAddress | String | 用户地址             |



### web3_hyperliquid_hyper_x_user_fills_summary

```javascript
[
  {
    "_id": ObjectId("686694116fc51490b88ff79f"),
    "ethAddress": "0x3cdd67815474d517fa95f0d827c3d0fe2dcbe7b1",
    "lastTime": NumberLong("1746639736599"),
    "updatedAt": ISODate("2025-07-03T14:28:34.467Z")
}
  ...
]
```
冗余表 记录每个地址和fills表中记录的最后订单的时间戳
| 字段        | 类型   | 描述                 |
|------------|--------|----------------------|
| ethAddress | String | 用户地址             |
| lastTime   | Date   | 记录的最后订单时间戳 |
| updatedAt  | Date   | 记录更新时间         |

## 项目结构

核心代码已放到 `src/hyperliquid_trader_stats`：

| 目录 | 作用 |
| ---- | ---- |
| `api/` | 请求工具与浏览器辅助请求 |
| `analytics/` | 已完成订单计算、胜率统计等核心分析逻辑 |
| `db/` | MongoDB 集合与索引初始化 |
| `plotting/` | 分析结果可视化与导出 |
| `services/` | 地址、状态、fills、金库等采集/同步流程 |

## 命令行入口

安装开发环境后可以使用：

```bash
pip install -e .
```

常用命令：

| 命令 | 作用 |
| ---- | ---- |
| `hyper-stats init-db` | 初始化 HyperX 相关 MongoDB 索引 |
| `hyper-stats fetch-leaderboard` | 采集排行榜用户地址入库 |
| `hyper-stats fetch-hyperdash-top-traders` | 采集 Hyperdash top trader 地址入库 |
| `hyper-stats fetch-block-addresses <start_height>` | 从区块中采集地址 |
| `hyper-stats fetch-user-states` | 采集用户持仓状态 |
| `hyper-stats fetch-user-fills --limit 30000 --incremental` | 获取用户历史成交 |
| `hyper-stats compute-trades` | 计算已完成订单与胜率摘要 |
| `hyper-stats analyze-ls-rate --visualize-result` | 统计胜率与多空分布并可视化 |
| `hyper-stats run-scheduler` | 执行当前 fetch/analyze 调度流程 |

## 运行快捷命令

下面每个代码块都是独立可运行命令。支持 Markdown 代码块运行按钮的编辑器，可以直接点击对应代码块运行。

### 安装本地开发命令

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
python -m pip install -e .
```

### 查看命令帮助

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats --help
```

### 初始化 MongoDB 索引

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats init-db
```

### 采集排行榜地址

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats fetch-leaderboard
```

### 采集 Hyperdash 顶级交易员地址

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats fetch-hyperdash-top-traders
```

### 采集用户持仓状态

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats fetch-user-states
```

### 采集用户历史成交

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats fetch-user-fills --limit 30000 --incremental
```

### 计算已完成订单和胜率

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats compute-trades
```

### 分析胜率与多空分布

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats analyze-ls-rate --visualize-result
```

### 执行内置调度流程

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats run-scheduler
```

### 未安装 CLI 时临时运行

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
PYTHONPATH=src python -m hyperliquid_trader_stats.cli --help
```

## 脚本说明
### `services/fetch_and_store_address.py`
采集排行榜的用户地址入库

### `services/fetch_and_store_user_state.py`
查询到没有有效字段的地址，请求仓位信息，计算出一些字段比如有效仓位等，更新到数据库

### 从金库获取地址

`services/vaults/fetch_and_store_vaults_list.py`
`services/vaults/fetch_and_store_vaults_info.py`
`services/add_addresses_from_vaults.py`

| 脚本                          | 作用                         | 完成 |
| ----------------------------- | ---------------------------- | ---- |
| `services/add_addresses_from_vaults.py` | 采集金库的存款用户地址入库 | ✅ |
| `services/fetch_and_store_user_state.py` | 采集用户持仓信息 | ✅ |
| `services/fetch_and_store_user_fills.py` | 获取用户历史成交 | ✅ |
| `plotting/analyze_ls_rate.py` | 统计胜率与多空分布并可视化 | ✅ |
| `plotting/analyze_ls_rate_over_value_pro.py` | 按入场价值区间细分胜率与多空分布 | ✅ |
| `plotting/analyze_analyze_result.py` | 按时间可视化已存储结果（2图） | ✅ |
| `plotting/analyze_analyze_result_pro.py` | 按类型/汇总可视化已存储结果 | ✅ |
| `services/run_fetch_states_and_analyze.py` | 定时执行当前采集/分析流程 | ✅ |

### 分析脚本说明
- `analyze_ls_rate.py`
  - 从地址与交易集合统计胜率分布（≥50/60/70/80/90）与多空仓位分布。
  - 输出 `winrate_distribution` 与 `position_distribution`，包含数量、价值总和、`ratio` 与 `value_ratio`。
  - 可选存储到 `web3_hyperliquid_hyper_x_analyze_result_collection`，并生成多张图（饼图、柱状图、折线图）。
- `analyze_ls_rate_over_value_pro.py`
  - 在上述基础上，按入场价值区间（`entry_value_summary` 的 `win_rate_over_1w/10w/100w/1000w`）进一步细分统计。
  - 额外输出 `value_position_distribution`，同样包含数量、价值总和与比值。
  - 可视化采用合并大图（2x2）保存到 `plots_tmp`，更适合总览对比。
- `analyze_analyze_result.py`
  - 读取已存储的分析结果集合，按时间绘制两张折线图：人数比 `ratio` 与价值比 `value_ratio`。
  - 支持导出 Excel（`analyze_result.xlsx`），便于二次分析与分享。
- `analyze_analyze_result_pro.py`
  - 读取已存储结果，支持两种模式：
    - `group`：按 `type`（如 `total`、`win_rate_over_1w/10w/100w/1000w`）逐组输出两图。
    - `big`：将所有 `type` 合并到两张大图（人数比与价值比，各 2x3 子图）。
  - 适合对 `position_distribution` 与 `value_position_distribution` 做更细致的时间序列对比。

## 需采集数据
- 地址历史操作数据，fills
- k线数据
- 区块数据
- 金库数据

## TODO 待办事项
实现已完成订单中间表而不是每次实时计算，实时计算会导致重新拉取新订单耗时，有速率限制【但是计算已完成订单需要去掉最后一单】
