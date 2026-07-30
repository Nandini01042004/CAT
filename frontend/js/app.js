/* ─── CAT Smart Rental — Full Application ─── */
const API = "http://localhost:8000";

// ─── State ───
let state = {
    stats: null,
    equipmentPage: 1,
    equipments: [],
    anomalyCount: 0,
};

// ─── Toast ───
function toast(msg, type = "success") {
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}

// ─── Navigation ───
document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", e => {
        e.preventDefault();
        document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
        item.classList.add("active");
        document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
        document.getElementById("view-" + item.dataset.view).classList.add("active");
    });
});

document.getElementById("menuToggle").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("open");
});

// ─── Format ───
function fmtNum(n) {
    if (n === null || n === undefined) return "—";
    return Number(n).toLocaleString("en-US", { maximumFractionDigits: 1 });
}
function fmtMoney(n) {
    if (n === null || n === undefined) return "—";
    return "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ─── API helpers ───
async function apiGet(path) {
    const res = await fetch(API + path);
    if (!res.ok) throw new Error(`GET ${path}: ${res.status}`);
    return res.json();
}
async function apiPost(path, body) {
    const res = await fetch(API + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`POST ${path}: ${res.status}`);
    return res.json();
}

// ─── Dashboard ───
async function loadDashboard() {
    try {
        const d = await apiGet("/api/dashboard/stats");
        state.stats = d.data;
        document.getElementById("statTotal").textContent = d.data.total;
        document.getElementById("statActive").textContent = d.data.checked_in;
        document.getElementById("statOverdue").textContent = d.data.overdue;
        document.getElementById("statEngine").textContent = fmtNum(d.data.total_engine_hours) + "h";
        document.getElementById("statIdle").textContent = fmtNum(d.data.total_idle_hours) + "h";
        document.getElementById("statFuel").textContent = fmtNum(d.data.total_fuel_used) + "L";
        document.getElementById("statCost").textContent = fmtMoney(d.data.total_rental_cost);
        document.getElementById("alertBadge").textContent = d.data.overdue;

        // Charts
        if (d.data.by_type && d.data.by_type.length) {
            renderPie("chartByType", d.data.by_type, "equipment_type", "count", "Equipment by Type");
        }
        if (d.data.by_site && d.data.by_site.length) {
            renderBar("chartBySite", d.data.by_site, "site_id", "count", "Distribution by Site");
        }
    } catch (e) {
        console.error("Dashboard:", e);
    }
}

let chartInstances = {};
function renderPie(canvasId, data, labelKey, valueKey, title) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (chartInstances[canvasId]) chartInstances[canvasId].destroy();
    const colors = ["#FFCC00","#22c55e","#3b82f6","#a855f7","#f97316","#ef4444","#f59e0b","#06b6d4","#ec4899","#14b8a6"];
    chartInstances[canvasId] = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: data.map(d => d[labelKey]),
            datasets: [{
                data: data.map(d => d[valueKey]),
                backgroundColor: colors.slice(0, data.length),
                borderColor: "#1e1e1e",
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: "right", labels: { color: "#9ca3af", boxWidth: 12, padding: 12, font: { size: 11 } } },
            },
        }
    });
}
function renderBar(canvasId, data, labelKey, valueKey, title) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (chartInstances[canvasId]) chartInstances[canvasId].destroy();
    chartInstances[canvasId] = new Chart(ctx, {
        type: "bar",
        data: {
            labels: data.map(d => d[labelKey]),
            datasets: [{
                label: title,
                data: data.map(d => d[valueKey]),
                backgroundColor: "#FFCC00",
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
            },
            scales: {
                x: { ticks: { color: "#9ca3af" }, grid: { color: "#2d2d2d" } },
                y: { ticks: { color: "#9ca3af", precision: 0 }, grid: { color: "#2d2d2d" } },
            }
        }
    });
}

