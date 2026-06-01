const adminState = {
  summary: null,
  products: [],
  orders: [],
  businesses: [],
  users: [],
  analytics: null,
  settings: null,
  nextImage: null,
  orderFilter: "all",
  businessFilter: "all",
  productQuery: ""
};

const $ = selector => document.querySelector(selector);

const inr = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 0
});

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
  const isFormData = options.body instanceof FormData;
  const res = await fetch(path, {
    headers: isFormData ? (options.headers || {}) : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "Request failed");
  return data;
}

function setTheme(theme) {
  document.body.dataset.theme = theme;
  localStorage.setItem("mc_admin_theme", theme);
}

function initTheme() {
  setTheme(localStorage.getItem("mc_admin_theme") || "dark");
  $("#themeToggle").addEventListener("click", () => {
    setTheme(document.body.dataset.theme === "dark" ? "light" : "dark");
  });
}

function setPanel(name) {
  document.querySelectorAll(".side-nav [data-panel]").forEach(button => {
    button.classList.toggle("active", button.dataset.panel === name);
  });
  document.querySelectorAll(".panel").forEach(panel => panel.classList.remove("active"));
  $(`#${name}Panel`).classList.add("active");
  $("#panelTitle").textContent = name[0].toUpperCase() + name.slice(1);
}

function bindNavigation() {
  document.querySelectorAll("[data-panel]").forEach(button => {
    button.addEventListener("click", () => setPanel(button.dataset.panel));
  });
  document.querySelectorAll("[data-panel-jump]").forEach(button => {
    button.addEventListener("click", () => setPanel(button.dataset.panelJump));
  });
}

function renderSummary() {
  const cards = adminState.summary?.cards || {};
  const items = [
    ["Users", cards.users ?? 0],
    ["Products", cards.products ?? 0],
    ["Orders", cards.orders ?? 0],
    ["Pending", cards.pending_approvals ?? cards.pending_orders ?? 0],
    ["Revenue", moneyLabel(cards.approved_revenue || 0)]
  ];
  $("#summaryCards").innerHTML = items.map(([label, value]) => `
    <article class="stat-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `).join("");

  const pending = adminState.orders.filter(order => order.status === "Pending").slice(0, 4);
  $("#pendingOrdersMini").innerHTML = pending.length ? pending.map(order => `
    <div class="mini-row">
      <div>
        <strong>${escapeHtml(order.invoice_number)}</strong>
        <span>${escapeHtml(order.customer.name)} &middot; ${moneyLabel(order.totals.total)}</span>
      </div>
      <span class="status Pending">Pending</span>
    </div>
  `).join("") : `<p class="hint">No pending orders.</p>`;

  const top = (adminState.analytics?.products || []).slice(0, 4);
  $("#topProductsMini").innerHTML = top.length ? top.map(row => `
    <div class="mini-row">
      <div>
        <strong>${escapeHtml(row.name)}</strong>
        <span>${row.units_sold} sold &middot; ${row.views} views</span>
      </div>
      <span>${moneyLabel(row.revenue)}</span>
    </div>
  `).join("") : `<p class="hint">No product signals yet.</p>`;
}

function specsToText(specs = {}) {
  return Object.entries(specs).map(([key, value]) => `${key}: ${value}`).join("\n");
}

