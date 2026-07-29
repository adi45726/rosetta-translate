(() => {
  const panel = document.getElementById("payment-panel");
  const openButton = document.getElementById("btn-upgrade");
  const closeButton = document.getElementById("btn-close-payment");
  const checkoutButton = document.getElementById("btn-start-checkout");
  const price = document.getElementById("payment-price");
  const methods = document.getElementById("payment-methods");
  const status = document.getElementById("payment-status");
  const toast = document.getElementById("payment-toast");
  let country = "";

  function countryHint() {
    const locale = navigator.language || "";
    const match = locale.match(/[-_]([A-Za-z]{2})$/);
    return match ? match[1].toUpperCase() : "";
  }

  function showToast(message, good = false) {
    toast.textContent = message;
    toast.classList.remove("hidden", "is-good");
    if (good) toast.classList.add("is-good");
    requestAnimationFrame(() => toast.classList.add("is-visible"));
    setTimeout(() => {
      toast.classList.remove("is-visible");
      setTimeout(() => toast.classList.add("hidden"), 300);
    }, 5000);
  }

  async function loadMarket() {
    try {
      const hint = countryHint();
      const response = await fetch(`/api/billing/market${hint ? `?country=${hint}` : ""}`);
      const market = await response.json();
      country = market.country || hint;
      price.textContent = market.price;
      methods.innerHTML = "";
      (market.methods || ["Cards"]).forEach((method, index) => {
        const chip = document.createElement("span");
        chip.textContent = method;
        chip.style.setProperty("--method-order", index);
        methods.appendChild(chip);
      });
    } catch {
      price.textContent = "$12";
      methods.innerHTML = "<span>Cards & local methods</span>";
    }
  }

  function openPayment() {
    panel.classList.remove("hidden");
    requestAnimationFrame(() => panel.classList.add("is-open"));
    openButton.setAttribute("aria-expanded", "true");
    syncModalBackdrop();
    loadMarket();
    setTimeout(() => closeButton.focus(), 80);
  }

  window.openPaymentPanel = openPayment;
  function closePayment() {
    panel.classList.remove("is-open");
    setTimeout(() => {
      panel.classList.add("hidden");
      syncModalBackdrop();
    }, 260);
    openButton.setAttribute("aria-expanded", "false");
    openButton.focus();
  }

  window.closePaymentPanel = closePayment;
  openButton.addEventListener("click", openPayment);
  closeButton.addEventListener("click", closePayment);

  checkoutButton.addEventListener("click", async () => {
    checkoutButton.disabled = true;
    checkoutButton.classList.add("is-loading");
    status.textContent = "Preparing your secure checkout…";
    try {
      const query = country ? `?country=${encodeURIComponent(country)}` : "";
      const response = await fetch(`/api/billing/checkout${query}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.url) throw new Error(data.error || "Checkout could not be started.");
      window.location.assign(data.url);
    } catch (error) {
      status.textContent = error.message;
      status.classList.add("is-error");
      checkoutButton.disabled = false;
      checkoutButton.classList.remove("is-loading");
    }
  });

  const params = new URLSearchParams(window.location.search);
  if (params.get("payment") === "success") {
    showToast("Payment complete — welcome to Rosetta Pro.", true);
  } else if (params.get("payment") === "cancelled") {
    showToast("Payment cancelled. Nothing was charged.");
  }

  window.addEventListener("rosetta:auth-ready", (event) => {
    if (event.detail?.guest || sessionStorage.getItem("rosetta-upgrade-after-login") !== "1") return;
    sessionStorage.removeItem("rosetta-upgrade-after-login");
    setTimeout(() => {
      panel.querySelector(".section-kicker").textContent = "WELCOME TO ROSETTA · MEET PRO";
      document.getElementById("payment-title").innerHTML = "You’re in.<br><em>Go limitless.</em>";
      openPayment();
    }, 650);
  });
})();
