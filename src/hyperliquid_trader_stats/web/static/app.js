const state = {
  page: 1,
  totalPages: 0,
};

const controls = [
  "search",
  "min_win_rate",
  "max_win_rate",
  "min_total_trades",
  "max_total_trades",
  "min_net_pnl",
  "max_net_pnl",
  "min_position_value",
  "max_position_value",
  "position_direction",
  "entry_value_tier",
  "min_entry_win_rate",
  "updated_after",
  "updated_before",
  "sort_by",
  "sort_dir",
  "page_size",
];

const rows = document.querySelector("#traderRows");
const resultSummary = document.querySelector("#resultSummary");
const pageLabel = document.querySelector("#pageLabel");
const detailDialog = document.querySelector("#detailDialog");
const detailContent = document.querySelector("#detailContent");
const detailTitle = document.querySelector("#detailTitle");
const tradeContent = document.querySelector("#tradeContent");
const tradePager = document.querySelector("#tradePager");
const tradePageLabel = document.querySelector("#tradePageLabel");
const prevTradePage = document.querySelector("#prevTradePage");
const nextTradePage = document.querySelector("#nextTradePage");
const sortByControl = document.querySelector("#sort_by");
const sortDirControl = document.querySelector("#sort_dir");
const sortHeaderButtons = document.querySelectorAll(".sort-header");
const detailState = {
  address: null,
  tradePage: 1,
  tradePages: 0,
};

function valueOf(id) {
  const value = document.querySelector(`#${id}`).value.trim();
  return value === "" ? null : value;
}

