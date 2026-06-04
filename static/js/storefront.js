function readStoredJson(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback));
    return Array.isArray(fallback) ? (Array.isArray(value) ? value : fallback) : (value && typeof value === "object" ? value : fallback);
  } catch (error) {
    localStorage.removeItem(key);
    return fallback;
  }
}

const state = {
  products: [],
  currentUser: null,
  cart: readStoredJson("mc_cart", []),
  wishlist: readStoredJson("mc_wishlist", []),
  communityReviews: readStoredJson("mc_community_reviews", []),
  communityPosts: [],
  searchHistory: readStoredJson("mc_search_history", []),
  category: "All",
  query: "",
  sort: "featured",
  authMode: "B2C",
  authToken: localStorage.getItem("mc_auth_token") || "",
  currentLocation: localStorage.getItem("mc_location") || "India",
  currentLocationDetails: null,
  searchIndex: -1,
  pendingAuthAction: null,
  config: null,
};

const els = {
  grid: document.querySelector("#productGrid"),
  categoryFilters: document.querySelector("#categoryFilters"),
  sort: document.querySelector("#sortSelect"),
  search: document.querySelector("#searchInput"),
  searchMobile: document.querySelector("#searchInputMobile"),
  searchSuggestions: document.querySelector("#searchSuggestions"),
  searchSuggestionsMobile: document.querySelector("#searchSuggestionsMobile"),
  locationBtn: document.querySelector("#locationBtn"),
  locationModal: document.querySelector("#locationModal"),
  locationForm: document.querySelector("#locationForm"),
  currentLocationLabel: document.querySelector("#currentLocationLabel"),
  cartDropdownItems: document.querySelector("#cartDropdownItems"),
  wishlistDropdownItems: document.querySelector("#wishlistDropdownItems"),
  miniCartSubtotal: document.querySelector("#miniCartSubtotal"),
  miniCartViewBtn: document.querySelector("#miniCartViewBtn"),
  miniCartCheckoutBtn: document.querySelector("#miniCartCheckoutBtn"),
  wishlistDropdownViewAll: document.querySelector("#wishlistDropdownViewAll"),
  searchCategorySelectDesktop: document.querySelector("#searchCategorySelectDesktop"),
  popularHeroPanel: document.querySelector("#popularHeroPanel"),
  communityPostForm: document.querySelector("#communityPostForm"),
  communityPostsList: document.querySelector("#communityPostsList"),
  communityCategories: document.querySelector("#communityCategories"),
  startPostBtn: document.querySelector("#startPostBtn"),
  postFormCard: document.querySelector("#postFormCard"),
  closePostFormBtn: document.querySelector("#closePostFormBtn"),
  postAuthorName: document.querySelector("#postAuthorName"),
  postLoginNotice: document.querySelector("#postLoginNotice"),
  previewAuthorInitial: document.querySelector("#previewAuthorInitial"),
  previewAuthorName: document.querySelector("#previewAuthorName"),
  previewCategory: document.querySelector("#previewCategory"),
  previewTitle: document.querySelector("#previewTitle"),
  previewContent: document.querySelector("#previewContent"),
  cartBtn: document.querySelector("#cartBtn"),
  wishlistBtn: document.querySelector("#wishlistBtn"),
  wishlistCount: document.querySelector("#wishlistCount"),
  wishlistModal: document.querySelector("#wishlistModal"),
  wishlistList: document.querySelector("#wishlistList"),
  cartDrawer: document.querySelector("#cartDrawer"),
  cartItems: document.querySelector("#cartItems"),
  cartCount: document.querySelector("#cartCount"),
  cartSubtotal: document.querySelector("#cartSubtotal"),
  cartTax: document.querySelector("#cartTax"),
  cartShipping: document.querySelector("#cartShipping"),
  cartTotal: document.querySelector("#cartTotal"),
  scrim: document.querySelector("#scrim"),
  authBtn: document.querySelector("#authBtn"),
  guestAccountMenu: document.querySelector("#guestAccountMenu"),
  guestAccountDropdown: document.querySelector("#guestAccountDropdown"),
  guestSignupBtn: document.querySelector("#guestSignupBtn"),
  guestLoginBtn: document.querySelector("#guestLoginBtn"),
  guestBusinessBtn: document.querySelector("#guestBusinessBtn"),
  businessAuthBtn: document.querySelector("#businessAuthBtn"),
  authModal: document.querySelector("#authModal"),
  productModal: document.querySelector("#productModal"),
  checkoutModal: document.querySelector("#checkoutModal"),
  ordersModal: document.querySelector("#ordersModal"),
  ordersNavTrigger: document.querySelector("#ordersNavTrigger"),
  helpModal: document.querySelector("#helpModal"),
  helpContent: document.querySelector("#helpContent"),
  settingsModal: document.querySelector("#settingsModal"),
  ordersBtn: document.querySelector("#ordersBtn"),
  profileMenu: document.querySelector("#profileMenu"),
  profileBtn: document.querySelector("#profileBtn"),
  profileDropdown: document.querySelector("#profileDropdown"),
  profileInitial: document.querySelector("#profileInitial"),
  profileDropdownInitial: document.querySelector("#profileDropdownInitial"),
  profileName: document.querySelector("#profileName"),
  profileEmail: document.querySelector("#profileEmail"),
  profileRoleBadge: document.querySelector("#profileRoleBadge"),
  profileOrdersBtn: document.querySelector("#profileOrdersBtn"),
  profileCartBtn: document.querySelector("#profileCartBtn"),
  profileWishlistBtn: document.querySelector("#profileWishlistBtn"),
  profileSettingsBtn: document.querySelector("#profileSettingsBtn"),
  profileThemeBtn: document.querySelector("#profileThemeBtn"),
  profileBusinessPanelBtn: document.querySelector("#profileBusinessPanelBtn"),
  profileLogoutBtn: document.querySelector("#profileLogoutBtn"),
  settingsList: document.querySelector("#settingsList"),
  profileSettingsForm: document.querySelector("#profileSettingsForm"),
  passwordSettingsForm: document.querySelector("#passwordSettingsForm"),
  deleteAccountForm: document.querySelector("#deleteAccountForm"),
  settingsThemeSelect: document.querySelector("#settingsThemeSelect"),
  settingsLogoutBtn: document.querySelector("#settingsLogoutBtn"),
  chatbotLauncher: document.querySelector("#chatbotLauncher"),
  chatbotPanel: document.querySelector("#chatbotPanel"),
  chatbotClose: document.querySelector("#chatbotClose"),
  chatbotMessages: document.querySelector("#chatbotMessages"),
  chatbotForm: document.querySelector("#chatbotForm"),
  chatbotInput: document.querySelector("#chatbotInput"),
  toast: document.querySelector("#toast"),
  sampleNote: document.querySelector("#sampleNote"),
  heroProductCount: document.querySelector("#heroProductCount"),
  themeToggle: document.querySelector("#themeToggle")
};

const inr = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 0
});
const API_TIMEOUT_MS = 20000;

function moneyLabel(value) {
  return `INR ${inr.format(Number(value || 0))}`;
}

function savedDeliveryLocation() {
  try {
    const details = JSON.parse(localStorage.getItem("mc_location_details") || "{}");
    if (details?.city || details?.pincode) return details;
  } catch (error) {}

  const legacy = localStorage.getItem("mc_location") || "";
  const match = legacy.match(/^(.*?)\s*\((\d{6})\)$/);
  if (match) {
    const locality = match[1].split(",")[0].trim();
    return { city: locality, pincode: match[2], state: "" };
  }
  return legacy && legacy !== "India" ? { city: legacy, pincode: "", state: "" } : null;
}

function syncCheckoutLocation(details, overwrite = false) {
  if (!details) return;
  const form = document.querySelector("#checkoutForm");
  if (!form) return;
  if (details.pincode && (overwrite || !form.pincode.value)) form.pincode.value = details.pincode;
  if (details.city && (overwrite || !form.city.value)) form.city.value = details.city;
  if (details.state && (overwrite || !form.state.value)) form.state.value = details.state;
}

function setDeliveryLocation(details, options = {}) {
  const city = String(details?.city || "").trim();
  const pincode = String(details?.pincode || "").replace(/\D+/g, "").slice(0, 6);
  const stateName = String(details?.state || "").trim();
  if (!city && !pincode) return;

  const clean = { city, pincode, state: stateName };
  state.currentLocationDetails = clean;
  state.currentLocation = pincode ? `${city || "India"} (${pincode})` : (city || "India");
  localStorage.setItem("mc_location_details", JSON.stringify(clean));
  localStorage.setItem("mc_location", state.currentLocation);

  const label = document.querySelector("#currentLocationLabel");
  if (label) {
    label.innerHTML = `
      <span class="location-locality">${escapeHtml(city || "India")}</span>
      ${pincode ? `<span class="location-pincode">${escapeHtml(pincode)}</span>` : ""}
    `;
  }
  if (options.syncCheckout) syncCheckoutLocation(clean, true);
}

function brandLabel(value) {
  const clean = (value || "").trim();
  return clean.toLowerCase() === "microchip cart" ? "MicroChip Cart" : (clean || "MicroChip Cart");
}

function brandMarkup(value) {
  const label = brandLabel(value);
  if (label.toLowerCase() === "microchip cart") {
    return `<span>MicroChip</span><span>Cart</span>`;
  }
  return escapeHtml(label);
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
  const openModal = document.querySelector("dialog.modal[open]");
  if (openModal && els.toast.parentElement !== openModal) {
    const closeRow = openModal.querySelector(".modal-close-row");
    openModal.insertBefore(els.toast, closeRow?.nextSibling || openModal.firstChild);
  } else if (!openModal && els.toast.parentElement !== document.body) {
    document.body.appendChild(els.toast);
  }
  els.toast.textContent = message;
  els.toast.classList.add("show");
  setTimeout(() => els.toast.classList.remove("show"), 2600);
}

const scrollLockState = {
  locked: false,
  scrollY: 0,
  scrollbarWidth: 0,
};

function hasBlockingOverlay() {
  return Boolean(document.querySelector(
    "dialog.modal[open], .cart-drawer.open, .mobile-sidebar.open, .header-nav-item.open"
  ));
}

function lockPageScroll() {
  if (scrollLockState.locked) return;
  scrollLockState.scrollY = window.scrollY || document.documentElement.scrollTop || 0;
  scrollLockState.scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
  document.body.style.position = "fixed";
  document.body.style.top = `-${scrollLockState.scrollY}px`;
  document.body.style.left = "0";
  document.body.style.right = "0";
  document.body.style.width = "100%";
  if (scrollLockState.scrollbarWidth > 0) {
    document.body.style.paddingRight = `${scrollLockState.scrollbarWidth}px`;
  }
  scrollLockState.locked = true;
}

function unlockPageScroll() {
  if (!scrollLockState.locked) return;
  const y = scrollLockState.scrollY;
  document.body.style.position = "";
  document.body.style.top = "";
  document.body.style.left = "";
  document.body.style.right = "";
  document.body.style.width = "";
  document.body.style.paddingRight = "";
  scrollLockState.locked = false;
  scrollLockState.scrollY = 0;
  scrollLockState.scrollbarWidth = 0;
  window.scrollTo(0, y);
}

function refreshPageScrollLock() {
  if (hasBlockingOverlay()) {
    lockPageScroll();
  } else {
    unlockPageScroll();
  }
}

