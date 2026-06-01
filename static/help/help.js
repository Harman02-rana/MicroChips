const searchInput = document.querySelector("#helpSearchInput");
const cards = Array.from(document.querySelectorAll(".help-topic-card"));
const empty = document.querySelector("#helpEmpty");

function applyHelpFilter() {
  const query = searchInput.value.trim().toLowerCase();
  let visibleCount = 0;

  cards.forEach(card => {
    const haystack = `${card.textContent} ${card.dataset.helpTopic || ""}`.toLowerCase();
    const isVisible = !query || haystack.includes(query);
    card.classList.toggle("hidden", !isVisible);
    if (isVisible) visibleCount += 1;
  });

  empty?.classList.toggle("hidden", visibleCount > 0);
}

document.body.dataset.theme = localStorage.getItem("mc_theme") || "dark";
searchInput?.addEventListener("input", applyHelpFilter);
applyHelpFilter();
