const ownerState = {
  data: null,
  customerQuery: "",
  businessQuery: "",
  orderFilter: "all"
};

const $ = selector => document.querySelector(selector);
const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

function moneyLabel(value) {
  return `INR ${inr.format(Number(value || 0))}`;
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "Request failed");
  return data;
}

function setTheme(theme) {
  document.body.dataset.theme = theme;
  localStorage.setItem("mc_owner_theme", theme);
}

function initTheme() {
  setTheme(localStorage.getItem("mc_owner_theme") || "dark");
  $("#themeToggle").addEventListener("click", () => {
    setTheme(document.body.dataset.theme === "dark" ? "light" : "dark");
  });
}

function setPanel(name) {
  document.querySelectorAll("[data-owner-panel]").forEach(button => {
    button.classList.toggle("active", button.dataset.ownerPanel === name);
  });
  document.querySelectorAll(".panel").forEach(panel => panel.classList.remove("active"));
  $(`#owner${name[0].toUpperCase() + name.slice(1)}Panel`)?.classList.add("active");
  $("#ownerPanelTitle").textContent = name === "businesses" ? "Business Distributors" : name[0].toUpperCase() + name.slice(1);
}

function barRows(rows, valueKey = "value", labelKey = "label", formatter = value => value) {
  const max = Math.max(...rows.map(row => Number(row[valueKey] || 0)), 1);
  return rows.map(row => `
    <div class="bar-row">
      <header>
        <span>${escapeHtml(row[labelKey])}</span>
        <strong>${escapeHtml(formatter(row[valueKey]))}</strong>
      </header>
      <div class="bar"><span style="width:${Math.max(3, (Number(row[valueKey] || 0) / max) * 100)}%"></span></div>
    </div>
  `).join("") || `<p class="hint">No data yet.</p>`;
}

function renderOverview() {
  const cards = ownerState.data.cards || {};
  const items = [
    ["Customers", cards.customers || 0],
    ["Distributors", cards.business_distributors || 0],
    ["Orders", cards.orders || 0],
    ["Revenue", moneyLabel(cards.revenue || 0)],
    ["Avg order", moneyLabel(cards.average_order || 0)],
    ["Inventory", moneyLabel(cards.inventory_value || 0)]
  ];
  $("#ownerSummaryCards").innerHTML = items.map(([label, value]) => `
    <article class="stat-card owner-stat-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `).join("");

  const topBusinesses = [...ownerState.data.businesses].sort((a, b) => (b.spend || 0) - (a.spend || 0)).slice(0, 5);
  $("#ownerBusinessSnapshot").innerHTML = topBusinesses.map(user => `
    <div class="mini-row">
      <div>
        <strong>${escapeHtml(user.company_name || user.name || "Business account")}</strong>
        <span>${escapeHtml(user.email)} &middot; ${escapeHtml(user.gstin || "GSTIN not added")}</span>
      </div>
      <strong>${moneyLabel(user.spend || 0)}</strong>
    </div>
  `).join("") || `<p class="hint">No business distributors yet.</p>`;

  const topCustomers = [...ownerState.data.customers].sort((a, b) => (b.spend || 0) - (a.spend || 0)).slice(0, 5);
  $("#ownerCustomerSnapshot").innerHTML = topCustomers.map(user => `
    <div class="mini-row">
      <div>
        <strong>${escapeHtml(user.name || "Customer")}</strong>
        <span>${escapeHtml(user.email)} &middot; ${user.orders || 0} order(s)</span>
      </div>
      <strong>${moneyLabel(user.spend || 0)}</strong>
    </div>
  `).join("") || `<p class="hint">No customers yet.</p>`;

  $("#ownerRecentOrders").innerHTML = ownerState.data.orders.slice(0, 5).map(order => `
    <div class="mini-row">
      <div>
        <strong>${escapeHtml(order.invoice_number || order.id)}</strong>
        <span>${escapeHtml(order.customer?.name || "Customer")} &middot; ${escapeHtml(order.payment_method || "")}</span>
      </div>
      <span class="status ${escapeHtml(order.status)}">${escapeHtml(order.status || "Pending")}</span>
    </div>
  `).join("") || `<p class="hint">No orders yet.</p>`;

  const attention = [
    [`Pending orders`, cards.pending_orders || 0],
    [`Likely cart drop-off`, cards.cart_dropoff || 0],
    [`Low-stock SKUs`, ownerState.data.insights.low_stock.length],
    [`B2B revenue`, moneyLabel(cards.b2b_revenue || 0)],
    [`B2C revenue`, moneyLabel(cards.b2c_revenue || 0)]
  ];
  $("#ownerAttentionList").innerHTML = attention.map(([label, value]) => `
    <div class="mini-row">
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(value)}</span>
    </div>
  `).join("");
}

