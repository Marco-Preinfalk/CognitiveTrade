// DeepTrade AI Dashboard Controller - Full SPA

let performanceChart = null;
let allocationChart = null;
let pnlChart = null;
let currentPage = 'dashboard';
let autoTradeState = false;  // Track auto-trade state separately
let equityChartRange = '1D'; // Current equity chart filter: 1D, 1W, 1M, ALL
let fullEquityHistory = [];  // Full equity history from API (unfiltered)

const fmt = (amount) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
const fmtPct = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
const fmtTime = (iso) => iso ? moment(iso).format('HH:mm:ss') : 'N/A';
const fmtDate = (iso) => iso ? moment(iso).format('DD.MM.YY HH:mm') : 'N/A';
const cc = (v) => v >= 0 ? 'text-success' : 'text-danger';

// ========== PAGE ROUTER ==========
function navigateTo(page) {
    currentPage = page;
    document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.nav-links li').forEach(li => li.classList.remove('active'));
    const el = document.getElementById('page-' + page);
    if (el) el.classList.add('active');
    const nav = document.querySelector(`[data-page="${page}"]`);
    if (nav) nav.classList.add('active');

    if (page === 'portfolio') updatePortfolioPage();
    if (page === 'history') updateHistoryPage();
}

// ========== CHART INIT ==========
const initChart = () => {
    const ctx = document.getElementById('performanceChart').getContext('2d');
    let g = ctx.createLinearGradient(0, 0, 0, 400);
    g.addColorStop(0, 'rgba(59, 130, 246, 0.5)');
    g.addColorStop(1, 'rgba(59, 130, 246, 0.0)');
    performanceChart = new Chart(ctx, {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Portfolio Equity', data: [], borderColor: '#3b82f6', backgroundColor: g, borderWidth: 2, pointRadius: 0, pointHoverRadius: 6, fill: true, tension: 0.4 }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false, backgroundColor: 'rgba(15,23,42,0.9)', titleColor: '#94a3b8', bodyColor: '#f8fafc', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, callbacks: { label: (c) => fmt(c.parsed.y) } } },
            scales: { x: { type: 'time', time: { unit: 'minute', displayFormats: { minute: 'HH:mm' } }, grid: { display: false }, ticks: { color: '#94a3b8', maxRotation: 0 } }, y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', callback: (v) => '$' + v } } },
            interaction: { mode: 'nearest', axis: 'x', intersect: false }
        }
    });
};

// ========== DASHBOARD UPDATES ==========
const updatePortfolio = async () => {
    try {
        const { data } = await axios.get('/api/portfolio');
        document.getElementById('total-equity').innerText = fmt(data.total_equity);
        document.getElementById('unrealized-pnl').innerText = fmt(data.unrealized_pnl);
        document.getElementById('unrealized-pnl').className = `value calc-font ${cc(data.unrealized_pnl)}`;
        document.getElementById('open-positions').innerText = `${data.positions.length} Open Positions`;
        document.getElementById('win-rate').innerText = `${data.win_rate.toFixed(1)}%`;
        document.getElementById('profit-factor').innerText = `PF: ${data.profit_factor.toFixed(2)}`;
        document.getElementById('sharpe-ratio').innerText = data.sharpe_ratio.toFixed(2);
        document.getElementById('max-drawdown').innerText = `${data.max_drawdown.toFixed(1)}%`;
        let r = document.getElementById('return-percent');
        r.innerText = fmtPct(data.return_percent);
        r.className = `trend-badge ${data.return_percent >= 0 ? 'positive' : 'negative'}`;

        if (data.equity_history && data.equity_history.length > 0) {
            fullEquityHistory = data.equity_history;
            applyEquityChartFilter(equityChartRange);
        }

        const tbody = document.getElementById('positions-table-body');
        tbody.innerHTML = '';
        if (data.positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No open positions</td></tr>';
        } else {
            data.positions.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `<td class="font-weight-bold">${p.asset}</td><td><span class="badge ${p.type === 'BUY' ? 'long' : 'short'}">${p.type}</span></td><td>${p.qty.toFixed(4)}</td><td class="calc-font">${fmt(p.entry_price)}</td><td class="calc-font">${fmt(p.current_price)}</td><td class="calc-font text-muted">${fmt(p.stop_loss)} / ${fmt(p.take_profit)}</td><td class="calc-font ${cc(p.unrealized_pnl)}">${fmt(p.unrealized_pnl)} (${fmtPct(p.unrealized_pnl_percent)})</td>`;
                tbody.appendChild(tr);
            });
        }
        updateLastSync(true);
    } catch (e) { console.error("Portfolio error:", e); updateLastSync(false); }
};

