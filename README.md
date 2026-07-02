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
或者从零开始的电脑创建虚拟环境  
```bash
cd /usr/local/src/hyperliquid_trader_stats

python3 -m venv venv

source venv/bin/activate

pip install -U pip

pip install -e .
```

常用命令：

| 命令                                                             | 作用                           |
|----------------------------------------------------------------|------------------------------|
| `hyper-stats init-db`                                          | 初始化 HyperX 相关 MongoDB 索引     |
| `hyper-stats fetch-leaderboard`                                | 采集排行榜用户地址入库                  |
| `hyper-stats fetch-hyperdash-top-traders`                      | 采集 Hyperdash top trader 地址入库 |
| `hyper-stats fetch-block-addresses [start_height]`             | 从区块中采集地址；省略高度时从最新区块开始        |
| `hyper-stats fetch-user-states`                                | 采集用户持仓状态                     |
| `hyper-stats fetch-user-fills --limit 30000 --incremental`     | 增量获取用户历史成交                   |
| `hyper-stats fetch-user-fills --limit 100000 --no-incremental` | 全量获取用户历史成交                   |
| `hyper-stats compute-trades`                                   | 计算已完成订单与胜率摘要                 |
| `hyper-stats analyze-ls-rate --visualize-result`               | 统计胜率与多空分布并可视化                |
| `hyper-stats analyze-history`                                  | 绘制已存储分析结果的历史趋势图             |
| `hyper-stats serve-web`                                        | 启动交易员数据筛选 Web 页面              |
| `hyper-stats run-scheduler`                                    | 执行当前 fetch/analyze 调度流程      |

## 代理配置

项目默认使用 Clash 本地 HTTP 代理：

```bash
HYPER_STATS_USE_PROXY=true
HYPER_STATS_PROXY_URL="http://127.0.0.1:7890"
```

如需临时关闭代理：

```bash
HYPER_STATS_USE_PROXY=false hyper-stats fetch-leaderboard
```

如需改代理端口：

```bash
HYPER_STATS_PROXY_URL="http://127.0.0.1:7891" hyper-stats fetch-leaderboard
```

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

该命令可以重复执行：已存在且定义相同的索引会被跳过。默认不创建超大 `user_fills` 集合的 `(ethAddress, time)` 索引，避免在数据量较大时长时间占用 MongoDB 资源或导致连接中断。

如已预留足够的磁盘空间和维护时间，可显式创建大表索引：

```bash
hyper-stats init-db --include-large-indexes
```

| 参数 | 作用 |
| ---- | ---- |
| `--include-large-indexes` | 同时创建 `user_fills` 的 `(ethAddress, time)` 索引；在超大集合上可能耗时很长，建议仅在低峰维护窗口执行。 |

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

### 从区块采集地址

不传区块高度时，会自动获取最新区块高度并向前扫描：

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats fetch-block-addresses
```

也可以手动指定起始区块高度：

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats fetch-block-addresses 651879309
```

默认向前扫描 1000 个区块，可通过 `--block-count` 调整。

默认使用 aiohttp 后端，并发数为 5：

```bash
hyper-stats fetch-block-addresses 651879309 --block-count 1000
```

如果 aiohttp 方式遇到网络兼容问题，可以切到 requests 后端；requests 后端默认并发数为 10，也可以手动调小：

```bash
hyper-stats fetch-block-addresses 651879309 --requests --concurrency 3
```

参数说明：

| 参数 | 作用 |
| ---- | ---- |
| `start_height` | 可选的起始区块高度，例如 `651879309`；省略时自动获取最新区块高度。 |
| `--block-count 1000` | 从起始高度向前扫描的区块数量，默认 1000。 |
| `--requests` | 改用 requests 后端采集区块，可在默认 aiohttp 方式异常时备用。 |
| `--concurrency` | 并发请求数量；默认 aiohttp 为 5，requests 为 10。 |

### 采集用户持仓状态

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
# 增量：仅采集缺少 marginSummary 的地址（默认）
hyper-stats fetch-user-states

# 全量：刷新所有有效地址
hyper-stats fetch-user-states --no-incremental

# 过期刷新：刷新该 UTC 日期之前更新或从未更新的地址
hyper-stats fetch-user-states --updated-before 2026-06-01
```

参数说明：

| 参数 | 作用 |
| ---- | ---- |
| `--incremental` | 仅采集缺少状态的地址，默认启用。 |
| `--no-incremental` | 全量刷新所有以 `0x` 开头的地址。 |
| `--updated-before YYYY-MM-DD` | 刷新在指定 UTC 日期之前更新或从未更新的地址。 |

### 绘制历史分析趋势图

默认读取 `web3_hyperliquid_hyper_x_analyze_result` 中已存储的分析结果，按类型分别绘制多空人数比和多空价值比趋势图：

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats analyze-history
```

