(function () {
  const { toDisplayCase } = window.ReverieShared;

  const tabs = Array.from(document.querySelectorAll(".entity-tabs button"));
  const filters = Array.from(document.querySelectorAll(".entity-filters button"));
  const searchEl = document.getElementById("entitySearch");
  const sortEl = document.getElementById("entitySort");
  const listEl = document.getElementById("entityList");
  const emptyEl = document.getElementById("entityEmpty");
  const statusEl = document.getElementById("entityStatus");
  const countEl = document.getElementById("entityListCount");
  const titleEl = document.getElementById("entityListTitle");
  const targetEl = document.getElementById("entityTarget");
  const selectionEl = document.getElementById("entitySelectionSummary");
  const impactEl = document.getElementById("entityImpact");
  const mergeBtn = document.getElementById("entityMerge");
  const renameBtn = document.getElementById("entityRename");
  const createBtn = document.getElementById("entityCreate");
  const deleteBtn = document.getElementById("entityDelete");

  let items = [];
  let kind = "person";
  let filter = "all";
  const selected = new Set();

  function itemKey(item) {
    return `${item.kind}:${String(item.value || "").toLowerCase()}`;
  }

  function selectedItems() {
    return items.filter((item) => item.kind === kind && selected.has(itemKey(item)));
  }

  function likelyDuplicate(item, all) {
    const value = String(item.value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    if (!value) return false;
    if ((item.aliases || []).length) return true;
    return all.some((other) => {
      if (other === item || other.kind !== item.kind) return false;
      const next = String(other.value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
      return next && (next.includes(value) || value.includes(next));
    });
  }

  async function api(path, body) {
    const resp = await fetch(path, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      credentials: "same-origin",
      cache: "no-store",
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await resp.json().catch(() => null);
    if (!resp.ok) throw new Error(data?.detail || `HTTP ${resp.status}`);
    return data;
  }

  function visibleItems() {
    const q = String(searchEl.value || "").trim().toLowerCase();
    let list = items.filter((item) => item.kind === kind);
    if (q) {
      list = list.filter((item) => [
        item.value,
        ...(Array.isArray(item.aliases) ? item.aliases : []),
      ].join(" ").toLowerCase().includes(q));
    }
    if (filter === "duplicates") list = list.filter((item) => likelyDuplicate(item, items));
    if (filter === "aliases") list = list.filter((item) => (item.aliases || []).length);
    if (filter === "single") list = list.filter((item) => Number(item.count || 0) <= 1);

    const sort = sortEl.value;
    list.sort((a, b) => {
      if (sort === "az") return String(a.value || "").localeCompare(String(b.value || ""));
      if (sort === "aliases") return (b.aliases || []).length - (a.aliases || []).length || String(a.value || "").localeCompare(String(b.value || ""));
      if (sort === "single") return Number(a.count || 0) - Number(b.count || 0) || String(a.value || "").localeCompare(String(b.value || ""));
      return Number(b.count || 0) - Number(a.count || 0) || String(a.value || "").localeCompare(String(b.value || ""));
    });
    return list;
  }

  function renderSelection() {
    const picks = selectedItems();
    if (!picks.length) {
      selectionEl.textContent = "Select one or more items.";
      impactEl.textContent = "No changes selected.";
      return;
    }
    const total = picks.reduce((sum, item) => sum + Number(item.count || 0), 0);
    selectionEl.textContent = `${picks.length} selected: ${picks.map((item) => toDisplayCase(item.value)).join(", ")}`;
    impactEl.textContent = `This will affect about ${total} ${total === 1 ? "memory" : "memories"}.`;
    if (!targetEl.value.trim()) targetEl.value = picks[0].value || "";
  }

  function render() {
    const list = visibleItems();
    titleEl.textContent = kind === "person" ? "People" : kind === "entity" ? "Entities" : "Tags";
    countEl.textContent = `${list.length} ${list.length === 1 ? "item" : "items"}`;
    listEl.innerHTML = "";
    emptyEl.classList.toggle("hidden", Boolean(list.length));

    list.forEach((item) => {
      const key = itemKey(item);
      const row = document.createElement("label");
      row.className = `entity-row ${selected.has(key) ? "selected" : ""}`.trim();

      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = selected.has(key);
      box.addEventListener("change", () => {
        if (box.checked) selected.add(key);
        else selected.delete(key);
        render();
      });
      row.appendChild(box);

      const copy = document.createElement("div");
      copy.className = "entity-row-copy";
      const title = document.createElement("strong");
      title.textContent = toDisplayCase(item.value);
      copy.appendChild(title);

      const meta = document.createElement("span");
      const aliases = Array.isArray(item.aliases) ? item.aliases : [];
      meta.textContent = `${toDisplayCase(item.kind)} • ${item.count || 0} memories${aliases.length ? ` • aliases: ${aliases.map(toDisplayCase).join(", ")}` : ""}`;
      copy.appendChild(meta);
      row.appendChild(copy);

      if (likelyDuplicate(item, items)) {
        const chip = document.createElement("span");
        chip.className = "entity-flag";
        chip.textContent = "Review";
        row.appendChild(chip);
      }
      listEl.appendChild(row);
    });
    renderSelection();
  }

  async function loadItems() {
    statusEl.textContent = "Loading...";
    try {
      const data = await api("/entities/manage");
      items = Array.isArray(data?.items) ? data.items : [];
      statusEl.textContent = `${items.length} saved entries loaded.`;
      render();
    } catch (err) {
      statusEl.textContent = err?.message || "Could not load entities.";
    }
  }

  async function runAction(action) {
    const picks = selectedItems();
    const target = targetEl.value.trim();
    try {
      if (action === "merge") {
        if (!picks.length || !target) throw new Error("Select items and enter the final value.");
        await api("/entities/manage/merge", { kind, values: picks.map((item) => item.value), target_value: target });
      } else if (action === "rename") {
        if (picks.length !== 1 || !target) throw new Error("Select one item and enter the new value.");
        await api("/entities/manage/rename", { kind, value: picks[0].value, new_value: target });
      } else if (action === "create") {
        if (!target) throw new Error("Enter a value to create.");
        await api("/entities/manage/create", { kind, value: target });
      } else if (action === "delete") {
        if (!picks.length) throw new Error("Select items to delete.");
        if (!window.confirm(`Delete ${picks.length} ${kind} ${picks.length === 1 ? "entry" : "entries"} from memories?`)) return;
        await api("/entities/manage/delete", { kind, values: picks.map((item) => item.value) });
      }
      selected.clear();
      targetEl.value = "";
      await loadItems();
      statusEl.textContent = "Updated.";
    } catch (err) {
      statusEl.textContent = err?.message || "Action failed.";
    }
  }

  tabs.forEach((tab) => tab.addEventListener("click", () => {
    kind = tab.dataset.kind;
    selected.clear();
    targetEl.value = "";
    tabs.forEach((item) => item.classList.toggle("active", item === tab));
    render();
  }));
  filters.forEach((button) => button.addEventListener("click", () => {
    filter = button.dataset.filter;
    filters.forEach((item) => item.classList.toggle("active", item === button));
    render();
  }));
  searchEl.addEventListener("input", render);
  sortEl.addEventListener("change", render);
  mergeBtn.addEventListener("click", () => runAction("merge"));
  renameBtn.addEventListener("click", () => runAction("rename"));
  createBtn.addEventListener("click", () => runAction("create"));
  deleteBtn.addEventListener("click", () => runAction("delete"));

  loadItems();
})();