const updateTrades = async () => {
    try {
        const { data: trades } = await axios.get('/api/trades');
        const tbody = document.getElementById('trades-table-body');
        tbody.innerHTML = '';
        if (trades.length === 0) { tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No recent trades</td></tr>'; return; }
        trades.slice(0, 10).forEach(t => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td class="text-muted"><small>${t.id.split('_')[1]}</small></td><td>${t.asset}</td><td class="${t.type === 'BUY' ? 'text-success' : 'text-danger'}">${t.type}</td><td><small>${fmtTime(t.entry_time)}</small></td><td class="calc-font ${cc(t.pnl)}">${fmt(t.pnl)}</td>`;
            tbody.appendChild(tr);
        });
    } catch (e) { console.error("Trades error:", e); }
};

const updateMarket = async () => {
    try {
        const { data: markets } = await axios.get('/api/market-info');
        const c = document.getElementById('market-ticker');
        c.innerHTML = '';
        markets.forEach(m => {
            const d = document.createElement('div');
            d.className = 'ticker-item';
            d.innerHTML = `<div><span class="ticker-symbol">${m.symbol}</span><span class="ticker-name">${m.name}</span></div><div class="text-right"><div class="ticker-price calc-font">${fmt(m.price)}</div><div class="calc-font ${cc(m.change)}"><small>${fmtPct(m.change)}</small></div></div>`;
            c.appendChild(d);
        });
    } catch (e) { console.error("Market error:", e); }
};

const updateSignals = async () => {
    try {
        const { data: signals } = await axios.get('/api/signals');
        const tbody = document.getElementById('signals-table-body');
        tbody.innerHTML = '';
        if (!signals || signals.length === 0) { tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No strong signals</td></tr>'; return; }
        signals.forEach(s => {
            const tr = document.createElement('tr');
            const bc = s.signal === 'BUY' ? 'badge long' : (s.signal === 'SELL' ? 'badge short' : 'badge neutral');
            tr.innerHTML = `<td class="font-weight-bold">${s.asset}</td><td><span class="${bc}">${s.signal}</span></td><td>${(s.confidence * 100).toFixed(0)}%</td><td><small>${s.risk_reward ? s.risk_reward.toFixed(2) : '--'}</small></td>`;
            tbody.appendChild(tr);
        });
    } catch (e) { console.error("Signals error:", e); }
};

// ========== PORTFOLIO PAGE ==========
const updatePortfolioPage = async () => {
    try {
        const { data } = await axios.get('/api/portfolio');
        document.getElementById('pf-cash').innerText = fmt(data.balance);
        const invested = data.initial_balance - data.balance;
        document.getElementById('pf-invested').innerText = fmt(invested > 0 ? invested : 0);
        document.getElementById('pf-realized-pnl').innerText = fmt(data.total_pnl);
        document.getElementById('pf-realized-pnl').className = `value calc-font ${cc(data.total_pnl)}`;
        document.getElementById('pf-total-trades').innerText = data.trades_count;

        // Performance bars
        document.getElementById('pf-win-rate').innerText = `${data.win_rate.toFixed(1)}%`;
        document.getElementById('pf-wr-bar').style.width = `${Math.min(data.win_rate, 100)}%`;
        document.getElementById('pf-profit-factor').innerText = data.profit_factor === Infinity ? '∞' : data.profit_factor.toFixed(2);
        document.getElementById('pf-pf-bar').style.width = `${Math.min(data.profit_factor * 20, 100)}%`;
        document.getElementById('pf-sharpe').innerText = data.sharpe_ratio.toFixed(2);
        document.getElementById('pf-sr-bar').style.width = `${Math.min(Math.abs(data.sharpe_ratio) * 25, 100)}%`;
        document.getElementById('pf-max-dd').innerText = `${data.max_drawdown.toFixed(1)}%`;
        document.getElementById('pf-dd-bar').style.width = `${Math.min(Math.abs(data.max_drawdown), 100)}%`;

        // Positions table
        const tbody = document.getElementById('pf-positions-body');
        tbody.innerHTML = '';
        if (data.positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">No open positions</td></tr>';
        } else {
            data.positions.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `<td><strong>${p.asset}</strong></td><td><span class="badge ${p.type === 'BUY' ? 'long' : 'short'}">${p.type}</span></td><td class="calc-font">${p.qty.toFixed(4)}</td><td class="calc-font">${fmt(p.entry_price)}</td><td class="calc-font">${fmt(p.current_price)}</td><td class="calc-font text-warning">${fmt(p.stop_loss)}</td><td class="calc-font text-success">${fmt(p.take_profit)}</td><td class="calc-font ${cc(p.unrealized_pnl)}">${fmt(p.unrealized_pnl)}</td><td class="calc-font ${cc(p.unrealized_pnl_percent)}">${fmtPct(p.unrealized_pnl_percent)}</td>`;
                tbody.appendChild(tr);
            });
        }

        // Allocation chart
        initAllocationChart(data);
    } catch (e) { console.error("Portfolio page error:", e); }
};

function initAllocationChart(data) {
    const ctx = document.getElementById('allocationChart').getContext('2d');
    if (allocationChart) allocationChart.destroy();
    const labels = ['Cash'];
    const values = [data.balance];
    const colors = ['rgba(59,130,246,0.7)'];
    const borderColors = ['#3b82f6'];
    const palette = ['rgba(139,92,246,0.7)', 'rgba(16,185,129,0.7)', 'rgba(245,158,11,0.7)', 'rgba(239,68,68,0.7)', 'rgba(6,182,212,0.7)'];
    const borderPalette = ['#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#06b6d4'];
    data.positions.forEach((p, i) => {
        labels.push(p.asset);
        values.push(p.qty * p.current_price);
        colors.push(palette[i % palette.length]);
        borderColors.push(borderPalette[i % borderPalette.length]);
    });
    allocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: colors, borderColor: borderColors, borderWidth: 2 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '65%', plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', padding: 16, font: { size: 12 } } } } }
    });
}

// ========== AI SIGNALS PAGE ==========
const loadDetailedSignals = async () => {
    const container = document.getElementById('detailed-signals-container');
    container.innerHTML = '<div class="text-center p-3"><i class="bi bi-arrow-repeat spin" style="font-size:2rem;color:var(--accent-primary)"></i><p class="text-muted" style="margin-top:12px">AI analysiert Märkte & News... Dies kann bis zu 2 Minuten dauern.</p></div>';
    try {
        const { data: signals } = await axios.get('/api/signals/detailed', { timeout: 180000 });
        container.innerHTML = '';
        if (!signals || signals.length === 0) { container.innerHTML = '<div class="text-center text-muted p-3">Keine Signale verfügbar</div>'; return; }
        signals.forEach(s => container.appendChild(buildSignalCard(s)));
    } catch (e) {
        console.error("Detailed signals error:", e);
        container.innerHTML = '<div class="text-center text-danger p-3"><i class="bi bi-exclamation-triangle"></i> Fehler beim Laden der Signale. Bitte erneut versuchen.</div>';
    }
};

function buildSignalCard(s) {
    const card = document.createElement('div');
    const isHold = s.signal === 'HOLD' || s.confidence === 0;
    const sigClass = s.signal === 'BUY' ? 'signal-buy' : s.signal === 'SELL' ? 'signal-sell' : 'signal-hold';
    const badgeClass = s.signal === 'BUY' ? 'long' : s.signal === 'SELL' ? 'short' : 'neutral';
    const confPct = (s.confidence * 100).toFixed(0);
    const confColor = s.confidence > 0.7 ? 'var(--accent-success)' : s.confidence > 0.5 ? 'var(--accent-warning)' : 'var(--text-muted)';
    card.className = `signal-card ${sigClass}`;

    let newsHtml = '<div class="text-muted" style="font-size:0.85rem;padding:8px 0;">Keine News verfügbar. Finnhub API Key in .env eintragen für echte Nachrichten.</div>';
    if (s.news && s.news.length > 0) {
        newsHtml = s.news.map(n => {
            const dt = n.datetime ? moment(n.datetime).fromNow() : '';
            return `<div class="news-item"><div class="news-headline"><a href="${n.url}" target="_blank" rel="noopener">${n.headline}</a></div><div class="news-meta"><span class="news-source">${n.source}</span><span>${dt}</span></div></div>`;
        }).join('');
    }

    let sentimentHtml = '';
    if (s.sentiment && s.sentiment.consensus) {
        const sc = s.sentiment.consensus === 'BULLISH' ? 'bullish' : s.sentiment.consensus === 'BEARISH' ? 'bearish' : 'neutral';
        sentimentHtml = `<span class="sentiment-badge ${sc}">${s.sentiment.consensus}</span>`;
    }

    card.innerHTML = `
        <div class="signal-card-header">
            <div class="signal-asset-info">
                <span class="signal-asset-name">${s.asset}</span>
                <span class="badge ${badgeClass}">${s.signal}</span>
                ${sentimentHtml}
            </div>
            <div class="signal-meta">
                <div class="confidence-bar-container">
                    <span class="text-muted" style="font-size:0.8rem">Confidence</span>
                    <div class="confidence-bar"><div class="confidence-bar-fill" style="width:${confPct}%;background:${confColor}"></div></div>
                    <span class="confidence-label" style="color:${confColor}">${confPct}%</span>
                </div>
            </div>
        </div>
        <div class="signal-card-body">
            <div class="signal-details">
                <div class="signal-detail-row"><span class="label">${isHold ? 'Aktueller Preis' : 'Entry Price'}</span><span class="value">${s.entry_price ? fmt(s.entry_price) : '--'}</span></div>
                ${!isHold ? `<div class="signal-detail-row"><span class="label">Stop Loss</span><span class="value text-danger">${s.stop_loss ? fmt(s.stop_loss) : '--'}</span></div>
                <div class="signal-detail-row"><span class="label">Take Profit</span><span class="value text-success">${s.take_profit ? fmt(s.take_profit) : '--'}</span></div>
                <div class="signal-detail-row"><span class="label">Risk/Reward</span><span class="value">${s.risk_reward ? s.risk_reward.toFixed(2) + ':1' : '--'}</span></div>` : ''}
                ${s.reason ? `<div class="signal-reason"><i class="bi bi-robot"></i> ${s.reason}</div>` : ''}
            </div>
            <div class="signal-news">
                <div class="signal-news-title"><i class="bi bi-newspaper"></i> Aktuelle Nachrichten</div>
                ${newsHtml}
            </div>
        </div>`;
    return card;
}

// ========== HISTORY PAGE ==========
const updateHistoryPage = async () => {
    try {
        const { data: trades } = await axios.get('/api/trades');
        const wins = trades.filter(t => t.pnl >= 0).length;
        const losses = trades.filter(t => t.pnl < 0).length;
        document.getElementById('hist-total').innerText = `${trades.length} Trades`;
        document.getElementById('hist-wins').innerText = `${wins} Wins`;
        document.getElementById('hist-losses').innerText = `${losses} Losses`;

        const tbody = document.getElementById('history-table-body');
        tbody.innerHTML = '';
        if (trades.length === 0) { tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">No trades yet</td></tr>'; return; }
        trades.forEach(t => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td class="text-muted">${t.id}</td><td><strong>${t.asset}</strong></td><td><span class="badge ${t.type === 'BUY' ? 'long' : 'short'}">${t.type}</span></td><td class="calc-font">${fmt(t.entry_price)}</td><td class="calc-font">${t.exit_price ? fmt(t.exit_price) : '--'}</td><td><small>${fmtDate(t.entry_time)}</small></td><td><small>${fmtDate(t.exit_time)}</small></td><td class="calc-font ${cc(t.pnl)}">${fmt(t.pnl)}</td><td class="calc-font ${cc(t.pnl_percent)}">${fmtPct(t.pnl_percent)}</td>`;
            tbody.appendChild(tr);
        });

        initPnlChart(trades);
    } catch (e) { console.error("History error:", e); }
};