function bindPageScrollLock() {
  if (window.HTMLDialogElement?.prototype?.showModal) {
    const nativeShowModal = window.HTMLDialogElement.prototype.showModal;
    const nativeClose = window.HTMLDialogElement.prototype.close;
    window.HTMLDialogElement.prototype.showModal = function(...args) {
      const result = nativeShowModal.apply(this, args);
      requestAnimationFrame(refreshPageScrollLock);
      return result;
    };
    window.HTMLDialogElement.prototype.close = function(...args) {
      const result = nativeClose.apply(this, args);
      requestAnimationFrame(refreshPageScrollLock);
      return result;
    };
  }
  document.querySelectorAll("dialog.modal").forEach(dialog => {
    dialog.addEventListener("close", () => requestAnimationFrame(refreshPageScrollLock));
    dialog.addEventListener("cancel", () => requestAnimationFrame(refreshPageScrollLock));
  });
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const authToken = state.authToken || localStorage.getItem("mc_auth_token") || "";
  if (authToken && !headers["X-Auth-Token"]) {
    headers["X-Auth-Token"] = authToken;
  }
  const controller = options.signal ? null : new AbortController();
  const timeoutMs = Number(options.timeoutMs || API_TIMEOUT_MS);
  const timeoutId = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
  let res;
  try {
    const { timeoutMs: _timeoutMs, signal: providedSignal, ...fetchOptions } = options;
    res = await fetch(path, {
      credentials: "same-origin",
      ...fetchOptions,
      headers,
      signal: controller?.signal || providedSignal
    });
  } catch (error) {
    if (error.name === "AbortError") {
      const timeoutError = new Error("This is taking longer than expected. Please try again.");
      timeoutError.status = 408;
      throw timeoutError;
    }
    throw error;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
  let data = {};
  try {
    data = await res.json();
  } catch (error) {
    data = { ok: false, error: res.ok ? "Empty server response" : "Server is temporarily unavailable" };
  }
  if (!data.ok) {
    const error = new Error(data.error || "Request failed");
    error.status = res.status;
    error.data = data;
    throw error;
  }
  return data;
}

function setTheme(theme) {
  const nextTheme = theme === "light" ? "light" : "dark";
  document.body.dataset.theme = nextTheme;
  localStorage.setItem("mc_theme", nextTheme);
  els.themeToggle?.setAttribute("aria-label", "Toggle cyber blue contrast theme");
}

function initTheme() {
  setTheme(localStorage.getItem("mc_theme") || "dark");
  els.themeToggle?.addEventListener("click", () => {
    setTheme(document.body.dataset.theme === "dark" ? "light" : "dark");
  });
}

function saveCart() {
  localStorage.setItem("mc_cart", JSON.stringify(state.cart));
  renderCart();
}

function saveWishlist() {
  localStorage.setItem("mc_wishlist", JSON.stringify(state.wishlist));
  renderWishlistCount();
  renderProducts();
}

function isWishlisted(productId) {
  return state.wishlist.includes(productId);
}

function renderWishlistCount() {
  if (els.wishlistCount) els.wishlistCount.textContent = state.wishlist.length;
  renderMiniWishlist();
}

function toggleWishlist(productId) {
  const product = state.products.find(item => item.id === productId);
  if (!product) return;
  if (isWishlisted(productId)) {
    state.wishlist = state.wishlist.filter(id => id !== productId);
    toast("Removed from wishlist");
  } else {
    state.wishlist.unshift(productId);
    toast("Added to wishlist");
  }
  saveWishlist();
}

function showWishlist() {
  if (!els.wishlistModal || !els.wishlistList) return;
  const products = state.wishlist
    .map(id => state.products.find(product => product.id === id))
    .filter(Boolean);
  els.wishlistList.innerHTML = products.length ? products.map(product => `
    <article class="wishlist-item">
      <img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}" onerror="this.src='/static/images/product-placeholder.webp'">
      <div>
        <strong>${escapeHtml(product.name)}</strong>
        <span>${moneyLabel(product.price)} &middot; ${product.stock > 0 ? `${product.stock} in stock` : "Out of stock"}</span>
      </div>
      <button class="secondary-btn" type="button" data-view-product="${product.id}">View</button>
      <button class="icon-btn" type="button" data-wishlist-toggle="${product.id}" aria-label="Remove ${escapeHtml(product.name)} from wishlist">&times;</button>
    </article>
  `).join("") : `<p class="form-help">Your wishlist is empty. Tap the heart on products you like.</p>`;
  if (!els.wishlistModal.open) els.wishlistModal.showModal();
}

function cartTotals() {
  const subtotal = state.cart.reduce((sum, item) => sum + Number(item.price) * item.quantity, 0);
  const tax = subtotal * 0.18;
  const shipping = subtotal === 0 || subtotal >= 999 ? 0 : 79;
  return { subtotal, tax, shipping, total: subtotal + tax + shipping };
}

function renderCart() {
  const count = state.cart.reduce((sum, item) => sum + item.quantity, 0);
  els.cartCount.textContent = count;
  if (!state.cart.length) {
    els.cartItems.innerHTML = `<p class="form-help">Cart is empty.</p>`;
  } else {
    els.cartItems.innerHTML = state.cart.map(item => `
      <article class="cart-item">
        <img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.name)}" onerror="this.src='/static/images/product-placeholder.webp'">
        <div>
          <div class="cart-item-top">
            <div>
              <h3>${escapeHtml(item.name)}</h3>
              <p class="stock">${moneyLabel(item.price)} each</p>
            </div>
            <strong class="cart-line-total">${moneyLabel(Number(item.price) * item.quantity)}</strong>
          </div>
          <div class="qty-row">
            <button type="button" data-cart-dec="${item.id}">&minus;</button>
            <strong>${item.quantity}</strong>
            <button type="button" data-cart-inc="${item.id}">+</button>
            <button type="button" data-cart-remove="${item.id}">Remove</button>
          </div>
        </div>
      </article>
    `).join("");
  }
  const totals = cartTotals();
  els.cartSubtotal.textContent = moneyLabel(totals.subtotal);
  els.cartTax.textContent = moneyLabel(totals.tax);
  els.cartShipping.textContent = moneyLabel(totals.shipping);
  els.cartTotal.textContent = moneyLabel(totals.total);
  renderMiniCart();
}

function openCart() {
  els.cartDrawer.classList.add("open");
  els.cartDrawer.setAttribute("aria-hidden", "false");
  els.scrim.classList.add("show");
  refreshPageScrollLock();
}

function closeCart() {
  els.cartDrawer.classList.remove("open");
  els.cartDrawer.setAttribute("aria-hidden", "true");
  els.scrim.classList.remove("show");
  refreshPageScrollLock();
}

function productStars(product) {
  const rating = Number(product.rating_avg || 0);
  return `<span class="rating" aria-hidden="true">&#9733;&#9733;&#9733;&#9733;&#9733;</span> <span>${rating ? rating.toFixed(1) : "New"} (${product.review_count || 0})</span>`;
}

function popularityScore(product) {
  return (Number(product.cart_adds || 0) * 5)
    + (Number(product.review_count || 0) * 3)
    + Number(product.views || 0)
    + Number(product.rating_avg || 0);
}

function renderPopularHero() {
  if (!els.popularHeroPanel) return;
  const [product] = [...state.products].sort((a, b) => popularityScore(b) - popularityScore(a));
  if (!product) {
    els.popularHeroPanel.innerHTML = "";
    return;
  }
  els.popularHeroPanel.innerHTML = `
    <p class="eyebrow">Most popular</p>
    <button class="popular-hero-card" type="button" data-view-product="${product.id}">
      <img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}" onerror="this.src='/static/images/product-placeholder.webp'">
      <span>
        <strong>${escapeHtml(product.name)}</strong>
        <small>${moneyLabel(product.price)} &middot; ${product.cart_adds || 0} cart adds &middot; ${product.review_count || 0} reviews</small>
      </span>
    </button>
  `;
}

function searchMatches() {
  const query = state.query.trim().toLowerCase();
  if (!query) return [];
  return state.products.filter(product => {
    const haystack = `${product.name} ${product.description} ${product.sku} ${product.model} ${product.brand} ${product.category}`.toLowerCase();
    return haystack.includes(query);
  }).slice(0, 6);
}

function saveSearchTerm(term) {
  if (!term || !term.trim()) return;
  term = term.trim();
  let history = state.searchHistory || [];
  history = history.filter(item => item.toLowerCase() !== term.toLowerCase());
  history.unshift(term);
  state.searchHistory = history.slice(0, 5);
  localStorage.setItem("mc_search_history", JSON.stringify(state.searchHistory));
}

function renderSearchSuggestionsFor(inputEl, suggestionsEl) {
  if (!inputEl || !suggestionsEl) return;
  const val = inputEl.value.trim();
  
  if (!val) {
    const history = state.searchHistory || [];
    const hasHistory = history.length > 0;
    
    let historyHtml = "";
    if (hasHistory) {
      historyHtml = `
        <div class="search-history-container">
          <div class="search-suggestions-header">
            <span>Recent Searches</span>
            <button class="clear-all-history" type="button" id="clearAllHistoryBtn">Clear All</button>
          </div>
          <div class="search-history-list">
            ${history.map((term, index) => `
              <div class="search-history-item">
                <button type="button" class="history-term-btn" data-history-term="${escapeHtml(term)}">
                  <span class="history-clock-icon">&#9200;</span> ${escapeHtml(term)}
                </button>
                <button type="button" class="delete-history-btn" data-delete-history-idx="${index}" aria-label="Remove search term">&times;</button>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }
    
    const popularChips = ["ESP32", "STM32", "ATmega328P", "WiFi", "Bluetooth", "Microcontroller", "Wireless Module"];
    const chipsHtml = `
      <div class="popular-chips-container">
        <div class="search-suggestions-header">
          <span>Popular Searches</span>
        </div>
        <div class="search-chips-list">
          ${popularChips.map(chip => `
            <button type="button" class="search-chip-badge" data-search-chip="${escapeHtml(chip)}">${escapeHtml(chip)}</button>
          `).join("")}
        </div>
      </div>
    `;
    
    const featured = state.products.slice(0, 3);
    let featuredHtml = "";
    if (featured.length) {
      featuredHtml = `
        <div class="featured-products-container" style="padding: 6px;">
          <div class="search-suggestions-header">
            <span>Trending Components</span>
          </div>
          <div style="display:flex; flex-direction:column; gap: 4px; margin-top:6px;">
            ${featured.map(product => `
              <button type="button" data-suggestion-product="${product.id}" style="width:100%;">
                <img src="${escapeHtml(product.image_url)}" alt="" onerror="this.src='/static/images/product-placeholder.webp'" style="width:32px; height:32px; object-fit:contain; border-radius:4px; padding: 2px; background:#04091a;">
                <span style="display:flex; flex-direction:column; text-align:left; margin-left:10px;">
                  <strong>${escapeHtml(product.name)}</strong>
                  <small style="color:var(--muted); font-size:11px;">${escapeHtml(product.category)} &middot; ${moneyLabel(product.price)}</small>
                </span>
              </button>
            `).join("")}
          </div>
        </div>
      `;
    }
    
    suggestionsEl.innerHTML = `
      <div class="search-dropdown-menu">
        ${historyHtml}
        ${chipsHtml}
        ${featuredHtml}
      </div>
    `;
    suggestionsEl.classList.remove("hidden");
    return;
  }
  
  const matches = searchMatchesFor(val);
  suggestionsEl.classList.toggle("hidden", !matches.length);
  
  suggestionsEl.innerHTML = matches.map(product => {
    const regex = new RegExp(`(${escapeRegExp(val)})`, "gi");
    const highlightedName = escapeHtml(product.name).replace(regex, `<span class="highlight-match">$1</span>`);
    
    return `
      <button type="button" data-suggestion-product="${product.id}" role="option">
        <img src="${escapeHtml(product.image_url)}" alt="" onerror="this.src='/static/images/product-placeholder.webp'">
        <span>
          <strong>${highlightedName}</strong>
          <small>${escapeHtml(product.category || "Component")} &middot; ${escapeHtml(product.sku || "SKU")} &middot; ${moneyLabel(product.price)}</small>
        </span>
      </button>
    `;
  }).join("");
}

function escapeRegExp(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function searchMatchesFor(queryVal) {
  const query = queryVal.trim().toLowerCase();
  if (!query) return [];
  return state.products.filter(product => {
    const haystack = `${product.name} ${product.description} ${product.sku} ${product.model} ${product.brand} ${product.category}`.toLowerCase();
    return haystack.includes(query);
  }).slice(0, 6);
}

function renderSearchSuggestions() {
  const activeInput = document.activeElement;
  if (activeInput === els.search) {
    renderSearchSuggestionsFor(els.search, els.searchSuggestions);
  } else if (activeInput === els.searchMobile) {
    renderSearchSuggestionsFor(els.searchMobile, els.searchSuggestionsMobile);
  } else {
    document.querySelectorAll(".search-suggestions-dropdown").forEach(d => d.classList.add("hidden"));
  }
}

function closeSearchSuggestions() {
  document.querySelectorAll(".search-suggestions-dropdown").forEach(dropdown => dropdown.classList.add("hidden"));
  state.searchIndex = -1;
}

function handleSearchKeyboardNavigation(event) {
  const suggestionsDropdown = event.target.id === "searchInputMobile" ? els.searchSuggestionsMobile : els.searchSuggestions;
  if (!suggestionsDropdown || suggestionsDropdown.classList.contains("hidden")) return;
  
  const items = Array.from(suggestionsDropdown.querySelectorAll("button[data-suggestion-product], .search-history-item button.history-term-btn, .search-chip-badge"));
  if (!items.length) return;
  
  if (event.key === "ArrowDown") {
    event.preventDefault();
    state.searchIndex = (state.searchIndex + 1) % items.length;
    highlightSearchItem(items);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    state.searchIndex = (state.searchIndex - 1 + items.length) % items.length;
    highlightSearchItem(items);
  } else if (event.key === "Enter") {
    if (state.searchIndex >= 0 && state.searchIndex < items.length) {
      event.preventDefault();
      items[state.searchIndex].click();
      state.searchIndex = -1;
    }
  } else if (event.key === "Escape") {
    suggestionsDropdown.classList.add("hidden");
    state.searchIndex = -1;
  }
}

function highlightSearchItem(items) {
  items.forEach((item, idx) => {
    item.classList.toggle("selected", idx === state.searchIndex);
  });
}

function renderMiniCart() {
  if (!els.cartDropdownItems) return;
  if (!state.cart.length) {
    els.cartDropdownItems.innerHTML = `<p class="preview-empty">Your cart is empty.</p>`;
    if (els.miniCartSubtotal) els.miniCartSubtotal.textContent = moneyLabel(0);
    return;
  }
  
  els.cartDropdownItems.innerHTML = state.cart.map(item => `
    <div class="preview-item">
      <img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.name)}" onerror="this.src='/static/images/product-placeholder.webp'">
      <div class="preview-item-info">
        <span class="preview-item-name">${escapeHtml(item.name)}</span>
        <span class="preview-item-meta">Qty: ${item.quantity}</span>
      </div>
      <strong class="preview-item-price">${moneyLabel(Number(item.price) * item.quantity)}</strong>
    </div>
  `).join("");
  
  const totals = cartTotals();
  if (els.miniCartSubtotal) els.miniCartSubtotal.textContent = moneyLabel(totals.subtotal);
}

function renderMiniWishlist() {
  if (!els.wishlistDropdownItems) return;
  const wishlistedProducts = state.wishlist
    .map(id => state.products.find(product => product.id === id))
    .filter(Boolean);
    
  if (!wishlistedProducts.length) {
    els.wishlistDropdownItems.innerHTML = `<p class="preview-empty">Your wishlist is empty.</p>`;
    return;
  }
  
  els.wishlistDropdownItems.innerHTML = wishlistedProducts.slice(0, 4).map(product => `
    <div class="preview-item" data-view-product="${product.id}">
      <img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}" onerror="this.src='/static/images/product-placeholder.webp'">
      <div class="preview-item-info">
        <span class="preview-item-name">${escapeHtml(product.name)}</span>
        <span class="preview-item-meta">${product.stock > 0 ? "In Stock" : "Out of stock"}</span>
      </div>
      <strong class="preview-item-price">${moneyLabel(product.price)}</strong>
    </div>
  `).join("");
}

async function showOrdersWithFilter(filterType) {
  if (!state.currentUser) {
    showAuth("login", "B2C");
    return;
  }

  let title = "Your Orders";
  if (filterType === "current") {
    title = "Current Active Orders";
  } else if (filterType === "returns") {
    title = "Initiate Returns (Delivered Items)";
  } else if (filterType === "refunds") {
    title = "Refund Status & Cancellations";
  }

  const list = document.querySelector("#ordersList");
  const modalTitle = els.ordersModal?.querySelector("h2");
  if (modalTitle) modalTitle.textContent = title;
  if (list) {
    list.innerHTML = `<p class="form-help">Loading matching orders...</p>`;
  }
  els.ordersModal?.showModal();

  try {
    const data = await api("/api/orders/my");
    let orders = data.orders || [];
    
    if (filterType === "current") {
      orders = orders.filter(order => !["Delivered", "Cancelled"].includes(order.status));
      if (!orders.length) {
        // Safe check
      }
    } else if (filterType === "returns") {
      orders = orders.filter(order => order.status === "Delivered");
      if (!orders.length) {
        toast("No eligible delivered orders found for returns.");
      }
    } else if (filterType === "refunds") {
      orders = orders.filter(order => order.payment_status === "Refunded" || order.status === "Cancelled");
    }
    
    if (list) {
      list.innerHTML = orders.length ? orders.map(order => `
        <article class="order-card">
          <header>
            <strong>${escapeHtml(order.invoice_number)}</strong>
            <span class="pill">${escapeHtml(order.status)}</span>
          </header>
          ${order.business?.order_type === "B2B" ? `<p class="order-business">${escapeHtml(order.business.company_name || "Business order")}${order.business.gstin ? ` &middot; GSTIN ${escapeHtml(order.business.gstin)}` : ""}</p>` : ""}
          <div class="order-items">
            ${order.items.map(item => `
              <div class="order-item-row">
                <span>${escapeHtml(item.name)} x ${item.quantity}</span>
                <strong>${moneyLabel(item.line_total)}</strong>
              </div>
            `).join("")}
          </div>
          <div class="order-total-row">
            <span>Payment: ${escapeHtml(order.payment_status)}</span>
            <strong>${moneyLabel(order.totals.total)}</strong>
          </div>
          ${filterType === "returns" && order.status === "Delivered" ? `
            <div style="margin-top: 10px; text-align: right;">
              <button class="secondary-btn" style="min-height:30px; font-size:12px;" onclick="toast('Return request submitted for ${escapeHtml(order.invoice_number)}. Our team will verify and approve within 24 hours.')">Request Return</button>
            </div>
          ` : ""}
          ${order.status === "Pending" ? `
            <div style="margin-top: 10px; text-align: right;">
              <button class="secondary-btn cancel-order-btn" style="min-height:30px; font-size:12px; background-color: rgba(239, 68, 68, 0.08); color: var(--danger, #ef4444); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 12px; padding: 4px 12px; cursor: pointer; font-weight: 600;" data-order-id="${order.id}">Cancel Order</button>
            </div>
          ` : ""}
        </article>
      `).join("") : `<p class="form-help">No matching orders found under this filter.</p>`;
    }
  } catch (error) {
    toast(error.message);
    if (list) {
      list.innerHTML = `<p class="form-help">Failed to load orders.</p>`;
    }
  }
}

function sortedProducts(products) {
  const items = [...products];
  if (state.sort === "price-low") items.sort((a, b) => a.price - b.price);
  if (state.sort === "price-high") items.sort((a, b) => b.price - a.price);
  if (state.sort === "rating") items.sort((a, b) => (b.rating_avg || 0) - (a.rating_avg || 0));
  return items;
}

function visibleProducts() {
  return sortedProducts(state.products.filter(product => {
    const inCategory = state.category === "All" || product.category === state.category;
    const haystack = `${product.name} ${product.description} ${product.sku} ${product.model} ${product.brand}`.toLowerCase();
    return inCategory && haystack.includes(state.query.toLowerCase());
  }));
}

function catalogCategories() {
  return ["All", ...new Set(state.products.map(product => product.category).filter(Boolean))];
}

function renderSearchCategoryOptions() {
  if (!els.searchCategorySelectDesktop) return;
  els.searchCategorySelectDesktop.innerHTML = catalogCategories().map(category => `
    <option value="${escapeHtml(category)}">${category === "All" ? "All Categories" : escapeHtml(category)}</option>
  `).join("");
  els.searchCategorySelectDesktop.value = state.category;
}

function setCategory(category, options = {}) {
  state.category = category || "All";
  document.querySelectorAll("[data-home-category]").forEach(button => {
    button.classList.toggle("active", button.dataset.homeCategory === state.category);
  });
  document.querySelectorAll("[data-sidebar-cat]").forEach(button => {
    button.classList.toggle("active", button.dataset.sidebarCat === state.category);
  });
  if (els.searchCategorySelectDesktop) {
    els.searchCategorySelectDesktop.value = [...els.searchCategorySelectDesktop.options].some(option => option.value === state.category)
      ? state.category
      : "All";
  }
  renderSearchCategoryOptions();
  renderCategories();
  renderProducts();
  if (options.scrollToProducts) {
    document.querySelector(".toolbar")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function renderCategories() {
  if (!els.categoryFilters) return;
  renderSearchCategoryOptions();
  els.categoryFilters.innerHTML = catalogCategories().map(category => `
    <button type="button" class="${category === state.category ? "active" : ""}" data-category="${escapeHtml(category)}">${escapeHtml(category)}</button>
  `).join("");
}

function renderSidebarCategories() {
  const sidebarCategoryList = document.querySelector("#sidebarCategoryList");
  if (sidebarCategoryList) {
    sidebarCategoryList.innerHTML = catalogCategories().map(cat => `
      <button type="button" class="sidebar-link ${cat === state.category ? "active" : ""}" data-sidebar-cat="${cat}">${cat}</button>
    `).join("");
  }
}

function renderProducts() {
  const products = visibleProducts();
  if (els.heroProductCount) els.heroProductCount.textContent = state.products.length;
  renderPopularHero();
  els.sampleNote?.classList.toggle("hidden", !state.products.some(product => product.sample));
  if (!products.length) {
    els.grid.innerHTML = `<p class="form-help">No products match your search.</p>`;
    return;
  }
  els.grid.innerHTML = products.map(product => {
    const specEntries = Object.entries(product.specs || {}).slice(0, 3);
    const liked = isWishlisted(product.id);
    const badge = product.stock <= 0 ? "Out of stock" : popularityScore(product) > 28 ? "Best seller" : product.rating_avg >= 4.5 ? "Top rated" : "Fast moving";
    return `
      <article class="product-card">
        <button class="wishlist-heart ${liked ? "active" : ""}" type="button" data-wishlist-toggle="${product.id}" aria-label="${liked ? "Remove from" : "Add to"} wishlist">
          ${liked ? "&hearts;" : "&#9825;"}
        </button>
        <button class="product-image" type="button" data-view-product="${product.id}" aria-label="View ${escapeHtml(product.name)}">
          <img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}" onerror="this.src='/static/images/product-placeholder.webp'">
        </button>
        <div class="product-body">
          <div class="meta-row">
            <span class="pill">${escapeHtml(product.category || "Microchip")}</span>
            <span class="pill deal-pill">${escapeHtml(badge)}</span>
            <span class="pill">${escapeHtml(product.sku || "SKU")}</span>
          </div>
          <h2 class="product-title">${escapeHtml(product.name)}</h2>
          <p class="product-description">${escapeHtml(product.description)}</p>
          <div class="meta-row">${productStars(product)}</div>
          <div class="meta-row">
            ${specEntries.map(([key, value]) => `<span class="pill">${escapeHtml(key)}: ${escapeHtml(value)}</span>`).join("")}
          </div>
          <div class="price-row">
            <span class="price">${moneyLabel(product.price)}</span>
            <span class="stock">${product.stock > 0 ? `${product.stock} in stock` : "Out of stock"}</span>
          </div>
          <div class="commerce-row">
            <span>GST invoice</span>
            <span>Protected checkout</span>
          </div>
          <div class="card-actions">
            <button class="secondary-btn" type="button" data-view-product="${product.id}">Details</button>
            <button class="primary-btn" type="button" data-add-cart="${product.id}" ${product.stock <= 0 ? "disabled" : ""}>Add to Cart</button>
          </div>
        </div>
      </article>
    `;
  }).join("");
}

async function loadProducts() {
  const [productsData, config] = await Promise.all([
    api("/api/products"),
    state.config ? Promise.resolve(state.config) : api("/api/config")
  ]);
  state.products = productsData.products;
  if (!state.config) {
    state.config = config;
  }
  if (config.settings?.store_name) {
    document.querySelector("#storeName").innerHTML = brandMarkup(config.settings.store_name);
  }
  if (config.settings?.announcement) {
    const announcement = document.querySelector("#announcement");
    if (announcement) announcement.textContent = config.settings.announcement;
  }
  renderCategories();
  renderSidebarCategories();
  renderPopularHero();
  renderSearchSuggestions();
  renderProducts();
}

let currentCategoryFilter = "All";

const demoCommunityThoughts = [
  {
    id: "demo-esp32-brownout",
    user_name: "Rohan",
    category: "Need Eyes",
    title: "ESP32 drops when WiFi wakes",
    content: "Try a 470uF capacitor near 3V3 and check regulator headroom before blaming the module. This fixed my lab build today.",
    likes: 12,
    reply_count: 4,
    liked_by: []
  },
  {
    id: "demo-lora-range",
    user_name: "Neha",
    category: "Bench Win",
    title: "LoRa range doubled after antenna swap",
    content: "The same SX1278 board went from patchy to solid after moving to a tuned 433MHz antenna. Cheap module, big difference.",
    likes: 18,
    reply_count: 6,
    liked_by: []
  },
  {
    id: "demo-pick-and-place",
    user_name: "Aarav",
    category: "Build Drop",
    title: "Mini pick-and-place controller build",
    content: "Using STM32, TMC2209 drivers, and a tiny vacuum pump. Need suggestions for a reliable nozzle holder before I order parts.",
    likes: 25,
    reply_count: 9,
    liked_by: []
  },
  {
    id: "demo-connector-match",
    user_name: "Fatima",
    category: "Part Hunt",
    title: "Anyone matched this 1.25mm connector?",
    content: "Looks like JST-GH but the latch feels different. If someone has a confirmed equivalent, save me one wrong cart.",
    likes: 9,
    reply_count: 3,
    liked_by: []
  },
  {
    id: "demo-sensor-noise",
    user_name: "Kabir",
    category: "Bench Win",
    title: "IMU noise dropped after grounding change",
    content: "Shared ground was the villain. Star ground plus shorter I2C lines made the readings finally behave.",
    likes: 16,
    reply_count: 5,
    liked_by: []
  }
];

async function loadCommunityPosts() {
  if (!els.communityPostsList) return;
  try {
    const data = await api("/api/community/posts");
    state.communityPosts = data.posts || [];
    renderCommunityPosts();
  } catch (error) {
    console.error("Failed to load community posts:", error);
  }
}

function renderCommunityPosts() {
  if (!els.communityPostsList) return;
  const posts = state.communityPosts.length ? state.communityPosts : demoCommunityThoughts;
  const filtered = posts.filter(post => {
    return currentCategoryFilter === "All" || communityCategoryLabel(post.category) === currentCategoryFilter;
  });
  
  if (!filtered.length) {
    els.communityPostsList.innerHTML = `<p class="form-help">No matching thoughts yet. Start one and set the vibe.</p>`;
    return;
  }
  
  els.communityPostsList.innerHTML = filtered.map(post => {
    const isDemoPost = String(post.id).startsWith("demo-");
    const isLiked = state.currentUser 
      ? (post.liked_by || []).includes(state.currentUser.id) 
      : false;
      
    let dateStr = isDemoPost ? "Live now" : "Just now";
    if (post.created_at) {
      try {
        const d = new Date(post.created_at);
        dateStr = d.toLocaleDateString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
      } catch (e) {}
    }
    
    const displayCategory = communityCategoryLabel(post.category);
    const catClass = categoryBadgeClass(displayCategory);

    return `
      <article class="post-card-board" data-post-id="${post.id}">
        <header class="post-header-board">
          <div class="post-author-info">
            <span class="user-avatar-initial">${escapeHtml(post.user_name.charAt(0).toUpperCase())}</span>
            <div>
              <strong class="author-name">${escapeHtml(post.user_name)}</strong>
              <small class="post-time">${dateStr}</small>
            </div>
          </div>
          <div class="post-card-tools">
            <span class="category-badge ${catClass}">${escapeHtml(displayCategory)}</span>
            ${post.can_delete ? `<button type="button" class="post-action-btn delete-community-btn" data-delete-post-id="${post.id}" aria-label="Delete signal">&times;</button>` : ""}
          </div>
        </header>
        <div class="post-body-board">
          <h3 class="post-title-board">${escapeHtml(post.title)}</h3>
          <p class="post-content-board">${escapeHtml(post.content).replaceAll("\n", "<br>")}</p>
        </div>
        <footer class="post-footer-board">
          <button type="button" class="post-action-btn like-btn ${isLiked ? "liked" : ""}" ${isDemoPost ? "disabled" : `data-like-post-id="${post.id}"`}>
            <span class="heart-icon">${isLiked ? "&hearts;" : "&#9825;"}</span>
            <span class="likes-count">${post.likes || 0}</span> Likes
          </button>
          <button type="button" class="post-action-btn comment-btn" ${isDemoPost ? "disabled" : `data-toggle-replies-id="${post.id}"`}>
            <span class="comment-icon">&#128172;</span>
            <span class="replies-count">${post.reply_count || 0}</span> Replies
          </button>
        </footer>
        
        ${isDemoPost ? "" : `<div class="post-replies-section hidden" id="repliesSection-${post.id}">
          <div class="replies-list" id="repliesList-${post.id}">
            <p class="form-help">Loading comments...</p>
          </div>
          <form class="post-reply-form" data-reply-to-post-id="${post.id}">
            <div class="reply-input-row">
              ${!state.currentUser ? `<input class="reply-guest-name" name="name" placeholder="Name" required>` : ""}
              <input class="reply-text-input" name="content" placeholder="Write a reply..." required>
              <button class="primary-btn reply-submit-btn" type="submit">Reply</button>
            </div>
          </form>
        </div>`}
      </article>
    `;
  }).join("");

  requestAnimationFrame(bindLiveThoughtScroll);
}

function bindLiveThoughtScroll() {
  const list = els.communityPostsList;
  if (!list || list.dataset.liveScrollBound === "true") return;
  list.dataset.liveScrollBound = "true";
  let direction = 1;
  let paused = false;

  list.addEventListener("mouseenter", () => {
    paused = true;
  });
  list.addEventListener("mouseleave", () => {
    paused = false;
  });
  list.addEventListener("focusin", () => {
    paused = true;
  });
  list.addEventListener("focusout", () => {
    paused = false;
  });

  window.setInterval(() => {
    if (paused || list.scrollHeight <= list.clientHeight + 4) return;
    list.scrollTop += direction;
    if (list.scrollTop + list.clientHeight >= list.scrollHeight - 2) direction = -1;
    if (list.scrollTop <= 0) direction = 1;
  }, 70);
}

function openCommunityComposer() {
  if (!els.postFormCard) return;
  els.postFormCard.classList.remove("hidden");
  els.startPostBtn?.classList.add("hidden");
  updateThoughtPreview();
  setTimeout(() => els.postAuthorName?.focus({ preventScroll: true }), 120);
}

function updateThoughtPreview() {
  if (!els.communityPostForm || !els.previewTitle) return;
  const formData = new FormData(els.communityPostForm);
  const name = String(formData.get("name") || "").trim();
  const category = String(formData.get("category") || "Need Eyes").trim();
  const title = String(formData.get("title") || "").trim();
  const content = String(formData.get("content") || "").trim();
  const author = name || "Your name";

  if (els.previewAuthorInitial) {
    els.previewAuthorInitial.textContent = author.charAt(0).toUpperCase();
  }
  if (els.previewAuthorName) {
    els.previewAuthorName.textContent = author;
  }
  if (els.previewCategory) {
    els.previewCategory.textContent = category || "Need Eyes";
    els.previewCategory.className = `category-badge ${categoryBadgeClass(category)}`;
  }
  els.previewTitle.textContent = title || "Your signal title will appear here";
  if (els.previewContent) {
    els.previewContent.textContent = content || "Start typing details and the live community card will update here.";
  }
}

function categoryBadgeClass(category) {
  if (category === "Need Eyes") return "badge-eyes";
  if (category === "Bench Win") return "badge-win";
  if (category === "Part Hunt") return "badge-hunt";
  if (category === "Build Drop") return "badge-build";
  return "badge-general";
}

function communityCategoryLabel(category) {
  if (category === "Problem") return "Need Eyes";
  if (category === "Experience") return "Bench Win";
  if (category === "Project") return "Build Drop";
  if (category === "General") return "Part Hunt";
  return category || "Need Eyes";
}

async function loadAndRenderReplies(postId) {
  const list = document.getElementById(`repliesList-${postId}`);
  if (!list) return;
  try {
    const res = await api(`/api/community/posts/${postId}/replies`);
    const replies = res.replies || [];
    if (!replies.length) {
      list.innerHTML = `<p class="form-help">No replies yet. Be the first to comment!</p>`;
      return;
    }
    list.innerHTML = replies.map(r => {
      let rDateStr = "Just now";
      if (r.created_at) {
        try {
          const d = new Date(r.created_at);
          rDateStr = d.toLocaleDateString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
        } catch (e) {}
      }
      return `
        <article class="reply-card-board" data-reply-id="${r.id}">
          <header class="reply-header-board">
            <span class="user-avatar-initial small-avatar">${escapeHtml(r.user_name.charAt(0).toUpperCase())}</span>
            <strong>${escapeHtml(r.user_name)}</strong>
            <small>${rDateStr}</small>
            ${r.can_delete ? `<button type="button" class="reply-delete-btn" data-delete-reply-id="${r.id}" data-parent-post-id="${postId}" aria-label="Delete reply">&times;</button>` : ""}
          </header>
          <p class="reply-content-board">${escapeHtml(r.content)}</p>
        </article>
      `;
    }).join("");
  } catch (err) {
    list.innerHTML = `<p class="form-help error">Failed to load replies: ${escapeHtml(err.message)}</p>`;
  }
}

function bindCommunityForum() {
  if (!els.communityPostsList) return;
  
  loadCommunityPosts();
  
  if (state.currentUser) {
    if (els.postAuthorName) {
      els.postAuthorName.value = state.currentUser.name || state.currentUser.email;
      els.postAuthorName.disabled = true;
    }
    if (els.postLoginNotice) {
      els.postLoginNotice.innerHTML = `Posting as verified member <strong>${escapeHtml(state.currentUser.name || state.currentUser.email)}</strong>.`;
    }
  } else {
    if (els.postAuthorName) {
      els.postAuthorName.value = "";
      els.postAuthorName.disabled = false;
    }
    if (els.postLoginNotice) {
      els.postLoginNotice.innerHTML = `You are posting as a guest. <button type="button" class="text-link-btn" id="postFormLoginBtn">Log in</button> to post as a verified member.`;
    }
  }

  els.startPostBtn?.addEventListener("click", () => {
    openCommunityComposer();
  });

  els.closePostFormBtn?.addEventListener("click", () => {
    els.postFormCard.classList.add("hidden");
    els.startPostBtn.classList.remove("hidden");
  });

  els.communityPostForm?.addEventListener("input", updateThoughtPreview);
  els.communityPostForm?.addEventListener("change", updateThoughtPreview);
  
  document.querySelector("#postFormLoginBtn")?.addEventListener("click", () => {
    showAuth("login");
  });

  els.communityCategories?.addEventListener("click", event => {
    const tab = event.target.closest(".category-tab");
    if (!tab) return;
    
    document.querySelectorAll(".category-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    currentCategoryFilter = tab.dataset.category;
    renderCommunityPosts();
  });

  els.communityPostForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form).entries());
    
    try {
      await api("/api/community/posts", {
        method: "POST",
        body: JSON.stringify(body)
      });
      toast("Signal posted live");
      form.reset();
      updateThoughtPreview();
      els.postFormCard.classList.add("hidden");
      els.startPostBtn.classList.remove("hidden");
      await loadCommunityPosts();
    } catch (err) {
      toast(err.message);
    }
  });

  els.communityPostsList.addEventListener("click", async event => {
    const deletePostBtn = event.target.closest("[data-delete-post-id]");
    if (deletePostBtn) {
      const postId = deletePostBtn.dataset.deletePostId;
      if (!confirm("Delete this community signal?")) return;
      try {
        await api(`/api/community/posts/${postId}`, { method: "DELETE" });
        state.communityPosts = state.communityPosts.filter(p => p.id !== postId);
        renderCommunityPosts();
        toast("Signal deleted");
      } catch (err) {
        toast(err.message);
      }
      return;
    }

    const deleteReplyBtn = event.target.closest("[data-delete-reply-id]");
    if (deleteReplyBtn) {
      const replyId = deleteReplyBtn.dataset.deleteReplyId;
      const postId = deleteReplyBtn.dataset.parentPostId;
      if (!confirm("Delete this reply?")) return;
      try {
        await api(`/api/community/replies/${replyId}`, { method: "DELETE" });
        await loadAndRenderReplies(postId);
        const postIdx = state.communityPosts.findIndex(p => p.id === postId);
        if (postIdx > -1) {
          state.communityPosts[postIdx].reply_count = Math.max(0, (state.communityPosts[postIdx].reply_count || 0) - 1);
          const countSpan = document.querySelector(`[data-toggle-replies-id="${postId}"] .replies-count`);
          if (countSpan) countSpan.textContent = state.communityPosts[postIdx].reply_count;
        }
        toast("Reply deleted");
      } catch (err) {
        toast(err.message);
      }
      return;
    }

    const likeBtn = event.target.closest("[data-like-post-id]");
    if (likeBtn) {
      const postId = likeBtn.dataset.likePostId;
      try {
        const res = await api(`/api/community/posts/${postId}/like`, { method: "POST", body: "{}" });
        const postIdx = state.communityPosts.findIndex(p => p.id === postId);
        if (postIdx > -1) {
          state.communityPosts[postIdx] = res.post;
          renderCommunityPosts();
        }
      } catch (err) {
        toast(err.message);
      }
      return;
    }

    const commentBtn = event.target.closest("[data-toggle-replies-id]");
    if (commentBtn) {
      const postId = commentBtn.dataset.toggleRepliesId;
      const section = document.getElementById(`repliesSection-${postId}`);
      if (section) {
        const isCollapsed = section.classList.toggle("hidden");
        if (!isCollapsed) {
          loadAndRenderReplies(postId);
        }
      }
      return;
    }
  });

  els.communityPostsList.addEventListener("submit", async event => {
    const form = event.target.closest("[data-reply-to-post-id]");
    if (!form) return;
    event.preventDefault();
    const postId = form.dataset.replyToPostId;
    const body = Object.fromEntries(new FormData(form).entries());
    
    try {
      await api(`/api/community/posts/${postId}/replies`, {
        method: "POST",
        body: JSON.stringify(body)
      });
      form.reset();
      toast("Reply submitted");
      
      await loadAndRenderReplies(postId);
      
      const postIdx = state.communityPosts.findIndex(p => p.id === postId);
      if (postIdx > -1) {
        state.communityPosts[postIdx].reply_count = (state.communityPosts[postIdx].reply_count || 0) + 1;
        const countSpan = document.querySelector(`[data-toggle-replies-id="${postId}"] .replies-count`);
        if (countSpan) {
          countSpan.textContent = state.communityPosts[postIdx].reply_count;
        }
      }
    } catch (err) {
      toast(err.message);
    }
  });
}

async function loadMe() {
  try {
    const data = await api("/api/auth/me");
    state.currentUser = data.user || null;
    if (data.auth_token) {
      state.authToken = data.auth_token;
      localStorage.setItem("mc_auth_token", data.auth_token);
    } else if (!state.currentUser) {
      state.authToken = "";
      localStorage.removeItem("mc_auth_token");
    }
  } catch (error) {
    state.currentUser = null;
    if (error.status === 401 || error.status === 403) {
      state.authToken = "";
      localStorage.removeItem("mc_auth_token");
    }
    console.warn("Could not load current user", error);
  }
  updateAuthUi();
  checkProfileSetup();
}

async function confirmSignedIn() {
  await loadMe();
  return Boolean(state.currentUser && (state.authToken || localStorage.getItem("mc_auth_token")));
}

function updateAuthUi() {
  const loggedIn = Boolean(state.currentUser);
  
  if (els.guestAccountMenu) els.guestAccountMenu.classList.toggle("hidden", loggedIn);
  if (els.businessAuthBtn) els.businessAuthBtn.classList.toggle("hidden", loggedIn);
  if (els.ordersBtn) els.ordersBtn.classList.toggle("hidden", !loggedIn);
  if (els.profileMenu) els.profileMenu.classList.toggle("hidden", !loggedIn);
  closeGuestAccountMenu();
  closeOrdersMenu();
  els.profileBtn?.setAttribute("aria-expanded", "false");
  els.profileMenu?.classList.remove("open");
  
  const sidebarLabel = document.querySelector("#sidebarUserLabel");
  const sidebarActions = document.querySelector("#sidebarUserActions");
  
  if (loggedIn) {
    const name = state.currentUser.name || "User";
    const isBusinessUser = (state.currentUser.account_type || "B2C") === "B2B";
    const isApprovedBusiness = isBusinessUser;
    if (document.querySelector("#profileNameLabel")) {
      document.querySelector("#profileNameLabel").textContent = name;
    }
    els.profileBusinessPanelBtn?.classList.toggle("hidden", !isApprovedBusiness);
    if (sidebarLabel) sidebarLabel.textContent = `Hello, ${name}`;
    if (sidebarActions) {
      sidebarActions.innerHTML = `
        <button type="button" class="sidebar-link" id="sidebarAccountBtn">Your Account</button>
        ${isApprovedBusiness ? `<button type="button" class="sidebar-link" id="sidebarBusinessPanelBtn">Business Panel</button>` : ""}
        <button type="button" class="sidebar-link" id="sidebarLogoutBtn" style="color:var(--danger);">Logout</button>
      `;
      document.querySelector("#sidebarAccountBtn")?.addEventListener("click", () => {
        document.querySelector("#mobileSidebar")?.classList.remove("open");
        document.querySelector("#sidebarBackdrop")?.classList.remove("show");
        showSettings();
      });
      document.querySelector("#sidebarBusinessPanelBtn")?.addEventListener("click", () => {
        document.querySelector("#mobileSidebar")?.classList.remove("open");
        document.querySelector("#sidebarBackdrop")?.classList.remove("show");
        window.location.assign("/admin");
      });
      document.querySelector("#sidebarLogoutBtn")?.addEventListener("click", async () => {
        // Toggle mobile sidebar close
        document.querySelector("#mobileSidebar")?.classList.remove("open");
        document.querySelector("#sidebarBackdrop")?.classList.remove("show");
        await logout();
      });
    }
  } else {
    if (sidebarLabel) sidebarLabel.textContent = "Hello, Sign In";
    if (sidebarActions) {
      sidebarActions.innerHTML = `
        <button type="button" class="sidebar-link" id="sidebarLoginBtn">Login to your account</button>
        <button type="button" class="sidebar-link" id="sidebarSignupBtn">Create new account</button>
      `;
      document.querySelector("#sidebarLoginBtn")?.addEventListener("click", () => {
        document.querySelector("#mobileSidebar")?.classList.remove("open");
        document.querySelector("#sidebarBackdrop")?.classList.remove("show");
        showAuth("login", "B2C");
      });
      document.querySelector("#sidebarSignupBtn")?.addEventListener("click", () => {
        document.querySelector("#mobileSidebar")?.classList.remove("open");
        document.querySelector("#sidebarBackdrop")?.classList.remove("show");
        showAuth("signup", "B2C");
      });
    }
  }
  
  if (els.postAuthorName) {
    if (loggedIn) {
      els.postAuthorName.value = state.currentUser.name || state.currentUser.email;
      els.postAuthorName.disabled = true;
      if (els.postLoginNotice) {
        els.postLoginNotice.innerHTML = `Posting as verified member <strong>${escapeHtml(state.currentUser.name || state.currentUser.email)}</strong>.`;
      }
    } else {
      els.postAuthorName.value = "";
      els.postAuthorName.disabled = false;
      if (els.postLoginNotice) {
        els.postLoginNotice.innerHTML = `You are posting as a guest. <button type="button" class="text-link-btn" id="postFormLoginBtn">Log in</button> to post as a verified member.`;
        document.querySelector("#postFormLoginBtn")?.addEventListener("click", () => {
          showAuth("login");
        });
      }
    }
  }

  if (!loggedIn) {
    if (els.profileName) els.profileName.textContent = "User";
    if (els.profileEmail) els.profileEmail.textContent = "Signed out";
    if (els.profileDropdownInitial) els.profileDropdownInitial.textContent = "U";
    if (els.profileRoleBadge) els.profileRoleBadge.textContent = "Guest";
    els.profileBusinessPanelBtn?.classList.add("hidden");
    return;
  }
  const name = state.currentUser.name || "User";
  const role = (state.currentUser.account_type || "B2C") === "B2B" ? "Business" : "Customer";
  if (els.profileInitial) els.profileInitial.textContent = name.trim().charAt(0).toUpperCase() || "U";
  if (els.profileDropdownInitial) els.profileDropdownInitial.textContent = name.trim().charAt(0).toUpperCase() || "U";
  if (els.profileName) els.profileName.textContent = name;
  if (els.profileEmail) els.profileEmail.textContent = state.currentUser.email || "Signed in";
  if (els.profileRoleBadge) els.profileRoleBadge.textContent = role;
}

function checkProfileSetup() {
  const modal = document.querySelector("#profileSetupModal");
  if (!modal) return;

  if (state.currentUser && !state.currentUser.profile_completed && !state.currentUser.is_admin) {
    const emailEl = document.querySelector("#profileSetupUserEmail");
    if (emailEl) emailEl.textContent = state.currentUser.email || "";

    const nameInput = document.querySelector("#profileSetupNameInput");
    if (nameInput && !nameInput.value) {
      nameInput.value = state.currentUser.name || state.currentUser.full_name || "";
    }

    const phoneInput = document.querySelector("#profileSetupPhoneInput");
    if (phoneInput && !phoneInput.value) {
      phoneInput.value = state.currentUser.phone || "";
    }

    const authMethodEl = document.querySelector("#profileSetupAuthMethod");
    const authIconEl = document.querySelector("#profileSetupAuthIcon");
    const isGoogle = state.currentUser.auth_provider === "google";
    if (authMethodEl) authMethodEl.textContent = isGoogle ? "Google OAuth" : "Email";
    if (authIconEl) authIconEl.textContent = isGoogle ? "🌐" : "📧";

    const type = state.currentUser.account_type || "B2C";
    setProfileSetupMode(type);

    if (!modal.open) {
      modal.showModal();
    }
  } else {
    if (modal.open) {
      modal.close();
    }
  }
}

function setProfileSetupMode(mode) {
  const accountTypeInput = document.querySelector("#profileSetupAccountType");
  if (accountTypeInput) accountTypeInput.value = mode;

  const tabB2C = document.querySelector("#profileSetupTabB2C");
  const tabB2B = document.querySelector("#profileSetupTabB2B");
  if (tabB2C) tabB2C.classList.toggle("active", mode === "B2C");
  if (tabB2B) tabB2B.classList.toggle("active", mode === "B2B");

  const businessFields = document.querySelector("#profileSetupBusinessFields");
  if (businessFields) {
    if (mode === "B2B") {
      businessFields.style.display = "grid";
      businessFields.classList.remove("hidden");
      businessFields.querySelectorAll("input").forEach(input => {
        input.disabled = false;
        input.required = (input.name === "company_name");
      });
    } else {
      businessFields.style.display = "none";
      businessFields.classList.add("hidden");
      businessFields.querySelectorAll("input").forEach(input => {
        input.disabled = true;
        input.required = false;
      });
    }
  }
}

function bindProfileSetup() {
  const tabB2C = document.querySelector("#profileSetupTabB2C");
  const tabB2B = document.querySelector("#profileSetupTabB2B");

  tabB2C?.addEventListener("click", () => setProfileSetupMode("B2C"));
  tabB2B?.addEventListener("click", () => setProfileSetupMode("B2B"));

  const profileSetupForm = document.querySelector("#profileSetupForm");
  profileSetupForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (profileSetupForm.dataset.busy === "true") return;
    setFormBusy(profileSetupForm, true, "Saving...");
    try {
      const body = Object.fromEntries(new FormData(profileSetupForm).entries());
      body.account_type = document.querySelector("#profileSetupAccountType")?.value || "B2C";
      
      const data = await api("/api/auth/complete-profile", {
        method: "POST",
        body: JSON.stringify(body)
      });
      toast(data.message || "Profile completed successfully!");
      state.currentUser = data.user;
      
      if (data.auth_token) {
        state.authToken = data.auth_token;
        localStorage.setItem("mc_auth_token", data.auth_token);
      }
      
      updateAuthUi();
      
      const modal = document.querySelector("#profileSetupModal");
      if (modal) modal.close();

      // Redirect based on role
      let targetUrl = "/";
      if (state.currentUser.is_admin) {
        targetUrl = "/admin";
      } else if ((state.currentUser.account_type || "B2C") === "B2B") {
        targetUrl = "/admin";
      } else {
        targetUrl = "/#account-settings";
      }
      window.location.assign(targetUrl);
    } catch (error) {
      toast(error.message);
    } finally {
      setFormBusy(profileSetupForm, false);
    }
  });

  document.querySelector("#profileSetupLogoutBtn")?.addEventListener("click", async () => {
    const modal = document.querySelector("#profileSetupModal");
    if (modal) modal.close();
    await logout();
  });


  document.querySelector("#profileSetupEmailBtn")?.addEventListener("click", async () => {
    const modal = document.querySelector("#profileSetupModal");
    if (modal) modal.close();
    await logout();
    showAuth("login", "B2C");
  });

  const modal = document.querySelector("#profileSetupModal");
  modal?.addEventListener("cancel", (event) => {
    event.preventDefault(); // Prevents escape closing
  });
}