function buildParams() {
  const params = new URLSearchParams();
  params.set("page", state.page);
  for (const id of controls) {
    const value = valueOf(id);
    if (value !== null) {
      if (id === "updated_after" || id === "updated_before") {
        params.set(id, `${value}T00:00:00`);
      } else {
        params.set(id, value);
      }
    }
  }
  return params;
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toLocaleString("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function shortAddress(address) {
  if (!address || address.length < 16) {
    return address || "-";
  }
  return `${address.slice(0, 8)}...${address.slice(-6)}`;
}

function hyperdashAddressUrl(address) {
  return `https://hyperdash.com/address/${encodeURIComponent(address)}`;
}

async function copyAddress(address, button) {
  try {
    await navigator.clipboard.writeText(address);
  } catch {
    const input = document.createElement("textarea");
    input.value = address;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }

  const originalTitle = button.title;
  const originalLabel = button.getAttribute("aria-label");
  button.title = "已复制";
  button.setAttribute("aria-label", "已复制");
  button.classList.add("copied");
  window.setTimeout(() => {
    button.title = originalTitle;
    button.setAttribute("aria-label", originalLabel);
    button.classList.remove("copied");
  }, 1200);
}

function updateSortHeaders() {
  for (const button of sortHeaderButtons) {
    const active = button.dataset.sortBy === sortByControl.value;
    const header = button.closest("th");
    const indicator = button.querySelector(".sort-indicator");
    button.classList.toggle("active", active);
    header.setAttribute(
      "aria-sort",
      active
        ? sortDirControl.value === "desc"
          ? "descending"
          : "ascending"
        : "none",
    );
    indicator.textContent = active
      ? sortDirControl.value === "desc"
        ? "↓"
        : "↑"
      : "↕";
  }
}

function pnlClass(value) {
  if (Number(value) > 0) {
    return "positive";
  }
  if (Number(value) < 0) {
    return "negative";
  }
  return "muted";
}

function entryRates(summary = {}) {
  const keys = ["win_rate_over_1w", "win_rate_over_10w", "win_rate_over_100w"];
  return keys
    .map((key) => {
      const stat = summary[key] || {};
      return stat.total_trades ? `${formatNumber(stat.win_rate)}%` : "-";
    })
    .join(" / ");
}

function flattenSummary(value, path = "", result = []) {
  if (value === null || value === undefined || typeof value !== "object") {
    result.push([path, value]);
    return result;
  }

  const entries = Array.isArray(value)
    ? value.map((item, index) => [`[${index}]`, item])
    : Object.entries(value);
  if (!entries.length) {
    result.push([path, Array.isArray(value) ? "[]" : "{}"]);
    return result;
  }
  for (const [key, item] of entries) {
    const nextPath = Array.isArray(value)
      ? `${path}${key}`
      : path
        ? `${path}.${key}`
        : key;
    flattenSummary(item, nextPath, result);
  }
  return result;
}

function renderSummaryTable(data) {
  detailContent.innerHTML = `
    <table class="summary-table">
      <thead>
        <tr><th>字段</th><th>值</th></tr>
      </thead>
      <tbody></tbody>
    </table>
  `;
  const body = detailContent.querySelector("tbody");
  for (const [field, value] of flattenSummary(data)) {
    const tr = document.createElement("tr");
    const fieldCell = document.createElement("td");
    const valueCell = document.createElement("td");
    fieldCell.className = "detail-field";
    fieldCell.textContent = field;
    valueCell.textContent =
      typeof value === "number" ? formatNumber(value, 6) : String(value);
    tr.append(fieldCell, valueCell);
    body.appendChild(tr);
  }
}

const tradeColumns = [
  ["coin", "币种"],
  ["direction", "方向"],
  ["end_time", "结束时间"],
  ["total_size", "数量"],
  ["entry_avg_price", "平均入场价"],
  ["exit_avg_price", "平均出场价"],
  ["closed_pnl", "已实现盈亏"],
  ["fees", "手续费"],
  ["net_pnl", "净盈亏"],
  ["profit_percentage", "收益率 %"],
  ["duration", "持仓时长"],
  ["fills_count", "成交数"],
];

function renderTradesTable(items) {
  tradeContent.innerHTML = `
    <table class="trade-table">
      <thead><tr></tr></thead>
      <tbody></tbody>
    </table>
  `;
  const header = tradeContent.querySelector("thead tr");
  const body = tradeContent.querySelector("tbody");
  for (const [, label] of tradeColumns) {
    const th = document.createElement("th");
    th.textContent = label;
    header.appendChild(th);
  }
  for (const item of items) {
    const tr = document.createElement("tr");
    for (const [field] of tradeColumns) {
      const td = document.createElement("td");
      const value = item[field];
      if (["closed_pnl", "net_pnl"].includes(field)) {
        td.className = pnlClass(value);
      }
      td.textContent =
        typeof value === "number" ? formatNumber(value, 6) : (value ?? "-");
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

function renderRows(items) {
  rows.innerHTML = "";
  if (!items.length) {
    rows.innerHTML = `<tr><td colspan="8" class="muted">没有符合条件的数据</td></tr>`;
    return;
  }

  for (const item of items) {
    const net = item.completed_trade_pnl?.net;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>
        <div class="address-cell">
          <span class="address" title="${item.ethAddress}">${shortAddress(item.ethAddress)}</span>
          <button
            class="table-action copy-address"
            type="button"
            title="复制完整地址"
            aria-label="复制完整地址"
          >
            <svg class="copy-icon" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="8" y="8" width="11" height="11" rx="2"></rect>
              <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>
            </svg>
            <svg class="check-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="m5 12 4 4L19 6"></path>
            </svg>
          </button>
          <a
            class="table-action"
            href="${hyperdashAddressUrl(item.ethAddress)}"
            target="_blank"
            rel="noopener noreferrer"
            title="在 Hyperdash 查看"
            aria-label="在 Hyperdash 查看"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M14 5h5v5"></path>
              <path d="M10 14 19 5"></path>
              <path d="M19 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"></path>
            </svg>
          </a>
        </div>
      </td>
      <td>${formatNumber(item.win_rate)}%</td>
      <td>${formatNumber(item.win_rate_score)}</td>
      <td>${item.winning_trades ?? 0} / ${item.total_trades ?? 0}</td>
      <td class="${pnlClass(net)}">${formatNumber(net)}</td>
      <td class="${pnlClass(item.effective_position_value)}">${formatNumber(item.effective_position_value, 3)}</td>
      <td>${entryRates(item.entry_value_summary)}</td>
      <td>${formatDate(item.updated_at)}</td>
    `;
    tr.addEventListener("click", () => openDetail(item.ethAddress));
    tr.querySelector(".copy-address").addEventListener("click", (event) => {
      event.stopPropagation();
      copyAddress(item.ethAddress, event.currentTarget);
    });
    tr.querySelector("a").addEventListener("click", (event) => {
      event.stopPropagation();
    });
    rows.appendChild(tr);
  }
}

async function loadData() {
  resultSummary.textContent = "正在载入交易员数据";
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);
  let response;
  try {
    response = await fetch(`/api/traders?${buildParams().toString()}`, {
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("查询超过 15 秒，请减少筛选范围或检查 MongoDB 索引");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
  const data = await response.json();
  state.totalPages = data.pages;
  renderRows(data.items);
  resultSummary.textContent = `共 ${data.total.toLocaleString("zh-CN")} 个地址，当前显示 ${data.items.length} 个`;
  pageLabel.textContent = `第 ${data.page} / ${Math.max(data.pages, 1)} 页`;
  document.querySelector("#prevPage").disabled = data.page <= 1;
  document.querySelector("#nextPage").disabled = data.page >= data.pages;
}

async function openDetail(address) {
  detailContent.textContent = "载入中";
  detailTitle.textContent = shortAddress(address);
  detailState.address = address;
  detailState.tradePage = 1;
  detailState.tradePages = 0;
  tradeContent.hidden = false;
  tradeContent.textContent = "正在载入交易明细";
  tradePager.hidden = true;
  detailDialog.showModal();
  loadTraderTrades(1);
  const response = await fetch(`/api/traders/${encodeURIComponent(address)}`);
  if (detailState.address !== address) {
    return;
  }
  if (!response.ok) {
    detailContent.textContent = `读取失败：HTTP ${response.status}`;
    return;
  }
  const data = await response.json();
  renderSummaryTable(data);
}

async function loadTraderTrades(page = 1) {
  const address = detailState.address;
  if (!address) {
    return;
  }

  tradeContent.hidden = false;
  tradeContent.textContent = "正在载入交易明细";
  const params = new URLSearchParams({ page, page_size: 20 });
  let response;
  try {
    response = await fetch(
      `/api/traders/${encodeURIComponent(address)}/trades?${params.toString()}`,
    );
  } catch {
    if (detailState.address === address) {
      tradeContent.textContent = "交易明细读取失败";
    }
    return;
  }
  if (detailState.address !== address) {
    return;
  }
  if (!response.ok) {
    tradeContent.textContent = `读取失败：HTTP ${response.status}`;
    return;
  }

  const data = await response.json();
  detailState.tradePage = data.page;
  detailState.tradePages = data.pages;
  renderTradesTable(data.items);
  tradePager.hidden = false;
  tradePageLabel.textContent = `第 ${data.page} / ${Math.max(data.pages, 1)} 页，共 ${data.total.toLocaleString("zh-CN")} 笔`;
  prevTradePage.disabled = data.page <= 1;
  nextTradePage.disabled = data.page >= data.pages;
}

prevTradePage.addEventListener("click", () => {
  if (detailState.tradePage > 1) {
    loadTraderTrades(detailState.tradePage - 1);
  }
});

nextTradePage.addEventListener("click", () => {
  if (detailState.tradePage < detailState.tradePages) {
    loadTraderTrades(detailState.tradePage + 1);
  }
});

detailDialog.addEventListener("click", (event) => {
  const rect = detailDialog.getBoundingClientRect();
  const clickedOutside =
    event.clientX < rect.left ||
    event.clientX > rect.right ||
    event.clientY < rect.top ||
    event.clientY > rect.bottom;
  if (clickedOutside) {
    detailDialog.close();
  }
});

function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
}

const reloadFromFirstPage = debounce(() => {
  state.page = 1;
  loadData().catch((error) => {
    resultSummary.textContent = `加载失败：${error.message}`;
  });
}, 250);

for (const id of controls) {
  document.querySelector(`#${id}`).addEventListener("input", reloadFromFirstPage);
}

sortByControl.addEventListener("input", updateSortHeaders);
sortDirControl.addEventListener("input", updateSortHeaders);

for (const button of sortHeaderButtons) {
  button.addEventListener("click", () => {
    if (sortByControl.value === button.dataset.sortBy) {
      sortDirControl.value = sortDirControl.value === "desc" ? "asc" : "desc";
    } else {
      sortByControl.value = button.dataset.sortBy;
      sortDirControl.value = "desc";
    }
    state.page = 1;
    updateSortHeaders();
    loadData().catch((error) => {
      resultSummary.textContent = `加载失败：${error.message}`;
    });
  });
}

document.querySelector("#refreshButton").addEventListener("click", () => {
  loadData().catch((error) => {
    resultSummary.textContent = `加载失败：${error.message}`;
  });
});

document.querySelector("#resetButton").addEventListener("click", () => {
  for (const id of controls) {
    const element = document.querySelector(`#${id}`);
    if (id === "sort_by") {
      element.value = "win_rate_score";
    } else if (id === "sort_dir") {
      element.value = "desc";
    } else if (id === "position_direction" || id === "entry_value_tier") {
      element.value = id === "position_direction" ? "any" : "all";
    } else if (id === "page_size") {
      element.value = "20";
    } else {
      element.value = "";
    }
  }
  state.page = 1;
  updateSortHeaders();
  loadData().catch((error) => {
    resultSummary.textContent = `加载失败：${error.message}`;
  });
});

document.querySelector("#prevPage").addEventListener("click", () => {
  if (state.page > 1) {
    state.page -= 1;
    loadData().catch((error) => {
      resultSummary.textContent = `加载失败：${error.message}`;
    });
  }
});

document.querySelector("#nextPage").addEventListener("click", () => {
  if (state.page < state.totalPages) {
    state.page += 1;
    loadData().catch((error) => {
      resultSummary.textContent = `加载失败：${error.message}`;
    });
  }
});

updateSortHeaders();
loadData().catch((error) => {
  resultSummary.textContent = `加载失败：${error.message}`;
});