// ─── Chatbot ───
async function sendChat() {
    const input = document.getElementById("chatInput");
    const q = input.value.trim();
    if (!q) return;
    const msgs = document.getElementById("chatMessages");
    msgs.innerHTML += `<div class="chat-msg user"><div class="chat-bubble">${escapeHtml(q)}</div></div>`;
    input.value = "";
    msgs.innerHTML += `<div class="chat-msg bot"><div class="chat-bubble loading">Thinking...</div></div>`;
    msgs.scrollTop = msgs.scrollHeight;

    try {
        const res = await apiGet("/api/chat?q=" + encodeURIComponent(q));
        msgs.querySelector(".chat-msg.bot:last-child").remove();
        let html = `<div class="chat-msg bot"><div class="chat-bubble">${escapeHtml(res.answer)}</div></div>`;
        if (res.data && res.data.length) {
            const sample = res.data.slice(0, 5);
            html += `<div class="chat-msg bot"><div class="chat-bubble" style="font-size:.75rem;background:var(--cat-dark);">`;
            sample.forEach(r => {
                html += `<div>${Object.entries(r).map(([k,v]) => `<b>${k}:</b> ${v ?? "—"}`).join(" | ")}</div>`;
            });
            if (res.data.length > 5) html += `<div style="margin-top:4px;color:var(--cat-text-muted);">… and ${res.data.length - 5} more</div>`;
            html += `</div></div>`;
        }
        msgs.innerHTML += html;
    } catch (e) {
        msgs.querySelector(".chat-msg.bot:last-child").remove();
        msgs.innerHTML += `<div class="chat-msg bot"><div class="chat-bubble" style="color:var(--red);">Error: ${e.message}</div></div>`;
    }
    msgs.scrollTop = msgs.scrollHeight;
}

document.getElementById("chatSend").addEventListener("click", sendChat);
document.getElementById("chatInput").addEventListener("keydown", e => { if (e.key === "Enter") sendChat(); });

function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}

// ─── Equipment List ───
async function loadEquipment(page = 1) {
    try {
        const status = document.getElementById("filterStatus").value;
        const type = document.getElementById("filterType").value;
        const site = document.getElementById("filterSite").value;
        let path = `/api/equipment?page=${page}&per_page=20`;
        if (status) path += `&status=${status}`;
        if (type) path += `&type=${encodeURIComponent(type)}`;
        if (site) path += `&site=${encodeURIComponent(site)}`;
        const res = await apiGet(path);
        state.equipments = res.data;

        const tbody = document.querySelector("#equipmentTable tbody");
        if (!res.data.length) {
            tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--cat-text-muted);">No equipment found</td></tr>`;
            return;
        }
        tbody.innerHTML = res.data.map(eq => `
            <tr>
                <td><strong>${eq.equipment_id}</strong></td>
                <td>${eq.equipment_type}</td>
                <td>${eq.site_id || "—"}</td>
                <td>${eq.operator_id || "—"}</td>
                <td><span class="status-badge-tag ${eq.status}">${eq.status.replace("_", " ")}</span></td>
                <td>${fmtNum(eq.engine_hours)}</td>
                <td>${fmtNum(eq.idle_hours)}</td>
                <td>${fmtNum(eq.fuel_used)}L</td>
                <td>${fmtMoney(eq.rental_cost)}</td>
            </tr>
        `).join("");

        const total = res.total || 0;
        const pages = Math.ceil(total / 20);
        state.equipmentPage = page;
        const pg = document.getElementById("equipmentPagination");
        pg.innerHTML = "";
        if (pages > 1) {
            if (page > 1) pg.innerHTML += `<button onclick="loadEquipment(${page-1})">← Prev</button>`;
            pg.innerHTML += `<span>Page ${page} of ${pages}</span>`;
            if (page < pages) pg.innerHTML += `<button onclick="loadEquipment(${page+1})">Next →</button>`;
        }
    } catch (e) {
        console.error("Equipment:", e);
    }
}

// ─── Load filter options ───
async function loadFilters() {
    try {
        const d = await apiGet("/api/dashboard/stats");
        const types = d.data.by_type || [];
        const sites = d.data.by_site || [];
        const typeSel = document.getElementById("filterType");
        types.forEach(t => {
            typeSel.innerHTML += `<option value="${t.equipment_type}">${t.equipment_type}</option>`;
        });
        const siteSel = document.getElementById("filterSite");
        sites.forEach(s => {
            siteSel.innerHTML += `<option value="${s.site_id}">${s.site_id}</option>`;
        });
    } catch (e) {}
}

// ─── Alerts ───
async function loadAlerts() {
    try {
        const res = await apiGet("/api/alerts");
        const banner = document.getElementById("alertBanner");
        if (res.overdue_count === 0) {
            banner.textContent = "✅ No overdue equipment. All equipment accounted for.";
            banner.style.background = "rgba(34,197,94,.1)";
            banner.style.borderColor = "rgba(34,197,94,.3)";
        } else {
            banner.textContent = `⚠️ ${res.overdue_count} equipment overdue! Total rental cost at risk. Review below.`;
        }
        const tbody = document.querySelector("#alertTable tbody");
        if (!res.overdue.length) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--cat-text-muted);">No overdue equipment</td></tr>`;
            return;
        }
        tbody.innerHTML = res.overdue.map(eq => `
            <tr>
                <td><strong>${eq.equipment_id}</strong></td>
                <td>${eq.equipment_type}</td>
                <td>${eq.site_id || "—"}</td>
                <td>${eq.operator_id || "—"}</td>
                <td>${fmtMoney(eq.rental_cost)}</td>
                <td><span style="color:var(--red);">⚠️ Overdue</span></td>
            </tr>
        `).join("");
    } catch (e) { console.error("Alerts:", e); }
}