function renderProducts() {
  const query = adminState.productQuery.toLowerCase();
  const products = adminState.products.filter(product => {
    const haystack = `${product.name} ${product.sku} ${product.category} ${product.brand} ${product.model}`.toLowerCase();
    return haystack.includes(query);
  });
  $("#productsTable").innerHTML = products.length ? products.map(product => `
    <tr>
      <td>
        <div class="product-cell">
          <img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}" onerror="this.src='/static/images/product-placeholder.webp'">
          <div>
            <strong>${escapeHtml(product.name)}</strong>
            <small>${escapeHtml(product.category || "Microchip")}${product.sample ? " &middot; Sample" : ""}</small>
          </div>
        </div>
      </td>
      <td>${escapeHtml(product.sku || "")}</td>
      <td>${moneyLabel(product.price || 0)}</td>
      <td>${product.stock || 0}</td>
      <td><span class="status ${product.active ? "Approved" : "Rejected"}">${product.active ? "Active" : "Hidden"}</span></td>
      <td>
        <div class="row-actions">
          <button type="button" data-edit-product="${product.id}">Edit</button>
          <button type="button" data-toggle-product="${product.id}">${product.active ? "Hide" : "Show"}</button>
          ${product.sample ? "" : `<button type="button" class="danger-btn" data-delete-product="${product.id}">Delete</button>`}
        </div>
      </td>
    </tr>
  `).join("") : `
    <tr>
      <td colspan="6"><p class="hint">No products yet. Add a product manually or scan a SKU to start inventory.</p></td>
    </tr>
  `;

  if (adminState.nextImage) {
    $("#nextPathBadge").textContent = adminState.nextImage.display_path;
    $("#imageUrlField").value = adminState.nextImage.web_path;
  }
}

function renderOrders() {
  const visible = adminState.orders.filter(order => adminState.orderFilter === "all" || order.status === adminState.orderFilter);
  $("#ordersTable").innerHTML = visible.length ? visible.map(order => `
    <article class="order-card">
      <header>
        <div>
          <strong>${escapeHtml(order.invoice_number)}</strong>
          <span>${escapeHtml(order.customer.name)} &middot; ${escapeHtml(order.customer.email)}</span>
          ${order.business?.order_type === "B2B" ? `<span>${escapeHtml(order.business.company_name || "Business order")}${order.business.gstin ? ` &middot; GSTIN ${escapeHtml(order.business.gstin)}` : ""}</span>` : ""}
        </div>
        <span class="status ${escapeHtml(order.status)}">${escapeHtml(order.status)}</span>
      </header>
      <ul>
        ${order.items.map(item => `<li>${escapeHtml(item.name)} x ${item.quantity} &middot; ${moneyLabel(item.line_total)}</li>`).join("")}
      </ul>
      <div class="mini-row">
        <div>
          <strong>${moneyLabel(order.totals.total)}</strong>
          <span>${escapeHtml(order.payment_method)} &middot; ${escapeHtml(order.payment_status)}</span>
        </div>
        <div class="order-actions">
          <button type="button" data-order-invoice="${order.id}">Invoice</button>
          <button type="button" data-order-status="${order.id}" data-status="Approved">Approve</button>
          <button type="button" class="danger-btn" data-order-status="${order.id}" data-status="Rejected">Reject</button>
        </div>
      </div>
    </article>
  `).join("") : `<p class="hint">No orders in this view.</p>`;
}

function renderBusinesses() {
  const visible = adminState.businesses.filter(b => adminState.businessFilter === "all" || b.status === adminState.businessFilter);
  $("#businessesTable").innerHTML = visible.length ? visible.map(b => `
    <article class="order-card">
      <header>
        <div>
          <strong>${escapeHtml(b.company_name)}</strong>
          <span>${escapeHtml(b.name)} &middot; ${escapeHtml(b.email)}</span>
          <span>GSTIN: ${escapeHtml(b.gstin)} &middot; Phone: ${escapeHtml(b.phone)}</span>
          <span>Address: ${escapeHtml(b.address)}</span>
        </div>
        <span class="status ${escapeHtml(b.status)}">${escapeHtml(b.status)}</span>
      </header>
      <div class="mini-row">
        <div>
        </div>
        <div class="order-actions">
          ${b.status !== 'Approved' ? `<button type="button" data-business-status="${b.id}" data-status="Approved">Approve</button>` : ''}
          ${b.status !== 'Rejected' ? `<button type="button" class="danger-btn" data-business-status="${b.id}" data-status="Rejected">Reject</button>` : ''}
        </div>
      </div>
    </article>
  `).join("") : `<p class="hint">No businesses in this view.</p>`;
}