function addToCart(productId) {
  const product = state.products.find(item => item.id === productId);
  if (!product) return;
  const existing = state.cart.find(item => item.id === productId);
  if (existing) {
    existing.quantity = Math.min(existing.quantity + 1, product.stock);
  } else {
    state.cart.push({
      id: product.id,
      product_id: product.id,
      name: product.name,
      sku: product.sku || "",
      slug: product.slug || "",
      price: product.price,
      image_url: product.image_url,
      quantity: 1
    });
  }
  saveCart();
  openCart();
  api("/api/events", {
    method: "POST",
    body: JSON.stringify({ type: "cart_add", product_id: product.id })
  }).catch(() => {});
  toast("Added to cart");
}

function productForCartItem(item) {
  const storedId = item.product_id || item.id;
  return state.products.find(product => product.id === storedId)
    || state.products.find(product => product.name === item.name);
}

function checkoutItemsFromCart() {
  const rows = new Map();
  const repairedCart = [];
  let removedCount = 0;

  state.cart.forEach(item => {
    const product = productForCartItem(item);
    const quantity = Math.max(1, Number(item.quantity) || 1);
    if (!product || Number(product.stock || 0) <= 0) {
      removedCount += quantity;
      return;
    }
    const current = rows.get(product.id) || {
      product_id: product.id,
      quantity: 0,
      product,
    };
    current.quantity = Math.min(Number(product.stock || 0), current.quantity + quantity);
    rows.set(product.id, current);
  });

  rows.forEach(row => {
    repairedCart.push({
      id: row.product.id,
      product_id: row.product.id,
      name: row.product.name,
      sku: row.product.sku || "",
      slug: row.product.slug || "",
      price: row.product.price,
      image_url: row.product.image_url,
      quantity: row.quantity,
    });
  });

  if (removedCount || repairedCart.length !== state.cart.length) {
    state.cart = repairedCart;
    saveCart();
  }

  return repairedCart.map(item => {
    const product = productForCartItem(item);
    return {
      product_id: item.product_id,
      sku: item.sku || product?.sku || "",
      slug: item.slug || product?.slug || "",
      name: item.name || product?.name || "",
      quantity: item.quantity,
    };
  });
}

