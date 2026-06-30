const dashboardElements = {
  status: document.querySelector("#dashboardStatus"),
  trackedAddresses: document.querySelector("#trackedAddresses"),
  analysisCoverage: document.querySelector("#analysisCoverage"),
  traderCount: document.querySelector("#traderCount"),
  highWinRate: document.querySelector("#highWinRate"),
  eliteTraders: document.querySelector("#eliteTraders"),
  eliteRate: document.querySelector("#eliteRate"),
  longExposure: document.querySelector("#longExposure"),
  shortExposure: document.querySelector("#shortExposure"),
  longBar: document.querySelector("#longBar"),
  shortBar: document.querySelector("#shortBar"),
  positionBias: document.querySelector("#positionBias"),
  analysisUpdatedAt: document.querySelector("#analysisUpdatedAt"),
  footerAnalysisTime: document.querySelector("#footerAnalysisTime"),
  leaders: document.querySelector("#dashboardLeaders"),
};

function integerNumber(value) {
  return Math.round(Number(value || 0)).toLocaleString("zh-CN");
}

function money(value) {
  const number = Number(value || 0);
  const sign = number < 0 ? "-" : "";
  const formatted = Math.abs(number).toLocaleString("zh-CN", {
    maximumFractionDigits: 2,
  });
  return `${sign}$${formatted}`;
}

function percent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

function dateTime(value) {
  if (!value) return "暂无";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "暂无";
  return date.toLocaleString("zh-CN", { hour12: false });
}

function shortAddress(address) {
  if (!address) return "—";
  return `${address.slice(0, 7)}…${address.slice(-5)}`;
}

function renderLeaders(items) {
  dashboardElements.leaders.innerHTML = "";
  if (!items.length) {
    dashboardElements.leaders.innerHTML =
      '<p class="dashboard-empty">暂无交易员统计数据</p>';
    return;
  }

  items.forEach((item, index) => {
    const netPnl = Number(item.completed_trade_pnl?.net || 0);
    const row = document.createElement("a");
    row.className = "leader-row";
    row.href = `/leaderboard?address=${encodeURIComponent(item.ethAddress)}`;
    row.innerHTML = `
      <span class="leader-rank">${String(index + 1).padStart(2, "0")}</span>
      <span class="leader-address">${shortAddress(item.ethAddress)}</span>
      <span class="leader-stat">
        <small>胜率</small>
        <strong>${percent(item.win_rate)}</strong>
      </span>
      <span class="leader-stat">
        <small>交易</small>
        <strong>${integerNumber(item.total_trades)}</strong>
      </span>
      <span class="leader-pnl ${netPnl >= 0 ? "positive" : "negative"}">${money(netPnl)}</span>
    `;
    dashboardElements.leaders.appendChild(row);
  });
}

function renderDashboard(data) {
  const tracked = Number(data.tracked_addresses || 0);
  const traders = Number(data.trader_count || 0);
  const winrates = data.winrate_distribution || {};
  const positions = data.position_distribution?.ge_50 || {};
  const longExposure = Number(positions.long_value_sum || 0);
  const shortExposure = Math.abs(Number(positions.short_value_sum || 0));
  const totalExposure = longExposure + shortExposure;
  const longShare = totalExposure ? (longExposure / totalExposure) * 100 : 50;
  const thresholds = [50, 60, 70, 80, 90];
  const highWinRate = Number(winrates.ge_50 || 0);
  const eliteTraders = Number(winrates.ge_80 || 0);

  dashboardElements.trackedAddresses.textContent = integerNumber(tracked);
  dashboardElements.analysisCoverage.textContent =
    `分析覆盖 ${tracked ? percent((traders / tracked) * 100) : "0.0%"}`;
  dashboardElements.traderCount.textContent = integerNumber(traders);
  dashboardElements.highWinRate.textContent = integerNumber(highWinRate);
  dashboardElements.eliteTraders.textContent = integerNumber(eliteTraders);
  dashboardElements.eliteRate.textContent =
    `占已分析交易员 ${traders ? percent((eliteTraders / traders) * 100) : "0.0%"}`;
  thresholds.forEach((threshold) => {
    const count = Number(winrates[`ge_${threshold}`] || 0);
    document.querySelector(`#quality${threshold}`).textContent = integerNumber(count);
    document.querySelector(`#qualityBar${threshold}`).style.width =
      `${highWinRate ? (count / highWinRate) * 100 : 0}%`;
  });
  dashboardElements.longExposure.textContent = money(longExposure);
  dashboardElements.shortExposure.textContent = money(shortExposure);
  dashboardElements.longBar.style.width = `${longShare}%`;
  dashboardElements.shortBar.style.width = `${100 - longShare}%`;
  dashboardElements.positionBias.textContent =
    totalExposure === 0 ? "暂无仓位" : longShare >= 50 ? `偏多 ${percent(longShare)}` : `偏空 ${percent(100 - longShare)}`;
  dashboardElements.positionBias.classList.toggle(
    "positive",
    totalExposure > 0 && longShare >= 50,
  );
  dashboardElements.positionBias.classList.toggle(
    "negative",
    totalExposure > 0 && longShare < 50,
  );
  dashboardElements.analysisUpdatedAt.textContent = dateTime(data.analysis_updated_at);
  dashboardElements.footerAnalysisTime.textContent =
    `分析数据更新：${dateTime(data.analysis_updated_at)}`;
  dashboardElements.status.textContent = `已同步 · ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
  renderLeaders(data.top_traders || []);
}

async function loadDashboard() {
  dashboardElements.status.textContent = "正在同步";
  try {
    const response = await fetch("/api/dashboard");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderDashboard(await response.json());
  } catch (error) {
    dashboardElements.status.textContent = `加载失败 · ${error.message}`;
  }
}

document.querySelector("#dashboardRefresh").addEventListener("click", loadDashboard);
loadDashboard();