function initPnlChart(trades) {
    const ctx = document.getElementById('pnlChart').getContext('2d');
    if (pnlChart) pnlChart.destroy();
    const labels = trades.map(t => t.asset);
    const values = trades.map(t => t.pnl);
    const colors = values.map(v => v >= 0 ? 'rgba(16,185,129,0.7)' : 'rgba(239,68,68,0.7)');
    pnlChart = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ label: 'P&L', data: values, backgroundColor: colors, borderRadius: 4, borderSkipped: false }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmt(c.parsed.y) } } }, scales: { x: { grid: { display: false }, ticks: { color: '#94a3b8' } }, y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', callback: (v) => '$' + v } } } }
    });
}

// ========== HEALTH & SYNC ==========
const updateLastSync = (online) => {
    const ind = document.getElementById('health-indicator');
    const upd = document.getElementById('last-update');
    const ping = document.querySelector('.ping');
    if (online) { ind.innerText = 'System Online'; ind.classList.remove('text-danger'); ping.style.background = 'var(--accent-success)'; ping.style.boxShadow = '0 0 8px var(--glow-success)'; }
    else { ind.innerText = 'System Offline'; ind.classList.add('text-danger'); ping.style.background = 'var(--accent-danger)'; ping.style.boxShadow = '0 0 8px var(--glow-danger)'; }
    upd.innerText = `Updated: ${moment().format('HH:mm:ss')}`;
};