async function showProduct(productId) {
  const product = state.products.find(item => item.id === productId);
  if (!product) return;

  try {
    const specs = Object.entries(product.specs || {});
    els.productModal.innerHTML = `
      <form method="dialog" class="modal-close-row"><button class="icon-btn" aria-label="Close">&times;</button></form>
      <div class="detail-grid">
        <div class="detail-image">
          <img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}" onerror="this.src='/static/images/product-placeholder.webp'">
        </div>
        <div>
          <p class="eyebrow">${escapeHtml(product.category || "Microchip")}</p>
          <h2>${escapeHtml(product.name)}</h2>
          <p class="form-help">${escapeHtml(product.description)}</p>
          <div class="meta-row">${productStars(product)}</div>
          <div class="price-row">
            <span class="price">${moneyLabel(product.price)}</span>
            <span class="stock">${product.stock} in stock</span>
          </div>
          <div class="spec-grid">
            ${specs.map(([key, value]) => `<div><span>${escapeHtml(key)}</span>${escapeHtml(value)}</div>`).join("")}
          </div>
          <div class="card-actions">
            <button class="primary-btn" type="button" data-add-cart="${product.id}">Add to Cart</button>
            ${product.datasheet_url ? `<a class="secondary-btn" href="${escapeHtml(product.datasheet_url)}" target="_blank" rel="noreferrer">Datasheet</a>` : `<button class="secondary-btn" type="button" disabled>No datasheet</button>`}
          </div>
          <form id="reviewForm" class="checkout-form" style="margin-top:18px">
            <h2>Rate this product</h2>
            <div class="two-col">
              <label>Rating
                <select name="rating" required>
                  <option value="5">5 stars</option>
                  <option value="4">4 stars</option>
                  <option value="3">3 stars</option>
                  <option value="2">2 stars</option>
                  <option value="1">1 star</option>
                </select>
              </label>
              <label>Review<input name="comment" placeholder="Short review"></label>
            </div>
            <button class="secondary-btn" type="submit">Submit review</button>
          </form>
          <div class="review-list" id="modalReviewList">
            <p class="form-help">Loading reviews...</p>
          </div>
        </div>
      </div>
    `;
    els.productModal.showModal();

    document.querySelector("#reviewForm").addEventListener("submit", async event => {
      event.preventDefault();
      if (!state.currentUser) {
        els.productModal.close();
        showAuth("login");
        return;
      }
      const body = Object.fromEntries(new FormData(event.currentTarget).entries());
      try {
        await api(`/api/products/${product.id}/reviews`, {
          method: "POST",
          body: JSON.stringify(body)
        });
        toast("Review added");
        els.productModal.close();
        await loadProducts();
      } catch (error) {
        toast(error.message);
      }
    });

    // Load reviews asynchronously
    api(`/api/products/${productId}`).then(data => {
      const reviewList = document.querySelector("#modalReviewList");
      if (reviewList) {
        reviewList.innerHTML = (data.reviews || []).map(review => `
          <article class="review">
            <strong>${escapeHtml(review.name || "Customer")} &middot; ${Array.from({ length: review.rating }, () => "&#9733;").join("")}</strong>
            <p>${escapeHtml(review.comment || "Rated this product")}</p>
          </article>
        `).join("") || `<p class="form-help">No reviews yet.</p>`;
      }
    }).catch(error => {
      console.warn("Async reviews load failed:", error);
      const reviewList = document.querySelector("#modalReviewList");
      if (reviewList) {
        reviewList.innerHTML = `<p class="form-help">Could not load reviews.</p>`;
      }
    });

  } catch (error) {
    toast(error.message);
  }
}

