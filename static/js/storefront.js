const state = {
  products: [],
  currentUser: null,
  cart: JSON.parse(localStorage.getItem("mc_cart") || "[]"),
  wishlist: JSON.parse(localStorage.getItem("mc_wishlist") || "[]"),
  communityReviews: JSON.parse(localStorage.getItem("mc_community_reviews") || "[]"),
  communityPosts: [],
  searchHistory: JSON.parse(localStorage.getItem("mc_search_history") || "[]"),
  category: "All",
  query: "",
  sort: "featured",
  authMode: "B2C",
};

const els = {
  grid: document.querySelector("#productGrid"),
  categoryFilters: document.querySelector("#categoryFilters"),
  sort: document.querySelector("#sortSelect"),
  search: document.querySelector("#searchInput"),
  searchSuggestions: document.querySelector("#searchSuggestions"),
  popularHeroPanel: document.querySelector("#popularHeroPanel"),
  communityPostForm: document.querySelector("#communityPostForm"),
  communityPostsList: document.querySelector("#communityPostsList"),
  communityCategories: document.querySelector("#communityCategories"),
  startPostBtn: document.querySelector("#startPostBtn"),
  postFormCard: document.querySelector("#postFormCard"),
  closePostFormBtn: document.querySelector("#closePostFormBtn"),
  postAuthorName: document.querySelector("#postAuthorName"),
  postLoginNotice: document.querySelector("#postLoginNotice"),
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
  profileOrdersBtn: document.querySelector("#profileOrdersBtn"),
  profileCartBtn: document.querySelector("#profileCartBtn"),
  profileWishlistBtn: document.querySelector("#profileWishlistBtn"),
  profileSettingsBtn: document.querySelector("#profileSettingsBtn"),
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
  els.toast.textContent = message;
  els.toast.classList.add("show");
  setTimeout(() => els.toast.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  const data = await res.json();
  if (!data.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function setTheme(theme) {
  document.body.dataset.theme = theme;
  localStorage.setItem("mc_theme", theme);
}

function initTheme() {
  setTheme(localStorage.getItem("mc_theme") || "dark");
  els.themeToggle.addEventListener("click", () => {
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
}

function openCart() {
  els.cartDrawer.classList.add("open");
  els.cartDrawer.setAttribute("aria-hidden", "false");
  els.scrim.classList.add("show");
}

function closeCart() {
  els.cartDrawer.classList.remove("open");
  els.cartDrawer.setAttribute("aria-hidden", "true");
  els.scrim.classList.remove("show");
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

function renderSearchSuggestions() {
  if (!els.searchSuggestions) return;
  const query = state.query.trim();
  if (!query) {
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
                  <span class="history-clock-icon">&#8986;</span> ${escapeHtml(term)}
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
    
    els.searchSuggestions.innerHTML = `
      <div class="search-dropdown-menu">
        ${historyHtml}
        ${chipsHtml}
      </div>
    `;
    els.searchSuggestions.classList.remove("hidden");
    return;
  }
  
  const matches = searchMatches();
  els.searchSuggestions.classList.toggle("hidden", !matches.length);
  els.searchSuggestions.innerHTML = matches.map(product => `
    <button type="button" data-suggestion-product="${product.id}" role="option">
      <img src="${escapeHtml(product.image_url)}" alt="" onerror="this.src='/static/images/product-placeholder.webp'">
      <span>
        <strong>${escapeHtml(product.name)}</strong>
        <small>${escapeHtml(product.category || "Component")} &middot; ${escapeHtml(product.sku || "SKU")} &middot; ${moneyLabel(product.price)}</small>
      </span>
    </button>
  `).join("");
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

function renderCategories() {
  const categories = ["All", ...new Set(state.products.map(product => product.category).filter(Boolean))];
  els.categoryFilters.innerHTML = categories.map(category => `
    <button type="button" class="${category === state.category ? "active" : ""}" data-category="${escapeHtml(category)}">${escapeHtml(category)}</button>
  `).join("");
}

function renderProducts() {
  const products = visibleProducts();
  els.heroProductCount.textContent = state.products.length;
  renderPopularHero();
  els.sampleNote.classList.toggle("hidden", !state.products.some(product => product.sample));
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
            <button class="primary-btn" type="button" data-add-cart="${product.id}" ${product.stock <= 0 ? "disabled" : ""}>Add cart</button>
          </div>
        </div>
      </article>
    `;
  }).join("");
}

async function loadProducts() {
  const [productsData, config] = await Promise.all([
    api("/api/products"),
    api("/api/config")
  ]);
  state.products = productsData.products;
  if (config.settings?.store_name) {
    document.querySelector("#storeName").textContent = config.settings.store_name;
  }
  if (config.settings?.announcement) {
    document.querySelector("#announcement").textContent = config.settings.announcement;
  }
  renderCategories();
  renderPopularHero();
  renderSearchSuggestions();
  renderProducts();
}

let currentCategoryFilter = "All";

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
  const filtered = state.communityPosts.filter(post => {
    return currentCategoryFilter === "All" || post.category === currentCategoryFilter;
  });
  
  if (!filtered.length) {
    els.communityPostsList.innerHTML = `<p class="form-help">No discussions here yet. Be the first to start a topic!</p>`;
    return;
  }
  
  els.communityPostsList.innerHTML = filtered.map(post => {
    const isLiked = state.currentUser 
      ? post.liked_by.includes(state.currentUser.id) 
      : false;
      
    let dateStr = "Just now";
    if (post.created_at) {
      try {
        const d = new Date(post.created_at);
        dateStr = d.toLocaleDateString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
      } catch (e) {}
    }
    
    let catClass = "badge-general";
    if (post.category === "Problem") catClass = "badge-problem";
    if (post.category === "Experience") catClass = "badge-experience";
    if (post.category === "Project") catClass = "badge-project";

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
          <span class="category-badge ${catClass}">${escapeHtml(post.category)}</span>
        </header>
        <div class="post-body-board">
          <h3 class="post-title-board">${escapeHtml(post.title)}</h3>
          <p class="post-content-board">${escapeHtml(post.content).replaceAll("\n", "<br>")}</p>
        </div>
        <footer class="post-footer-board">
          <button type="button" class="post-action-btn like-btn ${isLiked ? "liked" : ""}" data-like-post-id="${post.id}">
            <span class="heart-icon">${isLiked ? "&hearts;" : "&#9825;"}</span>
            <span class="likes-count">${post.likes || 0}</span> Likes
          </button>
          <button type="button" class="post-action-btn comment-btn" data-toggle-replies-id="${post.id}">
            <span class="comment-icon">&#128172;</span>
            <span class="replies-count">${post.reply_count || 0}</span> Comments
          </button>
        </footer>
        
        <div class="post-replies-section hidden" id="repliesSection-${post.id}">
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
        </div>
      </article>
    `;
  }).join("");
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
        <article class="reply-card-board">
          <header class="reply-header-board">
            <span class="user-avatar-initial small-avatar">${escapeHtml(r.user_name.charAt(0).toUpperCase())}</span>
            <strong>${escapeHtml(r.user_name)}</strong>
            <small>${rDateStr}</small>
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
    els.postFormCard.classList.remove("hidden");
    els.startPostBtn.classList.add("hidden");
    els.postFormCard.scrollIntoView({ behavior: "smooth", block: "center" });
  });

  els.closePostFormBtn?.addEventListener("click", () => {
    els.postFormCard.classList.add("hidden");
    els.startPostBtn.classList.remove("hidden");
  });
  
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
      toast("Discussion posted successfully");
      form.reset();
      els.postFormCard.classList.add("hidden");
      els.startPostBtn.classList.remove("hidden");
      await loadCommunityPosts();
    } catch (err) {
      toast(err.message);
    }
  });

  els.communityPostsList.addEventListener("click", async event => {
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
  const data = await api("/api/auth/me");
  state.currentUser = data.user;
  updateAuthUi();
}

function updateAuthUi() {
  const loggedIn = Boolean(state.currentUser);
  els.guestAccountMenu?.classList.toggle("hidden", loggedIn);
  els.businessAuthBtn?.classList.toggle("hidden", loggedIn);
  els.ordersBtn.classList.toggle("hidden", loggedIn);
  els.profileMenu.classList.toggle("hidden", !loggedIn);
  closeGuestAccountMenu();
  els.profileBtn?.setAttribute("aria-expanded", "false");
  els.profileMenu?.classList.remove("open");
  
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

  if (!loggedIn) return;
  const name = state.currentUser.name || "User";
  els.profileInitial.textContent = name.trim().charAt(0).toUpperCase() || "U";
  if (els.profileDropdownInitial) els.profileDropdownInitial.textContent = name.trim().charAt(0).toUpperCase() || "U";
  els.profileName.textContent = name;
  els.profileEmail.textContent = state.currentUser.email || "Signed in";
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

async function showProduct(productId) {
  try {
    const data = await api(`/api/products/${productId}`);
    const product = data.product;
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
            <button class="primary-btn" type="button" data-add-cart="${product.id}">Add cart</button>
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
          <div class="review-list">
            ${(data.reviews || []).map(review => `
              <article class="review">
                <strong>${escapeHtml(review.name || "Customer")} &middot; ${Array.from({ length: review.rating }, () => "&#9733;").join("")}</strong>
                <p>${escapeHtml(review.comment || "Rated this product")}</p>
              </article>
            `).join("") || `<p class="form-help">No reviews yet.</p>`}
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
  document.querySelectorAll("#loginForm [name='account_type'], #signupForm [name='account_type']").forEach(input => {
    input.value = state.authMode;
  });
  const signupPhone = document.querySelector("#signupForm [name='phone']");
  if (signupPhone) {
    signupPhone.required = isBusiness;
    signupPhone.placeholder = isBusiness ? "Required for business accounts" : "";
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
  els.authModal.showModal();
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

  document.querySelectorAll("[data-auth-tab]").forEach(button => {
    button.addEventListener("click", () => showAuth(button.dataset.authTab));
  });

  document.querySelector("#loginForm").addEventListener("submit", async event => {
    event.preventDefault();
    try {
      const body = Object.fromEntries(new FormData(event.currentTarget).entries());
      body.account_type = state.authMode;
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(body)
      });
      state.currentUser = data.user;
      await loadMe();
      els.authModal.close();
      toast("Logged in");
      window.location.assign(data.redirect_url || authDestination());
    } catch (error) {
      toast(error.message);
    }
  });

  document.querySelector("#signupForm").addEventListener("submit", async event => {
    event.preventDefault();
    try {
      const body = Object.fromEntries(new FormData(event.currentTarget).entries());
      body.account_type = state.authMode;

      if (state.authMode === "B2B") {
        const phoneData = await api("/api/auth/send-phone-otp", {
          method: "POST",
          body: JSON.stringify({ phone: body.phone })
        });
        const otp = prompt(`An OTP has been sent to ${body.phone}. Enter OTP to complete registration:`);
        if (!otp) {
          toast("Registration cancelled. OTP is required.");
          return;
        }
        body.otp = otp;
      }

      const data = await api("/api/auth/signup", {
        method: "POST",
        body: JSON.stringify(body)
      });
      state.currentUser = data.user;
      await loadMe();
      els.authModal.close();
      toast(`${state.authMode === "B2B" ? "Business" : "Customer"} account created. ${state.authMode === "B2B" ? "Pending admin approval." : ""}`);
      window.location.assign(data.redirect_url || authDestination());
    } catch (error) {
      toast(error.message);
    }
  });
}

function handleHashRoute() {
  const hash = decodeURIComponent(location.hash || "");
  if (hash === "#login") showAuth("login");
  if (hash === "#signup") showAuth("signup");
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
  if (!state.currentUser) {
    closeCart();
    showAuth("login", "B2C");
    return;
  }
  await api("/api/events", { method: "POST", body: JSON.stringify({ type: "checkout_open" }) }).catch(() => {});
  const form = document.querySelector("#checkoutForm");
  form.name.value = state.currentUser.name || "";
  form.email.value = state.currentUser.email || "";
  form.phone.value = state.currentUser.phone || "";
  form.order_type.value = state.currentUser.account_type || "B2C";
  form.company_name.value = state.currentUser.company_name || "";
  form.gstin.value = state.currentUser.gstin || "";
  setBusinessFields(form, "order_type");
  els.checkoutModal.showModal();
}

function bindCheckout() {
  document.querySelector("#checkoutBtn").addEventListener("click", checkout);
  document.querySelector("#checkoutForm").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const address = Object.fromEntries(new FormData(form).entries());
    const paymentMethod = address.payment_method;
    delete address.payment_method;
    try {
      await api("/api/events", {
        method: "POST",
        body: JSON.stringify({ type: "payment_selected", metadata: { payment_method: paymentMethod } })
      }).catch(() => {});
      const orderPayload = {
        items: state.cart.map(item => ({ product_id: item.product_id, quantity: item.quantity })),
        address,
        payment_method: paymentMethod
      };
      if (["Card", "UPI"].includes(paymentMethod)) {
        const paymentData = await api("/api/payments/checkout", {
          method: "POST",
          body: JSON.stringify(orderPayload)
        });
        window.location.assign(paymentData.checkout_url);
        return;
      }
      const data = await api("/api/orders", {
        method: "POST",
        body: JSON.stringify(orderPayload)
      });
      state.cart = [];
      saveCart();
      closeCart();
      els.checkoutModal.close();
      toast(`Order placed: ${data.order.invoice_number}`);
      await loadProducts();
    } catch (error) {
      toast(error.message);
    }
  });
}

async function showOrders() {
  if (!state.currentUser) {
    showAuth("login", "B2C");
    return;
  }
  try {
    const data = await api("/api/orders/my");
    const list = document.querySelector("#ordersList");
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
      </article>
    `).join("") : `<p class="form-help">No orders yet.</p>`;
    els.ordersModal.showModal();
  } catch (error) {
    toast(error.message);
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
    try {
      const body = Object.fromEntries(new FormData(event.currentTarget).entries());
      await api("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify(body)
      });
      event.currentTarget.reset();
      toast("Password changed");
    } catch (error) {
      toast(error.message);
    }
  });
  els.settingsThemeSelect?.addEventListener("change", event => {
    setTheme(event.target.value);
    toast(`${event.target.value === "dark" ? "Dark" : "Light"} theme applied`);
  });
  els.settingsLogoutBtn?.addEventListener("click", async () => {
    els.settingsModal.close();
    await logout();
  });
  els.deleteAccountForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget).entries());
    try {
      await api("/api/auth/me", {
        method: "DELETE",
        body: JSON.stringify(body)
      });
      state.currentUser = null;
      state.cart = [];
      state.wishlist = [];
      localStorage.removeItem("mc_cart");
      localStorage.removeItem("mc_wishlist");
      els.settingsModal.close();
      await loadMe();
      renderCart();
      renderWishlistCount();
      renderProducts();
      toast("Account deleted");
    } catch (error) {
      toast(error.message);
    }
  });
}

function closeProfileMenu() {
  els.profileMenu?.classList.remove("open");
  els.profileBtn?.setAttribute("aria-expanded", "false");
}

function closeGuestAccountMenu() {
  els.guestAccountMenu?.classList.remove("open");
  els.authBtn?.setAttribute("aria-expanded", "false");
}

function toggleGuestAccountMenu() {
  const isOpen = els.guestAccountMenu.classList.toggle("open");
  els.authBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
}

function toggleProfileMenu() {
  const isOpen = els.profileMenu.classList.toggle("open");
  els.profileBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
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
  document.querySelector("#searchForm")?.addEventListener("submit", event => {
    event.preventDefault();
    if (state.query.trim()) {
      saveSearchTerm(state.query.trim());
      renderSearchSuggestions();
      els.searchSuggestions.classList.add("hidden");
    }
  });
  els.search.addEventListener("input", event => {
    state.query = event.target.value;
    renderSearchSuggestions();
    renderProducts();
  });
  els.search.addEventListener("focus", renderSearchSuggestions);
  els.searchSuggestions?.addEventListener("click", event => {
    const suggestBtn = event.target.closest("[data-suggestion-product]");
    if (suggestBtn) {
      const product = state.products.find(item => item.id === suggestBtn.dataset.suggestionProduct);
      if (!product) return;
      saveSearchTerm(product.name);
      state.query = product.name;
      els.search.value = product.name;
      renderSearchSuggestions();
      els.searchSuggestions.classList.add("hidden");
      renderProducts();
      showProduct(product.id);
      return;
    }
    
    const historyBtn = event.target.closest("[data-history-term]");
    if (historyBtn) {
      const term = historyBtn.dataset.historyTerm;
      saveSearchTerm(term);
      state.query = term;
      els.search.value = term;
      renderSearchSuggestions();
      els.searchSuggestions.classList.add("hidden");
      renderProducts();
      return;
    }
    
    const chipBtn = event.target.closest("[data-search-chip]");
    if (chipBtn) {
      const term = chipBtn.dataset.searchChip;
      saveSearchTerm(term);
      state.query = term;
      els.search.value = term;
      renderSearchSuggestions();
      els.searchSuggestions.classList.add("hidden");
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
  });
  els.sort.addEventListener("change", event => {
    state.sort = event.target.value;
    renderProducts();
  });
  els.categoryFilters.addEventListener("click", event => {
    const button = event.target.closest("[data-category]");
    if (!button) return;
    state.category = button.dataset.category;
    renderCategories();
    renderProducts();
  });
  els.grid.addEventListener("click", event => {
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
  els.productModal.addEventListener("click", event => {
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
  els.cartItems.addEventListener("click", event => {
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
  els.cartBtn.addEventListener("click", openCart);
  document.querySelector("[data-close-cart]").addEventListener("click", closeCart);
  els.scrim.addEventListener("click", closeCart);
  els.authBtn.addEventListener("click", event => {
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
  els.ordersBtn.addEventListener("click", showOrders);
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
  els.profileLogoutBtn?.addEventListener("click", async () => {
    closeProfileMenu();
    await logout();
  });
  document.addEventListener("click", event => {
    if (!els.guestAccountMenu?.contains(event.target)) closeGuestAccountMenu();
    if (!els.profileMenu?.contains(event.target)) closeProfileMenu();
    if (!event.target.closest(".search")) els.searchSuggestions?.classList.add("hidden");
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      closeGuestAccountMenu();
      closeProfileMenu();
    }
  });
  document.querySelectorAll("[data-help-topic]").forEach(button => {
    button.addEventListener("click", () => showHelpTopic(button.dataset.helpTopic));
  });
}

async function init() {
  initTheme();
  bindEvents();
  bindAuth();
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
  handleHashRoute();
  window.addEventListener("hashchange", handleHashRoute);
}

init();