function filterRows(rows, query, keys) {
  const clean = query.toLowerCase();
  return rows.filter(row => keys.map(key => row[key] || "").join(" ").toLowerCase().includes(clean));
}

function renderCustomers() {
  const rows = filterRows(ownerState.data.customers, ownerState.customerQuery, ["name", "email", "phone"]);
  $("#ownerCustomersTable").innerHTML = rows.map(user => `
    <tr>
      <td>${escapeHtml(user.name || "")}</td>
      <td>${escapeHtml(user.email || "")}</td>
      <td>${escapeHtml(user.phone || "")}</td>
      <td>${escapeHtml(user.orders || 0)}</td>
      <td>${moneyLabel(user.spend || 0)}</td>
      <td>${escapeHtml(user.last_login || "-")}</td>
    </tr>
  `).join("") || `<tr><td colspan="6">No customers found.</td></tr>`;
}

function renderBusinesses() {
  const rows = filterRows(ownerState.data.businesses, ownerState.businessQuery, ["name", "email", "phone", "company_name", "gstin"]);
  $("#ownerBusinessesTable").innerHTML = rows.map(user => `
    <tr>
      <td>
        <strong>${escapeHtml(user.company_name || "Business account")}</strong>
        <small>${escapeHtml(user.name || "")}</small>
      </td>
      <td>${escapeHtml(user.email || "")}<br><small>${escapeHtml(user.phone || "")}</small></td>
      <td>${escapeHtml(user.gstin || "-")}</td>
      <td>${escapeHtml(user.orders || 0)}</td>
      <td>${moneyLabel(user.spend || 0)}</td>
      <td>${escapeHtml(user.last_login || "-")}</td>
    </tr>
  `).join("") || `<tr><td colspan="6">No business distributors found.</td></tr>`;
}

function renderCommerce() {
  const statusCounts = ownerState.data.insights.status_counts || {};
  const statusRows = Object.entries(statusCounts).map(([label, value]) => ({ label, value }));
  $("#ownerOrderCount").textContent = `${ownerState.data.orders.length} orders`;
  $("#ownerOrderMix").innerHTML = barRows(statusRows);

  const events = ownerState.data.insights.event_counts || {};
  const funnelRows = [
    { label: "Product views", value: events.view || 0 },
    { label: "Cart adds", value: events.cart_add || 0 },
    { label: "Checkout opens", value: events.checkout_open || 0 },
    { label: "Payment choices", value: events.payment_selected || 0 }
  ];
  $("#ownerFunnel").innerHTML = barRows(funnelRows);

  const visible = ownerState.data.orders.filter(order => ownerState.orderFilter === "all" || order.status === ownerState.orderFilter);
  $("#ownerOrdersList").innerHTML = visible.map(order => `
    <article class="order-card">
      <header>
        <div>
          <strong>${escapeHtml(order.invoice_number || order.id)}</strong>
          <span>${escapeHtml(order.customer?.name || "Customer")} &middot; ${escapeHtml(order.customer?.email || "")}</span>
          <span>${escapeHtml(order.customer?.city || "")} ${escapeHtml(order.customer?.state || "")}</span>
        </div>
        <span class="status ${escapeHtml(order.status)}">${escapeHtml(order.status || "Pending")}</span>
      </header>
      <ul>
        ${(order.items || []).map(item => `<li>${escapeHtml(item.name || "Product")} x ${escapeHtml(item.quantity || 1)} = ${moneyLabel(item.line_total || 0)}</li>`).join("")}
      </ul>
      <div class="mini-row">
        <span>${escapeHtml(order.payment_method || "")} &middot; ${escapeHtml(order.payment_status || "")}</span>
        <strong>${moneyLabel(order.totals?.total || 0)}</strong>
      </div>
    </article>
  `).join("") || `<p class="hint">No orders in this view.</p>`;
}

