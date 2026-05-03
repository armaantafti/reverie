(function () {
  const panel = document.getElementById("quickCapturePanel");
  const backdrop = document.getElementById("quickCaptureBackdrop");
  const closeBtn = document.getElementById("quickCaptureClose");
  const saveBtn = document.getElementById("quickCaptureSave");
  const uploadBtn = document.getElementById("quickCaptureUpload");
  const uploadInput = document.getElementById("quickCaptureUploadInput");
  const textEl = document.getElementById("quickCaptureText");
  const statusEl = document.getElementById("quickCaptureStatus");

  if (!panel || !backdrop) return;

  async function ensureSession() {
    const url = new URL("/session", window.location.origin);
    url.searchParams.set("_", String(Date.now()));
    const resp = await fetch(url.toString(), { credentials: "same-origin", cache: "no-store" });
    if (!resp.ok) return false;
    const data = await resp.json().catch(() => null);
    return Boolean(data?.authenticated);
  }

  function openPanel() {
    document.body.classList.add("quick-capture-open");
    statusEl.textContent = "";
  }

  function closePanel() {
    document.body.classList.remove("quick-capture-open");
  }

  async function saveText() {
    if (!(await ensureSession())) {
      statusEl.textContent = "Please sign in on Home first.";
      return;
    }
    const text = String(textEl.value || "").trim();
    if (!text) {
      statusEl.textContent = "Type something first.";
      return;
    }
    const prev = saveBtn.textContent;
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
    statusEl.textContent = "Saving...";
    try {
      const resp = await fetch("/notes/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
        credentials: "same-origin",
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      textEl.value = "";
      statusEl.textContent = "Saved.";
      window.dispatchEvent(new CustomEvent("reverie:notes-changed"));
      window.setTimeout(closePanel, 450);
    } catch (err) {
      statusEl.textContent = err?.message || "Save failed.";
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = prev;
    }
  }

  async function uploadFiles(files) {
    if (!(await ensureSession())) {
      statusEl.textContent = "Please sign in on Home first.";
      return;
    }
    if (!files.length) return;
    if (files.length > 10) {
      statusEl.textContent = "Upload at most 10 files at once.";
      return;
    }
    const prev = uploadBtn.textContent;
    uploadBtn.disabled = true;
    uploadBtn.textContent = "Uploading...";
    statusEl.textContent = "Uploading files...";
    try {
      const form = new FormData();
      files.forEach((file) => form.append("files", file, file.name));
      const resp = await fetch("/notes/uploads", {
        method: "POST",
        body: form,
        credentials: "same-origin",
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data?.detail || `HTTP ${resp.status}`);
      statusEl.textContent = data?.message || "Files uploaded.";
      window.dispatchEvent(new CustomEvent("reverie:notes-changed"));
      window.setTimeout(closePanel, 600);
    } catch (err) {
      statusEl.textContent = err?.message || "Upload failed.";
    } finally {
      uploadBtn.disabled = false;
      uploadBtn.textContent = prev;
      uploadInput.value = "";
    }
  }

  document.querySelectorAll('a[href="#quickCapturePanel"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      openPanel();
    });
  });
  closeBtn?.addEventListener("click", closePanel);
  backdrop?.addEventListener("click", closePanel);
  saveBtn?.addEventListener("click", saveText);
  uploadBtn?.addEventListener("click", () => uploadInput?.click());
  uploadInput?.addEventListener("change", async () => {
    const files = Array.from(uploadInput.files || []);
    await uploadFiles(files);
  });
})();
