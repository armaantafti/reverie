(function () {
  const SETTINGS_KEY = "reverie:notifications:enabled";
  const IDS_KEY = "reverie:notifications:scheduled-ids";
  const LOOKAHEAD_DAYS = 30;

  function plugin() {
    return window.Capacitor?.Plugins?.LocalNotifications || null;
  }

  function isNative() {
    return Boolean(window.ReverieShared?.isNativeShell?.() || window.Capacitor?.isNativePlatform?.());
  }

  function getEnabled() {
    try {
      return localStorage.getItem(SETTINGS_KEY) === "1";
    } catch (_) {
      return false;
    }
  }

  function setEnabled(value) {
    try {
      localStorage.setItem(SETTINGS_KEY, value ? "1" : "0");
    } catch (_) {}
  }

  function notificationId(note) {
    const raw = String(note?.id || note?.note_id || note?.title || note?.due_time || "");
    let hash = 0;
    for (let i = 0; i < raw.length; i += 1) {
      hash = ((hash << 5) - hash + raw.charCodeAt(i)) | 0;
    }
    return Math.abs(hash) + 10000;
  }

  function readScheduledIds() {
    try {
      const parsed = JSON.parse(localStorage.getItem(IDS_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.filter(Number.isFinite) : [];
    } catch (_) {
      return [];
    }
  }

  function writeScheduledIds(ids) {
    try {
      localStorage.setItem(IDS_KEY, JSON.stringify(ids));
    } catch (_) {}
  }

  async function requestPermissions() {
    const localNotifications = plugin();
    if (!localNotifications) return { display: "unavailable" };
    const current = await localNotifications.checkPermissions();
    if (current?.display === "granted") return current;
    return localNotifications.requestPermissions();
  }

  async function cancelScheduled() {
    const localNotifications = plugin();
    const ids = readScheduledIds();
    if (!localNotifications || !ids.length) return;
    await localNotifications.cancel({
      notifications: ids.map((id) => ({ id })),
    }).catch(() => {});
    writeScheduledIds([]);
  }

  function notificationBody(note) {
    const summary = String(note?.summary || note?.title || "A Reverie reminder is due.").trim();
    return summary.length > 140 ? `${summary.slice(0, 137)}...` : summary;
  }

  function dueNotifications(notes) {
    const now = Date.now();
    const max = now + LOOKAHEAD_DAYS * 24 * 60 * 60 * 1000;
    return notes
      .filter((note) => {
        const type = String(note?.note_type || "").toLowerCase();
        const status = String(note?.status || "pending").toLowerCase();
        if (!["note", "reminder"].includes(type) || status !== "pending" || !note?.due_time) return false;
        const due = new Date(note.due_time).getTime();
        return Number.isFinite(due) && due > now && due <= max;
      })
      .slice(0, 50)
      .map((note) => ({
        id: notificationId(note),
        title: note?.note_type === "reminder" ? "Reminder due" : "Task due",
        body: notificationBody(note),
        schedule: { at: new Date(note.due_time) },
        extra: {
          noteId: String(note?.id || note?.note_id || ""),
          path: "/tasks",
        },
      }));
  }

  async function sync() {
    if (!isNative() || !getEnabled()) return { scheduled: 0, reason: "disabled" };
    const localNotifications = plugin();
    if (!localNotifications) return { scheduled: 0, reason: "unavailable" };

    const permissions = await requestPermissions();
    if (permissions?.display !== "granted") return { scheduled: 0, reason: "permission" };

    const sessionOk = await window.ReverieShared?.ensureSession?.(true);
    if (!sessionOk) return { scheduled: 0, reason: "signed-out" };

    const response = await fetch("/notes?types=note,reminder&limit=100", {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const notes = await response.json();
    const notifications = dueNotifications(Array.isArray(notes) ? notes : []);

    await cancelScheduled();
    if (notifications.length) {
      await localNotifications.schedule({ notifications });
      writeScheduledIds(notifications.map((item) => item.id));
    }
    return { scheduled: notifications.length };
  }

  async function enableFromButton(button, statusEl) {
    if (!isNative()) {
      if (statusEl) statusEl.textContent = "Notifications are available in the Android app.";
      return;
    }
    button.disabled = true;
    const oldText = button.querySelector("span")?.textContent || button.textContent;
    const label = button.querySelector("span");
    if (label) label.textContent = "Setting up...";
    try {
      setEnabled(true);
      const result = await sync();
      if (statusEl) {
        statusEl.textContent = result.reason === "permission"
          ? "Notification permission was not granted."
          : `Reminder notifications enabled. ${result.scheduled || 0} scheduled.`;
      }
    } catch (err) {
      console.error(err);
      if (statusEl) statusEl.textContent = err?.message || "Could not enable notifications.";
    } finally {
      if (label) label.textContent = oldText;
      button.disabled = false;
    }
  }

  function installAccountControls() {
    document.querySelectorAll("[data-reverie-enable-notifications]").forEach((button) => {
      if (button.dataset.reverieNotificationsReady === "1") return;
      button.dataset.reverieNotificationsReady = "1";
      const statusEl = button.closest(".account-actions")?.querySelector("[data-reverie-notification-status]");
      button.addEventListener("click", () => enableFromButton(button, statusEl));
    });
  }

  async function init() {
    installAccountControls();
    if (!isNative()) return;
    plugin()?.addListener?.("localNotificationActionPerformed", () => {
      window.location.href = "/tasks";
    });
    if (getEnabled()) {
      window.setTimeout(() => sync().catch((err) => console.warn("Notification sync failed", err)), 1200);
    }
  }

  window.ReverieNotifications = {
    sync,
    requestPermissions,
    cancelScheduled,
    getEnabled,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
  window.addEventListener("reverie:notes-changed", () => {
    if (getEnabled()) sync().catch(() => {});
  });
})();
