// ============================================================
// CognitiveTrade — Terminal Dashboard Controller
// 
// Handles real-time UI updates, asynchronous data fetching from
// the Flask backend, and dynamic chart rendering.
// ============================================================

let performanceChart = null;
let allocationChart = null;
let pnlChart = null;
let currentPage = 'dashboard';
let autoTradeState = false;
let equityChartRange = '1D';
let fullEquityHistory = [];
let executionLog = [];
const MAX_LOG_ENTRIES = 80;

// ========== FORMATTERS ==========
const fmt = (amount) => {
    if (amount === undefined || amount === null || isNaN(amount)) return '$--';
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(amount);
};

const fmtCompact = (amount) => {
    if (amount === undefined || amount === null || isNaN(amount)) return '$--';
    const abs = Math.abs(amount);
    if (abs >= 1e6) return (amount >= 0 ? '' : '-') + '$' + (abs / 1e6).toFixed(2) + 'M';
    if (abs >= 1e3) return (amount >= 0 ? '' : '-') + '$' + (abs / 1e3).toFixed(1) + 'K';
    return fmt(amount);
};

const fmtPct = (v) => {
    if (v === undefined || v === null || isNaN(v)) return '--%';
    return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
};

const fmtTime = (iso) => iso ? moment(iso).format('HH:mm:ss') : '--:--:--';
const fmtDate = (iso) => iso ? moment(iso).format('DD.MM.YY HH:mm') : 'N/A';
const cc = (v) => v >= 0 ? 'text-green' : 'text-red';

// ========== LIVE CLOCK ==========
function updateClock() {
    const now = new Date();
    const gmt = now.toUTCString().slice(17, 25);
    const el = document.getElementById('sys-clock');
    if (el) el.textContent = gmt + ' GMT';
}

// ========== EXECUTION LOG ==========
function addLogEntry(asset, signal, pnl, action, source, customTime) {
    const time = customTime ? fmtTime(customTime) : moment().format('HH:mm:ss');
    const entry = { time, asset, signal, pnl, action, source: source || 'AI' };
    executionLog.unshift(entry);
    if (executionLog.length > MAX_LOG_ENTRIES) executionLog.pop();
    renderExecutionLog();
}

function renderExecutionLog() {
    const container = document.getElementById('exec-log');
    if (!container) return;

    if (executionLog.length === 0) {
        container.innerHTML = '<div class="log-entry"><span class="log-time">[--:--:--]</span><span class="log-action">:: Awaiting system initialization...</span></div>';
        return;
    }

    container.innerHTML = executionLog.map(e => {
        const sigClass = e.signal === 'BUY' ? 'buy' : (e.signal === 'SELL' ? 'sell' : '');
        const pnlClass = e.pnl !== undefined && e.pnl !== null ? (e.pnl >= 0 ? 'log-pnl-pos' : 'log-pnl-neg') : '';
        const pnlText = e.pnl !== undefined && e.pnl !== null ? `[P&L: ${fmtPct(e.pnl)}]` : '';

        return `<div class="log-entry">` +
            `<span class="log-time">[${e.time}]</span>` +
            `<span class="log-asset">${e.asset || '--'}</span>` +
            `<span class="log-signal ${sigClass}">[${e.signal || 'INFO'}]</span>` +
            (pnlText ? `<span class="${pnlClass}">${pnlText}</span>` : '') +
            `<span class="log-action">:: ${e.action || ''}</span>` +
            `</div>`;
    }).join('');
}

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