function renderUsers() {
  const orders = adminState.orders.filter(order => order.status !== "Rejected");
  $("#userCountBadge").textContent = `${orders.length} shipments`;
  $("#usersTable").innerHTML = orders.length ? orders.map(order => {
    const customer = order.customer || {};
    const address = [customer.line1, customer.city, customer.state, customer.pincode].filter(Boolean).join(", ");
    return `
      <article class="order-card">
        <header>
          <div>
            <strong>${escapeHtml(order.invoice_number)}</strong>
            <span>${escapeHtml(customer.name || "Customer")} &middot; ${escapeHtml(customer.phone || customer.email || "")}</span>
            <span>Ship to: ${escapeHtml(address || "Address not provided")}</span>
          </div>
          <span class="status ${escapeHtml(order.status)}">${escapeHtml(order.status)}</span>
        </header>
        <ul>
          ${(order.items || []).map(item => `<li>${escapeHtml(item.name)} - quantity to ship: ${item.quantity}</li>`).join("")}
        </ul>
        <div class="mini-row">
          <span>${escapeHtml(order.payment_method || "")} &middot; ${escapeHtml(order.payment_status || "")}</span>
          <strong>${moneyLabel(order.totals?.total || 0)}</strong>
        </div>
      </article>
    `;
  }).join("") : `<p class="hint">No shipments to track yet.</p>`;
}

function renderAnalytics() {
  const rows = adminState.analytics?.products || [];
  const top = adminState.analytics?.top_product;
  $("#topProductBadge").textContent = top ? `${top.name} - ${moneyLabel(top.revenue)}` : "No sales yet";
  const maxRevenue = Math.max(1, ...rows.map(row => row.revenue || 0));
  $("#analyticsBars").innerHTML = rows.slice(0, 8).map(row => `
    <div class="bar-row">
      <header>
        <strong>${escapeHtml(row.name)}</strong>
        <span>${moneyLabel(row.revenue)} &middot; ${row.units_sold} units</span>
      </header>
      <div class="bar"><span style="width:${Math.max(3, (row.revenue / maxRevenue) * 100)}%"></span></div>
    </div>
  `).join("") || `<p class="hint">Sales bars will appear after approved orders.</p>`;

  $("#analyticsTable").innerHTML = rows.length ? rows.map(row => `
    <tr>
      <td>${escapeHtml(row.name)}${row.sample ? " (sample)" : ""}</td>
      <td>${row.views}</td>
      <td>${row.cart_adds}</td>
      <td>${row.units_sold}</td>
      <td>${row.conversion}%</td>
      <td>${row.interest_score}</td>
    </tr>
  `).join("") : `<tr><td colspan="6"><p class="hint">No product performance data yet.</p></td></tr>`;
}

function renderSettings() {
  const settings = adminState.settings || {};
  const form = $("#settingsForm");
  form.store_name.value = settings.store_name || "Microchip Cart";
  form.support_email.value = settings.support_email || "";
  form.announcement.value = settings.announcement || "";
  [...form.elements].forEach(input => {
    if (!input.name || !input.name.includes(".")) return;
    const [section, field] = input.name.split(".");
    input.value = settings?.[section]?.[field] || "";
  });
}

async function loadSummary() {
  const data = await api("/api/admin/summary");
  adminState.summary = data;
}

async function loadProducts() {
  const data = await api("/api/admin/products");
  adminState.products = data.products;
  adminState.nextImage = data.next_image;
  renderProducts();
}

async function loadOrders() {
  const data = await api("/api/admin/orders");
  adminState.orders = data.orders;
  renderOrders();
  renderUsers();
}

async function loadBusinesses() {
  try {
    const data = await api("/api/admin/businesses");
    adminState.businesses = data.businesses;
    adminState.businessFilter = "all";
    renderBusinesses();
  } catch (e) {
    // Graceful fail if endpoint doesn't exist
  }
}

async function loadUsers() {
  const data = await api("/api/admin/users");
  adminState.users = data.users;
  renderUsers();
}

async function loadAnalytics() {
  const data = await api("/api/admin/analytics");
  adminState.analytics = data.analytics;
  renderAnalytics();
}

async function loadSettings() {
  const data = await api("/api/admin/settings");
  adminState.settings = data.settings;
  renderSettings();
}

