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

    summaryEl.style.display = "none";
    summaryEl.textContent = "";

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
      if (data?.summary) {
        summaryEl.textContent = data.summary;
        summaryEl.style.display = "block";
      }
      statusEl.textContent = `${notes.length} ${notes.length === 1 ? "match" : "matches"} found.`;
      return notes;
    }

    const url = new URL("/notes", window.location.origin);
    url.searchParams.set("_", String(Date.now()));
    const notes = await fetchJson(url.toString());
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    const filtered = (Array.isArray(notes) ? notes : [])
      .filter((note) => matchesQuery(note, terms))
      .filter((note) => matchesDays(note, cleanDays));

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
        new Date(b?.created_at || b?.due_time || 0) - new Date(a?.created_at || a?.due_time || 0)
      );
      return { primary: sorted, secondary: [] };
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
    summaryEl.style.display = "none";
    summaryEl.textContent = "";
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
      if (data?.summary) {
        summaryEl.textContent = data.summary;
        summaryEl.style.display = "block";
      }
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