// ========== CHART INIT — No fills, thin lines ==========
const initChart = () => {
    const ctx = document.getElementById('performanceChart').getContext('2d');

    performanceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Portfolio Equity',
                data: [],
                borderColor: '#FF6A00',
                backgroundColor: 'transparent',
                borderWidth: 1.5,
                pointRadius: 0,
                pointHoverRadius: 3,
                pointHoverBackgroundColor: '#FF6A00',
                pointHoverBorderColor: '#FF6A00',
                fill: false,
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: '#111111',
                    titleColor: '#888888',
                    bodyColor: '#e8e8e8',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    titleFont: { family: "'JetBrains Mono', monospace", size: 10 },
                    bodyFont: { family: "'JetBrains Mono', monospace", size: 11, weight: '700' },
                    padding: 8,
                    cornerRadius: 0,
                    displayColors: false,
                    callbacks: {
                        label: (c) => fmt(c.parsed.y)
                    }
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: { unit: 'minute', displayFormats: { minute: 'HH:mm' } },
                    grid: { display: false },
                    ticks: {
                        color: '#555555',
                        font: { family: "'JetBrains Mono', monospace", size: 9 },
                        maxRotation: 0
                    },
                    border: { color: 'rgba(255,255,255,0.06)' }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.03)', lineWidth: 1 },
                    ticks: {
                        color: '#555555',
                        font: { family: "'JetBrains Mono', monospace", size: 9 },
                        callback: (v) => '$' + v.toLocaleString()
                    },
                    border: { color: 'rgba(255,255,255,0.06)' }
                }
            },
            interaction: { mode: 'nearest', axis: 'x', intersect: false }
        }
    });
};

// ========== SYSTEM BAR TICKER ==========
function updateSystemBarTicker(markets) {
    const container = document.getElementById('sys-ticker');
    if (!container || !markets || markets.length === 0) return;

    container.innerHTML = markets.slice(0, 6).map(m => {
        const color = m.change >= 0 ? 'var(--terminal-green)' : 'var(--terminal-red)';
        return `<span class="ticker-item-inline">` +
            `<span class="sym">${m.symbol}</span>` +
            `<span style="color:${color};font-weight:600;">${fmtPct(m.change)}</span>` +
            `</span>`;
    }).join('');
}

// ========== DASHBOARD UPDATES ==========
const updatePortfolio = async () => {
    try {
        const { data } = await axios.get('/api/portfolio');
        document.getElementById('total-equity').innerText = fmt(data.total_equity);
        document.getElementById('unrealized-pnl').innerText = fmt(data.unrealized_pnl);
        document.getElementById('unrealized-pnl').className = `value calc-font ${cc(data.unrealized_pnl)}`;
        document.getElementById('open-positions').innerText = `${data.positions.length} OPEN`;
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

        // Positions table
        const tbody = document.getElementById('positions-table-body');
        tbody.innerHTML = '';
        if (data.positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No open positions</td></tr>';
        } else {
            data.positions.forEach(p => {
                const tr = document.createElement('tr');
                const pnlColor = p.unrealized_pnl >= 0 ? 'text-green' : 'text-red';
                tr.innerHTML = `<td style="font-weight:700;">${p.asset}</td>` +
                    `<td><span class="badge ${p.type === 'BUY' ? 'long' : 'short'}">${p.type}</span></td>` +
                    `<td>${p.qty.toFixed(4)}</td>` +
                    `<td>${fmt(p.entry_price)}</td>` +
                    `<td>${fmt(p.current_price)}</td>` +
                    `<td style="color:var(--text-tertiary)">${fmt(p.stop_loss)} / ${fmt(p.take_profit)}</td>` +
                    `<td class="${pnlColor}" style="font-weight:700;">${fmt(p.unrealized_pnl)} (${fmtPct(p.unrealized_pnl_percent)})</td>`;
                tbody.appendChild(tr);
            });
        }

        // Build execution log from positions & trades
        if (data.positions.length > 0) {
            data.positions.forEach(p => {
                const exists = executionLog.find(e => e.asset === p.asset && e.signal === p.type);
                if (!exists) {
                    addLogEntry(p.asset, p.type, p.unrealized_pnl_percent,
                        `${p.type} ${p.qty.toFixed(2)} @ ${fmt(p.entry_price)} | Current: ${fmt(p.current_price)}`, 'AI', p.entry_time);
                }
            });
        }

        updateLastSync(true);
    } catch (e) {
        console.error("Portfolio error:", e);
        updateLastSync(false);
    }
};