function setAuthMode(mode = "B2C") {
  state.authMode = mode === "B2B" ? "B2B" : "B2C";
  const isBusiness = state.authMode === "B2B";
  document.querySelectorAll("[data-auth-mode]").forEach(button => {
    button.classList.toggle("active", button.dataset.authMode === state.authMode);
  });
  document.querySelectorAll("[data-auth-title]").forEach(node => {
    node.textContent = isBusiness ? "Business" : "Customer";
  });
  document.querySelectorAll("[data-auth-help]").forEach(node => {
    node.textContent = isBusiness
      ? "Business accounts are for companies, distributors, GST invoices, and order approvals."
      : "Customer accounts are for individual purchases, order tracking, and quick reorders.";
  });
  document.querySelectorAll("#loginForm [name='account_type'], #resetPasswordForm [name='account_type'], #signupForm [name='account_type']").forEach(input => {
    input.value = state.authMode;
  });
  const signupPhone = document.querySelector("#signupForm [name='phone']");
  if (signupPhone) {
    signupPhone.required = false;
    signupPhone.placeholder = isBusiness ? "Optional business contact number" : "";
  }
  setBusinessFields(document.querySelector("#signupForm"), "account_type");
}

function showAuth(tab = "login", mode = state.authMode) {
  setAuthMode(mode);
  document.querySelectorAll("[data-auth-tab]").forEach(button => {
    button.classList.toggle("active", button.dataset.authTab === tab);
  });
  document.querySelectorAll("[data-auth-panel]").forEach(panel => {
    panel.classList.toggle("active", panel.dataset.authPanel === tab);
  });
  if (els.authModal && !els.authModal.open) els.authModal.showModal();
}

function setFormBusy(form, busy, label) {
  if (!form) return;
  form.dataset.busy = busy ? "true" : "false";
  const submit = form.querySelector("[type='submit']");
  if (!submit) return;
  if (busy) {
    submit.dataset.defaultText = submit.textContent;
    submit.textContent = label || "Please wait...";
  } else if (submit.dataset.defaultText) {
    submit.textContent = submit.dataset.defaultText;
  }
  submit.disabled = Boolean(busy);
}

async function ensureCurrentUser() {
  if (state.currentUser) return state.currentUser;
  await loadMe();
  return state.currentUser;
}

function authDestination() {
  return (state.currentUser?.account_type || "B2C") === "B2B" ? "/admin" : "/";
}

function setBusinessFields(form, fieldName) {
  if (!form) return;
  const selected = form.querySelector(`[name="${fieldName}"]:checked`)?.value || form.querySelector(`[name="${fieldName}"]`)?.value || "B2C";
  const fields = form.querySelector(".business-fields");
  if (!fields) return;
  const isBusiness = selected === "B2B";
  fields.classList.toggle("hidden", !isBusiness);
  fields.querySelectorAll("input").forEach(input => {
    input.disabled = !isBusiness;
    if (!isBusiness) input.value = "";
  });
}

function bindBusinessFields(formSelector, fieldName) {
  const form = document.querySelector(formSelector);
  if (!form) return;
  form.querySelectorAll(`[name="${fieldName}"]`).forEach(input => {
    input.addEventListener("change", () => setBusinessFields(form, fieldName));
  });
  setBusinessFields(form, fieldName);
}

function bindAuth() {
  document.querySelectorAll("[data-auth-mode]").forEach(button => {
    button.addEventListener("click", () => setAuthMode(button.dataset.authMode));
  });

  els.authModal?.addEventListener("close", () => {
    if (!state.currentUser) state.pendingAuthAction = null;
  });

  document.querySelectorAll("[data-auth-tab]").forEach(button => {
    button.addEventListener("click", () => showAuth(button.dataset.authTab));
  });

  document.querySelectorAll("[data-password-toggle]").forEach(button => {
    button.addEventListener("click", () => {
      const input = button.closest(".password-field")?.querySelector("input");
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.setAttribute("aria-label", show ? "Hide password" : "Show password");
      button.classList.toggle("active", show);
    });
  });

  document.querySelector("#forgotPasswordBtn")?.addEventListener("click", () => {
    const loginEmail = document.querySelector("#loginForm [name='email']")?.value || "";
    const resetEmail = document.querySelector("#resetPasswordForm [name='email']");
    if (resetEmail && loginEmail) resetEmail.value = loginEmail;
    showAuth("reset", state.authMode);
  });

  document.querySelector("#loginForm").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    if (form.dataset.busy === "true") return;
    setFormBusy(form, true, "Logging in...");
    try {
      const body = Object.fromEntries(new FormData(form).entries());
      body.account_type = state.authMode;
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(body),
        timeoutMs: 10000
      });
      state.currentUser = data.user;
      if (data.auth_token) {
        state.authToken = data.auth_token;
        localStorage.setItem("mc_auth_token", data.auth_token);
      }
      const pendingAction = state.pendingAuthAction;
      state.pendingAuthAction = null;
      els.authModal.close();
      updateAuthUi();
      toast("Logged in");
      if (pendingAction === "checkout") {
        await checkout();
        return;
      }
      const redirectUrl = data.redirect_url || authDestination();
      if (redirectUrl && redirectUrl !== "/" && redirectUrl !== window.location.pathname) {
        window.location.assign(redirectUrl);
      }
    } catch (error) {
      toast(error.message);
    } finally {
      setFormBusy(form, false);
    }
  });

  const resetPasswordForm = document.querySelector("#resetPasswordForm");
  const sendPasswordResetBtn = document.querySelector("#sendPasswordResetBtn");
  sendPasswordResetBtn?.addEventListener("click", async () => {
    if (!resetPasswordForm || sendPasswordResetBtn.disabled) return;
    const email = String(resetPasswordForm.querySelector("[name='email']")?.value || "").trim();
    if (!email) {
      toast("Email is required.");
      return;
    }
    const defaultLabel = sendPasswordResetBtn.textContent;
    sendPasswordResetBtn.disabled = true;
    sendPasswordResetBtn.textContent = "Sending...";
    try {
      const data = await api("/api/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email, account_type: state.authMode })
      });
      if (data.password_reset_fallback && data.reset_code) {
        const codeInput = resetPasswordForm.querySelector("[name='code']");
        if (codeInput) codeInput.value = data.reset_code;
      }
      toast(data.message || "If an account exists for that email, a reset code has been sent.");
    } catch (error) {
      toast(error.message);
    } finally {
      sendPasswordResetBtn.disabled = false;
      sendPasswordResetBtn.textContent = defaultLabel;
    }
  });

  resetPasswordForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    if (form.dataset.busy === "true") return;
    setFormBusy(form, true, "Resetting...");
    try {
      const body = Object.fromEntries(new FormData(form).entries());
      body.account_type = state.authMode;
      const data = await api("/api/auth/reset-password", {
        method: "POST",
        body: JSON.stringify(body)
      });
      state.currentUser = data.user || null;
      if (data.auth_token) {
        state.authToken = data.auth_token;
        localStorage.setItem("mc_auth_token", data.auth_token);
      }
      els.authModal.close();
      updateAuthUi();
      toast(data.message || "Password reset.");
      const redirectUrl = data.redirect_url || authDestination();
      if (redirectUrl && redirectUrl !== "/" && redirectUrl !== window.location.pathname) {
        window.location.assign(redirectUrl);
      }
    } catch (error) {
      toast(error.message);
    } finally {
      setFormBusy(form, false);
    }
  });

  const signupForm = document.querySelector("#signupForm");
  const sendEmailOtpBtn = document.querySelector("#sendEmailOtpBtn");


  const emailOtpLength = 6;
  const signupEmailInput = signupForm?.querySelector("[name='email']");
  const emailOtpInput = signupForm?.querySelector("[name='otp']");
  const otpEmailInput = signupForm?.querySelector("[name='otp_email']");
  const otpTokenInput = signupForm?.querySelector("[name='otp_token']");
  let emailOtpCooldownTimer = null;
  const startEmailOtpCooldown = seconds => {
    if (!sendEmailOtpBtn) return;
    clearInterval(emailOtpCooldownTimer);
    const defaultLabel = "Send Email OTP";
    let remaining = Math.max(1, Number(seconds) || 60);
    sendEmailOtpBtn.disabled = true;
    sendEmailOtpBtn.textContent = "OTP sent";
    emailOtpCooldownTimer = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearInterval(emailOtpCooldownTimer);
        emailOtpCooldownTimer = null;
        sendEmailOtpBtn.disabled = false;
        sendEmailOtpBtn.textContent = defaultLabel;
        return;
      }
    }, 1000);
  };





  sendEmailOtpBtn?.addEventListener("click", async () => {
    if (sendEmailOtpBtn.disabled) return;
    const email = String(signupEmailInput?.value || "").trim();
    if (!email) {
      toast("Email is required.");
      return;
    }
    sendEmailOtpBtn.disabled = true;
    const defaultOtpLabel = sendEmailOtpBtn.textContent;
    sendEmailOtpBtn.textContent = "Sending...";
    try {
      const response = await fetch("/api/auth/send-email-otp", {
        headers: { "Content-Type": "application/json" },
        method: "POST",
        body: JSON.stringify({ email })
      });
      const data = await response.json().catch(() => ({
        success: false,
        error: response.ok ? "Empty server response" : "Server is temporarily unavailable"
      }));
      if (!response.ok || data.success !== true) {
        throw new Error(data.error || "Could not send email OTP. Please try again.");
      }
      if (emailOtpInput) emailOtpInput.value = "";
      if (otpEmailInput) otpEmailInput.value = email;
      if (otpTokenInput) otpTokenInput.value = data.otp_token || "";
      if (data.verification_fallback && data.otp && emailOtpInput) {
        emailOtpInput.value = data.otp;
      }
      if (data.otp_token) localStorage.setItem("mc_email_otp", JSON.stringify({ email, token: data.otp_token }));
      toast(data.message || "OTP sent to your email.");
      startEmailOtpCooldown(data.cooldown_seconds || 60);
    } catch (error) {
      toast(error.message);
      sendEmailOtpBtn.disabled = false;
      sendEmailOtpBtn.textContent = defaultOtpLabel;
    } finally {
      if (!emailOtpCooldownTimer) {
        sendEmailOtpBtn.disabled = false;
        sendEmailOtpBtn.textContent = defaultOtpLabel;
      }
    }
  });

  signupEmailInput?.addEventListener("input", () => {
    const email = String(signupEmailInput.value || "").trim();
    if (!otpEmailInput?.value || otpEmailInput.value === email) return;
    if (emailOtpInput) emailOtpInput.value = "";
    if (otpTokenInput) otpTokenInput.value = "";
    otpEmailInput.value = "";
    localStorage.removeItem("mc_email_otp");
  });

  document.querySelector("#signupForm").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    if (form.dataset.busy === "true") return;
    setFormBusy(form, true, "Creating...");
    try {
      const body = Object.fromEntries(new FormData(form).entries());
      body.account_type = state.authMode;
      const visibleEmail = String(body.email || "").trim();
      const otpEmail = String(body.otp_email || "").trim();
      if (otpEmail && otpEmail !== visibleEmail) {
        toast("Please request a new OTP for this email.");
        return;
      }
      body.email = visibleEmail;
      body.otp_token = String(body.otp_token || "");
      if (!body.otp_token) {
        try {
          const savedOtp = JSON.parse(localStorage.getItem("mc_email_otp") || "{}");
          if (savedOtp.email === body.email && savedOtp.token) body.otp_token = savedOtp.token;
        } catch (error) {}
      }
      body.otp = String(body.otp || "").trim();
      if (body.otp.length !== emailOtpLength) {
        toast("Invalid or expired OTP. Please request a new code.");
        return;
      }

      const data = await api("/api/auth/verify-email-otp", {
        method: "POST",
        body: JSON.stringify(body)
      });
      toast(data.message || "Account created successfully.");
      localStorage.removeItem("mc_email_otp");
      form?.reset?.();

      if (data.auth_token && data.user) {
        state.currentUser = data.user;
        state.authToken = data.auth_token;
        localStorage.setItem("mc_auth_token", data.auth_token);
        updateAuthUi();
        els.authModal.close();
        const redirectUrl = data.redirect_url || authDestination();
        if (redirectUrl && redirectUrl !== "/" && redirectUrl !== window.location.pathname) {
          window.location.assign(redirectUrl);
          return;
        }
      } else {
        showAuth("login", state.authMode);
      }
    } catch (error) {
      toast(error.message);
    } finally {
      setFormBusy(form, false);
    }
  });
}

