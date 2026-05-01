    const { normaliseTags, normaliseEntities, toDisplayCase, displayNoteType, displayPerson, displayTag, displayEntity, formatWhen, toInputDateTimeValue, fromInputDateTimeValue, splitCommaList, chipClass, makeChip, appendImagePreview, fillAssetActions, noteStatus, isActionableNote, statusLabel, noteId, setModalVisible } = window.ReverieShared;
    const ALL_TAGS = Array.isArray(window.REVERIE_TAGS) ? window.REVERIE_TAGS : [];
    const TOPIC_BUTTONS = [...ALL_TAGS, "passive"];

function fillChipContainer(container, values, kind) {
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
        const rawValue = String(value).trim();
        const label = kind === "entity" ? displayEntity(rawValue) : displayTag(rawValue);
        const btn = makeChip(label, chipClass(index), "clickable-chip");
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          openContext(kind, rawValue, label);
        });
        container.appendChild(btn);
      });
    }

    const authPanel = document.getElementById("authPanel");
    const appShell = document.getElementById("appShell");
    const authForm = document.getElementById("authForm");
    const authEmail = document.getElementById("authEmail");
    const authPassword = document.getElementById("authPassword");
    const authSubmit = document.getElementById("authSubmit");
    const authStatus = document.getElementById("authStatus");
    const authHint = document.getElementById("authHint");
    const loginTab = document.getElementById("loginTab");
    const signupTab = document.getElementById("signupTab");
    const logoutBtn = document.getElementById("logoutBtn");
    const loginState = document.getElementById("loginState");

    const saveBtn = document.getElementById("saveBtn");
    const uploadBtn = document.getElementById("uploadBtn");
    const uploadInput = document.getElementById("uploadInput");
    const noteTextEl = document.getElementById("noteText");
    const saveStatusEl = document.getElementById("saveStatus");
    const searchQueryEl = document.getElementById("searchQuery");
    const searchRangeEl = document.getElementById("searchRange");
    const searchBtn = document.getElementById("searchBtn");
    const searchStatusEl = document.getElementById("searchStatus");
    const searchResultsEl = document.getElementById("searchResults");
    const smartSearchToggle = document.getElementById("smartSearchToggle");
    const smartSummaryEl = document.getElementById("smartSummary");
    const forYouListEl = document.getElementById("forYouList");
    const forYouEmptyEl = document.getElementById("forYouEmpty");
    const forYouMoreBtn = document.getElementById("forYouMoreBtn");
    const tagBubblesEl = document.getElementById("tagBubbles");
    const manageEntitiesBtn = document.getElementById("manageEntitiesBtn");

    const detailBackdrop = document.getElementById("detailBackdrop");
    const detailClose = document.getElementById("detailClose");
    const detailTitle = document.getElementById("detailTitle");
    const detailSub = document.getElementById("detailSub");
    const detailSummary = document.getElementById("detailSummary");
    const detailRaw = document.getElementById("detailRaw");
    const detailImage = document.getElementById("detailImage");
    const detailAssetActions = document.getElementById("detailAssetActions");
    const detailTags = document.getElementById("detailTags");
    const detailEntities = document.getElementById("detailEntities");
    const detailPerson = document.getElementById("detailPerson");
    const detailTime = document.getElementById("detailTime");
    const detailStatus = document.getElementById("detailStatus");

    const contextBackdrop = document.getElementById("contextBackdrop");
    const contextClose = document.getElementById("contextClose");
    const contextTitle = document.getElementById("contextTitle");
    const contextSub = document.getElementById("contextSub");
    const contextList = document.getElementById("contextList");

    const forYouBackdrop = document.getElementById("forYouBackdrop");
    const forYouClose = document.getElementById("forYouClose");
    const forYouModalList = document.getElementById("forYouModalList");
    const statusBackdrop = document.getElementById("statusBackdrop");
    const statusClose = document.getElementById("statusClose");
    const statusCancel = document.getElementById("statusCancel");
    const statusSave = document.getElementById("statusSave");
    const statusTitle = document.getElementById("statusTitle");
    const statusSub = document.getElementById("statusSub");
    const statusSelect = document.getElementById("statusSelect");
    const statusNote = document.getElementById("statusNote");
    const detailEditBtn = document.getElementById("detailEditBtn");
    const detailDeleteBtn = document.getElementById("detailDeleteBtn");
    const editBackdrop = document.getElementById("editBackdrop");
    const editClose = document.getElementById("editClose");
    const editCancel = document.getElementById("editCancel");
    const editSave = document.getElementById("editSave");
    const editTitle = document.getElementById("editTitle");
    const editSub = document.getElementById("editSub");
    const editType = document.getElementById("editType");
    const editDueTime = document.getElementById("editDueTime");
    const editPerson = document.getElementById("editPerson");
    const editTags = document.getElementById("editTags");
    const editEntities = document.getElementById("editEntities");
    const manageEntitiesBackdrop = document.getElementById("manageEntitiesBackdrop");
    const manageEntitiesClose = document.getElementById("manageEntitiesClose");
    const manageEntitiesSearch = document.getElementById("manageEntitiesSearch");
    const manageEntitiesList = document.getElementById("manageEntitiesList");
    const manageEntitiesEmpty = document.getElementById("manageEntitiesEmpty");
    const manageEntitiesKind = document.getElementById("manageEntitiesKind");
    const manageEntitiesValue = document.getElementById("manageEntitiesValue");
    const manageEntitiesMerge = document.getElementById("manageEntitiesMerge");
    const manageEntitiesRename = document.getElementById("manageEntitiesRename");
    const manageEntitiesCreate = document.getElementById("manageEntitiesCreate");
    const manageEntitiesDelete = document.getElementById("manageEntitiesDelete");
    const manageEntitiesStatus = document.getElementById("manageEntitiesStatus");

    let authMode = "login";
    let activeStatusNote = null;
    let activeDetailNote = null;
    let activeEditNote = null;
    let activeContextQuery = null;
    let sessionInfoPromise = null;
    let manageEntityItems = [];
    let manageEntitySelection = new Set();

    function manageItemKey(kind, value) {
      return `${String(kind || "").trim().toLowerCase()}:${String(value || "").trim().toLowerCase()}`;
    }

    function kindLabel(kind) {
      return kind === "person" ? "Name" : kind === "entity" ? "Entity" : "Topic";
    }

