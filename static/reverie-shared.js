window.ReverieShared = (() => {
  const isStandalone = window.matchMedia?.("(display-mode: standalone)")?.matches
    || window.navigator.standalone === true;
  document.documentElement.classList.toggle("app-mode", Boolean(isStandalone));

  function normaliseTags(tags) {
    if (!Array.isArray(tags)) return [];
    return tags.map((tag) => String(tag).trim()).filter(Boolean);
  }

  function normaliseEntities(values) {
    if (!Array.isArray(values)) return [];
    return values.map((value) => String(value).trim()).filter(Boolean);
  }

  function toDisplayCase(value) {
    const text = String(value || "").trim().replace(/[_-]+/g, " ");
    if (!text) return "";
    return text.toLowerCase().replace(/([a-z])/g, (match) => match.toUpperCase());
  }

  function displayNoteType(value) { return toDisplayCase(value); }
  function displayPerson(value) { return toDisplayCase(value); }
  function displayTag(value) { return toDisplayCase(value); }
  function displayEntity(value) { return toDisplayCase(value); }

  function formatWhen(value) {
    if (!value) return "";
    const date = new Date(value);
    if (!isNaN(date.getTime())) {
      return new Intl.DateTimeFormat("en-IN", {
        day: "numeric",
        month: "short",
        hour: "numeric",
        minute: "2-digit",
      }).format(date);
    }
    return String(value);
  }

  function toInputDateTimeValue(value) {
    if (!value) return "";
    const date = new Date(value);
    if (isNaN(date.getTime())) return "";
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hour = String(date.getHours()).padStart(2, "0");
    const minute = String(date.getMinutes()).padStart(2, "0");
    return `${year}-${month}-${day}T${hour}:${minute}`;
  }

  function fromInputDateTimeValue(value) {
    const text = String(value || "").trim();
    if (!text) return null;
    const date = new Date(text);
    if (isNaN(date.getTime())) throw new Error("Due time is invalid.");
    return date.toISOString();
  }

  function splitCommaList(value) {
    return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
  }

  function chipClass(index) {
    return index % 3 === 0 ? "chip" : index % 3 === 1 ? "chip soft" : "chip muted";
  }

  function makeChip(text, cls, extra = "") {
    const el = document.createElement("button");
    el.type = "button";
    el.className = `chip clickable-chip ${cls || ""} ${extra || ""}`.trim();
    el.textContent = text;
    return el;
  }

  function _assetUrl(note) {
    return String(note?.image_url || "").trim();
  }

  function _appendAssetLink(container, label, url, download) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    if (download) link.download = "";
    link.className = `asset-link ${download ? "asset-link-secondary" : ""}`.trim();
    link.textContent = label;
    link.addEventListener("click", (e) => e.stopPropagation());
    container.appendChild(link);
  }

  function fillAssetActions(container, note) {
    if (!container) return;
    container.innerHTML = "";
    const url = _assetUrl(note);
    if (!url) return;
    _appendAssetLink(container, note?.memory_type === "document" ? "Open document" : "Open file", url, false);
    _appendAssetLink(container, "Download copy", url, true);
  }

  function appendImagePreview(parent, note) {
    const url = _assetUrl(note);
    if (!url) return;
    if (String(note?.memory_type || "").toLowerCase() === "document") {
      const preview = document.createElement("div");
      preview.className = "document-preview";
      const title = document.createElement("div");
      title.className = "document-preview-title";
      title.textContent = "Document attached";
      preview.appendChild(title);
      const actions = document.createElement("div");
      actions.className = "asset-actions";
      fillAssetActions(actions, note);
      preview.appendChild(actions);
      parent.appendChild(preview);
      return;
    }
    const img = document.createElement("img");
    img.className = "note-image-preview";
    img.src = url;
    img.alt = note?.title || "Image memory";
    img.loading = "lazy";
    parent.appendChild(img);
  }

  function noteStatus(value) {
    const status = String(value || "pending").trim().toLowerCase();
    return ["pending", "completed", "skipped"].includes(status) ? status : "pending";
  }

  function isActionableNote(note) {
    const type = String(note?.note_type || "").trim().toLowerCase();
    return type === "note" || type === "recommendation" || type === "reminder";
  }

  function statusLabel(value) {
    const status = noteStatus(value);
    return status.charAt(0).toUpperCase() + status.slice(1);
  }

  function noteId(note) {
    return String(note?.id || note?.note_id || "").trim();
  }

  function setModalVisible(backdrop, visible) {
    backdrop.style.display = visible ? "flex" : "none";
    backdrop.setAttribute("aria-hidden", visible ? "false" : "true");
  }

  function isFastNavLink(link) {
    if (!link || link.target || link.hasAttribute("download")) return false;
    const href = link.getAttribute("href") || "";
    if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) return false;
    try {
      const url = new URL(link.href, window.location.href);
      if (url.origin !== window.location.origin) return false;
      return url.pathname !== window.location.pathname || url.search !== window.location.search;
    } catch (_) {
      return false;
    }
  }

  function prefetchPage(link) {
    if (!isFastNavLink(link) || link.dataset.prefetched === "true") return;
    link.dataset.prefetched = "true";
    fetch(link.href, {
      method: "GET",
      credentials: "same-origin",
      cache: "force-cache",
      headers: { "X-Reverie-Prefetch": "1" },
    }).catch(() => undefined);
  }

  function installFastNavigation() {
    document.querySelectorAll("a[href]").forEach((link) => {
      if (!isFastNavLink(link)) return;
      link.addEventListener("pointerenter", () => prefetchPage(link), { passive: true });
      link.addEventListener("touchstart", () => prefetchPage(link), { passive: true });
      link.addEventListener("click", () => {
        document.documentElement.classList.add("route-loading");
      });
    });
    const likely = ["/", "/search", "/tasks", "/recommendations", "/entities", "/uploads"];
    window.setTimeout(() => {
      likely
        .filter((path) => path !== window.location.pathname)
        .slice(0, 4)
        .forEach((path) => fetch(path, { credentials: "same-origin", cache: "force-cache" }).catch(() => undefined));
    }, 900);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", installFastNavigation, { once: true });
  } else {
    installFastNavigation();
  }

  return {
    normaliseTags,
    normaliseEntities,
    toDisplayCase,
    displayNoteType,
    displayPerson,
    displayTag,
    displayEntity,
    formatWhen,
    toInputDateTimeValue,
    fromInputDateTimeValue,
    splitCommaList,
    chipClass,
    makeChip,
    appendImagePreview,
    fillAssetActions,
    noteStatus,
    isActionableNote,
    statusLabel,
    noteId,
    setModalVisible,
    installFastNavigation,
  };
})();