// ─── Check In/Out ───
document.getElementById("checkinForm").addEventListener("submit", async e => {
    e.preventDefault();
    try {
        const body = {
            site_id: document.getElementById("cinSiteId").value,
            operator_id: document.getElementById("cinOperatorId").value,
            daily_rental_rate: parseFloat(document.getElementById("cinRate").value) || 500,
        };
        const res = await apiPost("/api/equipment/" + document.getElementById("cinEquipId").value + "/checkin", body);
        toast(res.message);
        loadRecentCheckins();
        loadDashboard();
    } catch (err) { toast(err.message, "error"); }
});

document.getElementById("checkoutForm").addEventListener("submit", async e => {
    e.preventDefault();
    try {
        const res = await apiPost("/api/equipment/" + document.getElementById("coutEquipId").value + "/checkout", {});
        toast(res.message);
        loadRecentCheckins();
        loadDashboard();
    } catch (err) { toast(err.message, "error"); }
});

async function loadRecentCheckins() {
    try {
        const res = await apiGet("/api/alerts");
        const el = document.getElementById("recentCheckins");
        if (!res.latest_checkins || !res.latest_checkins.length) {
            el.innerHTML = "No recent check-ins.";
            return;
        }
        el.innerHTML = res.latest_checkins.slice(0, 5).map(eq => `
            <div style="padding:.5rem 0;border-bottom:1px solid var(--cat-border);display:flex;justify-content:space-between;font-size:.85rem;">
                <span><strong>${eq.equipment_id}</strong> (${eq.equipment_type})</span>
                <span style="color:var(--cat-text-muted);">${eq.site_id} · ${eq.operator_id || "—"}</span>
            </div>
        `).join("");
    } catch (e) { console.error(e); }
}

// ─── Usage ───
async function loadUsageSelect() {
    try {
        const res = await apiGet("/api/equipment?per_page=200");
        const sel = document.getElementById("usageEquipSelect");
        res.data.forEach(eq => {
            sel.innerHTML += `<option value="${eq.equipment_id}">${eq.equipment_id} — ${eq.equipment_type}</option>`;
        });
    } catch (e) {}
}

document.getElementById("loadUsageBtn").addEventListener("click", async () => {
    const eid = document.getElementById("usageEquipSelect").value;
    if (!eid) return toast("Select an equipment", "error");
    try {
        const res = await apiGet(`/api/equipment/${eid}/usage`);
        const logs = res.data || [];
        const tbody = document.querySelector("#usageTable tbody");
        if (!logs.length) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--cat-text-muted);">No usage logs</td></tr>`;
            return;
        }
        tbody.innerHTML = logs.map(log => `
            <tr>
                <td>${new Date(log.date).toLocaleDateString()}</td>
                <td>${fmtNum(log.engine_hours)}h</td>
                <td>${fmtNum(log.idle_hours)}h</td>
                <td>${fmtNum(log.fuel_used)}L</td>
                <td>${log.location_lat || "—"}</td>
                <td>${log.location_lng || "—"}</td>
            </tr>
        `).join("");

        // Chart
        const ctx = document.getElementById("usageChart");
        if (chartInstances["usageChart"]) chartInstances["usageChart"].destroy();
        chartInstances["usageChart"] = new Chart(ctx, {
            type: "line",
            data: {
                labels: logs.map(l => new Date(l.date).toLocaleDateString()).reverse(),
                datasets: [
                    { label: "Engine Hours", data: logs.map(l => l.engine_hours).reverse(), borderColor: "#FFCC00", backgroundColor: "transparent", tension: .3, pointRadius: 3 },
                    { label: "Idle Hours", data: logs.map(l => l.idle_hours).reverse(), borderColor: "#f97316", backgroundColor: "transparent", tension: .3, pointRadius: 3 },
                    { label: "Fuel (L)", data: logs.map(l => l.fuel_used).reverse(), borderColor: "#3b82f6", backgroundColor: "transparent", tension: .3, pointRadius: 3, yAxisID: "y1" },
                ]
            },
            options: {
                responsive: true,
                interaction: { mode: "index", intersect: false },
                plugins: { legend: { labels: { color: "#9ca3af", boxWidth: 12, font: { size: 11 } } } },
                scales: {
                    x: { ticks: { color: "#9ca3af", maxTicksLimit: 10 }, grid: { color: "#2d2d2d" } },
                    y: { ticks: { color: "#9ca3af" }, grid: { color: "#2d2d2d" } },
                    y1: { position: "right", ticks: { color: "#3b82f6" }, grid: { display: false } },
                }
            }
        });
    } catch (e) { toast(e.message, "error"); }
});

