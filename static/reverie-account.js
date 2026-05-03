(function () {
  const { setModalVisible, invalidateSession } = window.ReverieShared || {};

  const backdrop = document.getElementById("mobileAccountBackdrop");
  const closeBtn = document.getElementById("mobileAccountClose");
  const logoutBtn = document.getElementById("mobileLogoutBtn");

  function openAccountSheet() {
    if (!backdrop || typeof setModalVisible !== "function") return false;
    setModalVisible(backdrop, true);
    return true;
  }

  function closeAccountSheet() {
    if (!backdrop || typeof setModalVisible !== "function") return;
    setModalVisible(backdrop, false);
  }

  async function performLogout() {
    try {
      await fetch("/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
        credentials: "same-origin",
      });
    } catch (_) {}
    invalidateSession?.();
    closeAccountSheet();
    window.location.href = "/";
  }

  document.addEventListener("click", (event) => {
    const accountLink = event.target.closest('a[href="#account"], a[href="/#account"]');
    if (!accountLink) return;
    if (!openAccountSheet()) return;
    event.preventDefault();
  });

  closeBtn?.addEventListener("click", closeAccountSheet);
  backdrop?.addEventListener("click", (event) => {
    if (event.target === backdrop) closeAccountSheet();
  });
  logoutBtn?.addEventListener("click", performLogout);

  if (window.location.hash === "#account") {
    window.setTimeout(openAccountSheet, 240);
  }
})();