function setAuthMode(nextMode) {
      authMode = nextMode === "signup" ? "signup" : "login";
      const isLogin = authMode === "login";
      loginTab.classList.toggle("active", isLogin);
      signupTab.classList.toggle("active", !isLogin);
      authSubmit.textContent = isLogin ? "Log in" : "Sign up";
      authHint.textContent = isLogin
        ? "Use your email and password to log in. If you are new, switch to Sign up."
        : "Create an account with your email and password. Then log in with the same details.";
      authStatus.textContent = "";
    }

function setAuthedState(isAuthed) {
      authPanel.classList.toggle("hidden", isAuthed);
      appShell.classList.toggle("hidden", !isAuthed);
      logoutBtn.classList.toggle("hidden", !isAuthed);
      loginState.textContent = isAuthed ? "Signed in" : "Signed out";
    }

    async function getSessionInfo(force = false) {
      if (!force && sessionInfoPromise) return sessionInfoPromise;
      sessionInfoPromise = (async () => {
        try {
          const url = new URL("/session", window.location.origin);
          url.searchParams.set("_", String(Date.now()));
          const resp = await fetch(url.toString(), {
            credentials: "same-origin",
            cache: "no-store",
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

    async function ensureSession(force = false) {
      const session = await getSessionInfo(force);
      const isAuthed = Boolean(session?.authenticated);
      setAuthedState(isAuthed);
      return isAuthed;
    }

    function invalidateSessionUi() {
      clearSession();
      throw new Error("Please log in first.");
    }

    async function apiGet(path, params = {}) {
      const url = new URL(path, window.location.origin);
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && String(value).trim() !== "") {
          url.searchParams.set(key, String(value));
        }
      });
      url.searchParams.set("_", String(Date.now()));
      const resp = await fetch(url.toString(), {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (resp.status === 401) invalidateSessionUi();
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    }

    async function apiPost(path, body) {
      const headers = { "Content-Type": "application/json" };
      const resp = await fetch(path, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        credentials: "same-origin",
      });
      if (resp.status === 401) invalidateSessionUi();
      if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try {
          const data = await resp.json();
          detail = data?.detail || data?.message || detail;
        } catch (_) {}
        throw new Error(detail);
      }
      return await resp.json();
    }

    function openStatusModal(note) {
      activeStatusNote = note || null;
      if (!activeStatusNote) return;
      statusTitle.textContent = "Update status";
      statusSub.textContent = activeStatusNote?.title || "(no title)";
      statusSelect.value = noteStatus(activeStatusNote?.status);
      statusNote.value = activeStatusNote?.status_note || "";
      setModalVisible(statusBackdrop, true);
      setTimeout(() => statusSelect.focus(), 0);
    }

    function closeStatusModal() {
      setModalVisible(statusBackdrop, false);
      activeStatusNote = null;
    }

    async function refreshAfterStatusChange() {
      const refreshes = [loadForYou()];
      if ((searchQueryEl.value || "").trim() || (searchRangeEl.value || "").trim()) {
        refreshes.push(runSearch());
      }
      if (activeContextQuery && contextBackdrop.getAttribute("aria-hidden") === "false") {
        refreshes.push(loadContextNotes(activeContextQuery.kind, activeContextQuery.value));
      }
      if (forYouBackdrop.getAttribute("aria-hidden") === "false") {
        refreshes.push(openForYouModal());
      }
      await Promise.all(refreshes);
    }

    async function saveStatusUpdate() {
      if (!activeStatusNote) return;
      if (!(await ensureSession())) throw new Error("Please log in first.");
      const id = noteId(activeStatusNote);
      if (!id) throw new Error("Could not identify this memory. Refresh and try again.");
      const nextStatus = statusSelect.value;
      const nextStatusNote = statusNote.value.trim();
      await apiPost("/notes/status", {
        note_id: id,
        status: nextStatus,
        status_note: nextStatusNote,
      });
      activeStatusNote.status = nextStatus;
      activeStatusNote.status_note = nextStatusNote;
      if (noteId(activeDetailNote) === id) {
        activeDetailNote.status = nextStatus;
        activeDetailNote.status_note = nextStatusNote;
        openDetail(activeDetailNote);
      }
      closeStatusModal();
      await refreshAfterStatusChange();
    }

    function closeManageEntitiesModal() {
      setModalVisible(manageEntitiesBackdrop, false);
      manageEntitiesStatus.textContent = "";
    }

    function selectedManageItems() {
      return manageEntityItems.filter((item) => manageEntitySelection.has(manageItemKey(item.kind, item.value)));
    }

    function selectedManageKind() {
      const kinds = [...new Set(selectedManageItems().map((item) => item.kind))];
      if (!kinds.length) return null;
      return kinds.length === 1 ? kinds[0] : null;
    }

    function renderManageEntitiesList() {
      const query = String(manageEntitiesSearch.value || "").trim().toLowerCase();
      const filtered = manageEntityItems.filter((item) => {
        if (!query) return true;
        const haystack = [item.value, ...(Array.isArray(item.aliases) ? item.aliases : []), item.kind]
          .join(" ")
          .toLowerCase();
        return haystack.includes(query);
      });

      manageEntitiesList.innerHTML = "";
      manageEntitiesEmpty.classList.toggle("hidden", filtered.length > 0);

      filtered.forEach((item) => {
        const key = manageItemKey(item.kind, item.value);
        const row = document.createElement("label");
        row.className = "manage-entities-item";

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = manageEntitySelection.has(key);
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) manageEntitySelection.add(key);
          else manageEntitySelection.delete(key);
          const kind = selectedManageKind();
          if (kind) manageEntitiesKind.value = kind;
        });
        row.appendChild(checkbox);

        const copy = document.createElement("div");
        copy.className = "manage-entities-copy";

        const title = document.createElement("div");
        title.className = "manage-entities-title";
        const name = document.createElement("span");
        name.className = "manage-entities-name";
        name.textContent = item.kind === "person" ? displayPerson(item.value) : item.kind === "entity" ? displayEntity(item.value) : displayTag(item.value);
        title.appendChild(name);

        const badge = document.createElement("span");
        badge.className = "chip muted";
        badge.textContent = kindLabel(item.kind);
        title.appendChild(badge);

        if (Number(item.count || 0) > 0) {
          const countChip = document.createElement("span");
          countChip.className = "chip soft";
          countChip.textContent = `${item.count} saved`;
          title.appendChild(countChip);
        }
        copy.appendChild(title);

        const meta = document.createElement("div");
        meta.className = "manage-entities-meta";
        const aliases = Array.isArray(item.aliases) ? item.aliases : [];
        meta.textContent = aliases.length
          ? `Aliases: ${aliases.map((value) => item.kind === "person" ? displayPerson(value) : item.kind === "entity" ? displayEntity(value) : displayTag(value)).join(", ")}`
          : "No aliases yet.";
        copy.appendChild(meta);

        row.appendChild(copy);
        manageEntitiesList.appendChild(row);
      });
    }

    async function loadManageEntities() {
      const data = await apiGet("/entities/manage");
      manageEntityItems = Array.isArray(data?.items) ? data.items : [];
      renderManageEntitiesList();
      if (!manageEntityItems.length) {
        manageEntitiesStatus.textContent = "Nothing filed yet.";
      }
    }

    async function refreshAfterManageEntitiesChange() {
      closeDetail();
      closeEditModal();
      await Promise.all([loadManageEntities(), loadForYou(), runSearch()]);
      if (activeContextQuery && contextBackdrop.getAttribute("aria-hidden") === "false") {
        await loadContextNotes(activeContextQuery.kind, activeContextQuery.value);
      }
      if (forYouBackdrop.getAttribute("aria-hidden") === "false") {
        await openForYouModal();
      }
    }

    async function withManageEntitiesAction(action, successMessage) {
      manageEntitiesStatus.textContent = "Saving…";
      try {
        await action();
        manageEntitySelection = new Set();
        manageEntitiesValue.value = "";
        await refreshAfterManageEntitiesChange();
        manageEntitiesStatus.textContent = successMessage;
      } catch (err) {
        console.error(err);
        manageEntitiesStatus.textContent = err?.message || "Could not update entities.";
      }
    }

    async function openManageEntitiesModal() {
      if (!(await ensureSession())) return;
      setModalVisible(manageEntitiesBackdrop, true);
      manageEntitiesStatus.textContent = "Loading…";
      manageEntitiesSearch.value = "";
      manageEntitiesValue.value = "";
      manageEntitySelection = new Set();
      try {
        await loadManageEntities();
        manageEntitiesStatus.textContent = "";
      } catch (err) {
        console.error(err);
        manageEntitiesStatus.textContent = err?.message || "Could not load entities.";
      }
      setTimeout(() => manageEntitiesSearch.focus(), 0);
    }

    function closeEditModal() {
      setModalVisible(editBackdrop, false);
      activeEditNote = null;
    }

    function openEditModal(note) {
      activeEditNote = note || activeDetailNote || null;
      if (!activeEditNote) return;
      editTitle.textContent = "Edit memory";
      editSub.textContent = activeEditNote?.title || "(no title)";
      editType.value = String(activeEditNote?.note_type || "note").toLowerCase();
      editDueTime.value = toInputDateTimeValue(activeEditNote?.due_time);
      editPerson.value = activeEditNote?.person_name || "";
      editTags.value = normaliseTags(activeEditNote?.tags).join(", ");
      editEntities.value = normaliseEntities(activeEditNote?.entities).join(", ");
      setModalVisible(editBackdrop, true);
      setTimeout(() => editPerson.focus(), 0);
    }

    async function refreshAfterNoteMutation() {
      await refreshAfterStatusChange();
    }

    async function saveNoteEdit() {
      if (!activeEditNote) return;
      if (!(await ensureSession())) throw new Error("Please log in first.");
      const id = noteId(activeEditNote);
      if (!id) throw new Error("Could not identify this memory. Refresh and try again.");
      await apiPost("/notes/update", {
        note_id: id,
        note_type: editType.value,
        due_time: fromInputDateTimeValue(editDueTime.value),
        person_name: editPerson.value.trim(),
        tags: splitCommaList(editTags.value),
        entities: splitCommaList(editEntities.value),
      });
      closeEditModal();
      closeDetail();
      await refreshAfterNoteMutation();
    }

    async function deleteNote(note) {
      if (!note) return;
      if (!window.confirm("Remove this memory entirely?")) return;
      if (!(await ensureSession())) throw new Error("Please log in first.");
      const id = noteId(note);
      if (!id) throw new Error("Could not identify this memory. Refresh and try again.");
      await apiPost("/notes/delete", { note_id: id });
      closeEditModal();
      if (activeDetailNote && noteId(activeDetailNote) === id) closeDetail();
      await refreshAfterNoteMutation();
    }

    async function deleteActiveNote() {
      await deleteNote(activeDetailNote || activeEditNote);
    }

    function renderNoteCard(note, extraClass = "", options = {}) {
      const btn = document.createElement("div");
      btn.className = `note-card ${extraClass}`.trim();
      btn.setAttribute("role", "button");
      btn.tabIndex = 0;
      btn.addEventListener("click", () => openDetail(note));
      btn.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openDetail(note);
        }
      });

      const top = document.createElement("div");
      top.className = "note-top";

      const title = document.createElement("h4");
      title.className = "note-title";
      title.textContent = note?.title || "(no title)";
      top.appendChild(title);

      if (options.showStatusButton && isActionableNote(note)) {
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
      }

      btn.appendChild(top);

      if (note?.summary) {
        const summary = document.createElement("p");
        summary.className = "note-summary";
        summary.textContent = note.summary;
        btn.appendChild(summary);
      }

      appendImagePreview(btn, note);

      const chips = document.createElement("div");
      chips.className = "chips";
      const meta = [];
      if (note?.note_type) meta.push({ text: displayNoteType(note.note_type), cls: "chip good" });
      if (note?.memory_type === "document") meta.push({ text: "Document", cls: "chip muted" });
      if (note?.memory_type === "image") meta.push({ text: "Image", cls: "chip muted" });
      if (note?.person_name) meta.push({ text: displayPerson(note.person_name), cls: "chip soft", kind: "person", value: note.person_name });
      if (note?.due_time) meta.push({ text: formatWhen(note.due_time), cls: "chip muted" });
      normaliseTags(note?.tags).slice(0, 4).forEach(tag => meta.push({ text: displayTag(tag), cls: "chip", kind: "tag", value: tag }));
      normaliseEntities(note?.entities).slice(0, 2).forEach((entity, index) => meta.push({ text: displayEntity(entity), cls: index % 2 ? "chip soft" : "chip muted", kind: "entity", value: entity }));
      meta.slice(0, 6).forEach(item => chips.appendChild(cardChip(item.text, item.cls, item.kind, item.value)));
      btn.appendChild(chips);
      return btn;
    }

    function cardChip(text, cls, kind = null, value = null) {
      const el = document.createElement(kind ? "button" : "span");
      if (kind) {
        el.type = "button";
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          openContext(kind, value, text);
        });
      }
      el.className = `${cls} ${kind ? "clickable-chip" : ""}`.trim();
      el.textContent = text;
      return el;
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
      notes.forEach(note => {
        contextList.appendChild(renderContextItem(note, isActionableNote(note), true));
      });
    }

    function openDetail(note) {
      activeDetailNote = note || null;
      detailTitle.textContent = note?.title || "(no title)";
      const bits = [];
      if (note?.note_type) bits.push(displayNoteType(note.note_type));
      if (note?.memory_type === "image") bits.push("Image");
      if (note?.memory_type === "document") bits.push("Document");
      if (note?.person_name) bits.push(displayPerson(note.person_name));
      if (note?.due_time) bits.push(formatWhen(note.due_time));
      detailSub.textContent = bits.join(" · ");
      detailSummary.textContent = note?.summary || "";
      detailRaw.textContent = note?.extracted_text || note?.raw_text || "";
      detailPerson.textContent = note?.person_name ? displayPerson(note.person_name) : "-";
      detailTime.textContent = note?.due_time ? formatWhen(note.due_time) : "-";
      detailStatus.innerHTML = "";
      if (isActionableNote(note)) {
        const statusBtn = document.createElement("button");
        statusBtn.type = "button";
        statusBtn.className = "status-btn";
        statusBtn.textContent = statusLabel(note?.status);
        statusBtn.setAttribute("aria-label", `Change status for ${note?.title || "this note"}`);
        statusBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          openStatusModal(note);
        });
        detailStatus.appendChild(statusBtn);
      } else {
        detailStatus.textContent = "-";
      }
      fillChipContainer(detailTags, note?.tags, "tag");
      fillChipContainer(detailEntities, note?.entities, "entity");
      if (note?.image_url && note?.memory_type === "image") {
        detailImage.src = note.image_url;
        detailImage.style.display = "block";
      } else {
        detailImage.removeAttribute("src");
        detailImage.style.display = "none";
      }
      fillAssetActions(detailAssetActions, note);
      setModalVisible(detailBackdrop, true);
    }

    function closeDetail() {
      setModalVisible(detailBackdrop, false);
      activeDetailNote = null;
    }
    detailClose.addEventListener("click", closeDetail);
    detailBackdrop.addEventListener("click", (e) => { if (e.target === detailBackdrop) closeDetail(); });
    detailEditBtn.addEventListener("click", () => openEditModal(activeDetailNote));
    detailDeleteBtn.addEventListener("click", async () => {
      try {
        await deleteActiveNote();
      } catch (err) {
        console.error(err);
        alert(err?.message || "Could not remove this memory.");
      }
    });

    async function loadContextNotes(kind, value) {
      const currentLabel = activeContextQuery?.label || value || "Context";
      contextTitle.textContent = currentLabel;
      contextSub.textContent = kind === "person"
        ? "Everything filed under this name"
        : kind === "entity"
          ? "Everything filed under this entity"
          : kind === "type"
            ? "Everything filed under this memory type"
            : "Everything filed under this tag";
      contextList.innerHTML = "";
      setModalVisible(contextBackdrop, true);
      try {
        const data = await apiGet("/context", { kind, value });
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

    async function openContext(kind, value, label) {
      if (!(await ensureSession())) return;
      activeContextQuery = { kind, value, label };
      contextTitle.textContent = label || value || "Context";
      setModalVisible(contextBackdrop, true);
      await loadContextNotes(kind, value);
    }

    function closeContext() {
      setModalVisible(contextBackdrop, false);
      activeContextQuery = null;
    }
    contextClose.addEventListener("click", closeContext);
    contextBackdrop.addEventListener("click", (e) => { if (e.target === contextBackdrop) closeContext(); });
    manageEntitiesBtn.addEventListener("click", openManageEntitiesModal);
    manageEntitiesClose.addEventListener("click", closeManageEntitiesModal);
    manageEntitiesBackdrop.addEventListener("click", (e) => { if (e.target === manageEntitiesBackdrop) closeManageEntitiesModal(); });
    manageEntitiesSearch.addEventListener("input", renderManageEntitiesList);
    manageEntitiesMerge.addEventListener("click", async () => {
      const items = selectedManageItems();
      const kind = selectedManageKind();
      const target = String(manageEntitiesValue.value || "").trim();
      if (!items.length) {
        manageEntitiesStatus.textContent = "Select at least one entry to merge.";
        return;
      }
      if (!kind) {
        manageEntitiesStatus.textContent = "Merge works within one type at a time.";
        return;
      }
      if (!target) {
        manageEntitiesStatus.textContent = "Enter the canonical value to merge into.";
        return;
      }
      await withManageEntitiesAction(
        () => apiPost("/entities/manage/merge", {
          kind,
          values: items.map((item) => item.value),
          target_value: target,
        }),
        `Merged into ${kind === "person" ? displayPerson(target) : kind === "entity" ? displayEntity(target) : displayTag(target)}.`
      );
    });
    manageEntitiesRename.addEventListener("click", async () => {
      const items = selectedManageItems();
      const target = String(manageEntitiesValue.value || "").trim();
      if (items.length !== 1) {
        manageEntitiesStatus.textContent = "Select exactly one entry to rename.";
        return;
      }
      if (!target) {
        manageEntitiesStatus.textContent = "Enter the new value.";
        return;
      }
      await withManageEntitiesAction(
        () => apiPost("/entities/manage/rename", {
          kind: items[0].kind,
          value: items[0].value,
          new_value: target,
        }),
        "Renamed."
      );
    });
    manageEntitiesCreate.addEventListener("click", async () => {
      const value = String(manageEntitiesValue.value || "").trim();
      const kind = String(manageEntitiesKind.value || "").trim().toLowerCase();
      if (!value) {
        manageEntitiesStatus.textContent = "Enter a value to create.";
        return;
      }
      await withManageEntitiesAction(
        () => apiPost("/entities/manage/create", { kind, value }),
        "Created."
      );
    });
    manageEntitiesDelete.addEventListener("click", async () => {
      const items = selectedManageItems();
      const kind = selectedManageKind();
      if (!items.length) {
        manageEntitiesStatus.textContent = "Select at least one entry to delete.";
        return;
      }
      if (!kind) {
        manageEntitiesStatus.textContent = "Delete works within one type at a time.";
        return;
      }
      if (!window.confirm("Remove these entries from saved memories and alias mappings?")) return;
      await withManageEntitiesAction(
        () => apiPost("/entities/manage/delete", {
          kind,
          values: items.map((item) => item.value),
        }),
        "Deleted."
      );
    });

    function renderForYouModal(notes) {
      forYouModalList.innerHTML = "";
      if (!notes || !notes.length) {
        const empty = document.createElement("div");
        empty.className = "context-empty";
        empty.textContent = "Nothing surfaced yet.";
        forYouModalList.appendChild(empty);
        return;
      }
      notes.forEach(note => {
        forYouModalList.appendChild(renderContextItem(note, true));
      });
    }

    function renderContextItem(note, showStatusButton = false, showManageActions = false) {
      const item = document.createElement("div");
      item.className = "context-item";
      const top = document.createElement("div");
      top.className = "note-top";
      const title = document.createElement("h4");
      title.className = "context-item-title";
      title.textContent = note?.title || "(no title)";
      top.appendChild(title);
      if (showStatusButton && isActionableNote(note)) {
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
      }
      item.appendChild(top);

      const meta = document.createElement("div");
      meta.className = "context-item-meta";
      if (note?.note_type) {
        const chip = document.createElement("span");
        chip.className = "chip good";
        chip.textContent = displayNoteType(note.note_type);
        meta.appendChild(chip);
      }
      if (note?.person_name) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "chip soft clickable-chip";
        chip.textContent = displayPerson(note.person_name);
        chip.addEventListener("click", (e) => {
          e.stopPropagation();
          openContext("person", note.person_name, displayPerson(note.person_name));
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
        chip.textContent = displayTag(tag);
        chip.addEventListener("click", (e) => {
          e.stopPropagation();
          openContext("tag", tag, displayTag(tag));
        });
        meta.appendChild(chip);
      });
      normaliseEntities(note?.entities).slice(0, 2).forEach((entity, index) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = `chip clickable-chip ${index % 2 ? "soft" : "muted"}`.trim();
        chip.textContent = displayEntity(entity);
        chip.addEventListener("click", (e) => {
          e.stopPropagation();
          openContext("entity", entity, displayEntity(entity));
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
      if (showManageActions) {
        const actions = document.createElement("div");
        actions.className = "context-actions";

        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "btn btn-secondary";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          openEditModal(note);
        });
        actions.appendChild(editBtn);

        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "btn btn-danger";
        deleteBtn.textContent = "Delete";
        deleteBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          try {
            await deleteNote(note);
          } catch (err) {
            console.error(err);
            alert(err?.message || "Could not remove this memory.");
          }
        });
        actions.appendChild(deleteBtn);

        item.appendChild(actions);
      }
      return item;
    }

    async function loadForYou() {
      if (!(await ensureSession())) return;
      try {
        const data = await apiGet("/for-you", { limit: 3 });
        const notes = Array.isArray(data?.notes) ? data.notes : [];
        forYouListEl.innerHTML = "";
        if (!notes.length) {
          forYouListEl.appendChild(forYouEmptyEl);
          return;
        }
        notes.forEach(note => {
          const card = renderNoteCard(note, "featured", { showStatusButton: true });
          forYouListEl.appendChild(card);
        });
      } catch (err) {
        console.error(err);
        forYouListEl.innerHTML = "";
        forYouListEl.appendChild(forYouEmptyEl);
      }
    }

    async function openForYouModal() {
      if (!(await ensureSession())) return;
      setModalVisible(forYouBackdrop, true);
      forYouModalList.innerHTML = "";
      try {
        const data = await apiGet("/for-you/all");
        const notes = Array.isArray(data?.notes) ? data.notes : [];
        renderForYouModal(notes);
      } catch (err) {
        console.error(err);
        forYouModalList.innerHTML = "";
        const empty = document.createElement("div");
        empty.className = "context-empty";
        empty.textContent = "Could not load this list.";
        forYouModalList.appendChild(empty);
      }
    }
    forYouMoreBtn.addEventListener("click", openForYouModal);
    forYouClose.addEventListener("click", () => setModalVisible(forYouBackdrop, false));
    forYouBackdrop.addEventListener("click", (e) => { if (e.target === forYouBackdrop) setModalVisible(forYouBackdrop, false); });
    statusClose.addEventListener("click", closeStatusModal);
    statusCancel.addEventListener("click", closeStatusModal);
    statusSave.addEventListener("click", async () => {
      try {
        await saveStatusUpdate();
      } catch (err) {
        console.error(err);
        alert(err?.message || "Could not update status.");
      }
    });
    statusBackdrop.addEventListener("click", (e) => { if (e.target === statusBackdrop) closeStatusModal(); });
    editClose.addEventListener("click", closeEditModal);
    editCancel.addEventListener("click", closeEditModal);
    editSave.addEventListener("click", async () => {
      try {
        await saveNoteEdit();
      } catch (err) {
        console.error(err);
        alert(err?.message || "Could not update this memory.");
      }
    });
    editBackdrop.addEventListener("click", (e) => { if (e.target === editBackdrop) closeEditModal(); });

    function loadImageElement(file) {
      return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = () => {
          URL.revokeObjectURL(url);
          resolve(img);
        };
        img.onerror = () => {
          URL.revokeObjectURL(url);
          reject(new Error("Could not read image."));
        };
        img.src = url;
      });
    }

    async function compressImageFile(file) {
      if (!file?.type?.startsWith("image/")) return file;
      try {
        const img = await loadImageElement(file);
        const maxSide = 1600;
        let width = img.naturalWidth || img.width;
        let height = img.naturalHeight || img.height;
        const scale = Math.min(1, maxSide / Math.max(width, height));
        width = Math.max(1, Math.round(width * scale));
        height = Math.max(1, Math.round(height * scale));

        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) return file;
        ctx.drawImage(img, 0, 0, width, height);

        const targetType = file.type === "image/png" ? "image/png" : "image/jpeg";
        const blob = await new Promise((resolve) => canvas.toBlob(resolve, targetType, 0.82));
        if (!blob || blob.size >= file.size) return file;

        const name = file.name.replace(/\.[^.]+$/, targetType === "image/png" ? ".png" : ".jpg");
        return new File([blob], name, { type: targetType });
      } catch (_) {
        return file;
      }
    }

    async function uploadFiles(files) {
      if (!(await ensureSession())) {
        saveStatusEl.textContent = "Please log in first.";
        return;
      }
      if (!files.length) return;
      if (files.length > 10) {
        saveStatusEl.textContent = "Upload at most 10 files at once.";
        return;
      }

      const prev = uploadBtn.textContent;
      uploadBtn.disabled = true;
      uploadBtn.textContent = "Uploading…";
      saveStatusEl.textContent = "Uploading files…";
      try {
        const prepared = [];
        for (const file of files) prepared.push(await compressImageFile(file));

        const form = new FormData();
        prepared.forEach((file) => form.append("files", file, file.name));

        const resp = await fetch("/notes/uploads", {
          method: "POST",
          body: form,
          credentials: "same-origin",
        });
        if (resp.status === 401) invalidateSessionUi();
        if (!resp.ok) {
          let detail = `HTTP ${resp.status}`;
          try {
            const data = await resp.json();
            detail = data?.detail || detail;
          } catch (_) {}
          throw new Error(detail);
        }

        const data = await resp.json();
        saveStatusEl.textContent = data?.message || "Files uploaded. Processing is running in the background.";
        await Promise.all([loadForYou(), runSearch()]);
      } catch (err) {
        console.error(err);
        saveStatusEl.textContent = err?.message || "Upload failed.";
      } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = prev;
        uploadInput.value = "";
      }
    }

    async function saveNote() {
      if (!(await ensureSession())) {
        saveStatusEl.textContent = "Please log in first.";
        return;
      }
      const text = noteTextEl.value.trim();
      if (!text) {
        saveStatusEl.textContent = "Type something first.";
        return;
      }
      const prev = saveBtn.textContent;
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving…";
      saveStatusEl.textContent = "Saving…";
      try {
        const note = await apiPost("/notes/text", {
          text,
        });
        noteTextEl.value = "";
        saveStatusEl.textContent = "Saved.";
        await Promise.all([loadForYou(), runSearch()]);
      } catch (err) {
        console.error(err);
        saveStatusEl.textContent = "Save failed.";
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = prev;
      }
    }
    saveBtn.addEventListener("click", saveNote);
    uploadBtn.addEventListener("click", () => uploadInput.click());
    uploadInput.addEventListener("change", async () => {
      const files = Array.from(uploadInput.files || []);
      if (!files.length) return;
      await uploadFiles(files);
    });

    async function runSearch() {
      if (!(await ensureSession())) {
        searchStatusEl.textContent = "Please log in first.";
        return;
      }

      const q = (searchQueryEl.value || "").trim();
      const rangeVal = (searchRangeEl.value || "").trim();
      searchResultsEl.innerHTML = "";
      smartSummaryEl.innerHTML = "";
      smartSummaryEl.style.display = "none";

      if (!q && !rangeVal) {
        searchStatusEl.textContent = "";
        return;
      }

      const prev = searchBtn.textContent;
      searchBtn.disabled = true;
      searchBtn.textContent = "Searching…";
      searchStatusEl.textContent = "Searching…";

      try {
        if (smartSearchToggle.checked && q) {
          const body = { query: q };
          if (rangeVal && rangeVal !== "0") body.days = parseInt(rangeVal, 10);
          const data = await apiPost("/smart-search", body);
          const notes = Array.isArray(data.notes) ? data.notes : [];
          searchStatusEl.textContent = notes.length ? "" : "No matches.";
          if (data.summary) {
            const summaryCard = document.createElement("div");
            summaryCard.className = "note-card";
            summaryCard.style.cursor = "default";
            summaryCard.tabIndex = -1;
            const title = document.createElement("h4");
            title.className = "note-title";
            title.textContent = "Smart summary";
            summaryCard.appendChild(title);
            const summary = document.createElement("p");
            summary.className = "note-summary";
            summary.textContent = data.summary;
            summaryCard.appendChild(summary);
            smartSummaryEl.appendChild(summaryCard);
            smartSummaryEl.style.display = "grid";
          }
          notes.forEach(note => searchResultsEl.appendChild(renderNoteCard(note, "search", { showStatusButton: true })));
        } else {
          const data = await apiGet("/notes", {
            query: q || undefined,
            days: rangeVal || undefined
          });
          const notes = Array.isArray(data) ? data : [];
          searchStatusEl.textContent = notes.length ? "" : "No matches.";
          notes.forEach(note => searchResultsEl.appendChild(renderNoteCard(note, "search", { showStatusButton: true })));
        }
      } catch (err) {
        console.error(err);
        searchStatusEl.textContent = "Search failed.";
      } finally {
        searchBtn.disabled = false;
        searchBtn.textContent = prev;
      }
    }
    searchBtn.addEventListener("click", runSearch);
    searchQueryEl.addEventListener("keydown", (e) => { if (e.key === "Enter") runSearch(); });

    function buildTagShelf() {
      tagBubblesEl.innerHTML = "";
      TOPIC_BUTTONS.forEach(tag => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "chip topic-chip clickable-chip";
        btn.textContent = displayTag(tag);
        const kind = tag === "passive" ? "type" : "tag";
        btn.addEventListener("click", () => openContext(kind, tag, displayTag(tag)));
        tagBubblesEl.appendChild(btn);
      });
    }

    function showAppForUser() {
      setAuthedState(true);
      buildTagShelf();
      loadForYou();
      runSearch();
    }

    function clearSession() {
      sessionInfoPromise = Promise.resolve(null);
      localStorage.removeItem("reverie_email");
      setAuthedState(false);
      authEmail.value = "";
      authPassword.value = "";
      authStatus.textContent = "";
    }

    async function handleAuthSubmit(e) {
      e.preventDefault();
      const email = authEmail.value.trim();
      const password = authPassword.value;
      if (!email || !password) {
        authStatus.textContent = "Enter email and password.";
        return;
      }

      authSubmit.disabled = true;
      const prev = authSubmit.textContent;
      authSubmit.textContent = authMode === "login" ? "Logging in…" : "Signing up…";
      authStatus.textContent = authMode === "login" ? "Logging in…" : "Signing up…";

      try {
        const path = authMode === "login" ? "/login" : "/signup";
        await apiPost(path, { email, password });

        localStorage.setItem("reverie_email", email);
        const authed = await ensureSession(true);
        if (!authed) {
          authStatus.textContent = authMode === "signup"
            ? "Account created. Sign in after verification if required."
            : "Login failed to establish a session.";
          return;
        }

        authStatus.textContent = authMode === "login" ? "Logged in." : "Account created.";
        showAppForUser();
      } catch (err) {
        console.error(err);
        authStatus.textContent = err.message || "Authentication failed.";
      } finally {
        authSubmit.disabled = false;
        authSubmit.textContent = prev;
      }
    }

    loginTab.addEventListener("click", () => setAuthMode("login"));
    signupTab.addEventListener("click", () => setAuthMode("signup"));
    authForm.addEventListener("submit", handleAuthSubmit);
    logoutBtn.addEventListener("click", async () => {
      try {
        await apiPost("/logout", {});
      } catch (_) {}
      clearSession();
    });

    detailBackdrop.addEventListener("click", (e) => {
      if (e.target === detailBackdrop) closeDetail();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeDetail();
        closeEditModal();
        closeContext();
        closeManageEntitiesModal();
        setModalVisible(forYouBackdrop, false);
        setModalVisible(statusBackdrop, false);
      }
    });

    (async function boot() {
      if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
          navigator.serviceWorker.register("/service-worker.js").catch((err) => {
            console.warn("Service worker registration failed", err);
          });
        });
      }

      setAuthMode("login");
      if (await ensureSession(true)) {
        setAuthedState(true);
        buildTagShelf();
        loadForYou();
        runSearch();
      } else {
        setAuthedState(false);
      }
    })();
