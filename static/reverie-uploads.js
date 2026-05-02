(function () {
  const listEl = document.getElementById("uploadsList");
  const emptyEl = document.getElementById("uploadsEmpty");
  const countEl = document.getElementById("uploadsCount");
  const statusEl = document.getElementById("uploadsStatus");
  const { displayNoteType, formatWhen, noteId } = window.ReverieShared;

  async function api(path, options) {
    const resp = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...(options || {}),
    });
    const data = await resp.json().catch(() => null);
    if (!resp.ok) {
      if (resp.status === 401) throw new Error("Please sign in again on Home.");
      throw new Error(data?.detail || data?.message || `HTTP ${resp.status}`);
    }
    return data;
  }

  function assetLabel(note) {
    return String(note?.memory_type || "").toLowerCase() === "document" ? "Document" : "Image";
  }

  function renderItem(note) {
    const row = document.createElement("article");
    row.className = "upload-row";

    const preview = document.createElement("div");
    preview.className = "upload-preview";
    const type = assetLabel(note);
    if (type === "Image" && note?.image_url) {
      const img = document.createElement("img");
      img.src = note.image_url;
      img.alt = note?.title || "Uploaded image";
      img.loading = "lazy";
      preview.appendChild(img);
    } else {
      preview.textContent = "DOC";
    }
    row.appendChild(preview);

    const copy = document.createElement("div");
    copy.className = "upload-copy";
    const title = document.createElement("h3");
    title.textContent = note?.title || "(no title)";
    copy.appendChild(title);

    const summary = document.createElement("p");
    summary.textContent = note?.summary || note?.raw_text || "No summary saved.";
    copy.appendChild(summary);

    const meta = document.createElement("div");
    meta.className = "context-item-meta";
    [type, note?.note_type ? displayNoteType(note.note_type) : "", note?.created_at ? formatWhen(note.created_at) : ""]
      .filter(Boolean)
      .forEach((text, index) => {
        const chip = document.createElement("span");
        chip.className = index === 0 ? "chip good" : "chip muted";
        chip.textContent = text;
        meta.appendChild(chip);
      });
    copy.appendChild(meta);
    row.appendChild(copy);

    const actions = document.createElement("div");
    actions.className = "upload-actions";
    const open = document.createElement("a");
    open.className = "btn btn-secondary";
    open.href = note?.image_url || "#";
    open.target = "_blank";
    open.rel = "noopener noreferrer";
    open.textContent = type === "Document" ? "Open" : "View";
    actions.appendChild(open);

    const remove = document.createElement("button");
    remove.className = "btn btn-danger";
    remove.type = "button";
    remove.textContent = "Remove file";
    remove.addEventListener("click", async () => {
      if (!window.confirm("Remove this uploaded file but keep the memory item?")) return;
      remove.disabled = true;
      statusEl.textContent = "Removing file...";
      try {
        await api("/uploads/manage/remove", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note_id: noteId(note) }),
        });
        await loadUploads();
      } catch (err) {
        statusEl.textContent = err?.message || "Could not remove file.";
        remove.disabled = false;
      }
    });
    actions.appendChild(remove);
    row.appendChild(actions);
    return row;
  }

  async function loadUploads() {
    try {
      statusEl.textContent = "Loading...";
      const data = await api("/uploads/manage");
      const items = Array.isArray(data?.items) ? data.items : [];
      listEl.innerHTML = "";
      emptyEl.classList.toggle("hidden", items.length > 0);
      countEl.textContent = `${items.length} ${items.length === 1 ? "item" : "items"}`;
      items.forEach((item) => listEl.appendChild(renderItem(item)));
      statusEl.textContent = items.length ? "Choose a file to remove from its memory." : "No uploaded files found.";
    } catch (err) {
      listEl.innerHTML = "";
      emptyEl.classList.remove("hidden");
      countEl.textContent = "0 items";
      statusEl.textContent = err?.message || "Could not load uploads.";
    }
  }

  loadUploads();
})();