async function refreshAll() {
  await Promise.all([loadSummary(), loadProducts(), loadOrders(), loadBusinesses(), loadAnalytics(), loadSettings()]);
  renderSummary();
  renderUsers();
}

function bindProductForm() {
  $("#barcodeLookupBtn")?.addEventListener("click", async () => {
    const input = $("#barcodeInput");
    const code = input.value.trim();
    if (!code) {
      toast("Scan or enter a SKU first");
      input.focus();
      return;
    }
    const button = $("#barcodeLookupBtn");
    button.disabled = true;
    button.textContent = "Scanning...";
    try {
      const data = await api(`/api/admin/products/lookup?code=${encodeURIComponent(code)}`);
      const form = $("#productForm");
      form.sku.value = code;
      if (data.found && data.product) {
        const product = data.product;
        form.name.value = product.name || "";
        form.description.value = product.description || "";
        form.category.value = product.category || "";
        form.brand.value = product.brand || "";
        form.model.value = product.model || "";
        form.sku.value = product.sku || code;
        form.price.value = product.price || "";
        form.stock.value = product.stock || "";
        form.specs.value = specsToText(product.specs || {});
        form.datasheet_url.value = product.datasheet_url || "";
        form.lead_time.value = product.lead_time || "";
        form.warranty.value = product.warranty || "";
        form.image_url.value = product.image_url || "";
        $("#barcodeScanHint").textContent = "Existing product found. Review fields, adjust stock/price, then save if needed.";
        toast("Product fields filled from database");
      } else {
        form.name.focus();
        $("#barcodeScanHint").textContent = "New SKU. Complete the missing product fields manually.";
        toast("New SKU. Complete product details.");
      }
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = "Scan";
    }
  });

  $("#barcodeInput")?.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      $("#barcodeLookupBtn").click();
    }
  });

  $("#nextPathBadge").addEventListener("click", () => {
    if (!adminState.nextImage) return;
    $("#imageUrlField").value = adminState.nextImage.web_path;
    $("#productForm").use_suggested_image.checked = true;
    toast(`Using ${adminState.nextImage.display_path}`);
  });

  $("#productForm").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    try {
      const data = await api("/api/admin/products", {
        method: "POST",
        body: formData
      });
      form.reset();
      adminState.nextImage = data.next_image;
      await Promise.all([loadProducts(), loadSummary(), loadAnalytics()]);
      renderSummary();
      toast("Product added");
    } catch (error) {
      toast(error.message);
    }
  });

  $("#refreshProductsBtn").addEventListener("click", loadProducts);
  $("#inventorySearch").addEventListener("input", event => {
    adminState.productQuery = event.target.value;
    renderProducts();
  });

  $("#productsTable").addEventListener("click", async event => {
    const edit = event.target.closest("[data-edit-product]");
    const toggle = event.target.closest("[data-toggle-product]");
    const del = event.target.closest("[data-delete-product]");
    try {
      if (edit) {
        openEditProduct(edit.dataset.editProduct);
      }
      if (toggle) {
        const product = adminState.products.find(row => row.id === toggle.dataset.toggleProduct);
        await api(`/api/admin/products/${product.id}`, {
          method: "PATCH",
          body: JSON.stringify({ active: !product.active })
        });
        await loadProducts();
        toast(product.active ? "Product hidden" : "Product active");
      }
      if (del) {
        if (!confirm("Delete this product?")) return;
        await api(`/api/admin/products/${del.dataset.deleteProduct}`, { method: "DELETE" });
        await Promise.all([loadProducts(), loadSummary(), loadAnalytics()]);
        renderSummary();
        toast("Product deleted");
      }
    } catch (error) {
      toast(error.message);
    }
  });
}