const updateTrades = async () => {
    try {
        const { data: trades } = await axios.get('/api/trades');
        const tbody = document.getElementById('trades-table-body');
        tbody.innerHTML = '';
        if (trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No recent trades</td></tr>';
            return;
        }
        trades.slice(0, 10).forEach(t => {
            const tr = document.createElement('tr');
            const pnlColor = t.pnl >= 0 ? 'text-green' : 'text-red';
            tr.innerHTML = `<td style="color:var(--text-tertiary)">${t.id.split('_')[1]}</td>` +
                `<td style="font-weight:700;">${t.asset}</td>` +
                `<td><span class="badge ${t.type === 'BUY' ? 'long' : 'short'}">${t.type}</span></td>` +
                `<td style="color:var(--text-tertiary)">${fmtTime(t.entry_time)}</td>` +
                `<td class="${pnlColor}" style="font-weight:700;">${fmt(t.pnl)}</td>`;
            tbody.appendChild(tr);
        });

        // Add closed trades to execution log
        trades.slice(0, 5).forEach(t => {
            const exists = executionLog.find(e => e.asset === t.asset && e.action && e.action.includes('CLOSED'));
            if (!exists) {
                addLogEntry(t.asset, t.type === 'BUY' ? 'SELL' : 'BUY', t.pnl_percent,
                    `CLOSED ${t.asset} | Entry: ${fmt(t.entry_price)} → Exit: ${fmt(t.exit_price)}`, 'EXEC', t.exit_time);
            }
        });
    } catch (e) { console.error("Trades error:", e); }
};

const updateMarket = async () => {
    try {
        const { data: markets } = await axios.get('/api/market-info');
        const c = document.getElementById('market-ticker');
        c.innerHTML = '';

        if (markets.length === 0) {
            c.innerHTML = '<div class="text-center p-3 text-muted">No market data</div>';
            return;
        }

        markets.forEach(m => {
            const d = document.createElement('div');
            d.className = 'ticker-item';
            const changeColor = m.change >= 0 ? 'var(--terminal-green)' : 'var(--terminal-red)';
            d.innerHTML = `<div><span class="ticker-symbol">${m.symbol}</span><span class="ticker-name">${m.name}</span></div>` +
                `<div style="text-align:right"><div class="ticker-price">${fmt(m.price)}</div>` +
                `<div style="color:${changeColor};font-size:0.72rem;font-weight:600;">${fmtPct(m.change)}</div></div>`;
            c.appendChild(d);
        });

        updateSystemBarTicker(markets);
    } catch (e) { console.error("Market error:", e); }
};

const updateSignals = async () => {
    try {
        const { data: signals } = await axios.get('/api/signals');
        const tbody = document.getElementById('signals-table-body');
        tbody.innerHTML = '';
        if (!signals || signals.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No strong signals</td></tr>';
            return;
        }
        signals.forEach(s => {
            const tr = document.createElement('tr');
            const bc = s.signal === 'BUY' ? 'badge long' : (s.signal === 'SELL' ? 'badge short' : 'badge neutral');
            const confPct = (s.confidence * 100).toFixed(0);
            tr.innerHTML = `<td style="font-weight:700;">${s.asset}</td>` +
                `<td><span class="${bc}">${s.signal}</span></td>` +
                `<td>${confPct}%</td>` +
                `<td>${s.risk_reward ? s.risk_reward.toFixed(2) : '--'}</td>`;
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

        // Performance
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
                const pnlColor = p.unrealized_pnl >= 0 ? 'text-green' : 'text-red';
                tr.innerHTML = `<td style="font-weight:700;">${p.asset}</td>` +
                    `<td><span class="badge ${p.type === 'BUY' ? 'long' : 'short'}">${p.type}</span></td>` +
                    `<td>${p.qty.toFixed(4)}</td>` +
                    `<td>${fmt(p.entry_price)}</td>` +
                    `<td>${fmt(p.current_price)}</td>` +
                    `<td style="color:var(--terminal-yellow)">${fmt(p.stop_loss)}</td>` +
                    `<td style="color:var(--terminal-green)">${fmt(p.take_profit)}</td>` +
                    `<td class="${pnlColor}" style="font-weight:700;">${fmt(p.unrealized_pnl)}</td>` +
                    `<td class="${pnlColor}" style="font-weight:700;">${fmtPct(p.unrealized_pnl_percent)}</td>`;
                tbody.appendChild(tr);
            });
        }

        initAllocationChart(data);
    } catch (e) { console.error("Portfolio page error:", e); }
};

