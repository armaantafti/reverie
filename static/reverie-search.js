(function () {
  const queryEl = document.getElementById("searchPageQuery");
  const rangeEl = document.getElementById("searchPageRange");
  const smartEl = document.getElementById("searchPageSmart");
  const statusEl = document.getElementById("searchPageStatus");
  const summaryEl = document.getElementById("searchPageSummary");
  const mapEl = document.getElementById("memoryMapGroups");

  let contextNotesOverride = null;
  let searchHasRun = false;

  function normaliseText(value) {
    return String(value || "").toLowerCase();
  }

  function matchesQuery(note, terms) {
    if (!terms.length) return true;
    const haystack = [
      note?.title,
      note?.summary,
      note?.raw_text,
      note?.extracted_text,
      note?.person_name,
      note?.note_type,
      note?.memory_type,
      ...(Array.isArray(note?.tags) ? note.tags : []),
      ...(Array.isArray(note?.entities) ? note.entities : []),
    ].map(normaliseText).join(" ");
    return terms.every((term) => haystack.includes(term));
  }

  function matchesDays(note, days) {
    if (!days || days < 1) return true;
    const stamp = note?.created_at || note?.due_time;
    if (!stamp) return true;
    const date = new Date(stamp);
    if (Number.isNaN(date.getTime())) return true;
    return date >= new Date(Date.now() - days * 24 * 60 * 60 * 1000);
  }

  function clearSmartSummary() {
    summaryEl.style.display = "none";
    summaryEl.innerHTML = "";
  }

  function appendTextList(parent, className, items) {
    const clean = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!clean.length) return;
    const list = document.createElement("ul");
    list.className = className;
    clean.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = String(item);
      list.appendChild(li);
    });
    parent.appendChild(list);
  }

  function renderSmartSummary(summary, fallbackText = "") {
    clearSmartSummary();
    if (!summary && !fallbackText) return;

    if (!summary || typeof summary !== "object") {
      summaryEl.textContent = fallbackText || String(summary || "");
      summaryEl.style.display = "block";
      return;
    }

    const header = document.createElement("div");
    header.className = "smart-answer-header";
    const titleWrap = document.createElement("div");
    const kicker = document.createElement("span");
    kicker.className = "smart-answer-kicker";
    kicker.textContent = "Smart answer";
    const title = document.createElement("h3");
    title.textContent = summary.answer_title || "What I found";
    titleWrap.append(kicker, title);
    const confidence = document.createElement("span");
    confidence.className = `smart-confidence ${summary.confidence || "medium"}`;
    confidence.textContent = summary.confidence || "medium";
    header.append(titleWrap, confidence);
    summaryEl.appendChild(header);

    const executive = document.createElement("p");
    executive.className = "smart-executive";
    executive.textContent = summary.executive_summary || fallbackText || "";
    summaryEl.appendChild(executive);

    appendTextList(summaryEl, "smart-key-points", summary.key_points);

    const actions = Array.isArray(summary.action_items) ? summary.action_items.filter((item) => item?.title) : [];
    if (actions.length) {
      const actionWrap = document.createElement("div");
      actionWrap.className = "smart-action-items";
      const actionTitle = document.createElement("strong");
      actionTitle.textContent = "Open actions";
      actionWrap.appendChild(actionTitle);
      actions.forEach((item) => {
        const row = document.createElement("div");
        row.className = "smart-action-row";
        const name = document.createElement("span");
        name.textContent = item.title;
        const meta = document.createElement("small");
        meta.textContent = [item.due_time, item.status].filter(Boolean).join(" · ");
        row.append(name, meta);
        actionWrap.appendChild(row);
      });
      summaryEl.appendChild(actionWrap);
    }

    const chips = [...(summary.people_or_entities || []), ...(summary.suggested_next_searches || [])].filter(Boolean);
    if (chips.length) {
      const chipRow = document.createElement("div");
      chipRow.className = "smart-suggestion-row";
      chips.slice(0, 8).forEach((chip) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "smart-suggestion-chip";
        button.textContent = String(chip);
        button.addEventListener("click", () => {
          queryEl.value = String(chip);
          searchHasRun = true;
          document.getElementById("searchPageBtn")?.click();
        });
        chipRow.appendChild(button);
      });
      summaryEl.appendChild(chipRow);
    }

    if (!actions.length && summary.empty_state_suggestion) {
      const hint = document.createElement("p");
      hint.className = "smart-empty-hint";
      hint.textContent = summary.empty_state_suggestion;
      summaryEl.appendChild(hint);
    }

    summaryEl.style.display = "block";
  }

  async function fetchJson(url, options) {
    const resp = await fetch(url, {
      credentials: "same-origin",
      cache: "no-store",
      ...(options || {}),
    });
    const data = await resp.json().catch(() => null);
    if (!resp.ok) {
      if (resp.status === 401) throw new Error("Please sign in again on Home.");
      throw new Error(data?.detail || data?.message || ("HTTP " + resp.status));
    }
    return data;
  }

  async function fetchContextNotes(kind, value) {
    const url = new URL("/context", window.location.origin);
    url.searchParams.set("kind", kind);
    url.searchParams.set("value", value);
    const data = await fetchJson(url.toString());
    return {
      notes: Array.isArray(data?.notes) ? data.notes : [],
      summary: "",
      fallback: true,
    };
  }

  async function fetchSearchNotes() {
    if (contextNotesOverride) {
      const notes = contextNotesOverride.notes || [];
      const title = contextNotesOverride.title || "Memory group";
      statusEl.textContent = `${notes.length} ${notes.length === 1 ? "memory" : "memories"} in ${title}.`;
      contextNotesOverride = null;
      return notes;
    }

    const query = (queryEl?.value || "").trim();
    const days = Number.parseInt(rangeEl?.value || "", 10);
    const cleanDays = Number.isFinite(days) && days > 0 ? days : null;

    clearSmartSummary();

    if (!searchHasRun) {
      statusEl.textContent = "Search or tap a tag, entity, or person to begin.";
      return [];
    }

    if (!query) {
      statusEl.textContent = "Enter a search term or tap a memory-map chip.";
      return [];
    }

    statusEl.textContent = "Searching memories...";

    if (query && smartEl?.checked) {
      statusEl.textContent = "Running smart search...";
      const data = await fetchJson("/smart-search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, days: cleanDays }),
      });
      const notes = Array.isArray(data?.notes) ? data.notes : [];
      renderSmartSummary(data?.summary_json, data?.summary);
      statusEl.textContent = `${notes.length} ${notes.length === 1 ? "match" : "matches"} found.`;
      return notes;
    }

    const url = new URL("/notes", window.location.origin);
    url.searchParams.set("query", query);
    if (cleanDays) url.searchParams.set("days", String(cleanDays));
    url.searchParams.set("_", String(Date.now()));
    const notes = await fetchJson(url.toString());
    const filtered = Array.isArray(notes) ? notes : [];

    statusEl.textContent = `${filtered.length} ${filtered.length === 1 ? "match" : "matches"} found.`;
    return filtered;
  }

  initReverieListPage({
    primary: {
      listId: "searchResultsList",
      emptyId: "searchResultsEmpty",
      emptyText: "No matching memories",
    },
    secondary: {
      listId: "searchSecondaryList",
      emptyId: "searchSecondaryEmpty",
      emptyText: "No secondary results",
    },
    signedOutText: "Sign in on Home to search your memories",
    reloadButtonId: "searchPageBtn",
    searchInputId: "searchPageQuery",
    fetchNotes: fetchSearchNotes,
    errorText(err) {
      const message = err?.message || "Search could not load.";
      statusEl.textContent = message;
      return message;
    },
    detail: {
      backdropId: "searchModal",
      closeId: "searchCloseBtn",
      titleId: "searchDetailTitle",
      subId: "searchDetailSub",
      summaryId: "searchDetailSummary",
      rawId: "searchDetailRaw",
      tagsId: "searchDetailTags",
      entitiesId: "searchDetailEntities",
      personId: "searchDetailPerson",
      timeId: "searchDetailTime",
      imageId: "searchDetailImage",
      assetActionsId: "searchDetailAssetActions",
      editBtnId: "searchEditBtn",
      deleteBtnId: "searchDeleteBtn",
    },
    context: {
      backdropId: "searchContextBackdrop",
      closeId: "searchContextClose",
      titleId: "searchContextTitle",
      subId: "searchContextSub",
      listId: "searchContextList",
    },
    status: {
      backdropId: "searchStatusBackdrop",
      closeId: "searchStatusClose",
      cancelId: "searchStatusCancel",
      saveId: "searchStatusSave",
      titleId: "searchStatusTitle",
      subId: "searchStatusSub",
      selectId: "searchStatusSelect",
      noteId: "searchStatusNote",
    },
    edit: {
      backdropId: "searchEditBackdrop",
      closeId: "searchEditClose",
      cancelId: "searchEditCancel",
      saveId: "searchEditSave",
      titleId: "searchEditTitle",
      subId: "searchEditSub",
      typeId: "searchEditType",
      dueTimeId: "searchEditDueTime",
      personId: "searchEditPerson",
      tagsId: "searchEditTags",
      entitiesId: "searchEditEntities",
    },
    splitNotes(notes) {
      const sorted = notes.slice().sort((a, b) =>
        Number(b?.search_score || 0) - Number(a?.search_score || 0)
        || new Date(b?.created_at || b?.due_time || 0) - new Date(a?.created_at || a?.due_time || 0)
      );
      const primary = sorted.filter((note) => ["best", "action"].includes(note?.search_section)).slice(0, 12);
      const primaryIds = new Set(primary.map((note) => note?.id));
      const secondary = sorted.filter((note) => !primaryIds.has(note?.id));
      const relatedPanel = document.querySelector(".search-related-panel");
      if (relatedPanel) relatedPanel.style.display = secondary.length ? "" : "none";
      return { primary: primary.length ? primary : sorted, secondary };
    },
  });

  document.getElementById("searchPageBtn")?.addEventListener("click", () => {
    searchHasRun = true;
  }, true);

  queryEl?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") searchHasRun = true;
  }, true);

  function chipLabel(item) {
    return window.ReverieShared.toDisplayCase(item?.value || "");
  }

  function renderMapGroup(title, kind, entries) {
    const section = document.createElement("section");
    section.className = "memory-map-group";
    const head = document.createElement("div");
    head.className = "memory-map-head";
    head.innerHTML = `<strong>${title}</strong><span>${entries.length}</span>`;
    section.appendChild(head);

    const row = document.createElement("div");
    row.className = "memory-map-chips";
    entries.slice(0, 14).forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "memory-map-chip";
      button.innerHTML = `<span>${chipLabel(item)}</span><small>${item.count || 0}</small>`;
      button.addEventListener("click", () => loadContextSummary(kind, item.value));
      row.appendChild(button);
    });
    section.appendChild(row);
    return section;
  }

  async function loadMemoryMap() {
    if (!mapEl) return;
    try {
      const data = await fetchJson("/entities/manage");
      const items = Array.isArray(data?.items) ? data.items : [];
      const byKind = (kind) => items
        .filter((item) => item.kind === kind && Number(item.count || 0) > 0)
        .sort((a, b) => Number(b.count || 0) - Number(a.count || 0));
      mapEl.innerHTML = "";
      const groups = [
        ["Top Tags", "tag", byKind("tag")],
        ["Top Entities", "entity", byKind("entity")],
        ["People", "person", byKind("person")],
      ].filter(([, , entries]) => entries.length);
      if (!groups.length) {
        mapEl.innerHTML = '<div class="context-empty">No tags or entities yet.</div>';
        return;
      }
      groups.forEach(([title, kind, entries]) => mapEl.appendChild(renderMapGroup(title, kind, entries)));
    } catch (err) {
      mapEl.innerHTML = `<div class="context-empty">${err?.message || "Could not load memory map."}</div>`;
    }
  }

  async function loadContextSummary(kind, value) {
    const title = `${window.ReverieShared.toDisplayCase(kind)}: ${window.ReverieShared.toDisplayCase(value)}`;
    statusEl.textContent = `Loading ${title}...`;
    clearSmartSummary();
    try {
      let data;
      try {
        data = await fetchJson("/context-summary", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind, value }),
        });
      } catch (err) {
        if (String(err?.message || "").toLowerCase().includes("not found") || String(err?.message || "").includes("404")) {
          data = await fetchContextNotes(kind, value);
          data.summary = "Loaded matching memories. Smart summary needs the local server restarted so the new /context-summary route is active.";
        } else {
          throw err;
        }
      }
      const notes = Array.isArray(data?.notes) ? data.notes : [];
      renderSmartSummary(data?.summary_json, data?.summary);
      queryEl.value = title;
      contextNotesOverride = { title, notes };
      searchHasRun = true;
      document.getElementById("searchPageBtn")?.click();
      document.getElementById("searchResultsList")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      statusEl.textContent = err?.message || "Could not load this memory group.";
    }
  }

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js").catch((err) => {
        console.warn("Service worker registration failed", err);
      });
    });
  }
  loadMemoryMap();
})();