function handleHashRoute() {
  const params = new URLSearchParams(window.location.search || "");
  if (params.get("google_oauth") === "failed") {
    toast("Google signup failed. Please try again or use email signup.");
    window.history.replaceState({}, document.title, `${window.location.pathname}${window.location.hash || ""}`);
  }
  if (params.get("pending_approval") === "1") {
    toast("Your business account is pending approval. Please wait for an administrator to review your details.");
    window.history.replaceState({}, document.title, `${window.location.pathname}${window.location.hash || ""}`);
  }
  const hash = decodeURIComponent(location.hash || "");
  const categoryHashMap = {
    "#microcontrollers": "Microcontroller",
    "#mcu": "Microcontroller",
    "#wireless": "Wireless Module",
    "#sensors": "Sensor",
    "#sensor": "Sensor",
    "#power": "Power IC",
    "#connectors": "Connector",
    "#boards": "Development Board",
    "#bulk": "Microcontroller",
    "#deals": "All"
  };
  if (hash === "#login") showAuth("login");
  if (hash === "#signup") showAuth("signup");
  if (hash === "#account-settings") showSettings();
  if (categoryHashMap[hash.toLowerCase()]) {
    setCategory(categoryHashMap[hash.toLowerCase()], { scrollToProducts: true });
  }
  if (hash.startsWith("#payment=success")) {
    state.cart = [];
    saveCart();
    toast("Payment received. Your order is being prepared.");
  }
  if (hash.startsWith("#payment=cancel")) {
    toast("Payment was cancelled. Your cart is still available to retry.");
  }
}

async function checkout() {
  if (!state.cart.length) {
    toast("Cart is empty");
    return;
  }
  const user = await ensureCurrentUser();
  if (!user) {
    state.pendingAuthAction = "checkout";
    closeCart();
    showAuth("login", "B2C");
    return;
  }
  api("/api/events", { method: "POST", body: JSON.stringify({ type: "checkout_open" }) }).catch(() => {});
  const form = document.querySelector("#checkoutForm");
  form.name.value = user.name || "";
  form.email.value = user.email || "";
  form.phone.value = user.phone || "";
  form.order_type.value = user.account_type || "B2C";
  form.company_name.value = user.company_name || "";
  form.gstin.value = user.gstin || "";
  syncCheckoutLocation(savedDeliveryLocation(), false);
  setBusinessFields(form, "order_type");
  if (els.checkoutModal && !els.checkoutModal.open) els.checkoutModal.showModal();
}

function bindCheckout() {
  document.querySelector("#checkoutBtn").addEventListener("click", checkout);
  document.querySelector("#checkoutForm").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    if (form.dataset.busy === "true") return;
    setFormBusy(form, true, "Placing...");
    const address = Object.fromEntries(new FormData(form).entries());
    const paymentMethod = address.payment_method;
    delete address.payment_method;
    try {
      if (address.pincode || address.city) {
        setDeliveryLocation({
          city: address.city || address.line1 || "",
          pincode: address.pincode || "",
          state: address.state || ""
        });
      }
      const user = await ensureCurrentUser();
      if (!user) {
        state.pendingAuthAction = "checkout";
        if (els.checkoutModal?.open) els.checkoutModal.close();
        showAuth("login", "B2C");
        return;
      }
      api("/api/events", {
        method: "POST",
        body: JSON.stringify({ type: "payment_selected", metadata: { payment_method: paymentMethod } })
      }).catch(() => {});
      const items = checkoutItemsFromCart();
      if (!items.length) {
        toast("Cart refreshed. Please add an available product again.");
        els.checkoutModal.close();
        openCart();
        return;
      }
      const orderPayload = {
        items,
        address,
        payment_method: paymentMethod,
        auth_token: state.authToken || localStorage.getItem("mc_auth_token") || ""
      };
      if (!orderPayload.auth_token) {
        await loadMe();
        orderPayload.auth_token = state.authToken || localStorage.getItem("mc_auth_token") || "";
      }
      const data = await api("/api/orders", {
        method: "POST",
        body: JSON.stringify(orderPayload),
        timeoutMs: 12000
      });
      state.cart = [];
      saveCart();
      closeCart();
      els.checkoutModal.close();
      toast(`Order placed: ${data.order.invoice_number}`);
      renderProducts();
    } catch (error) {
      if (error.status === 401 && /login/i.test(error.message || "")) {
        state.currentUser = null;
        state.pendingAuthAction = "checkout";
        if (els.checkoutModal?.open) els.checkoutModal.close();
        showAuth("login", "B2C");
        toast("Please login again to finish checkout.");
        return;
      }
      toast(error.message);
    } finally {
      setFormBusy(form, false);
    }
  });
}

async function showOrders() {
  if (!state.currentUser) {
    showAuth("login", "B2C");
    return;
  }

  const list = document.querySelector("#ordersList");
  const modalTitle = els.ordersModal?.querySelector("h2");
  if (modalTitle) modalTitle.textContent = "Your orders";
  if (list) {
    list.innerHTML = `<p class="form-help">Loading your orders...</p>`;
  }
  els.ordersModal.showModal();

  try {
    const data = await api("/api/orders/my");
    if (list) {
      list.innerHTML = data.orders.length ? data.orders.map(order => `
        <article class="order-card">
          <header>
            <strong>${escapeHtml(order.invoice_number)}</strong>
            <span class="pill">${escapeHtml(order.status)}</span>
          </header>
          ${order.business?.order_type === "B2B" ? `<p class="order-business">${escapeHtml(order.business.company_name || "Business order")}${order.business.gstin ? ` &middot; GSTIN ${escapeHtml(order.business.gstin)}` : ""}</p>` : ""}
          <div class="order-items">
            ${order.items.map(item => `
              <div class="order-item-row">
                <span>${escapeHtml(item.name)} x ${item.quantity}</span>
                <strong>${moneyLabel(item.line_total)}</strong>
              </div>
            `).join("")}
          </div>
          <div class="order-total-row">
            <span>${escapeHtml(order.payment_status)}</span>
            <strong>${moneyLabel(order.totals.total)}</strong>
          </div>
          ${order.status === "Pending" ? `
            <div style="margin-top: 10px; text-align: right;">
              <button class="secondary-btn cancel-order-btn" style="min-height:30px; font-size:12px; background-color: rgba(239, 68, 68, 0.08); color: var(--danger, #ef4444); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 12px; padding: 4px 12px; cursor: pointer; font-weight: 600;" data-order-id="${order.id}">Cancel Order</button>
            </div>
          ` : ""}
        </article>
      `).join("") : `<p class="form-help">No orders yet.</p>`;
    }
  } catch (error) {
    toast(error.message);
    if (list) {
      list.innerHTML = `<p class="form-help">Failed to load orders.</p>`;
    }
  }
}

function showSettings() {
  if (!state.currentUser) {
    showAuth("login", "B2C");
    return;
  }
  const user = state.currentUser;
  const form = els.profileSettingsForm;
  form.name.value = user.name || "";
  form.email.value = user.email || "";
  form.phone.value = user.phone || "";
  form.account_type.value = user.account_type || "B2C";
  form.company_name.value = user.company_name || "";
  form.gstin.value = user.gstin || "";
  document.querySelector("#settingsBusinessFields")?.classList.toggle("hidden", (user.account_type || "B2C") !== "B2B");
  if (els.settingsThemeSelect) els.settingsThemeSelect.value = document.body.dataset.theme || "light";
  activateSettingsTab("profile");
  if (!els.settingsModal.open) els.settingsModal.showModal();
}

async function logout() {
  await api("/api/auth/logout", { method: "POST", body: "{}" });
  state.currentUser = null;
  state.authToken = "";
  localStorage.removeItem("mc_auth_token");
  await loadMe();
  toast("Logged out");
}

function activateSettingsTab(tab) {
  document.querySelectorAll("[data-settings-tab]").forEach(button => {
    button.classList.toggle("active", button.dataset.settingsTab === tab);
  });
  document.querySelectorAll("[data-settings-panel]").forEach(panel => {
    panel.classList.toggle("active", panel.dataset.settingsPanel === tab);
  });
}

function bindSettings() {
  document.querySelectorAll("[data-settings-tab]").forEach(button => {
    button.addEventListener("click", () => activateSettingsTab(button.dataset.settingsTab));
  });
  els.profileSettingsForm?.addEventListener("submit", async event => {
    event.preventDefault();
    try {
      const body = Object.fromEntries(new FormData(event.currentTarget).entries());
      const data = await api("/api/auth/me", {
        method: "PATCH",
        body: JSON.stringify(body)
      });
      state.currentUser = data.user;
      updateAuthUi();
      showSettings();
      toast("Profile updated");
    } catch (error) {
      toast(error.message);
    }
  });
  els.passwordSettingsForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const body = Object.fromEntries(new FormData(form).entries());
      if (!await confirmSignedIn()) {
        els.settingsModal?.close();
        showAuth("login");
        throw new Error("Your login expired. Please log in again.");
      }
      body.auth_token = state.authToken || localStorage.getItem("mc_auth_token") || "";
      let data;
      try {
        data = await api("/api/auth/change-password", {
          method: "POST",
          body: JSON.stringify(body)
        });
      } catch (error) {
        if (error.status !== 401 || !/login/i.test(error.message || "")) {
          throw error;
        }
        if (!await confirmSignedIn()) {
          els.settingsModal?.close();
          showAuth("login");
          throw new Error("Your login expired. Please log in again.");
        }
        body.auth_token = state.authToken || localStorage.getItem("mc_auth_token") || "";
        data = await api("/api/auth/change-password", {
          method: "POST",
          body: JSON.stringify(body)
        });
      }
      if (data.auth_token) {
        state.authToken = data.auth_token;
        localStorage.setItem("mc_auth_token", data.auth_token);
      }
      form.reset();
      toast("Password changed");
    } catch (error) {
      toast(error.message);
    }
  });
  els.settingsThemeSelect?.addEventListener("change", event => {
    setTheme(event.target.value);
    toast(`${event.target.value === "dark" ? "Cyber Blue" : "Deep Cyan"} theme applied`);
  });
  els.settingsLogoutBtn?.addEventListener("click", async () => {
    els.settingsModal.close();
    await logout();
  });
  els.deleteAccountForm?.addEventListener("submit", async event => {
    event.preventDefault();
    if (!confirm("Are you sure you want to permanently delete your account? This action cannot be undone and all your profile settings will be lost.")) {
      return;
    }
    const body = Object.fromEntries(new FormData(event.currentTarget).entries());
    try {
      await api("/api/auth/me", {
        method: "DELETE",
        body: JSON.stringify(body)
      });
      state.currentUser = null;
      state.authToken = "";
      state.cart = [];
      state.wishlist = [];
      localStorage.removeItem("mc_auth_token");
      localStorage.removeItem("mc_cart");
      localStorage.removeItem("mc_wishlist");
      localStorage.removeItem("mc_email_otp");
      els.settingsModal.close();
      toast("Account deleted successfully.");
      setTimeout(() => {
        window.location.href = "/";
      }, 1500);
    } catch (error) {
      toast(error.message);
    }
  });
}

function closeProfileMenu() {
  els.profileMenu?.classList.remove("open");
  els.profileBtn?.setAttribute("aria-expanded", "false");
  refreshPageScrollLock();
}