function initAllocationChart(data) {
    const ctx = document.getElementById('allocationChart').getContext('2d');
    if (allocationChart) allocationChart.destroy();
    const labels = ['Cash'];
    const values = [data.balance];
    const colors = ['rgba(255,106,0,0.6)'];
    const borderColors = ['#FF6A00'];
    const palette = [
        'rgba(0,230,118,0.4)', 'rgba(255,23,68,0.4)', 'rgba(255,214,0,0.4)',
        'rgba(0,229,255,0.4)', 'rgba(255,255,255,0.15)'
    ];
    const borderPalette = ['#00E676', '#FF1744', '#FFD600', '#00E5FF', '#888888'];

    data.positions.forEach((p, i) => {
        labels.push(p.asset);
        values.push(p.qty * p.current_price);
        colors.push(palette[i % palette.length]);
        borderColors.push(borderPalette[i % borderPalette.length]);
    });

    allocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderColor: borderColors,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#888888',
                        padding: 12,
                        font: { family: "'JetBrains Mono', monospace", size: 10 },
                        boxWidth: 8,
                        boxHeight: 8,
                        usePointStyle: false
                    }
                },
                tooltip: {
                    backgroundColor: '#111111',
                    titleColor: '#888888',
                    bodyColor: '#e8e8e8',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    cornerRadius: 0,
                    titleFont: { family: "'JetBrains Mono', monospace", size: 10 },
                    bodyFont: { family: "'JetBrains Mono', monospace", size: 11, weight: '700' },
                    callbacks: {
                        label: (c) => ` ${c.label}: ${fmt(c.parsed)}`
                    }
                }
            }
        }
    });
}

// ========== AI SIGNALS PAGE ==========
const loadDetailedSignals = async () => {
    const container = document.getElementById('detailed-signals-container');
    container.innerHTML = '<div class="text-center p-3" style="border:1px solid var(--border-default);background:var(--bg-panel);"><i class="bi bi-arrow-repeat spin" style="font-size:1.2rem;color:var(--accent)"></i><p style="margin-top:8px;font-family:var(--font-mono);font-size:0.78rem;color:var(--text-tertiary)">LLM pipeline executing... This may take up to 2 minutes.</p></div>';

    addLogEntry('SYSTEM', 'INFO', null, 'LLM signal pipeline initiated — analyzing markets & news...', 'SYS');

    try {
        const { data: signals } = await axios.get('/api/signals/detailed', { timeout: 180000 });
        container.innerHTML = '';
        if (!signals || signals.length === 0) {
            container.innerHTML = '<div class="text-center text-muted p-3" style="border:1px solid var(--border-default);background:var(--bg-panel);">No signals available</div>';
            return;
        }
        signals.forEach(s => container.appendChild(buildSignalCard(s)));

        addLogEntry('SYSTEM', 'INFO', null, `Signal pipeline complete — ${signals.length} assets analyzed`, 'SYS');
    } catch (e) {
        console.error("Detailed signals error:", e);
        container.innerHTML = '<div class="text-center p-3" style="border:1px solid var(--border-default);background:var(--bg-panel);color:var(--terminal-red);"><i class="bi bi-exclamation-triangle"></i> Signal pipeline error. Retry analysis.</div>';
        addLogEntry('SYSTEM', 'ERROR', null, 'Signal pipeline failed — check LLM connectivity', 'SYS');
    }
};