const updateAutoTradeButton = (enabled) => {
    autoTradeState = enabled;
    const btn = document.getElementById('btn-autotrade');
    if (enabled) { btn.className = 'btn btn-danger'; btn.innerHTML = '<i class="bi bi-stop-fill"></i> Auto-Trade: ON'; }
    else { btn.className = 'btn btn-primary'; btn.innerHTML = '<i class="bi bi-play-fill"></i> Auto-Trade: OFF'; }
};

const toggleAutoTrade = async () => {
    try {
        const { data } = await axios.post('/api/autotrade/toggle');
        updateAutoTradeButton(data.enabled);
    } catch (e) { console.error("Autotrade error:", e); }
};

const checkStatus = async () => {
    try {
        const { data } = await axios.get('/api/health');
        updateLastSync(data.status === 'online');
        updateAutoTradeButton(data.auto_trade);
    } catch (e) {
        updateLastSync(false);
    }
};

const refreshAll = () => { checkStatus(); updatePortfolio(); updateTrades(); updateMarket(); updateSignals(); };

// ========== EQUITY CHART FILTER ==========
function applyEquityChartFilter(range) {
    equityChartRange = range;
    if (!fullEquityHistory || fullEquityHistory.length === 0) return;

    const now = new Date();
    let cutoff;
    let timeUnit = 'minute';
    let displayFormat = 'HH:mm';

    switch (range) {
        case '1D':
            cutoff = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            timeUnit = 'minute';
            displayFormat = 'HH:mm';
            break;
        case '1W':
            cutoff = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            timeUnit = 'hour';
            displayFormat = 'ddd HH:mm';
            break;
        case '1M':
            cutoff = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            timeUnit = 'day';
            displayFormat = 'DD.MM';
            break;
        case 'ALL':
        default:
            cutoff = null;
            timeUnit = fullEquityHistory.length > 200 ? 'day' : fullEquityHistory.length > 50 ? 'hour' : 'minute';
            displayFormat = fullEquityHistory.length > 200 ? 'DD.MM' : fullEquityHistory.length > 50 ? 'ddd HH:mm' : 'HH:mm';
            break;
    }

    const filtered = cutoff
        ? fullEquityHistory.filter(i => new Date(i.timestamp) >= cutoff)
        : fullEquityHistory;

    // If no data in the selected range, show all data as fallback
    const dataToShow = filtered.length > 0 ? filtered : fullEquityHistory;

    performanceChart.data.labels = dataToShow.map(i => new Date(i.timestamp));
    performanceChart.data.datasets[0].data = dataToShow.map(i => i.equity);
    performanceChart.options.scales.x.time.unit = timeUnit;
    performanceChart.options.scales.x.time.displayFormats = { [timeUnit]: displayFormat };
    performanceChart.update();

    // Update active button state
    document.querySelectorAll('#equity-chart-filters button').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.range === range);
    });
}

// ========== INIT ==========
document.addEventListener('DOMContentLoaded', () => {
    // Page router
    document.querySelectorAll('.nav-links li[data-page]').forEach(li => {
        li.addEventListener('click', (e) => { e.preventDefault(); navigateTo(li.dataset.page); });
    });

    // Equity chart filter buttons
    document.querySelectorAll('#equity-chart-filters button[data-range]').forEach(btn => {
        btn.addEventListener('click', () => applyEquityChartFilter(btn.dataset.range));
    });

    initChart();
    // Load auto-trade status immediately
    checkStatus();
    refreshAll();

    setInterval(() => { checkStatus(); updatePortfolio(); updateTrades(); updateMarket(); }, 15000);
    setInterval(updateSignals, 60000);
});