function renderProducts() {
  const analyticsById = new Map((ownerState.data.analytics.products || []).map(row => [row.id, row]));
  $("#ownerProductCount").textContent = `${ownerState.data.products.length} products`;
  $("#ownerProductsTable").innerHTML = ownerState.data.products.map(product => {
    const row = analyticsById.get(product.id) || {};
    return `
      <tr>
        <td class="product-cell">
          <img src="${escapeHtml(product.image_url)}" alt="">
          <div>
            <strong>${escapeHtml(product.name)}</strong>
            <small>${escapeHtml(product.sku || product.category || "")}</small>
          </div>
        </td>
        <td>${escapeHtml(product.stock || 0)}</td>
        <td>${escapeHtml(row.views || product.views || 0)}</td>
        <td>${escapeHtml(row.cart_adds || product.cart_adds || 0)}</td>
        <td>${escapeHtml(row.units_sold || 0)}</td>
        <td>${moneyLabel(row.revenue || 0)}</td>
        <td>${escapeHtml(row.conversion || 0)}%</td>
      </tr>
    `;
  }).join("") || `<tr><td colspan="7">No products yet.</td></tr>`;
}

function renderInsights() {
  const categoryRows = Object.entries(ownerState.data.insights.category_counts || {}).map(([label, value]) => ({ label, value }));
  $("#ownerCategoryBars").innerHTML = barRows(categoryRows);
  $("#ownerLowStock").innerHTML = ownerState.data.insights.low_stock.map(product => `
    <div class="mini-row">
      <div>
        <strong>${escapeHtml(product.name)}</strong>
        <span>${escapeHtml(product.sku || product.category || "")}</span>
      </div>
      <span class="status Pending">${escapeHtml(product.stock || 0)} left</span>
    </div>
  `).join("") || `<p class="hint">No low-stock products.</p>`;

  $("#ownerActivityList").innerHTML = ownerState.data.events.map(event => `
    <div class="mini-row">
      <div>
        <strong>${escapeHtml(event.type || "activity")}</strong>
        <span>User ${escapeHtml(event.user_id || "guest")} &middot; ${escapeHtml(event.created_at || "")}</span>
      </div>
      <span>${escapeHtml(event.product_id || "store")}</span>
    </div>
  `).join("") || `<p class="hint">No activity yet.</p>`;
}

function renderAll() {
  renderOverview();
  renderCustomers();
  renderBusinesses();
  renderCommerce();
  renderProducts();
  renderInsights();
}

function bindEvents() {
  document.querySelectorAll("[data-owner-panel]").forEach(button => {
    button.addEventListener("click", () => setPanel(button.dataset.ownerPanel));
  });
  document.querySelectorAll("[data-owner-jump]").forEach(button => {
    button.addEventListener("click", () => setPanel(button.dataset.ownerJump));
  });
  $("#ownerCustomerSearch").addEventListener("input", event => {
    ownerState.customerQuery = event.target.value;
    renderCustomers();
  });
  $("#ownerBusinessSearch").addEventListener("input", event => {
    ownerState.businessQuery = event.target.value;
    renderBusinesses();
  });
  $("#ownerOrderFilter").addEventListener("change", event => {
    ownerState.orderFilter = event.target.value;
    renderCommerce();
  });
  $("#logoutBtn").addEventListener("click", async () => {
    await api("/api/owner/logout", { method: "POST", body: "{}" });
    location.href = "/owner/login";
  });
}

async function init() {
  initTheme();
  bindEvents();
  try {
    ownerState.data = await api("/api/owner/overview");
    renderAll();
  } catch (error) {
    toast(error.message);
  }
}

init();