function buildSignalCard(s) {
    const card = document.createElement('div');
    const isHold = s.signal === 'HOLD' || s.confidence === 0;
    const sigClass = s.signal === 'BUY' ? 'signal-buy' : s.signal === 'SELL' ? 'signal-sell' : 'signal-hold';
    const badgeClass = s.signal === 'BUY' ? 'long' : s.signal === 'SELL' ? 'short' : 'neutral';
    const confPct = (s.confidence * 100).toFixed(0);
    const confColor = s.confidence > 0.7 ? 'var(--terminal-green)' : s.confidence > 0.5 ? 'var(--terminal-yellow)' : 'var(--text-tertiary)';
    card.className = `signal-card ${sigClass}`;

    let newsHtml = '<div style="font-size:0.72rem;color:var(--text-tertiary);padding:4px 0;font-family:var(--font-mono)">No news data available. Configure FINNHUB_API_KEY in .env</div>';
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
                    <span style="font-size:0.65rem;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:0.08em">CONF</span>
                    <div class="confidence-bar"><div class="confidence-bar-fill" style="width:${confPct}%;background:${confColor}"></div></div>
                    <span class="confidence-label" style="color:${confColor}">${confPct}%</span>
                </div>
            </div>
        </div>
        <div class="signal-card-body">
            <div class="signal-details">
                <div class="signal-detail-row"><span class="label">${isHold ? 'CURRENT PRICE' : 'ENTRY PRICE'}</span><span class="value">${s.entry_price ? fmt(s.entry_price) : '--'}</span></div>
                ${!isHold ? `<div class="signal-detail-row"><span class="label">STOP LOSS</span><span class="value text-danger">${s.stop_loss ? fmt(s.stop_loss) : '--'}</span></div>
                <div class="signal-detail-row"><span class="label">TAKE PROFIT</span><span class="value text-success">${s.take_profit ? fmt(s.take_profit) : '--'}</span></div>
                <div class="signal-detail-row"><span class="label">RISK/REWARD</span><span class="value">${s.risk_reward ? s.risk_reward.toFixed(2) + ':1' : '--'}</span></div>` : ''}
                ${s.reason ? `<div class="signal-reason">${s.reason}</div>` : ''}
            </div>
            <div class="signal-news">
                <div class="signal-news-title"><i class="bi bi-newspaper"></i> NEWS FEED</div>
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
        document.getElementById('hist-total').innerText = `${trades.length} TRADES`;
        document.getElementById('hist-wins').innerText = `${wins} WINS`;
        document.getElementById('hist-losses').innerText = `${losses} LOSSES`;

        const tbody = document.getElementById('history-table-body');
        tbody.innerHTML = '';
        if (trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">No trades yet</td></tr>';
            return;
        }
        trades.forEach(t => {
            const tr = document.createElement('tr');
            const pnlColor = t.pnl >= 0 ? 'text-green' : 'text-red';
            tr.innerHTML = `<td style="color:var(--text-tertiary)">${t.id}</td>` +
                `<td style="font-weight:700;">${t.asset}</td>` +
                `<td><span class="badge ${t.type === 'BUY' ? 'long' : 'short'}">${t.type}</span></td>` +
                `<td>${fmt(t.entry_price)}</td>` +
                `<td>${t.exit_price ? fmt(t.exit_price) : '--'}</td>` +
                `<td style="color:var(--text-tertiary)">${fmtDate(t.entry_time)}</td>` +
                `<td style="color:var(--text-tertiary)">${fmtDate(t.exit_time)}</td>` +
                `<td class="${pnlColor}" style="font-weight:700;">${fmt(t.pnl)}</td>` +
                `<td class="${pnlColor}" style="font-weight:700;">${fmtPct(t.pnl_percent)}</td>`;
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
    const colors = values.map(v => v >= 0 ? 'rgba(0,230,118,0.6)' : 'rgba(255,23,68,0.6)');
    const borderColors = values.map(v => v >= 0 ? '#00E676' : '#FF1744');

    pnlChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'P&L',
                data: values,
                backgroundColor: colors,
                borderColor: borderColors,
                borderWidth: 1,
                borderRadius: 0,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#111111',
                    titleColor: '#888888',
                    bodyColor: '#e8e8e8',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    cornerRadius: 0,
                    titleFont: { family: "'JetBrains Mono', monospace", size: 10 },
                    bodyFont: { family: "'JetBrains Mono', monospace", size: 11, weight: '700' },
                    callbacks: { label: (c) => fmt(c.parsed.y) }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        color: '#555555',
                        font: { family: "'JetBrains Mono', monospace", size: 9 }
                    },
                    border: { color: 'rgba(255,255,255,0.06)' }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.03)', lineWidth: 1 },
                    ticks: {
                        color: '#555555',
                        font: { family: "'JetBrains Mono', monospace", size: 9 },
                        callback: (v) => '$' + v
                    },
                    border: { color: 'rgba(255,255,255,0.06)' }
                }
            }
        }
    });
}

