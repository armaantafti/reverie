(function () {
  function normaliseTags(tags) {
    if (!Array.isArray(tags)) return [];
    return tags.map((tag) => String(tag).trim()).filter(Boolean);
  }

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

  function chipClass(index) {
    return index % 3 === 0 ? "chip" : index % 3 === 1 ? "chip soft" : "chip muted";
  }

  function makeChip(text, cls, extra) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = `chip clickable-chip ${cls || ""} ${extra || ""}`.trim();
    el.textContent = text;
    return el;
  }

  function normaliseEntities(values) {
    if (!Array.isArray(values)) return [];
    return values.map((value) => String(value).trim()).filter(Boolean);
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

  function fillChipContainer(container, values, kind, openContext) {
    container.innerHTML = "";
    const list = kind === "entity" ? normaliseEntities(values) : normaliseTags(values);
    if (!list.length) {
      const span = document.createElement("span");
      span.className = "chip muted";
      span.textContent = kind === "entity" ? "No entities" : "No tags";
      container.appendChild(span);
      return;
    }
    list.forEach((value, index) => {
      const btn = makeChip(value, chipClass(index), "clickable-chip");
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        openContext(kind, value, value);
      });
      container.appendChild(btn);
    });
  }

  let sessionInfoPromise = null;

  async function getSessionInfo(force) {
    if (!force && sessionInfoPromise) return sessionInfoPromise;
    sessionInfoPromise = (async () => {
      try {
        const resp = await fetch("/session", {
          credentials: "same-origin",
        });
        if (!resp.ok) return null;
        const data = await resp.json();
        return data?.authenticated ? data : null;
      } catch (_) {
        return null;
      }
    })();
    return sessionInfoPromise;
  }

  async function ensureSession(force) {
    return Boolean((await getSessionInfo(force))?.authenticated);
  }

  function invalidateSession() {
    sessionInfoPromise = Promise.resolve(null);
  }

  function noteStatus(value) {
    const status = String(value || "pending").trim().toLowerCase();
    return ["pending", "completed", "skipped"].includes(status) ? status : "pending";
  }

  function statusLabel(value) {
    const status = noteStatus(value);
    return status.charAt(0).toUpperCase() + status.slice(1);
  }

  function setModalVisible(backdrop, visible) {
    backdrop.style.display = visible ? "flex" : "none";
    backdrop.setAttribute("aria-hidden", visible ? "false" : "true");
  }

  function initReverieListPage(config) {
    const primaryList = document.getElementById(config.primary.listId);
    const primaryEmpty = document.getElementById(config.primary.emptyId);
    const secondaryList = document.getElementById(config.secondary.listId);
    const secondaryEmpty = document.getElementById(config.secondary.emptyId);

    const detailBackdrop = document.getElementById(config.detail.backdropId);
    const detailClose = document.getElementById(config.detail.closeId);
    const detailTitle = document.getElementById(config.detail.titleId);
    const detailSub = document.getElementById(config.detail.subId);
    const detailSummary = document.getElementById(config.detail.summaryId);
    const detailRaw = document.getElementById(config.detail.rawId);
    const detailTags = document.getElementById(config.detail.tagsId);
    const detailEntities = document.getElementById(config.detail.entitiesId);
    const detailPerson = document.getElementById(config.detail.personId);
    const detailTime = document.getElementById(config.detail.timeId);
    const detailImage = document.getElementById(config.detail.imageId);

    const contextBackdrop = document.getElementById(config.context.backdropId);
    const contextClose = document.getElementById(config.context.closeId);
    const contextTitle = document.getElementById(config.context.titleId);
    const contextSub = document.getElementById(config.context.subId);
    const contextList = document.getElementById(config.context.listId);

    const statusBackdrop = document.getElementById(config.status.backdropId);
    const statusClose = document.getElementById(config.status.closeId);
    const statusCancel = document.getElementById(config.status.cancelId);
    const statusSave = document.getElementById(config.status.saveId);
    const statusTitle = document.getElementById(config.status.titleId);
    const statusSub = document.getElementById(config.status.subId);
    const statusSelect = document.getElementById(config.status.selectId);
    const statusNote = document.getElementById(config.status.noteId);

    let activeStatusNote = null;

    function resetEmptyState() {
      primaryEmpty.querySelector(".note-title").textContent = config.primary.emptyText;
      secondaryEmpty.querySelector(".note-title").textContent = config.secondary.emptyText;
    }

    function setSignedOutState() {
      primaryList.innerHTML = "";
      secondaryList.innerHTML = "";
      primaryEmpty.querySelector(".note-title").textContent = config.signedOutText;
      secondaryEmpty.querySelector(".note-title").textContent = config.signedOutText;
      primaryList.appendChild(primaryEmpty);
      secondaryList.appendChild(secondaryEmpty);
    }

    function openDetail(note) {
      detailTitle.textContent = note?.title || "(no title)";
      const bits = [];
      if (note?.note_type) bits.push(note.note_type);
      if (note?.memory_type === "image") bits.push("image");
      if (note?.person_name) bits.push(note.person_name);
      if (note?.due_time) bits.push(formatWhen(note.due_time));
      detailSub.textContent = bits.join(" · ");
      detailSummary.textContent = note?.summary || "";
      detailRaw.textContent = note?.extracted_text || note?.raw_text || "";
      detailPerson.textContent = note?.person_name || "—";
      detailTime.textContent = note?.due_time ? formatWhen(note.due_time) : "—";
      fillChipContainer(detailTags, note?.tags, "tag", openContext);
      fillChipContainer(detailEntities, note?.entities, "entity", openContext);
      if (detailImage) {
        if (note?.image_url) {
          detailImage.src = note.image_url;
          detailImage.style.display = "block";
        } else {
          detailImage.removeAttribute("src");
          detailImage.style.display = "none";
        }
      }

      setModalVisible(detailBackdrop, true);
    }

    function closeDetail() {
      setModalVisible(detailBackdrop, false);
    }

    function renderContextList(notes) {
      contextList.innerHTML = "";
      if (!notes || !notes.length) {
        const empty = document.createElement("div");
        empty.className = "context-empty";
        empty.textContent = "Nothing filed here yet.";
        contextList.appendChild(empty);
        return;
      }

      notes.forEach((note) => {
        const item = document.createElement("div");
        item.className = "context-item";

        const title = document.createElement("h4");
        title.className = "context-item-title";
        title.textContent = note?.title || "(no title)";
        item.appendChild(title);

        const meta = document.createElement("div");
        meta.className = "context-item-meta";

        if (note?.note_type) {
          const chip = document.createElement("span");
          chip.className = "chip good";
          chip.textContent = note.note_type;
          meta.appendChild(chip);
        }

        if (note?.person_name) {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className = "chip soft clickable-chip";
          chip.textContent = note.person_name;
          chip.addEventListener("click", (e) => {
            e.stopPropagation();
            openContext("person", note.person_name, note.person_name);
          });
          meta.appendChild(chip);
        }

        if (note?.due_time) {
          const chip = document.createElement("span");
          chip.className = "chip muted";
          chip.textContent = formatWhen(note.due_time);
          meta.appendChild(chip);
        }

        normaliseTags(note?.tags).slice(0, 4).forEach((tag, index) => {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className = `chip clickable-chip ${index % 2 ? "muted" : ""}`.trim();
          chip.textContent = tag;
          chip.addEventListener("click", (e) => {
            e.stopPropagation();
            openContext("tag", tag, tag);
          });
          meta.appendChild(chip);
        });

        normaliseEntities(note?.entities).slice(0, 2).forEach((entity, index) => {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className = `chip clickable-chip ${index % 2 ? "soft" : "muted"}`.trim();
          chip.textContent = entity;
          chip.addEventListener("click", (e) => {
            e.stopPropagation();
            openContext("entity", entity, entity);
          });
          meta.appendChild(chip);
        });

        item.appendChild(meta);
        appendImagePreview(item, note);

        if (note?.summary) {
          const summary = document.createElement("p");
          summary.className = "context-item-summary";
          summary.textContent = note.summary;
          item.appendChild(summary);
        }

        contextList.appendChild(item);
      });
    }

    async function openContext(kind, value, label) {
      if (!(await ensureSession())) return;

      contextTitle.textContent = label || value || "Context";
      contextSub.textContent = kind === "person"
        ? "Everything filed under this name"
        : kind === "entity"
          ? "Everything filed under this entity"
          : "Everything filed under this tag";
      contextList.innerHTML = "";
      setModalVisible(contextBackdrop, true);

      try {
        const params = new URLSearchParams({ kind, value });
        const resp = await fetch(`/context?${params.toString()}`, {
          credentials: "same-origin",
        });
        if (resp.status === 401) {
          invalidateSession();
          setSignedOutState();
          return;
        }
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        renderContextList(Array.isArray(data?.notes) ? data.notes : []);
      } catch (err) {
        console.error(err);
        contextList.innerHTML = "";
        const empty = document.createElement("div");
        empty.className = "context-empty";
        empty.textContent = "Could not load this view.";
        contextList.appendChild(empty);
      }
    }

    function openStatusModal(note) {
      activeStatusNote = note || null;
      if (!activeStatusNote) return;
      statusTitle.textContent = "Update status";
      statusSub.textContent = activeStatusNote?.title ? activeStatusNote.title : "(no title)";
      statusSelect.value = noteStatus(activeStatusNote?.status);
      statusNote.value = activeStatusNote?.status_note || "";
      setModalVisible(statusBackdrop, true);
      setTimeout(() => statusSelect.focus(), 0);
    }

    function closeStatusModal() {
      setModalVisible(statusBackdrop, false);
      activeStatusNote = null;
    }

    async function saveStatusUpdate() {
      if (!activeStatusNote) return;
      if (!(await ensureSession())) {
        alert("Please sign in first.");
        return;
      }

      const resp = await fetch("/notes/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          note_id: activeStatusNote.id,
          status: statusSelect.value,
          status_note: statusNote.value.trim(),
        }),
        credentials: "same-origin",
      });
      if (resp.status === 401) {
        invalidateSession();
        closeStatusModal();
        setSignedOutState();
        throw new Error("Please sign in first.");
      }

      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || ("HTTP " + resp.status));
      }

      closeStatusModal();
      await loadItems();
    }

    function renderCard(note) {
      const card = document.createElement("div");
      card.className = "note-card";
      card.setAttribute("role", "button");
      card.tabIndex = 0;
      card.addEventListener("click", () => openDetail(note));
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openDetail(note);
        }
      });

      const top = document.createElement("div");
      top.className = "note-top";

      const titleWrap = document.createElement("div");
      titleWrap.className = "note-title-wrap";

      const title = document.createElement("h4");
      title.className = "note-title";
      title.textContent = note?.title || "(no title)";
      titleWrap.appendChild(title);
      top.appendChild(titleWrap);

      const statusBtn = document.createElement("button");
      statusBtn.type = "button";
      statusBtn.className = "status-btn";
      statusBtn.textContent = statusLabel(note?.status);
      statusBtn.setAttribute("aria-label", `Change status for ${note?.title || "this note"}`);
      statusBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openStatusModal(note);
      });
      top.appendChild(statusBtn);

      card.appendChild(top);

      if (note?.summary) {
        const summary = document.createElement("p");
        summary.className = "note-summary";
        summary.textContent = note.summary;
        card.appendChild(summary);
      }

      appendImagePreview(card, note);

      const chips = document.createElement("div");
      chips.className = "chips";
      const meta = [];
      if (note?.person_name) meta.push({ text: note.person_name, cls: "chip soft", kind: "person", value: note.person_name });
      if (note?.due_time) meta.push({ text: formatWhen(note.due_time), cls: "chip muted" });
      if (note?.note_type) meta.push({ text: note.note_type, cls: "chip good" });
      normaliseTags(note?.tags).slice(0, 4).forEach((tag) => meta.push({ text: tag, cls: "chip", kind: "tag", value: tag }));
      normaliseEntities(note?.entities).slice(0, 2).forEach((entity, index) => meta.push({ text: entity, cls: index % 2 ? "chip soft" : "chip muted", kind: "entity", value: entity }));

      meta.slice(0, 6).forEach((item) => {
        const el = item.kind ? document.createElement("button") : document.createElement("span");
        if (item.kind) {
          el.type = "button";
          el.addEventListener("click", (e) => {
            e.stopPropagation();
            openContext(item.kind, item.value, item.text);
          });
        }
        el.className = `${item.cls} ${item.kind ? "clickable-chip" : ""}`.trim();
        el.textContent = item.text;
        chips.appendChild(el);
      });

      card.appendChild(chips);
      return card;
    }

    async function loadItems() {
      try {
        resetEmptyState();
        if (!(await ensureSession())) {
          setSignedOutState();
          return;
        }

        const resp = await fetch("/notes", {
          credentials: "same-origin",
        });
        if (resp.status === 401) {
          invalidateSession();
          setSignedOutState();
          return;
        }
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const notes = await resp.json();
        const groups = config.splitNotes(Array.isArray(notes) ? notes : []);

        primaryList.innerHTML = "";
        secondaryList.innerHTML = "";

        if (!groups.primary.length) {
          primaryList.appendChild(primaryEmpty);
        } else {
          groups.primary.forEach((note) => primaryList.appendChild(renderCard(note)));
        }

        if (!groups.secondary.length) {
          secondaryList.appendChild(secondaryEmpty);
        } else {
          groups.secondary.forEach((note) => secondaryList.appendChild(renderCard(note)));
        }
      } catch (err) {
        console.error(err);
      }
    }

    detailClose.addEventListener("click", closeDetail);
    detailBackdrop.addEventListener("click", (e) => {
      if (e.target === detailBackdrop) closeDetail();
    });

    contextClose.addEventListener("click", () => setModalVisible(contextBackdrop, false));
    contextBackdrop.addEventListener("click", (e) => {
      if (e.target === contextBackdrop) setModalVisible(contextBackdrop, false);
    });

    statusClose.addEventListener("click", closeStatusModal);
    statusCancel.addEventListener("click", closeStatusModal);
    statusSave.addEventListener("click", async () => {
      try {
        await saveStatusUpdate();
      } catch (err) {
        alert(err?.message || "Could not update status.");
        console.error(err);
      }
    });
    statusBackdrop.addEventListener("click", (e) => {
      if (e.target === statusBackdrop) closeStatusModal();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeDetail();
        setModalVisible(contextBackdrop, false);
        setModalVisible(statusBackdrop, false);
      }
    });

    loadItems();
    window.addEventListener("focus", loadItems);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) loadItems();
    });
    setInterval(loadItems, 30000);
  }

  window.initReverieListPage = initReverieListPage;
})();