function closeGuestAccountMenu() {
  els.guestAccountMenu?.classList.remove("open");
  els.authBtn?.setAttribute("aria-expanded", "false");
  refreshPageScrollLock();
}

function closeOrdersMenu() {
  els.ordersNavTrigger?.classList.remove("open");
  els.ordersNavTrigger?.setAttribute("aria-expanded", "false");
  refreshPageScrollLock();
}

function toggleGuestAccountMenu() {
  const isOpen = els.guestAccountMenu.classList.toggle("open");
  els.authBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
  if (isOpen) {
    closeProfileMenu();
    closeOrdersMenu();
  }
  refreshPageScrollLock();
}

function toggleProfileMenu() {
  const isOpen = els.profileMenu.classList.toggle("open");
  els.profileBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
  if (isOpen) {
    closeGuestAccountMenu();
    closeOrdersMenu();
  }
  refreshPageScrollLock();
}

function toggleOrdersMenu() {
  if (!els.ordersNavTrigger) return;
  const isOpen = els.ordersNavTrigger.classList.toggle("open");
  els.ordersNavTrigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
  if (isOpen) {
    closeGuestAccountMenu();
    closeProfileMenu();
  }
  refreshPageScrollLock();
}

function helpTopicContent(topic) {
  const topics = {
    returns: {
      title: "Returns",
      body: [
        "Start a return by contacting Microchip Cart with your invoice number, product name, order date, and issue details.",
        "Items should be unused, in original packaging, with labels and invoice available. Damaged, incorrect, or missing items should be reported as soon as possible.",
        "Return approval depends on product condition, supplier rules, warranty terms, and applicable law."
      ]
    },
    account: {
      title: "Your account",
      body: [
        "Create an account to track orders, keep a wishlist, save profile details, and checkout faster.",
        "Open the profile menu after login to view orders, cart, wishlist, and settings.",
        "In settings you can update your profile, change password, change theme, read privacy terms, log out, or delete your account."
      ]
    },
    help: {
      title: "Help",
      body: [
        "For product help, use the AI chip assistant on the bottom right or search by product name, model, SKU, brand, or category.",
        "For order help, contact Microchip Cart at microchipcaty025@gmail.com or 9175536112.",
        "Business buyers can switch to a business account for GST details, invoices, and business order workflows."
      ]
    }
  };
  return topics[topic] || topics.help;
}

function showHelpTopic(topic) {
  const content = helpTopicContent(topic);
  els.helpContent.innerHTML = `
    <p class="eyebrow">Let us help you</p>
    <h2>${escapeHtml(content.title)}</h2>
    <div class="help-topic-body">
      ${content.body.map(item => `<p>${escapeHtml(item)}</p>`).join("")}
    </div>
  `;
  els.helpModal.showModal();
}

function productKnowledgeText() {
  if (!state.products.length) {
    return "I do not see live products loaded yet. Try again after the catalog finishes loading.";
  }
  return state.products.map(product => {
    return `• **${product.name}** (${product.sku || product.model || "SKU"}): ${moneyLabel(product.price)} | [View Details](product:${product.id})`;
  }).join("\n");
}

function findChipMatches(message) {
  const query = message.toLowerCase().trim();
  if (!query) return [];
  return state.products.filter(product => {
    const haystack = `${product.name} ${product.description} ${product.sku} ${product.model} ${product.brand} ${product.category} ${Object.values(product.specs || {}).join(" ")}`.toLowerCase();
    if (haystack.includes(query)) return true;
    return query.split(/\s+/).some(word => word.length >= 2 && haystack.includes(word));
  }).slice(0, 3);
}

function chatbotAnswer(message) {
  const text = message.toLowerCase();
  const matches = findChipMatches(message);
  if (text.includes("available") || text.includes("website") || text.includes("site") || text.includes("products")) {
    return `Here are the products currently on Microchip Cart:\n\n${productKnowledgeText()}`;
  }
  if (matches.length) {
    return `I found these matching products on this website:\n\n${matches.map(product => `**${product.name}**\n• Price: ${moneyLabel(product.price)} | Stock: ${product.stock > 0 ? `${product.stock} units` : "Out of stock"}\n• Details: ${product.description || "No description available."}\n[View details & buy product](product:${product.id})`).join("\n\n")}\n\nFor purchasing, check voltage, package, clock speed, memory, connectivity, stock, and whether you need a development module or bare IC.`;
  }
  if (text.includes("esp32") || text.includes("iot") || text.includes("wifi") || text.includes("bluetooth")) {
    return "For IoT, ESP32-family chips are usually a strong choice because they combine MCU, WiFi, Bluetooth/BLE, GPIO, and good community support. Use them for connected sensors, smart devices, dashboards, and wireless control. Check flash size, antenna type, module certification, and 3.3V power design.";
  }
  if (text.includes("stm32") || text.includes("arm") || text.includes("cortex")) {
    return "STM32 parts are good when you need stronger real-time control, timers, ADCs, USB/CAN/SPI/I2C/UART options, and ARM Cortex performance. Choose by core family, clock, flash/RAM, package, peripherals, and toolchain support.";
  }
  if (text.includes("atmega") || text.includes("arduino") || text.includes("avr")) {
    return "ATmega328P and related AVR chips are friendly for Arduino-compatible projects, learning, simple control, DIP prototyping, and low-complexity embedded work. They are not ideal for WiFi-heavy or high-performance tasks unless paired with extra modules.";
  }
  if (text.includes("compare") || text.includes("difference")) {
    return "A good comparison checklist: processing speed, flash/RAM, GPIO count, ADC/PWM/timers, communication interfaces, voltage, package, power use, temperature range, ecosystem, price, stock, and whether your project needs wireless connectivity.";
  }
  if (text.includes("sensor")) {
    return "For sensor projects, pick a microcontroller with enough ADC resolution, I2C/SPI/UART interfaces, stable 3.3V or 5V compatibility, low-noise power, and sleep modes if battery life matters. ESP32 suits wireless sensors; STM32 suits precision control; ATmega suits simple prototypes.";
  }
  if (text.includes("help") || text.includes("choose") || text.includes("buy")) {
    return "Tell me your project goal, required connectivity, voltage, quantity, budget, and whether you need Arduino support. I can then suggest a chip type and check whether a matching product exists on this site.";
  }
  return "I can help with microcontrollers, wireless modules, Arduino/AVR, ESP32, STM32, sensors, package choice, voltage, memory, interfaces, and the products listed on Microchip Cart. Ask something like: 'Which chip for IoT?' or 'Compare ESP32 and ATmega328P'.";
}

function addChatMessage(role, message) {
  if (!els.chatbotMessages) return;
  const article = document.createElement("article");
  article.className = `chat-message ${role}`;
  
  let html = escapeHtml(message).replaceAll("\n", "<br>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\[([^\]]+)\]\(product:([a-zA-Z0-9_\-]+)\)/g, (match, text, id) => {
    return `<a href="#" class="chat-product-link" data-product-id="${id}">${text}</a>`;
  });
  
  article.innerHTML = `<strong>${role === "user" ? "You" : "Microman 🤖"}</strong><p>${html}</p>`;
  els.chatbotMessages.appendChild(article);
  els.chatbotMessages.scrollTop = els.chatbotMessages.scrollHeight;
}

function openChatbot() {
  els.chatbotPanel?.classList.remove("hidden");
  els.chatbotLauncher?.setAttribute("aria-expanded", "true");
  if (els.chatbotMessages && !els.chatbotMessages.dataset.ready) {
    addChatMessage("bot", "Hi! I'm **Microman** 🤖, your friendly chip expert! Ask me about any microcontroller, module, or sensor. If we have it in stock, I'll give you a direct link to check it out! ⚡");
    els.chatbotMessages.dataset.ready = "true";
  }
  els.chatbotInput?.focus();
}

function closeChatbot() {
  els.chatbotPanel?.classList.add("hidden");
  els.chatbotLauncher?.setAttribute("aria-expanded", "false");
}

function askChatbot(message) {
  const clean = message.trim();
  if (!clean) return;
  addChatMessage("user", clean);
  addChatMessage("bot", chatbotAnswer(clean));
}

function bindChatbot() {
  els.chatbotLauncher?.addEventListener("click", () => {
    if (els.chatbotPanel?.classList.contains("hidden")) openChatbot();
    else closeChatbot();
  });
  els.chatbotClose?.addEventListener("click", closeChatbot);
  els.chatbotForm?.addEventListener("submit", event => {
    event.preventDefault();
    askChatbot(els.chatbotInput.value);
    els.chatbotInput.value = "";
  });
  document.querySelectorAll("[data-chat-prompt]").forEach(button => {
    button.addEventListener("click", () => askChatbot(button.dataset.chatPrompt));
  });
  
  els.chatbotMessages?.addEventListener("click", event => {
    const link = event.target.closest(".chat-product-link");
    if (link) {
      event.preventDefault();
      const productId = link.dataset.productId;
      if (productId) {
        showProduct(productId);
      }
    }
  });
}

function bindEvents() {
  const handleSearchSubmit = event => {
    event.preventDefault();
    if (state.query.trim()) {
      saveSearchTerm(state.query.trim());
      renderSearchSuggestions();
      closeSearchSuggestions();
    }
  };
  
  document.querySelector("#searchFormDesktop")?.addEventListener("submit", handleSearchSubmit);
  document.querySelector("#searchFormMobile")?.addEventListener("submit", handleSearchSubmit);
  
  const handleSuggestionsClick = event => {
    const suggestBtn = event.target.closest("[data-suggestion-product]");
    if (suggestBtn) {
      const product = state.products.find(item => item.id === suggestBtn.dataset.suggestionProduct);
      if (!product) return;
      saveSearchTerm(product.name);
      state.query = product.name;
      if (els.search) els.search.value = product.name;
      if (els.searchMobile) els.searchMobile.value = product.name;
      renderSearchSuggestions();
      closeSearchSuggestions();
      renderProducts();
      showProduct(product.id);
      return;
    }
    
    const historyBtn = event.target.closest("[data-history-term]");
    if (historyBtn) {
      const term = historyBtn.dataset.historyTerm;
      saveSearchTerm(term);
      state.query = term;
      if (els.search) els.search.value = term;
      if (els.searchMobile) els.searchMobile.value = term;
      renderSearchSuggestions();
      closeSearchSuggestions();
      renderProducts();
      return;
    }
    
    const chipBtn = event.target.closest("[data-search-chip]");
    if (chipBtn) {
      const term = chipBtn.dataset.searchChip;
      saveSearchTerm(term);
      state.query = term;
      if (els.search) els.search.value = term;
      if (els.searchMobile) els.searchMobile.value = term;
      renderSearchSuggestions();
      closeSearchSuggestions();
      renderProducts();
      return;
    }
    
    const deleteBtn = event.target.closest("[data-delete-history-idx]");
    if (deleteBtn) {
      event.stopPropagation();
      const idx = parseInt(deleteBtn.dataset.deleteHistoryIdx, 10);
      state.searchHistory.splice(idx, 1);
      localStorage.setItem("mc_search_history", JSON.stringify(state.searchHistory));
      renderSearchSuggestions();
      return;
    }
    
    const clearBtn = event.target.closest("#clearAllHistoryBtn");
    if (clearBtn) {
      event.stopPropagation();
      state.searchHistory = [];
      localStorage.setItem("mc_search_history", JSON.stringify(state.searchHistory));
      renderSearchSuggestions();
      return;
    }
  };
  
  els.searchSuggestions?.addEventListener("click", handleSuggestionsClick);
  els.searchSuggestionsMobile?.addEventListener("click", handleSuggestionsClick);
  
  document.addEventListener("click", event => {
    if (!event.target.closest(".header-search-container")) {
      closeSearchSuggestions();
    }
  });
  els.sort?.addEventListener("change", event => {
    state.sort = event.target.value;
    renderProducts();
  });
  els.categoryFilters?.addEventListener("click", event => {
    const button = event.target.closest("[data-category]");
    if (!button) return;
    setCategory(button.dataset.category);
  });
  els.grid?.addEventListener("click", event => {
    const view = event.target.closest("[data-view-product]");
    const add = event.target.closest("[data-add-cart]");
    const wishlist = event.target.closest("[data-wishlist-toggle]");
    if (wishlist) {
      toggleWishlist(wishlist.dataset.wishlistToggle);
      return;
    }
    if (view) showProduct(view.dataset.viewProduct);
    if (add) addToCart(add.dataset.addCart);
  });
  els.popularHeroPanel?.addEventListener("click", event => {
    const button = event.target.closest("[data-view-product]");
    if (button) showProduct(button.dataset.viewProduct);
  });
  els.productModal?.addEventListener("click", event => {
    const add = event.target.closest("[data-add-cart]");
    if (add) addToCart(add.dataset.addCart);
  });
  els.wishlistBtn?.addEventListener("click", showWishlist);
  els.wishlistList?.addEventListener("click", event => {
    const view = event.target.closest("[data-view-product]");
    const wishlist = event.target.closest("[data-wishlist-toggle]");
    if (wishlist) {
      toggleWishlist(wishlist.dataset.wishlistToggle);
      showWishlist();
      return;
    }
    if (view) {
      els.wishlistModal.close();
      showProduct(view.dataset.viewProduct);
    }
  });
  els.cartItems?.addEventListener("click", event => {
    const inc = event.target.closest("[data-cart-inc]");
    const dec = event.target.closest("[data-cart-dec]");
    const remove = event.target.closest("[data-cart-remove]");
    const id = inc?.dataset.cartInc || dec?.dataset.cartDec || remove?.dataset.cartRemove;
    if (!id) return;
    const item = state.cart.find(row => row.id === id);
    if (!item) return;
    if (inc) item.quantity += 1;
    if (dec) item.quantity -= 1;
    if (remove || item.quantity <= 0) state.cart = state.cart.filter(row => row.id !== id);
    saveCart();
  });
  els.cartBtn?.addEventListener("click", openCart);
  document.querySelector("[data-close-cart]")?.addEventListener("click", closeCart);
  els.scrim?.addEventListener("click", closeCart);
  els.ordersNavTrigger?.addEventListener("click", event => {
    if (event.target.closest(".header-dropdown-menu")) return;
    event.stopPropagation();
    toggleOrdersMenu();
  });
  els.ordersNavTrigger?.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggleOrdersMenu();
    }
  });
  els.authBtn?.addEventListener("click", event => {
    event.stopPropagation();
    toggleGuestAccountMenu();
  });
  els.guestSignupBtn?.addEventListener("click", () => {
    closeGuestAccountMenu();
    showAuth("signup", "B2C");
  });
  els.guestLoginBtn?.addEventListener("click", () => {
    closeGuestAccountMenu();
    showAuth("login", "B2C");
  });
  els.guestBusinessBtn?.addEventListener("click", () => {
    closeGuestAccountMenu();
    showAuth("signup", "B2B");
  });
  els.businessAuthBtn?.addEventListener("click", () => showAuth("login", "B2B"));
  document.querySelector("#heroBusinessBtn")?.addEventListener("click", () => showAuth("login", "B2B"));
  els.ordersBtn?.addEventListener("click", showOrders);
  els.profileBtn?.addEventListener("click", event => {
    event.stopPropagation();
    toggleProfileMenu();
  });
  els.profileOrdersBtn?.addEventListener("click", () => {
    closeProfileMenu();
    showOrders();
  });
  els.profileCartBtn?.addEventListener("click", () => {
    closeProfileMenu();
    openCart();
  });
  els.profileWishlistBtn?.addEventListener("click", () => {
    closeProfileMenu();
    showWishlist();
  });
  els.profileSettingsBtn?.addEventListener("click", () => {
    closeProfileMenu();
    showSettings();
  });
  els.profileThemeBtn?.addEventListener("click", () => {
    setTheme(document.body.dataset.theme === "dark" ? "light" : "dark");
    closeProfileMenu();
    toast("Theme updated");
  });
  els.profileBusinessPanelBtn?.addEventListener("click", () => {
    closeProfileMenu();
    window.location.assign("/admin");
  });
  els.profileLogoutBtn?.addEventListener("click", async () => {
    closeProfileMenu();
    await logout();
  });
  document.addEventListener("click", event => {
    if (!els.guestAccountMenu?.contains(event.target)) closeGuestAccountMenu();
    if (!els.profileMenu?.contains(event.target)) closeProfileMenu();
    if (!els.ordersNavTrigger?.contains(event.target)) closeOrdersMenu();
    if (!event.target.closest(".header-search-container")) closeSearchSuggestions();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      closeGuestAccountMenu();
      closeProfileMenu();
      closeOrdersMenu();
      closeSearchSuggestions();
    }
  });
  document.querySelectorAll("[data-help-topic]").forEach(button => {
    button.addEventListener("click", () => showHelpTopic(button.dataset.helpTopic));
  });

  document.querySelector("#ordersList")?.addEventListener("click", async event => {
    const cancelBtn = event.target.closest(".cancel-order-btn");
    if (!cancelBtn) return;
    const orderId = cancelBtn.dataset.orderId;
    if (!orderId) return;
    if (!confirm("Are you sure you want to cancel this order?")) return;
    
    cancelBtn.disabled = true;
    const originalText = cancelBtn.textContent;
    cancelBtn.textContent = "Cancelling...";
    try {
      const data = await api(`/api/orders/${orderId}/cancel`, {
        method: "POST"
      });
      toast(data.message || "Order cancelled successfully.");
      const modalTitle = els.ordersModal?.querySelector("h2")?.textContent || "";
      if (modalTitle.toLowerCase().includes("current") || modalTitle.toLowerCase().includes("active")) {
        await showOrdersWithFilter("current");
      } else {
        await showOrders();
      }
    } catch (error) {
      toast(error.message);
      cancelBtn.disabled = false;
      cancelBtn.textContent = originalText;
    }
  });

  document.querySelector(".marketplace-category-strip")?.addEventListener("click", event => {
    const button = event.target.closest("[data-home-category]");
    if (!button) return;
    setCategory(button.dataset.homeCategory, { scrollToProducts: true });
  });
}