function openEditProduct(productId) {
  const product = adminState.products.find(row => row.id === productId);
  if (!product) return;
  const form = $("#editProductForm");
  form.id.value = product.id;
  form.name.value = product.name || "";
  form.description.value = product.description || "";
  form.price.value = product.price || 0;
  form.stock.value = product.stock || 0;
  form.category.value = product.category || "";
  form.sku.value = product.sku || "";
  form.brand.value = product.brand || "";
  form.model.value = product.model || "";
  form.datasheet_url.value = product.datasheet_url || "";
  form.lead_time.value = product.lead_time || "";
  form.warranty.value = product.warranty || "";
  form.image_url.value = product.image_url || "";
  form.specs.value = specsToText(product.specs || {});
  form.active.checked = Boolean(product.active);
  $("#editProductModal").showModal();
}

function bindEditProduct() {
  $("#editProductForm").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form).entries());
    body.active = form.active.checked;
    const id = body.id;
    delete body.id;
    try {
      await api(`/api/admin/products/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body)
      });
      $("#editProductModal").close();
      await Promise.all([loadProducts(), loadAnalytics()]);
      renderSummary();
      toast("Product saved");
    } catch (error) {
      toast(error.message);
    }
  });
}

function bindOrders() {
  $("#orderFilter").addEventListener("change", event => {
    adminState.orderFilter = event.target.value;
    renderOrders();
  });
  $("#ordersTable").addEventListener("click", async event => {
    const invoiceButton = event.target.closest("[data-order-invoice]");
    if (invoiceButton) {
      const url = `/admin/orders/${invoiceButton.dataset.orderInvoice}/invoice`;
      const opened = window.open(url, "_blank", "noopener,noreferrer");
      if (!opened) {
        location.href = url;
      }
      return;
    }

    const button = event.target.closest("[data-order-status]");
    if (!button) return;
    const status = button.dataset.status;
    if (button.disabled) return;
    const admin_notes = status === "Rejected" ? (prompt("Rejection reason (optional)", "") || "") : (prompt("Approval note (optional)", "") || "");
    const actionButtons = button.closest(".order-actions")?.querySelectorAll("button") || [];
    actionButtons.forEach(item => item.disabled = true);
    const originalText = button.textContent;
    button.textContent = status === "Approved" ? "Approving..." : "Rejecting...";
    try {
      await api(`/api/admin/orders/${button.dataset.orderStatus}`, {
        method: "PATCH",
        body: JSON.stringify({ status, admin_notes })
      });
      await Promise.all([loadOrders(), loadProducts(), loadSummary(), loadAnalytics()]);
      renderSummary();
      toast(`Order ${status.toLowerCase()}`);
    } catch (error) {
      toast(error.message);
    } finally {
      actionButtons.forEach(item => item.disabled = false);
      button.textContent = originalText;
    }
  });

  const businessFilter = $("#businessFilter");
  if (businessFilter) {
    businessFilter.addEventListener("change", event => {
      adminState.businessFilter = event.target.value;
      renderBusinesses();
    });
  }

  const businessesTable = $("#businessesTable");
  if (businessesTable) {
    businessesTable.addEventListener("click", async event => {
      const button = event.target.closest("[data-business-status]");
      if (!button) return;
      const status = button.dataset.status;
      try {
        await api(`/api/admin/businesses/${button.dataset.businessStatus}`, {
          method: "PATCH",
          body: JSON.stringify({ status })
        });
        await loadBusinesses();
        toast(`Business ${status.toLowerCase()}`);
      } catch (error) {
        toast(error.message);
      }
    });
  }
}

function bindSettings() {
  $("#settingsForm").addEventListener("submit", async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget).entries());
    try {
      const data = await api("/api/admin/settings", {
        method: "PUT",
        body: JSON.stringify(body)
      });
      adminState.settings = data.settings;
      renderSettings();
      toast("Settings saved");
    } catch (error) {
      toast(error.message);
    }
  });
}

function bindLogout() {
  $("#logoutBtn").addEventListener("click", async () => {
    await api("/api/admin/logout", { method: "POST", body: "{}" });
    location.href = "/admin/login";
  });
}

async function init() {
  initTheme();
  bindNavigation();
  bindProductForm();
  bindEditProduct();
  bindOrders();
  bindSettings();
  bindLogout();
  try {
    await refreshAll();
  } catch (error) {
    toast(error.message);
  }
}

init();