// ─── Forecast ───
async function loadForecast() {
    try {
        const res = await apiGet("/api/forecast");
        const preds = res.predictions || [];
        const tbody = document.querySelector("#forecastTable tbody");
        if (!preds.length) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--cat-text-muted);">No forecast data</td></tr>`;
            return;
        }
        tbody.innerHTML = preds.map(p => `
            <tr>
                <td>${p.equipment_type}</td>
                <td>${p.site_id}</td>
                <td>${p.cnt}</td>
                <td><strong>${p.forecast_needed}</strong></td>
                <td><span style="color:var(--cat-yellow);">${p.next_week_demand}</span></td>
            </tr>
        `).join("");

        // Group by type for chart
        const byType = {};
        preds.forEach(p => {
            if (!byType[p.equipment_type]) byType[p.equipment_type] = { current: 0, forecast: 0 };
            byType[p.equipment_type].current += p.cnt;
            byType[p.equipment_type].forecast += p.forecast_needed;
        });
        const labels = Object.keys(byType);
        const ctx = document.getElementById("forecastChart");
        if (chartInstances["forecastChart"]) chartInstances["forecastChart"].destroy();
        chartInstances["forecastChart"] = new Chart(ctx, {
            type: "bar",
            data: {
                labels,
                datasets: [
                    { label: "Current", data: labels.map(l => byType[l].current), backgroundColor: "#6b7280", borderRadius: 4 },
                    { label: "Forecast", data: labels.map(l => byType[l].forecast), backgroundColor: "#FFCC00", borderRadius: 4 },
                ]
            },
            options: {
                responsive: true,
                plugins: { legend: { labels: { color: "#9ca3af", boxWidth: 12, font: { size: 11 } } } },
                scales: {
                    x: { ticks: { color: "#9ca3af" }, grid: { color: "#2d2d2d" } },
                    y: { ticks: { color: "#9ca3af", precision: 0 }, grid: { color: "#2d2d2d" } },
                }
            }
        });
    } catch (e) { console.error("Forecast:", e); }
}

// ─── Anomalies ───
async function loadAnomalies() {
    try {
        const res = await apiGet("/api/anomalies");
        state.anomalyCount = res.count;
        const tbody = document.querySelector("#anomalyTable tbody");
        const statsEl = document.getElementById("anomalyStats");

        const high = res.data.filter(a => a.severity === "high").length;
        const med = res.data.filter(a => a.severity === "medium").length;

        statsEl.innerHTML = `
            <div class="stat-mini"><span class="stat-value" style="color:var(--cat-yellow);">${res.count}</span><span class="stat-label">Total Anomalies</span></div>
            <div class="stat-mini"><span class="stat-value" style="color:var(--red);">${high}</span><span class="stat-label">High Severity</span></div>
            <div class="stat-mini"><span class="stat-value" style="color:var(--orange);">${med}</span><span class="stat-label">Medium Severity</span></div>
        `;

        if (!res.data.length) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--cat-text-muted);">No anomalies detected ✅</td></tr>`;
            return;
        }
        tbody.innerHTML = res.data.map(a => `
            <tr>
                <td><strong>${a.equipment_id}</strong></td>
                <td>${a.type}</td>
                <td>${a.site_id || "—"}</td>
                <td>${a.operator_id || "—"}</td>
                <td><span class="severity-${a.severity}">${a.severity}</span></td>
                <td style="font-size:.8rem;">${a.anomalies.join("; ")}</td>
            </tr>
        `).join("");
    } catch (e) { console.error("Anomalies:", e); }
}

// ─── Global search ───
document.getElementById("globalSearch").addEventListener("keydown", async e => {
    if (e.key === "Enter" && e.target.value.trim()) {
        const q = e.target.value.trim();
        // Navigate to equipment view
        document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
        document.querySelector('[data-view="equipment"]').classList.add("active");
        document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
        document.getElementById("view-equipment").classList.add("active");
        // Filter by ID search
        loadEquipment(1);
    }
});

// ─── Toggle filter reload ───
document.getElementById("filterStatus").addEventListener("change", () => loadEquipment(1));
document.getElementById("filterType").addEventListener("change", () => loadEquipment(1));
document.getElementById("filterSite").addEventListener("change", () => loadEquipment(1));

// ─── Init ───
async function init() {
    loadDashboard();
    loadFilters();
    loadAlerts();
    loadRecentCheckins();
    loadUsageSelect();
    loadForecast();
    loadAnomalies();
    loadEquipment(1);
}

document.addEventListener("DOMContentLoaded", init);