function bindPromoCarousel() {
  const carousel = document.querySelector("#promoCarousel");
  if (!carousel) return;
  const slides = Array.from(carousel.querySelectorAll(".promo-slide"));
  const dots = Array.from(document.querySelectorAll("[data-promo-dot]"));
  const prev = document.querySelector("[data-promo-prev]");
  const next = document.querySelector("[data-promo-next]");
  if (!slides.length) return;

  let index = 0;
  let autoTimer = null;

  const setActiveDot = () => {
    dots.forEach((dot, idx) => {
      dot.classList.toggle("active", idx === index);
      dot.setAttribute("aria-current", idx === index ? "true" : "false");
    });
  };

  const goToSlide = (nextIndex) => {
    index = (nextIndex + slides.length) % slides.length;
    carousel.scrollTo({ left: slides[index].offsetLeft, behavior: "smooth" });
    setActiveDot();
  };

  const restartAuto = () => {
    window.clearInterval(autoTimer);
    autoTimer = window.setInterval(() => goToSlide(index + 1), 5200);
  };

  prev?.addEventListener("click", () => {
    goToSlide(index - 1);
    restartAuto();
  });
  next?.addEventListener("click", () => {
    goToSlide(index + 1);
    restartAuto();
  });
  dots.forEach(dot => {
    dot.addEventListener("click", () => {
      goToSlide(Number(dot.dataset.promoDot || 0));
      restartAuto();
    });
  });

  carousel.addEventListener("scroll", () => {
    const nearest = slides.reduce((best, slide, idx) => {
      const distance = Math.abs(slide.offsetLeft - carousel.scrollLeft);
      return distance < best.distance ? { idx, distance } : best;
    }, { idx: index, distance: Number.POSITIVE_INFINITY });
    if (nearest.idx !== index && nearest.distance < carousel.clientWidth * 0.4) {
      index = nearest.idx;
      setActiveDot();
    }
  }, { passive: true });

  carousel.addEventListener("mouseenter", () => window.clearInterval(autoTimer));
  carousel.addEventListener("mouseleave", restartAuto);
  setActiveDot();
  restartAuto();
}

async function init() {
  initTheme();
  bindPageScrollLock();
  bindEvents();
  bindPromoCarousel();
  bindAuth();
  bindProfileSetup();
  bindCheckout();
  bindCommunityForum();
  bindSettings();
  bindChatbot();
  bindBusinessFields("#signupForm", "account_type");
  bindBusinessFields("#checkoutForm", "order_type");
  renderCart();
  renderWishlistCount();
  try {
    await Promise.all([loadProducts(), loadMe()]);
  } catch (error) {
    toast(error.message);
  }
  initHeaderOverrides();
  handleHashRoute();
  window.addEventListener("hashchange", handleHashRoute);
}

function initHeaderOverrides() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
  
  const savedLocation = savedDeliveryLocation();
  if (savedLocation) setDeliveryLocation(savedLocation);
  
  const locationBtn = document.querySelector("#locationBtn");
  const locationModal = document.querySelector("#locationModal");
  const locationForm = document.querySelector("#locationForm");
  const locationPincodeInput = document.querySelector("#locationPincodeInput");
  const locationCityInput = document.querySelector("#locationCityInput");
  const locationStateSelect = document.querySelector("#locationStateSelect");
  const locationLookupStatus = document.querySelector("#locationLookupStatus");
  let locationLookupController = null;

  const setLocationLookupStatus = message => {
    if (locationLookupStatus) locationLookupStatus.textContent = message || "";
  };

  const normalizeIndianStateName = stateName => {
    const clean = (stateName || "").trim();
    const aliases = {
      "Orissa": "Odisha",
      "Pondicherry": "Puducherry",
      "NCT of Delhi": "Delhi",
      "Dadra and Nagar Haveli": "Dadra and Nagar Haveli and Daman and Diu",
      "Daman and Diu": "Dadra and Nagar Haveli and Daman and Diu",
      "Jammu & Kashmir": "Jammu and Kashmir"
    };
    return aliases[clean] || clean;
  };

  const lookupPincodeLocation = async pincode => {
    if (!/^\d{6}$/.test(pincode)) {
      setLocationLookupStatus("");
      return null;
    }
    locationLookupController?.abort();
    locationLookupController = new AbortController();
    setLocationLookupStatus("Fetching city and state...");
    try {
      const response = await fetch(`https://api.postalpincode.in/pincode/${encodeURIComponent(pincode)}`, {
        signal: locationLookupController.signal
      });
      if (!response.ok) throw new Error("Pincode lookup failed");
      const data = await response.json();
      const result = Array.isArray(data) ? data[0] : null;
      const postOffices = Array.isArray(result?.PostOffice) ? result.PostOffice : [];
      const postOffice = postOffices[0];
      if (!postOffice) throw new Error(result?.Message || "Pincode not found");

      const area = postOffice.Name || "";
      const district = postOffice.District || "";
      const city = [...new Set([area, district].filter(Boolean))].join(", ");
      const stateName = normalizeIndianStateName(postOffice.State);
      if (locationCityInput) locationCityInput.value = city;
      if (locationStateSelect && stateName) {
        const hasOption = [...locationStateSelect.options].some(option => option.value === stateName);
        locationStateSelect.value = hasOption ? stateName : "Other";
      }
      const moreAreas = postOffices.length > 1 ? ` ${postOffices.length} delivery areas found for this pincode.` : "";
      setLocationLookupStatus(city ? `Detected ${city}.${moreAreas}` : "Location detected.");
      return { city, area, district, state: stateName };
    } catch (error) {
      if (error.name === "AbortError") return null;
      setLocationLookupStatus("Could not auto-detect this pincode. Select the state manually.");
      return null;
    }
  };
  
  if (locationBtn && locationModal) {
    locationBtn.addEventListener("click", () => {
      const details = savedDeliveryLocation();
      if (details) {
        if (locationPincodeInput) locationPincodeInput.value = details.pincode || "";
        if (locationCityInput) locationCityInput.value = details.city || "";
        if (locationStateSelect) locationStateSelect.value = details.state || "";
      }
      if (!locationModal.open) locationModal.showModal();
    });
  }

  locationPincodeInput?.addEventListener("input", event => {
    event.currentTarget.value = event.currentTarget.value.replace(/\D+/g, "").slice(0, 6);
    if (event.currentTarget.value.length === 6) {
      lookupPincodeLocation(event.currentTarget.value);
    } else {
      if (locationCityInput) locationCityInput.value = "";
      setLocationLookupStatus("");
    }
  });
  
  if (locationForm && locationModal) {
    locationForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const pincode = locationForm.pincode.value;
      let cityVal = (locationForm.city?.value || "").trim();
      let stateVal = locationForm.state.value;
      if (!cityVal || !stateVal) {
        const detected = await lookupPincodeLocation(pincode);
        cityVal = cityVal || detected?.city || "";
        stateVal = stateVal || detected?.state || "";
      }
      setDeliveryLocation({ city: cityVal, pincode, state: stateVal }, { syncCheckout: true });
      locationModal.close();
      toast(`Delivery location updated to ${cityVal || "India"} ${pincode}`.trim());
    });
  }
  
  const mobileMenuToggle = document.querySelector("#mobileMenuToggle");
  const mobileSidebar = document.querySelector("#mobileSidebar");
  const sidebarUserInfo = document.querySelector("#sidebarUserInfo");
  const sidebarCloseBtn = document.querySelector("#sidebarCloseBtn");
  const sidebarBackdrop = document.querySelector("#sidebarBackdrop");
  
  function openMobileSidebar() {
    mobileSidebar?.classList.add("open");
    sidebarBackdrop?.classList.add("show");
    mobileMenuToggle?.setAttribute("aria-expanded", "true");
    refreshPageScrollLock();
  }
  
  function closeMobileSidebar() {
    mobileSidebar?.classList.remove("open");
    sidebarBackdrop?.classList.remove("show");
    mobileMenuToggle?.setAttribute("aria-expanded", "false");
    refreshPageScrollLock();
  }
  
  mobileMenuToggle?.setAttribute("aria-controls", "mobileSidebar");
  mobileMenuToggle?.setAttribute("aria-expanded", "false");
  mobileMenuToggle?.addEventListener("click", openMobileSidebar);
  sidebarCloseBtn?.addEventListener("click", closeMobileSidebar);
  sidebarBackdrop?.addEventListener("click", closeMobileSidebar);
  sidebarUserInfo?.addEventListener("click", () => {
    closeMobileSidebar();
    if (state.currentUser) {
      showSettings();
    } else {
      showAuth("login", "B2C");
    }
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") closeMobileSidebar();
  });
  
  const sidebarCategoryList = document.querySelector("#sidebarCategoryList");
  if (sidebarCategoryList) {
    renderSidebarCategories();
    
    sidebarCategoryList.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-sidebar-cat]");
      if (!btn) return;
      const cat = btn.dataset.sidebarCat;
      setCategory(cat, { scrollToProducts: true });
      closeMobileSidebar();
    });
  }
  
  const sidebarOrdersCurrent = document.querySelector("#sidebarOrdersCurrent");
  const sidebarOrdersHistory = document.querySelector("#sidebarOrdersHistory");
  const sidebarOrdersReturns = document.querySelector("#sidebarOrdersReturns");
  const sidebarOrdersRefunds = document.querySelector("#sidebarOrdersRefunds");
  
  sidebarOrdersCurrent?.addEventListener("click", () => { closeMobileSidebar(); showOrdersWithFilter("current"); });
  sidebarOrdersHistory?.addEventListener("click", () => { closeMobileSidebar(); showOrdersWithFilter("history"); });
  sidebarOrdersReturns?.addEventListener("click", () => { closeMobileSidebar(); showOrdersWithFilter("returns"); });
  sidebarOrdersRefunds?.addEventListener("click", () => { closeMobileSidebar(); showOrdersWithFilter("refunds"); });
  
  const navOrdersCurrent = document.querySelector("#navOrdersCurrent");
  const navOrdersHistory = document.querySelector("#navOrdersHistory");
  const navOrdersReturns = document.querySelector("#navOrdersReturns");
  const navOrdersRefunds = document.querySelector("#navOrdersRefunds");
  
  navOrdersCurrent?.addEventListener("click", () => { closeOrdersMenu(); showOrdersWithFilter("current"); });
  navOrdersHistory?.addEventListener("click", () => { closeOrdersMenu(); showOrdersWithFilter("history"); });
  navOrdersReturns?.addEventListener("click", () => { closeOrdersMenu(); showOrdersWithFilter("returns"); });
  navOrdersRefunds?.addEventListener("click", () => { closeOrdersMenu(); showOrdersWithFilter("refunds"); });
  
  const miniCartViewBtn = document.querySelector("#miniCartViewBtn");
  const miniCartCheckoutBtn = document.querySelector("#miniCartCheckoutBtn");
  
  miniCartViewBtn?.addEventListener("click", openCart);
  miniCartCheckoutBtn?.addEventListener("click", checkout);
  
  const wishlistDropdownViewAll = document.querySelector("#wishlistDropdownViewAll");
  wishlistDropdownViewAll?.addEventListener("click", showWishlist);
  
  const wishlistDropdownItems = document.querySelector("#wishlistDropdownItems");
  wishlistDropdownItems?.addEventListener("click", (e) => {
    const item = e.target.closest("[data-view-product]");
    if (item) {
      showProduct(item.dataset.viewProduct);
    }
  });

  renderMiniCart();
  renderMiniWishlist();
  
  const searchInput = document.querySelector("#searchInput");
  const searchInputMobile = document.querySelector("#searchInputMobile");
  const searchCategorySelectDesktop = document.querySelector("#searchCategorySelectDesktop");
  
  function syncSearchQuery(e) {
    state.query = e.target.value;
    if (e.target === searchInput && searchInputMobile) {
      searchInputMobile.value = state.query;
    } else if (e.target === searchInputMobile && searchInput) {
      searchInput.value = state.query;
    }
    
    state.searchIndex = -1;
    renderSearchSuggestions();
    renderProducts();
  }
  
  searchInput?.addEventListener("input", syncSearchQuery);
  searchInputMobile?.addEventListener("input", syncSearchQuery);
  
  searchInput?.addEventListener("focus", renderSearchSuggestions);
  searchInputMobile?.addEventListener("focus", renderSearchSuggestions);
  
  searchInput?.addEventListener("keydown", handleSearchKeyboardNavigation);
  searchInputMobile?.addEventListener("keydown", handleSearchKeyboardNavigation);
  
  searchCategorySelectDesktop?.addEventListener("change", (e) => {
    setCategory(e.target.value);
  });
}

init();
