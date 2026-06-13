const ownerState = {
  data: null,
  customerQuery: "",
  businessQuery: "",
  businessStatus: "all",
  businessCity: "",
  businessMinSpend: 0,
  businessSort: "newest",
  orderFilter: "all",
  revenue: null
};

const $ = selector => document.querySelector(selector);
const $$ = selector => Array.from(document.querySelectorAll(selector));
const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

function moneyLabel(value) {
  return `INR ${inr.format(Number(value || 0))}`;
}

function escapeHtml(value = "") {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function toast(message) {
  const el = $("#toast");
  if (!el) return;
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  const data = await res.json();
  if (!data.ok && !data.success) throw new Error(data.error || "Request failed");
  return data;
}

function setTheme(theme) {
  document.body.dataset.theme = theme;
  localStorage.setItem("mc_owner_theme", theme);
}

function initTheme() {
  setTheme(localStorage.getItem("mc_owner_theme") || "dark");
  $("#themeToggle")?.addEventListener("click", () => setTheme(document.body.dataset.theme === "dark" ? "light" : "dark"));
}

function setPanel(name) {
  $$("[data-owner-panel]").forEach(button => button.classList.toggle("active", button.dataset.ownerPanel === name));
  $$(".panel").forEach(panel => panel.classList.remove("active"));
  $(`#owner${name[0].toUpperCase() + name.slice(1)}Panel`)?.classList.add("active");
  $("#ownerPanelTitle").textContent = name === "businesses" ? "Business Distributors" : name[0].toUpperCase() + name.slice(1);
}

function barRows(rows, valueKey = "value", labelKey = "label", formatter = value => value) {
  const max = Math.max(...rows.map(row => Number(row[valueKey] || 0)), 1);
  return rows.map(row => `
    <div class="bar-row">
      <header><span>${escapeHtml(row[labelKey])}</span><strong>${escapeHtml(formatter(row[valueKey]))}</strong></header>
      <div class="bar"><span style="width:${Math.max(3, (Number(row[valueKey] || 0) / max) * 100)}%"></span></div>
    </div>
  `).join("") || `<p class="hint">No data yet.</p>`;
}

function storeControls() {
  const settings = ownerState.data?.settings || {};
  return {
    hero_slides: settings.hero_slides || [],
    trust_badges: settings.trust_badges || [],
    category_chips: settings.category_chips || [],
    hero_metrics: settings.hero_metrics || [],
    announcement: settings.announcement || "",
    announcement_visible: Boolean(settings.announcement_visible)
  };
}

function renderOverview() {
  const cards = ownerState.data.cards || {};
  const items = [["Customers", cards.customers || 0], ["Distributors", cards.business_distributors || 0], ["Orders", cards.orders || 0], ["Revenue", moneyLabel(cards.revenue || 0)], ["Avg order", moneyLabel(cards.average_order || 0)], ["Inventory", moneyLabel(cards.inventory_value || 0)]];
  $("#ownerSummaryCards").innerHTML = items.map(([label, value]) => `<article class="stat-card owner-stat-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
  $("#ownerBusinessSnapshot").innerHTML = [...ownerState.data.businesses].sort((a, b) => (b.spend || 0) - (a.spend || 0)).slice(0, 5).map(user => `<div class="mini-row"><div><strong>${escapeHtml(user.company_name || user.name || "Business account")}</strong><span>${escapeHtml(user.email)} &middot; ${escapeHtml(user.gstin || "GSTIN not added")}</span></div><strong>${moneyLabel(user.spend || 0)}</strong></div>`).join("") || `<p class="hint">No business distributors yet.</p>`;
  $("#ownerCustomerSnapshot").innerHTML = [...ownerState.data.customers].sort((a, b) => (b.spend || 0) - (a.spend || 0)).slice(0, 5).map(user => `<div class="mini-row"><div><strong>${escapeHtml(user.name || "Customer")}</strong><span>${escapeHtml(user.email)} &middot; ${user.orders || 0} order(s)</span></div><strong>${moneyLabel(user.spend || 0)}</strong></div>`).join("") || `<p class="hint">No customers yet.</p>`;
  $("#ownerRecentOrders").innerHTML = ownerState.data.orders.slice(0, 5).map(order => `<div class="mini-row"><div><strong>${escapeHtml(order.invoice_number || order.id)}</strong><span>${escapeHtml(order.customer?.name || "Customer")} &middot; ${escapeHtml(order.payment_method || "")}</span></div><span class="status ${escapeHtml(order.status)}">${escapeHtml(order.status || "Pending")}</span></div>`).join("") || `<p class="hint">No orders yet.</p>`;
  const attention = [["Pending orders", cards.pending_orders || 0], ["Likely cart drop-off", cards.cart_dropoff || 0], ["Low-stock SKUs", ownerState.data.insights.low_stock.length], ["B2B revenue", moneyLabel(cards.b2b_revenue || 0)], ["B2C revenue", moneyLabel(cards.b2c_revenue || 0)]];
  $("#ownerAttentionList").innerHTML = attention.map(([label, value]) => `<div class="mini-row"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span></div>`).join("");
}

function filterRows(rows, query, keys) {
  const clean = query.toLowerCase();
  return rows.filter(row => keys.map(key => row[key] || "").join(" ").toLowerCase().includes(clean));
}

function renderStorefront() {
  const controls = storeControls();
  $("#ownerHeroSlides").innerHTML = controls.hero_slides.map((slide, index) => `
    <form class="owner-edit-card hero-slide-editor" data-slide-id="${escapeHtml(slide.id)}" draggable="true">
      <header><strong>Slide ${index + 1}</strong><div><button type="button" data-move-slide="-1">Up</button><button type="button" data-move-slide="1">Down</button></div></header>
      <div class="form-grid">
        ${["kicker", "title", "description", "cta_label", "cta_link", "product1_name", "product1_price", "product1_badge", "product1_image", "product2_name", "product2_price", "product2_badge", "product2_image"].map(field => `<label>${field.replaceAll("_", " ")}<input name="${field}" value="${escapeHtml(slide[field] || "")}"></label>`).join("")}
      </div>
      <div class="row-actions"><button type="submit">Save slide</button><button type="button" class="danger-btn" data-delete-slide>Delete slide</button></div>
    </form>
  `).join("");
  $("#ownerAnnouncementForm").announcement.value = controls.announcement;
  $("#ownerAnnouncementForm").announcement_visible.checked = controls.announcement_visible;
  $("#ownerTrustBadges").innerHTML = controls.trust_badges.map(badge => `<div class="owner-edit-card" data-trust-id="${escapeHtml(badge.id)}"><div class="form-grid"><label>Icon<input name="icon" value="${escapeHtml(badge.icon || "")}"></label><label>Label<input name="label" value="${escapeHtml(badge.label || "")}"></label><label>Text<input name="text" value="${escapeHtml(badge.text || "")}"></label></div></div>`).join("");
  $("#ownerCategoryChips").innerHTML = controls.category_chips.map(chip => `<div class="owner-edit-card" data-chip-id="${escapeHtml(chip.id)}"><label class="inline-check"><input name="visible" type="checkbox" ${chip.visible !== false ? "checked" : ""}> ${escapeHtml(chip.label)}</label><div class="form-grid"><label>Code<input name="code" value="${escapeHtml(chip.code || "")}"></label><label>Category<input name="category" value="${escapeHtml(chip.category || "")}"></label><label>Label<input name="label" value="${escapeHtml(chip.label || "")}"></label></div></div>`).join("");
  $("#ownerHeroMetrics").innerHTML = controls.hero_metrics.map(metric => `<div class="owner-edit-card" data-metric-id="${escapeHtml(metric.id)}"><div class="form-grid"><label>Strong<input name="strong" value="${escapeHtml(metric.strong || "")}"></label><label>Text<input name="text" value="${escapeHtml(metric.text || "")}"></label></div></div>`).join("");
}

function renderCustomers() {
  const rows = filterRows(ownerState.data.customers, ownerState.customerQuery, ["name", "email", "phone"]);
  $("#ownerCustomersTable").innerHTML = rows.map(user => `
    <tr>
      <td><input type="checkbox" data-customer-select="${escapeHtml(user.id)}"></td>
      <td>${escapeHtml(user.name || "")}</td><td>${escapeHtml(user.email || "")}</td><td>${escapeHtml(user.phone || "")}</td>
      <td>${escapeHtml(user.orders || 0)}</td><td>${moneyLabel(user.spend || 0)}</td><td>${escapeHtml(user.last_login || "-")}</td>
      <td>${user.inactive ? `<span class="status Pending">Inactive</span>` : ""} ${user.banned ? `<span class="status Rejected">Banned</span>` : ""}<small>${escapeHtml(user.signup_ip || "")}</small></td>
      <td><div class="row-actions"><button type="button" data-customer-ban="${escapeHtml(user.id)}" data-banned="${user.banned ? "false" : "true"}">${user.banned ? "Unban" : "Ban"}</button><button type="button" class="danger-btn" data-customer-delete="${escapeHtml(user.id)}">Delete</button></div></td>
    </tr>
  `).join("") || `<tr><td colspan="9">No customers found.</td></tr>`;
}

function visibleBusinesses() {
  let rows = filterRows(ownerState.data.businesses, ownerState.businessQuery, ["name", "email", "phone", "company_name", "gstin", "business_address"]);
  if (ownerState.businessStatus !== "all") rows = rows.filter(row => ownerState.businessStatus === "Flagged" ? row.flagged : (row.approval_status || row.status) === ownerState.businessStatus);
  if (ownerState.businessCity) rows = rows.filter(row => `${row.city_state || ""} ${row.business_address || ""}`.toLowerCase().includes(ownerState.businessCity.toLowerCase()));
  if (ownerState.businessMinSpend) rows = rows.filter(row => Number(row.spend || 0) >= Number(ownerState.businessMinSpend));
  rows.sort((a, b) => ownerState.businessSort === "oldest" ? String(a.created_at).localeCompare(String(b.created_at)) : ownerState.businessSort === "spend" ? (b.spend || 0) - (a.spend || 0) : ownerState.businessSort === "orders" ? (b.orders || 0) - (a.orders || 0) : String(b.created_at).localeCompare(String(a.created_at)));
  return rows;
}

function renderBusinesses() {
  const rows = visibleBusinesses();
  $("#ownerBusinessesTable").innerHTML = rows.map(user => `
    <tr>
      <td><input type="checkbox" data-business-select="${escapeHtml(user.id)}"></td>
      <td><strong>${escapeHtml(user.company_name || "Business account")}</strong><small>${escapeHtml(user.name || "")}</small></td>
      <td>${escapeHtml((user.created_at || "").slice(0, 10) || "-")}</td>
      <td>${escapeHtml(Array.isArray(user.city_state) ? user.city_state.join(", ") : user.city_state || "-")}</td>
      <td>${escapeHtml(user.email || "")}<br><small>${escapeHtml(user.phone || "")}</small></td>
      <td>${escapeHtml(user.gstin || "-")}<br><small>${user.gstin_verified ? "Verified format" : "Not verified"}</small></td>
      <td>${escapeHtml(user.orders || 0)}</td><td>${moneyLabel(user.spend || 0)}</td>
      <td><span class="status ${escapeHtml(user.approval_status || user.status || "Pending")}">${escapeHtml(user.approval_status || user.status || "Pending")}</span></td>
      <td>${escapeHtml(user.last_login || "-")}</td><td>${user.flagged ? `<span class="status Rejected">${escapeHtml(user.flag_reason || "Flagged")}</span>` : "-"}</td>
      <td><div class="row-actions">
        <button type="button" data-owner-business-status="${escapeHtml(user.id)}" data-status="Approved">Approve</button>
        <button type="button" data-owner-business-status="${escapeHtml(user.id)}" data-status="Rejected">Reject</button>
        <button type="button" data-owner-business-status="${escapeHtml(user.id)}" data-status="Suspended">Suspend</button>
        <button type="button" data-business-email="${escapeHtml(user.email)}">Email</button>
        <button type="button" data-business-profile="${escapeHtml(user.id)}">View</button>
        <button type="button" class="danger-btn" data-business-delete="${escapeHtml(user.id)}">Delete</button>
      </div></td>
    </tr>
  `).join("") || `<tr><td colspan="12">No business distributors found.</td></tr>`;
  const flagged = ownerState.data.businesses.filter(row => row.flagged);
  $("#ownerFlaggedAccounts").innerHTML = flagged.map(row => `<div class="mini-row"><div><strong>${escapeHtml(row.company_name || row.email)}</strong><span>${escapeHtml(row.flag_reason || "Flagged account")}</span></div><span class="status Rejected">${escapeHtml(row.approval_status || row.status)}</span></div>`).join("") || `<p class="hint">No flagged accounts.</p>`;
}

function renderCommerce() {
  $("#ownerOrderCount").textContent = `${ownerState.data.orders.length} orders`;
  $("#ownerOrderMix").innerHTML = barRows(Object.entries(ownerState.data.insights.status_counts || {}).map(([label, value]) => ({ label, value })));
  const events = ownerState.data.insights.event_counts || {};
  $("#ownerFunnel").innerHTML = barRows([{ label: "Visitors", value: events.view || 0 }, { label: "Signups", value: ownerState.data.cards.customers || 0 }, { label: "Cart adds", value: events.cart_add || 0 }, { label: "First orders", value: ownerState.data.orders.length || 0 }]);
  const visible = ownerState.data.orders.filter(order => ownerState.orderFilter === "all" || order.status === ownerState.orderFilter);
  $("#ownerOrdersList").innerHTML = visible.map(order => `<article class="order-card"><header><div><strong>${escapeHtml(order.invoice_number || order.id)}</strong><span>${escapeHtml(order.customer?.name || "Customer")} &middot; ${escapeHtml(order.customer?.email || "")}</span></div><span class="status ${escapeHtml(order.status)}">${escapeHtml(order.status || "Pending")}</span></header><ul>${(order.items || []).map(item => `<li>${escapeHtml(item.name || "Product")} x ${escapeHtml(item.quantity || 1)} = ${moneyLabel(item.line_total || 0)}</li>`).join("")}</ul><div class="mini-row"><span>${escapeHtml(order.payment_method || "")} &middot; ${escapeHtml(order.payment_status || "")}</span><div class="order-actions"><strong>${moneyLabel(order.totals?.total || 0)}</strong><button type="button" data-owner-order-status="${escapeHtml(order.id)}" data-status="Approved">Approve</button><button type="button" class="danger-btn" data-owner-order-status="${escapeHtml(order.id)}" data-status="Rejected">Reject</button></div></div></article>`).join("") || `<p class="hint">No orders in this view.</p>`;
  renderRevenue();
}

function renderRevenue() {
  if (!ownerState.revenue) return;
  $("#ownerRevenueChart").innerHTML = barRows(ownerState.revenue.revenue || [], "revenue", "date", moneyLabel);
  $("#ownerTopDistributors").innerHTML = (ownerState.revenue.top_distributors || []).map(row => `<div class="mini-row"><div><strong>${escapeHtml(row.company_name || row.email)}</strong><span>${escapeHtml(row.orders || 0)} orders</span></div><strong>${moneyLabel(row.spend || 0)}</strong></div>`).join("") || `<p class="hint">No distributor spend yet.</p>`;
}

function renderProducts() {
  const analyticsById = new Map((ownerState.data.analytics.products || []).map(row => [row.id, row]));
  $("#ownerProductCount").textContent = `${ownerState.data.products.length} products`;
  $("#ownerProductsTable").innerHTML = ownerState.data.products.map(product => {
    const row = analyticsById.get(product.id) || {};
    return `<tr><td class="product-cell"><img src="${escapeHtml(product.image_url)}" alt=""><div><strong>${escapeHtml(product.name)}</strong><small>${escapeHtml(product.sku || product.category || "")}</small></div></td><td>${escapeHtml(product.stock || 0)} ${product.stock <= 0 ? `<span class="status Rejected">0 stock</span>` : ""}</td><td>${escapeHtml(row.views || product.views || 0)}</td><td>${escapeHtml(row.cart_adds || product.cart_adds || 0)}</td><td>${escapeHtml(row.units_sold || 0)}</td><td>${moneyLabel(row.revenue || 0)}</td><td>${escapeHtml(row.conversion || 0)}%</td><td><span class="status ${product.active ? "Approved" : "Rejected"}">${product.active ? "Active" : "Hidden"}</span>${product.featured ? `<span class="status Approved">Featured</span>` : ""}${product.on_sale ? `<span class="status Pending">Sale ${escapeHtml(product.sale_price)}</span>` : ""}</td><td><div class="row-actions"><button type="button" data-owner-product-toggle="${escapeHtml(product.id)}">${product.active ? "Hide" : "Show"}</button><button type="button" data-product-feature="${escapeHtml(product.id)}" data-featured="${product.featured ? "false" : "true"}">${product.featured ? "Unfeature" : "Feature"}</button><button type="button" data-product-sale="${escapeHtml(product.id)}">Sale</button><button type="button" data-product-oos="${escapeHtml(product.id)}">Out label</button></div></td></tr>`;
  }).join("") || `<tr><td colspan="9">No products yet.</td></tr>`;
}

function renderInsights() {
  $("#ownerCategoryBars").innerHTML = barRows(Object.entries(ownerState.data.insights.category_counts || {}).map(([label, value]) => ({ label, value })));
  $("#ownerLowStock").innerHTML = ownerState.data.insights.low_stock.map(product => `<div class="mini-row"><div><strong>${escapeHtml(product.name)}</strong><span>${escapeHtml(product.sku || product.category || "")}</span></div><span class="status Pending">${escapeHtml(product.stock || 0)} left</span></div>`).join("") || `<p class="hint">No low-stock products.</p>`;
  $("#ownerActivityList").innerHTML = ownerState.data.events.map(event => `<div class="mini-row"><div><strong>${escapeHtml(event.type || "activity")}</strong><span>User ${escapeHtml(event.user_id || "guest")} &middot; ${escapeHtml(event.created_at || "")}</span></div><span>${escapeHtml(event.product_id || "store")}</span></div>`).join("") || `<p class="hint">No activity yet.</p>`;
}

function renderSettings() {
  const settings = ownerState.data.settings || {};
  const form = $("#ownerSettingsForm");
  if (!form) return;
  form.store_name.value = settings.store_name || "Microchip Cart";
  form.support_email.value = settings.support_email || "";
  form.announcement.value = settings.announcement || "";
  form.maintenance_mode.checked = Boolean(settings.maintenance_mode);
  form.whitelist_ips.value = settings.whitelist_ips || "";
  form.session_timeout_minutes.value = settings.session_timeout_minutes || "";
  [...form.elements].forEach(input => {
    if (!input.name || !input.name.includes(".")) return;
    const [section, field] = input.name.split(".");
    input.value = settings?.[section]?.[field] || "";
  });
}

function renderAll() {
  renderOverview();
  renderStorefront();
  renderCustomers();
  renderBusinesses();
  renderCommerce();
  renderProducts();
  renderInsights();
  renderSettings();
}

async function reloadOwnerData() {
  ownerState.data = await api("/api/owner/overview");
  await loadRevenue();
  renderAll();
}

async function loadRevenue() {
  const period = $("#ownerRevenuePeriod")?.value || "30d";
  const data = await api(`/api/owner/insights/revenue?period=${encodeURIComponent(period)}`);
  ownerState.revenue = data.data;
}

function selectedBusinesses(flaggedOnly = false) {
  const ids = $$("[data-business-select]:checked").map(input => input.dataset.businessSelect);
  if (ids.length) return ids;
  if (flaggedOnly) return ownerState.data.businesses.filter(row => row.flagged).map(row => row.id);
  return [];
}

async function saveSettingsPatch(patch) {
  const data = await api("/api/owner/settings", { method: "PUT", body: JSON.stringify(patch) });
  ownerState.data.settings = data.settings || data.data;
  renderAll();
}

function collectCards(selector, idAttr) {
  return $$(selector).map((card, index) => {
    const values = { id: card.dataset[idAttr], order: index + 1 };
    card.querySelectorAll("input, textarea").forEach(input => values[input.name] = input.type === "checkbox" ? input.checked : input.value);
    return values;
  });
}

function bindEvents() {
  $$("[data-owner-panel]").forEach(button => button.addEventListener("click", () => setPanel(button.dataset.ownerPanel)));
  $$("[data-owner-jump]").forEach(button => button.addEventListener("click", () => setPanel(button.dataset.ownerJump)));
  $("#ownerCustomerSearch")?.addEventListener("input", event => { ownerState.customerQuery = event.target.value; renderCustomers(); });
  $("#ownerSelectAllCustomers")?.addEventListener("change", event => {
    $$("[data-customer-select]").forEach(input => input.checked = event.target.checked);
  });
  $("#ownerBusinessSearch")?.addEventListener("input", event => { ownerState.businessQuery = event.target.value; renderBusinesses(); });
  $("#ownerSelectAllBusinesses")?.addEventListener("change", event => {
    $$("[data-business-select]").forEach(input => input.checked = event.target.checked);
  });
  $("#ownerBusinessStatusFilter")?.addEventListener("change", event => { ownerState.businessStatus = event.target.value; renderBusinesses(); });
  $("#ownerBusinessCityFilter")?.addEventListener("input", event => { ownerState.businessCity = event.target.value; renderBusinesses(); });
  $("#ownerBusinessMinSpend")?.addEventListener("input", event => { ownerState.businessMinSpend = event.target.value; renderBusinesses(); });
  $("#ownerBusinessSort")?.addEventListener("change", event => { ownerState.businessSort = event.target.value; renderBusinesses(); });
  $("#ownerOrderFilter")?.addEventListener("change", event => { ownerState.orderFilter = event.target.value; renderCommerce(); });
  $("#ownerRevenuePeriod")?.addEventListener("change", async () => { await loadRevenue(); renderRevenue(); });

  $("#ownerHeroSlides")?.addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.target.closest("[data-slide-id]");
    const body = Object.fromEntries(new FormData(form).entries());
    await api(`/api/owner/hero-slides/${form.dataset.slideId}`, { method: "PUT", body: JSON.stringify(body) });
    await reloadOwnerData();
    toast("Slide saved");
  });
  $("#ownerHeroSlides")?.addEventListener("click", async event => {
    const form = event.target.closest("[data-slide-id]");
    if (!form) return;
    if (event.target.closest("[data-delete-slide]") && confirm("Delete this slide?")) {
      await api(`/api/owner/hero-slides/${form.dataset.slideId}`, { method: "DELETE" });
      await reloadOwnerData();
      toast("Slide deleted");
    }
    const mover = event.target.closest("[data-move-slide]");
    if (mover) {
      const cards = $$("#ownerHeroSlides [data-slide-id]");
      const index = cards.indexOf(form);
      const target = index + Number(mover.dataset.moveSlide);
      if (target >= 0 && target < cards.length) {
        const ids = cards.map(card => card.dataset.slideId);
        [ids[index], ids[target]] = [ids[target], ids[index]];
        await api("/api/owner/hero-slides/order", { method: "PUT", body: JSON.stringify({ ids }) });
        await reloadOwnerData();
      }
    }
  });
  $("#ownerAddHeroSlide")?.addEventListener("click", async () => {
    await api("/api/owner/hero-slides", { method: "POST", body: JSON.stringify({ title: "New storefront slide", kicker: "Storefront", cta_label: "Shop now", cta_link: "/products" }) });
    await reloadOwnerData();
  });
  $("#ownerAnnouncementForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    await saveSettingsPatch({ announcement: form.announcement.value, announcement_visible: form.announcement_visible.checked });
    toast("Announcement saved");
  });
  $("#ownerSaveTrust")?.addEventListener("click", async () => { await saveSettingsPatch({ trust_badges: collectCards("#ownerTrustBadges [data-trust-id]", "trustId") }); toast("Trust strip saved"); });
  $("#ownerSaveCategories")?.addEventListener("click", async () => { await saveSettingsPatch({ category_chips: collectCards("#ownerCategoryChips [data-chip-id]", "chipId") }); toast("Categories saved"); });
  $("#ownerSaveMetrics")?.addEventListener("click", async () => { await saveSettingsPatch({ hero_metrics: collectCards("#ownerHeroMetrics [data-metric-id]", "metricId") }); toast("Metrics saved"); });

  $("#ownerCustomersTable")?.addEventListener("click", async event => {
    const ban = event.target.closest("[data-customer-ban]");
    const del = event.target.closest("[data-customer-delete]");
    if (ban) {
      await api(`/api/owner/customers/${ban.dataset.customerBan}`, { method: "PUT", body: JSON.stringify({ banned: ban.dataset.banned === "true" }) });
      await reloadOwnerData();
    }
    if (del && confirm("Delete this customer account?")) {
      await api(`/api/owner/customers/${del.dataset.customerDelete}`, { method: "DELETE" });
      await reloadOwnerData();
    }
  });
  $("#ownerBanSelected")?.addEventListener("click", async () => {
    for (const id of $$("[data-customer-select]:checked").map(input => input.dataset.customerSelect)) {
      await api(`/api/owner/customers/${id}`, { method: "PUT", body: JSON.stringify({ banned: true }) });
    }
    await reloadOwnerData();
  });

  $("#ownerBusinessesTable")?.addEventListener("click", async event => {
    const statusBtn = event.target.closest("[data-owner-business-status]");
    const del = event.target.closest("[data-business-delete]");
    const email = event.target.closest("[data-business-email]");
    const profile = event.target.closest("[data-business-profile]");
    if (statusBtn) {
      const body = { status: statusBtn.dataset.status };
      if (body.status === "Rejected") body.reason = prompt("Rejection reason (optional)", "") || "";
      await api(`/api/admin/businesses/${statusBtn.dataset.ownerBusinessStatus}`, { method: "PUT", body: JSON.stringify(body) });
      await reloadOwnerData();
    }
    if (del && confirm("Delete this distributor account?")) {
      await api(`/api/admin/businesses/${del.dataset.businessDelete}`, { method: "DELETE" });
      await reloadOwnerData();
    }
    if (email) {
      location.href = `mailto:${email.dataset.businessEmail}?subject=${encodeURIComponent("Microchip Cart distributor update")}`;
    }
    if (profile) {
      const row = ownerState.data.businesses.find(item => item.id === profile.dataset.businessProfile);
      alert(JSON.stringify(row, null, 2));
    }
  });
  const bulk = async action => {
    const ids = selectedBusinesses(action === "delete");
    if (!ids.length) return toast("Select at least one distributor");
    if (action === "delete" && !confirm("Delete selected flagged accounts?")) return;
    await api("/api/owner/businesses/bulk-action", { method: "POST", body: JSON.stringify({ ids, action }) });
    await reloadOwnerData();
  };
  $("#ownerBulkSuspend")?.addEventListener("click", () => bulk("suspend"));
  $("#ownerBulkClear")?.addEventListener("click", () => bulk("clear_flag"));
  $("#ownerBulkDelete")?.addEventListener("click", () => bulk("delete"));

  $("#ownerProductsTable")?.addEventListener("click", async event => {
    const toggle = event.target.closest("[data-owner-product-toggle]");
    const feature = event.target.closest("[data-product-feature]");
    const sale = event.target.closest("[data-product-sale]");
    const oos = event.target.closest("[data-product-oos]");
    const id = toggle?.dataset.ownerProductToggle || feature?.dataset.productFeature || sale?.dataset.productSale || oos?.dataset.productOos;
    if (!id) return;
    const product = ownerState.data.products.find(row => row.id === id);
    const patch = {};
    if (toggle) patch.visible = !product.visible;
    if (feature) patch.featured = feature.dataset.featured === "true";
    if (sale) patch.sale_price = prompt("Sale price label", product.sale_price || "") || "";
    if (oos) patch.out_of_stock_label = !product.out_of_stock_label;
    await api(`/api/admin/products/${id}`, { method: "PUT", body: JSON.stringify(patch) });
    await reloadOwnerData();
  });

  $("#ownerSettingsForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget).entries());
    body.maintenance_mode = event.currentTarget.maintenance_mode.checked;
    try {
      const data = await api("/api/admin/settings", { method: "PUT", body: JSON.stringify(body) });
      await saveSettingsPatch({ maintenance_mode: body.maintenance_mode, whitelist_ips: body.whitelist_ips, session_timeout_minutes: body.session_timeout_minutes });
      ownerState.data.settings = { ...ownerState.data.settings, ...(data.settings || {}) };
      renderSettings();
      toast("Company settings saved");
    } catch (error) {
      toast(error.message);
    }
  });
  $("#ownerChangePassword")?.addEventListener("click", async () => {
    try {
      const form = $("#ownerSettingsForm");
      await api("/api/owner/change-password", { method: "POST", body: JSON.stringify({ current_password: form.current_password.value, new_password: form.new_password.value, confirm_password: form.confirm_password.value }) });
    } catch (error) {
      toast(error.message);
    }
  });
  $("#logoutBtn")?.addEventListener("click", async () => {
    await api("/api/owner/logout", { method: "POST", body: "{}" });
    location.href = "/owner/login";
  });
  $("#ownerNotificationBell")?.addEventListener("click", () => $("#ownerNotificationMenu")?.classList.toggle("hidden"));
}

async function loadNotifications() {
  try {
    const data = await api("/api/owner/notifications");
    const payload = data.data || {};
    $("#ownerNotificationCount").textContent = payload.count || 0;
    $("#ownerNotificationMenu").innerHTML = (payload.alerts || []).map(alert => `<button type="button" data-owner-jump="${escapeHtml((alert.url || "#overview").split("#")[1] || "overview")}"><strong>${escapeHtml(alert.count)}</strong> ${escapeHtml(alert.label)}<small>${escapeHtml(alert.timestamp || "")}</small></button>`).join("") || `<p class="hint">No alerts.</p>`;
    $("#ownerNotificationMenu").querySelectorAll("[data-owner-jump]").forEach(button => button.addEventListener("click", () => setPanel(button.dataset.ownerJump)));
  } catch (error) {
    $("#ownerNotificationCount").textContent = "!";
  }
}

async function loadSessions() {
  try {
    const data = await api("/api/owner/sessions");
    $("#ownerSessions").innerHTML = (data.data || []).map(row => `<div class="mini-row"><div><strong>${escapeHtml(row.admin)}</strong><span>${escapeHtml(row.ip)} &middot; ${escapeHtml(row.since || "current session")}</span></div><span>${row.current ? "Current" : ""}</span></div>`).join("");
  } catch {
    $("#ownerSessions").innerHTML = `<p class="hint">Sessions unavailable.</p>`;
  }
}

async function init() {
  initTheme();
  bindEvents();
  if (location.hash) setPanel(location.hash.replace("#", ""));
  try {
    await reloadOwnerData();
    await loadNotifications();
    await loadSessions();
    setInterval(loadNotifications, 30000);
  } catch (error) {
    toast(error.message);
  }
}

init();