// ========== HEALTH & SYNC ==========
const updateLastSync = (online) => {
    const ind = document.getElementById('health-indicator');
    const upd = document.getElementById('last-update');
    const ping = document.querySelector('.ping');
    const sysDot = document.getElementById('sys-status-dot');
    const sysText = document.getElementById('sys-status-text');

    if (online) {
        if (ind) { ind.innerText = 'SYSTEM ONLINE'; ind.style.color = ''; }
        if (ping) { ping.style.background = 'var(--terminal-green)'; }
        if (sysDot) { sysDot.className = 'status-dot active'; }
        if (sysText) { sysText.textContent = 'SYSTEM ACTIVE'; sysText.style.color = 'var(--terminal-green)'; }
    } else {
        if (ind) { ind.innerText = 'SYSTEM OFFLINE'; ind.style.color = 'var(--terminal-red)'; }
        if (ping) { ping.style.background = 'var(--terminal-red)'; }
        if (sysDot) { sysDot.className = 'status-dot inactive'; }
        if (sysText) { sysText.textContent = 'SYSTEM OFFLINE'; sysText.style.color = 'var(--terminal-red)'; }
    }
    if (upd) upd.innerText = `LAST SYNC: ${moment().format('HH:mm:ss')}`;
};

const updateAutoTradeButton = (enabled) => {
    autoTradeState = enabled;
    const btn = document.getElementById('btn-autotrade');
    const sysIndicator = document.getElementById('sys-auto-trade-indicator');

    if (enabled) {
        if (btn) {
            btn.className = 'btn btn-danger';
            btn.innerHTML = '<i class="bi bi-stop-fill"></i> AUTO-TRADE: ON';
        }
        if (sysIndicator) {
            sysIndicator.innerHTML = 'AUTO: <span style="color:var(--terminal-green);font-weight:600;">ON</span>';
        }
    } else {
        if (btn) {
            btn.className = 'btn btn-primary';
            btn.innerHTML = '<i class="bi bi-play-fill"></i> AUTO-TRADE: OFF';
        }
        if (sysIndicator) {
            sysIndicator.innerHTML = 'AUTO: <span style="color:var(--text-tertiary)">OFF</span>';
        }
    }
};

const toggleAutoTrade = async () => {
    try {
        const { data } = await axios.post('/api/autotrade/toggle');
        updateAutoTradeButton(data.enabled);
        addLogEntry('SYSTEM', 'INFO', null,
            `Auto-Trade ${data.enabled ? 'ACTIVATED' : 'DEACTIVATED'}`, 'SYS');
    } catch (e) { console.error("Autotrade error:", e); }
};

const checkStatus = async () => {
    try {
        const { data } = await axios.get('/api/health');
        updateLastSync(data.status === 'online');
        updateAutoTradeButton(data.auto_trade);

        // Update Alpaca status in system bar
        const alpacaEl = document.getElementById('sys-alpaca-status');
        if (alpacaEl) {
            if (data.alpaca_connected) {
                alpacaEl.innerHTML = 'ALPACA: <span style="color:var(--terminal-green);font-weight:600;">CONNECTED</span>';
            } else {
                alpacaEl.innerHTML = 'ALPACA: <span style="color:var(--text-tertiary)">DISCONNECTED</span>';
            }
        }
    } catch (e) {
        updateLastSync(false);
    }
};

const refreshAll = () => {
    checkStatus();
    updatePortfolio();
    updateTrades();
    updateMarket();
    updateSignals();
    addLogEntry('SYSTEM', 'INFO', null, 'Dashboard refresh triggered', 'SYS');
};

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

    const dataToShow = filtered.length > 0 ? filtered : fullEquityHistory;

    performanceChart.data.labels = dataToShow.map(i => new Date(i.timestamp));
    performanceChart.data.datasets[0].data = dataToShow.map(i => i.equity);
    performanceChart.options.scales.x.time.unit = timeUnit;
    performanceChart.options.scales.x.time.displayFormats = { [timeUnit]: displayFormat };
    performanceChart.update();

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

    // Live clock
    updateClock();
    setInterval(updateClock, 1000);

    // Initial log entry
    addLogEntry('SYSTEM', 'INFO', null, 'CognitiveTrade terminal initialized', 'SYS');
    addLogEntry('SYSTEM', 'INFO', null, 'Connecting to data feeds...', 'SYS');

    initChart();
    checkStatus();
    refreshAll();

    // Auto-refresh intervals
    setInterval(() => {
        checkStatus();
        updatePortfolio();
        updateTrades();
        updateMarket();
    }, 15000);

    setInterval(updateSignals, 60000);
});
