window.ReverieShared = (() => {
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

  function appendImagePreview(parent, note) {
    if (!note?.image_url) return;
    const img = document.createElement("img");
    img.className = "note-image-preview";
    img.src = note.image_url;
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
    noteStatus,
    isActionableNote,
    statusLabel,
    noteId,
    setModalVisible,
  };
})();