基础模式会绘制总胜率分布的两张折线图，并导出 `analyze_result.xlsx`：

```bash
hyper-stats analyze-history --basic
```

增强模式支持将所有类型合并为两张大图，并可保存 PNG：

```bash
hyper-stats analyze-history --mode big --output-dir plots_tmp --no-show
```

图片产出说明：

| 命令 | 产出 |
| ---- | ---- |
| `hyper-stats analyze-history` | 打开 Matplotlib 窗口；默认不保存 PNG。增强 `group` 模式会按 `total`、`win_rate_over_1w`、`win_rate_over_10w`、`win_rate_over_100w`、`win_rate_over_1000w` 分别生成一组“人数比/价值比”窗口。 |
| `hyper-stats analyze-history --output-dir plots_tmp --no-show` | 不打开窗口，保存 `plots_tmp/history_total_*.png`、`history_win_rate_over_1w_*.png`、`history_win_rate_over_10w_*.png`、`history_win_rate_over_100w_*.png`、`history_win_rate_over_1000w_*.png`。 |
| `hyper-stats analyze-history --mode big --output-dir plots_tmp --no-show` | 保存两张总览图：`history_ratio_big_*.png` 和 `history_value_ratio_big_*.png`，分别对应多空人数比和多空价值比。 |
| `hyper-stats analyze-history --basic` | 打开基础历史趋势窗口，并导出 `analyze_result.xlsx`。 |
| `hyper-stats analyze-history --basic --output-dir plots --no-show` | 保存 `plots/history_basic_*.png`，并导出 `analyze_result.xlsx`。 |

参数说明：

| 参数 | 作用 |
| ---- | ---- |
| `--basic` | 使用基础历史图，只绘制总胜率分布并导出 Excel。 |
| `--mode group\|big` | 增强历史图模式；`group` 按类型分别绘图，`big` 合并为两张大图。 |
| `--export-excel analyze_result.xlsx` | 基础模式导出的 Excel 路径；传空字符串可关闭导出。 |
| `--output-dir` | 可选的 PNG 保存目录；不传则只显示窗口。 |
| `--no-show` | 不显示 Matplotlib 窗口，适合服务器上只保存文件。 |

### 采集用户历史成交

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats fetch-user-fills --limit 30000 --incremental
```

参数说明：

| 参数 | 作用 |
| ---- | ---- |
| `--limit 30000` | 本次最多处理 30000 个符合条件的用户地址；CLI 默认值就是 30000，可按需要调小。排除金库地址后，实际处理数量可能更少。 |
| `--incremental` | 只处理尚未出现在 fills 摘要表中的新增地址。这是默认模式，因此可以省略该参数。 |
| `--no-incremental` | 从符合条件的地址中重新选择用户进行更新；已有用户会从摘要表记录的 `lastTime` 之后继续拉取，而不是重复下载全部历史成交。 |

所以下面这条命令与上面的示例等价：

```bash
hyper-stats fetch-user-fills
```

```bash
# 服务器后台运行
nohup hyper-stats fetch-user-fills --limit 100000 --no-incremental > fetch.log 2>&1 &
# 快捷重新运行
pkill -f "fetch-user-fills"
nohup hyper-stats fetch-user-fills --limit 100000 --no-incremental > fetch.log 2>&1 &
#其他命令
#查看日志
tail -f fetch.log
#查看进程
ps -ef | grep "fetch-user-fills"
#停止任务
kill PID
#强制停止：
kill -9 PID
```

### 计算已完成订单和胜率

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats compute-trades
```

参数说明：

| 参数 | 作用 |
| ---- | ---- |
| `--incremental` | 根据 `fills_summary.lastTime` 和 `completed_trades.processedThroughTime` 只计算有新成交或尚未生成结果的地址。这是默认模式，可以省略。 |
| `--no-incremental` | 重新计算 fills 集合中的全部地址，适合计算逻辑变更后刷新历史结果；数据量较大时会耗费更长时间。 |
| `--stale-days 7` | 重新计算超过指定天数未更新以及尚未生成结果的地址。 |
| `--updated-before 2026-06-01` | 重新计算指定 UTC 日期之前更新以及尚未生成结果的地址，日期格式为 `YYYY-MM-DD`。 |

`--incremental`、`--no-incremental`、`--stale-days` 和 `--updated-before` 是互斥模式，一次只能选择一种。

以下两条增量计算命令等价：

```bash
hyper-stats compute-trades
hyper-stats compute-trades --incremental
```

需要全量重算时使用：

```bash
hyper-stats compute-trades --no-incremental
```

更新超过 7 天未计算的地址：

```bash
hyper-stats compute-trades --stale-days 7
```

更新指定日期之前计算过的地址：

```bash
hyper-stats compute-trades --updated-before 2026-06-01
```

