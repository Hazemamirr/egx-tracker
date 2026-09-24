let allStocks = [];
let activeFilter = "all";
let searchTerm = "";

init();

async function init() {
  try {
    const res = await fetch("data/latest.json", { cache: "no-store" });
    const payload = await res.json();
    allStocks = (payload.stocks || []).filter((s) => s.error === undefined);

    renderMeta(payload);
    renderHero(allStocks);
    render();
  } catch (err) {
    document.getElementById("stockBody").innerHTML =
      `<tr><td colspan="5" class="loading-row">Couldn't load data/latest.json (${err.message}).</td></tr>`;
  }

  document.getElementById("tabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    activeFilter = btn.dataset.filter;
    render();
  });

  document.getElementById("search").addEventListener("input", (e) => {
    searchTerm = e.target.value.trim().toLowerCase();
    render();
  });
}

function renderMeta(payload) {
  const meta = document.getElementById("sessionMeta");
  if (payload.session_date) {
    meta.textContent = `session: ${payload.session_date}`;
  } else {
    meta.textContent = "no session data yet";
  }

  if (payload.demo) {
    document.getElementById("demoBanner").hidden = false;
  }

  renderFreshness(payload);
}

// Yahoo publishes the daily EGX bar hours after the 14:30 Cairo close, so a
// scheduled run can complete successfully and still return the *previous*
// session. Rather than pass that off as today's numbers, say plainly how old
// the session is. EGX trades Sun-Thu, so a Thursday close is legitimately
// three days old by Sunday morning -- only warn past that.
const STALE_AFTER_DAYS = 4;

function renderFreshness(payload) {
  const banner = document.getElementById("staleBanner");
  if (!payload.session_date) return;

  const ageDays = Math.floor(
    (Date.now() - Date.parse(`${payload.session_date}T12:00:00Z`)) / 86400000
  );
  if (ageDays < STALE_AFTER_DAYS) return;

  const checked = payload.updated_at
    ? new Date(payload.updated_at).toLocaleString()
    : "unknown";
  banner.innerHTML =
    `These are the closing prices from <strong>${payload.session_date}</strong>, ` +
    `about ${ageDays} days ago — the feed may have stopped updating. ` +
    `Last checked ${checked}.`;
  banner.hidden = false;
}

function renderHero(stocks) {
  const advancing = stocks.filter((s) => s.change_pct > 0).length;
  const declining = stocks.filter((s) => s.change_pct < 0).length;
  const flat = stocks.length - advancing - declining;

  document.getElementById("advCount").textContent = advancing;
  document.getElementById("decCount").textContent = declining;

  const strip = document.getElementById("heroStrip");
  strip.innerHTML = "";
  const segments = [
    { cls: "seg-up", count: advancing },
    { cls: "seg-flat", count: flat },
    { cls: "seg-down", count: declining },
  ];
  const total = Math.max(stocks.length, 1);
  segments.forEach(({ cls, count }) => {
    if (count === 0) return;
    const span = document.createElement("span");
    span.className = cls;
    span.style.width = `${(count / total) * 100}%`;
    strip.appendChild(span);
  });
}

function render() {
  let rows = [...allStocks];

  if (activeFilter === "gainers") {
    rows = rows.filter((s) => s.change_pct > 0).sort((a, b) => b.change_pct - a.change_pct);
  } else if (activeFilter === "losers") {
    rows = rows.filter((s) => s.change_pct < 0).sort((a, b) => a.change_pct - b.change_pct);
  } else if (activeFilter === "active") {
    rows = rows.sort((a, b) => b.volume - a.volume);
  } else {
    rows = rows.sort((a, b) => b.change_pct - a.change_pct);
  }

  if (searchTerm) {
    rows = rows.filter(
      (s) =>
        s.symbol.toLowerCase().includes(searchTerm) ||
        (s.name || "").toLowerCase().includes(searchTerm) ||
        (s.name_ar || "").includes(searchTerm)
    );
  }

  const body = document.getElementById("stockBody");
  const emptyState = document.getElementById("emptyState");

  if (rows.length === 0) {
    body.innerHTML = "";
    emptyState.hidden = false;
    return;
  }
  emptyState.hidden = true;

  body.innerHTML = rows.map(rowHtml).join("");
}

function rowHtml(s) {
  const dir = s.change_pct > 0 ? "up" : s.change_pct < 0 ? "down" : "flat";
  const sign = s.change_pct > 0 ? "+" : "";
  return `
    <tr>
      <td><span class="symbol">${s.symbol.replace(".CA", "")}</span></td>
      <td class="col-name"><span class="company-name">${s.name_ar || s.name}</span></td>
      <td class="col-num price">${formatPrice(s.price)}</td>
      <td class="col-num"><span class="change ${dir}">${sign}${s.change_pct.toFixed(2)}%</span></td>
      <td class="col-num volume">${formatVolume(s.volume)}</td>
    </tr>`;
}

function formatPrice(p) {
  return p == null ? "—" : p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatVolume(v) {
  if (v == null) return "—";
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(2) + "M";
  if (v >= 1_000) return (v / 1_000).toFixed(1) + "K";
  return String(v);
}