### 分析胜率与多空分布

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats analyze-ls-rate --visualize-result
```

常用运行方式：

```bash
# 默认进阶分析：按入场价值区间细分，保存一张总览图到 plots_tmp
hyper-stats analyze-ls-rate --visualize-result

# 只导出图片，不把本次分析快照写入 MongoDB
hyper-stats analyze-ls-rate --no-store-result --visualize-result

# 基础分析：不按入场价值区间细分，保存多张单项图到 plots
hyper-stats analyze-ls-rate --basic --no-store-result --visualize-result
```

图片产出说明：

| 命令 | 产出 |
| ---- | ---- |
| `hyper-stats analyze-ls-rate --visualize-result` | 使用进阶分析器，保存 `plots_tmp/all_in_one_*.png`，包含胜率分布、多空仓位数量分布、多空数量比值、多空价值比值四个子图。默认还会把分析结果写入 MongoDB。 |
| `hyper-stats analyze-ls-rate --no-store-result --visualize-result` | 同样保存 `plots_tmp/all_in_one_*.png`，但不写入 MongoDB，适合只想快速导图。 |
| `hyper-stats analyze-ls-rate --basic --visualize-result` | 使用基础分析器，保存多张图片到 `plots/`：`pie_address_*.png`、`bar_winrate_*.png`、`bar_position_counts_*.png`、`line_ratio_*.png`、`line_value_ratio_*.png`、`bar_value_sums_*.png`。 |
| `hyper-stats analyze-ls-rate --basic --no-store-result --visualize-result` | 同基础分析导图，但不把分析快照写入 MongoDB。 |

进阶分析写入的综合快照还包含 `coin_position_distribution`：它读取各地址
`state.assetPositions` 中的最新仓位，按币种和 `ge_50`、`ge_60`、`ge_70`、
`ge_80`、`ge_90`、`eq_100` 胜率门槛汇总多空人数、仓位价值、人数比和价值比。
快照中不保存地址明细，也不会额外生成地址级历史仓位记录。

参数说明：

| 参数 | 作用 |
| ---- | ---- |
| `--visualize-result` | 生成分析结果图表；默认不生成。 |
| `--store-result` / `--no-store-result` | 是否将分析结果写入 MongoDB，默认写入。 |
| `--basic` | 使用不按入场价值区间细分的基础分析器；默认使用进阶分析器。基础分析器输出多张单项 PNG，进阶分析器输出一张合并 PNG。 |

### 启动 Web 数据筛选页面

```bash
cd /Users/cpython666/git_pro/hyperliquid-trader-stats
hyper-stats serve-web
```

默认访问地址为：

```text
http://127.0.0.1:8000
```

页面支持按地址、胜率、交易数、净盈亏、当前有效持仓价值、仓位方向、入场价值分层胜率和更新时间筛选；支持按胜率评分、胜率、Wilson 下界、交易数、净盈亏、持仓价值、账户价值和更新时间排序。

参数说明：

| 参数 | 作用 |
| ---- | ---- |
| `--host 127.0.0.1` | Web 服务监听地址，默认 `127.0.0.1`。 |
| `--port 8000` | Web 服务监听端口，默认 `8000`。 |
| `--reload` | 开启 uvicorn 自动重载，适合本地开发。 |

后端接口：

| 接口 | 作用 |
| ---- | ---- |
| `GET /api/traders` | 分页查询交易员统计，可传筛选和排序参数。 |
| `GET /api/traders/{address}` | 查看单个地址的完整统计和地址状态。 |
| `GET /api/health` | 健康检查。 |

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
| `services/fetch_block_addresses.py` | 从区块采集账户地址入库 | ✅ |
| `services/fetch_and_store_user_state.py` | 采集用户持仓信息 | ✅ |
| `services/fetch_and_store_user_fills.py` | 获取用户历史成交 | ✅ |
| `plotting/analyze_ls_rate.py` | 统计胜率与多空分布并可视化 | ✅ |
| `plotting/analyze_ls_rate_over_value_pro.py` | 按入场价值区间细分胜率与多空分布 | ✅ |
| `plotting/analyze_history.py` | 按时间可视化已存储分析结果 | ✅ |
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
- `analyze_history.py`
  - 读取已存储的分析结果集合，按时间绘制人数比 `ratio` 与价值比 `value_ratio`。
  - `--basic` 可输出基础两图并导出 Excel（`analyze_result.xlsx`）。
  - 增强模式支持 `group` 与 `big`：适合对 `position_distribution` 与 `value_position_distribution` 做更细致的时间序列对比。

## 需采集数据
- 地址历史操作数据，fills
- k线数据
- 区块数据
- 金库数据

## TODO 待办事项
实现已完成订单中间表而不是每次实时计算，实时计算会导致重新拉取新订单耗时，有速率限制【但是计算已完成订单需要去掉最后一单】
