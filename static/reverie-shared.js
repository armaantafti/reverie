window.ReverieShared = (() => {
  const SESSION_CACHE_KEY = "reverie:session:v1";
  const SESSION_TTL_MS = 600000;
  const API_CACHE_PREFIX = "reverie:api:";
  const nativeFetch = window.fetch.bind(window);

  const isStandalone = window.matchMedia?.("(display-mode: standalone)")?.matches
    || window.navigator.standalone === true;
  document.documentElement.classList.toggle("app-mode", Boolean(isStandalone));
  window.ReveriePageCleanup?.forEach?.((cleanup) => {
    try { cleanup(); } catch (_) {}
  });
  window.ReveriePageCleanup = [];

  let sessionInfoPromise = null;
  let sessionRetryPromise = null;

  function isNativeShell() {
    return Boolean(window.Capacitor?.isNativePlatform?.() || window.Capacitor?.getPlatform?.() === "android");
  }
  document.documentElement.classList.toggle("native-shell", isNativeShell());
  try {
    localStorage.removeItem("reverie:access-token:v1");
  } catch (_) {}

  function isSameOriginUrl(input) {
    try {
      const url = new URL(typeof input === "string" ? input : input?.url, window.location.origin);
      return url.origin === window.location.origin ? url : null;
    } catch (_) {
      return null;
    }
  }

  function shouldRetryAuth(input) {
    const url = isSameOriginUrl(input);
    if (!url) return false;
    return !["/session", "/login", "/signup", "/logout"].includes(url.pathname);
  }

  async function refreshSessionForRetry() {
    if (!sessionRetryPromise) {
      sessionRetryPromise = (async () => {
        try {
          const url = new URL("/session", window.location.origin);
          url.searchParams.set("_", String(Date.now()));
          const resp = await nativeFetch(url.toString(), {
            credentials: "same-origin",
            cache: "no-store",
          });
          if (!resp.ok) return false;
          const data = await resp.json().catch(() => null);
          if (data?.authenticated) {
            writeStoredJson(SESSION_CACHE_KEY, data);
            return true;
          }
        } catch (_) {}
        return false;
      })().finally(() => {
        sessionRetryPromise = null;
      });
    }
    return sessionRetryPromise;
  }

  window.fetch = async (input, init) => {
    const response = await nativeFetch(input, init);
    if (response.status !== 401 || !shouldRetryAuth(input)) {
      return response;
    }
    const refreshed = await refreshSessionForRetry();
    if (!refreshed) {
      return response;
    }
    return nativeFetch(input, init);
  };

  function readStoredJson(key, ttlMs) {
    try {
      const raw = sessionStorage.getItem(key);
      if (!raw) return null;
      const cached = JSON.parse(raw);
      if (ttlMs && Date.now() - Number(cached.time || 0) > ttlMs) return null;
      return cached.data;
    } catch (_) {
      return null;
    }
  }

  function writeStoredJson(key, data) {
    try {
      sessionStorage.setItem(key, JSON.stringify({ time: Date.now(), data }));
    } catch (_) {}
  }

  function stableApiKey(urlText) {
    const parsed = new URL(urlText, window.location.origin);
    parsed.searchParams.delete("_");
    return API_CACHE_PREFIX + parsed.toString();
  }

  function readApiCache(urlText, ttlMs = 30000) {
    return readStoredJson(stableApiKey(urlText), ttlMs);
  }

  function writeApiCache(urlText, data) {
    writeStoredJson(stableApiKey(urlText), data);
  }

  function clearApiCache(prefix = null) {
    try {
      Object.keys(sessionStorage)
        .filter((key) => {
          if (prefix) return key.startsWith(prefix);
          return key.startsWith(API_CACHE_PREFIX) || key.startsWith("reverie:list:");
        })
        .forEach((key) => sessionStorage.removeItem(key));
    } catch (_) {}
  }

  function cachedSession() {
    return readStoredJson(SESSION_CACHE_KEY, SESSION_TTL_MS);
  }

  async function getSessionInfo(force = false) {
    if (!force) {
      const cached = cachedSession();
      if (cached) return cached;
      if (sessionInfoPromise) return sessionInfoPromise;
    }

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
        const session = data?.authenticated ? data : null;
        if (session) writeStoredJson(SESSION_CACHE_KEY, session);
        else sessionStorage.removeItem(SESSION_CACHE_KEY);
        return session;
      } catch (_) {
        return cachedSession();
      }
    })();
    return sessionInfoPromise;
  }

  async function ensureSession(force = false) {
    return Boolean((await getSessionInfo(force))?.authenticated);
  }

  function markSessionAuthenticated(data = { authenticated: true }) {
    const session = { authenticated: true, ...data };
    writeStoredJson(SESSION_CACHE_KEY, session);
    sessionInfoPromise = Promise.resolve(session);
  }

  function invalidateSession() {
    try {
      sessionStorage.removeItem(SESSION_CACHE_KEY);
    } catch (_) {}
    sessionInfoPromise = Promise.resolve(null);
  }

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

  function hasCalendarTime(note) {
    if (!note?.due_time || !noteId(note)) return false;
    const parsed = new Date(note.due_time);
    return Number.isFinite(parsed.getTime());
  }

  function calendarActionLabel(note) {
    if (!hasCalendarTime(note)) return "";
    return isNativeShell() && window.Capacitor?.Plugins?.CalendarBridge
      ? "Add to phone calendar"
      : "Download calendar file";
  }

  function calendarDescription(note) {
    const parts = [
      String(note?.summary || "").trim(),
      "",
      "Created from Reverie.",
    ];
    if (note?.person_name) parts.push(`Person: ${note.person_name}`);
    if (Array.isArray(note?.tags) && note.tags.length) parts.push(`Tags: ${note.tags.join(", ")}`);
    if (Array.isArray(note?.entities) && note.entities.length) parts.push(`Entities: ${note.entities.join(", ")}`);
    return parts.filter((part, index) => index === 1 || part).join("\n").trim();
  }

  async function addNoteToCalendar(note) {
    const id = noteId(note);
    if (!hasCalendarTime(note)) {
      throw new Error("This memory does not have a due time.");
    }
    const start = new Date(note.due_time);
    const end = new Date(start.getTime() + 30 * 60 * 1000);
    const bridge = window.Capacitor?.Plugins?.CalendarBridge;
    if (isNativeShell() && bridge?.addEvent) {
      return bridge.addEvent({
        title: note?.title || "Reverie reminder",
        description: calendarDescription(note),
        startIso: start.toISOString(),
        endIso: end.toISOString(),
      });
    }
    window.location.href = `/calendar/notes/${encodeURIComponent(id)}.ics`;
    return { opened: true, fallback: "ics" };
  }

  function shouldOfferCalendarPrompt(note) {
    if (!hasCalendarTime(note)) return false;
    const type = String(note?.note_type || "").trim().toLowerCase();
    return type === "reminder" || type === "task" || type === "note";
  }

  async function promptAddNoteToCalendar(note, { statusEl } = {}) {
    if (!shouldOfferCalendarPrompt(note)) return false;
    const label = calendarActionLabel(note) || "Add to calendar";
    const title = String(note?.title || "this reminder").trim();
    const ok = window.confirm(`Add "${title}" to your calendar?`);
    if (!ok) return false;
    try {
      if (statusEl) statusEl.textContent = `${label}...`;
      await addNoteToCalendar(note);
      if (statusEl) {
        statusEl.textContent = isNativeShell() && window.Capacitor?.Plugins?.CalendarBridge
          ? "Calendar entry opened. Save it in your phone calendar."
          : "Calendar file opened. Import it to your calendar.";
      }
      return true;
    } catch (error) {
      if (statusEl) statusEl.textContent = error?.message || "Calendar action failed.";
      return false;
    }
  }

  function speechRecognitionConstructor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function nativeSpeechBridge() {
    return window.Capacitor?.Plugins?.SpeechBridge || null;
  }

  function supportsAudioRecording() {
    return Boolean(window.MediaRecorder && navigator.mediaDevices?.getUserMedia);
  }

  function preferredAudioMimeType() {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/wav",
    ];
    return candidates.find((type) => window.MediaRecorder?.isTypeSupported?.(type)) || "";
  }

  function supportsVoiceInput() {
    return Boolean(nativeSpeechBridge()?.start || speechRecognitionConstructor() || supportsAudioRecording());
  }

  function appendTranscript(textEl, transcript) {
    const nextText = String(transcript || "").trim();
    if (!textEl || !nextText) return;
    const current = String(textEl.value || "");
    const spacer = current.trim() ? (current.endsWith(" ") || current.endsWith("\n") ? "" : " ") : "";
    textEl.value = `${current}${spacer}${nextText}`;
    textEl.dispatchEvent(new Event("input", { bubbles: true }));
    textEl.focus();
    try {
      const end = textEl.value.length;
      textEl.setSelectionRange(end, end);
    } catch (_) {}
  }

  function installVoiceInput({ button, textEl, statusEl, language = "en-US" }) {
    if (!button || !textEl) return null;
    const nativeSpeech = nativeSpeechBridge();
    const Recognition = speechRecognitionConstructor();
    if (!nativeSpeech?.start && !Recognition) {
      button.disabled = true;
      button.classList.add("unsupported");
      button.title = "Voice input is not supported on this device yet.";
      if (button.dataset.unsupportedLabel) button.textContent = button.dataset.unsupportedLabel;
      return null;
    }

    let recognition = null;
    let recorder = null;
    let recorderStream = null;
    let listening = false;

    function setListening(next) {
      listening = Boolean(next);
      button.classList.toggle("listening", listening);
      button.setAttribute("aria-pressed", listening ? "true" : "false");
      if (button.dataset.idleLabel && button.dataset.listeningLabel) {
        button.textContent = listening ? button.dataset.listeningLabel : button.dataset.idleLabel;
      }
    }

    function stop() {
      if (recorder && recorder.state === "recording") {
        try {
          recorder.stop();
        } catch (_) {
          setListening(false);
        }
        return;
      }
      if (!recognition || !listening) return;
      try {
        recognition.stop();
      } catch (_) {
        setListening(false);
      }
    }

    function stopRecorderStream() {
      if (!recorderStream) return;
      recorderStream.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch (_) {}
      });
      recorderStream = null;
    }

    async function uploadRecordedAudio(blob) {
      const extension = blob.type.includes("mp4") ? "m4a" : blob.type.includes("wav") ? "wav" : "webm";
      const form = new FormData();
      form.append("audio", blob, `voice.${extension}`);
      const response = await fetch("/voice/transcribe", {
        method: "POST",
        body: form,
        credentials: "same-origin",
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data?.detail || data?.message || `HTTP ${response.status}`);
      }
      return data;
    }

    async function startRecordingFallback() {
      if (!supportsAudioRecording()) {
        if (statusEl) statusEl.textContent = "Voice input is not supported on this device yet.";
        return;
      }
      if (listening) {
        stop();
        return;
      }

      try {
        recorderStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = preferredAudioMimeType();
        recorder = mimeType ? new MediaRecorder(recorderStream, { mimeType }) : new MediaRecorder(recorderStream);
        const chunks = [];

        recorder.ondataavailable = (event) => {
          if (event.data?.size) chunks.push(event.data);
        };
        recorder.onerror = () => {
          stopRecorderStream();
          setListening(false);
          if (statusEl) statusEl.textContent = "Voice recording failed. Try again.";
        };
        recorder.onstop = async () => {
          const type = recorder?.mimeType || mimeType || "audio/webm";
          recorder = null;
          stopRecorderStream();
          setListening(false);
          const blob = new Blob(chunks, { type });
          if (!blob.size) {
            if (statusEl) statusEl.textContent = "No speech recorded. Try again.";
            return;
          }
          if (statusEl) statusEl.textContent = "Transcribing...";
          try {
            const data = await uploadRecordedAudio(blob);
            const transcript = String(data?.transcript || "").trim();
            if (transcript) {
              appendTranscript(textEl, transcript);
              if (statusEl) statusEl.textContent = data?.message || "Transcript added. Review before saving.";
            } else if (statusEl) {
              statusEl.textContent = data?.message || "No speech detected. Try again.";
            }
          } catch (error) {
            if (statusEl) statusEl.textContent = error?.message || "Voice transcription failed.";
          }
        };

        recorder.start();
        setListening(true);
        if (statusEl) statusEl.textContent = "Recording... Tap Voice again to stop.";
        window.setTimeout(() => {
          if (recorder?.state === "recording") {
            if (statusEl) statusEl.textContent = "Recording stopped at 60 seconds. Transcribing...";
            recorder.stop();
          }
        }, 60000);
      } catch (error) {
        stopRecorderStream();
        setListening(false);
        const message = String(error?.message || error || "");
        if (statusEl) {
          statusEl.textContent = /permission|denied|notallowed/i.test(message)
            ? "Microphone permission was denied. Enable it in browser or app settings and try again."
            : "Voice recording could not start on this device.";
        }
      }
    }

    async function startNative() {
      if (listening) return;
      setListening(true);
      if (statusEl) statusEl.textContent = "Listening...";
      try {
        const result = await nativeSpeech.start({ language });
        const transcript = String(result?.transcript || "").trim();
        if (transcript) {
          appendTranscript(textEl, transcript);
          if (statusEl) statusEl.textContent = "Transcript added. Review before saving.";
        } else if (statusEl) {
          statusEl.textContent = "No speech detected. Try again.";
        }
      } catch (error) {
        const message = String(error?.message || error || "");
        if (statusEl) {
          statusEl.textContent = /permission|denied/i.test(message)
            ? "Microphone permission was denied. Enable it in Android app settings and try again."
            : message || "Voice input could not start on this device.";
        }
      } finally {
        setListening(false);
      }
    }

    function startBrowser() {
      if (listening) {
        stop();
        return;
      }
      recognition = new Recognition();
      recognition.lang = language;
      recognition.interimResults = true;
      recognition.continuous = false;
      let finalTranscript = "";
      let browserShouldFallback = false;

      recognition.onstart = () => {
        setListening(true);
        if (statusEl) statusEl.textContent = "Listening...";
      };
      recognition.onresult = (event) => {
        let interim = "";
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index];
          const transcript = String(result?.[0]?.transcript || "").trim();
          if (!transcript) continue;
          if (result.isFinal) finalTranscript = `${finalTranscript} ${transcript}`.trim();
          else interim = `${interim} ${transcript}`.trim();
        }
        if (statusEl && interim) statusEl.textContent = `Listening: ${interim}`;
      };
      recognition.onerror = (event) => {
        const code = event?.error || "";
        browserShouldFallback = !["not-allowed", "no-speech", "aborted"].includes(code) && supportsAudioRecording();
        const message = code === "not-allowed"
          ? "Microphone permission was denied."
          : code === "no-speech"
            ? "No speech detected. Try again."
            : browserShouldFallback
              ? "Voice recognition unavailable. Switching to recording..."
              : "Voice input could not start on this device.";
        if (statusEl) statusEl.textContent = message;
      };
      recognition.onend = () => {
        if (finalTranscript) {
          appendTranscript(textEl, finalTranscript);
          if (statusEl) statusEl.textContent = "Transcript added. Review before saving.";
        } else if (browserShouldFallback) {
          setListening(false);
          startRecordingFallback();
          return;
        } else if (statusEl && listening && statusEl.textContent === "Listening...") {
          statusEl.textContent = "No speech detected. Try again.";
        }
        setListening(false);
      };

      try {
        recognition.start();
      } catch (_) {
        setListening(false);
        if (statusEl) statusEl.textContent = "Voice input is already starting. Try again.";
      }
    }

    function start() {
      if (nativeSpeech?.start) {
        startNative();
        return;
      }
      if (Recognition) {
        startBrowser();
        return;
      }
      startRecordingFallback();
    }

    button.type = "button";
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", start);
    window.addEventListener("beforeunload", stop);
    return { start, stop, isListening: () => listening };
  }

  function syncKeyboardInset() {
    const viewport = window.visualViewport;
    const inset = viewport
      ? Math.max(0, Math.round(window.innerHeight - viewport.height - viewport.offsetTop))
      : 0;
    document.documentElement.style.setProperty("--keyboard-inset", `${inset}px`);
  }

  function installKeyboardInsetSync() {
    if (window.__reverieKeyboardInsetInstalled) return;
    window.__reverieKeyboardInsetInstalled = true;
    syncKeyboardInset();
    window.addEventListener("resize", syncKeyboardInset, { passive: true });
    window.addEventListener("orientationchange", () => window.setTimeout(syncKeyboardInset, 120), { passive: true });
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", syncKeyboardInset, { passive: true });
      window.visualViewport.addEventListener("scroll", syncKeyboardInset, { passive: true });
    }
  }

  async function fetchNoteDetail(note) {
    const id = noteId(note);
    if (!id) return note || null;
    const cacheUrl = `/notes/${encodeURIComponent(id)}`;
    const cached = readApiCache(cacheUrl, 120000);
    if (cached) return { ...(note || {}), ...cached };
    const resp = await fetch(cacheUrl, {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!resp.ok) throw new Error(resp.status === 404 ? "Note not found." : `HTTP ${resp.status}`);
    const detail = await resp.json();
    writeApiCache(cacheUrl, detail);
    return { ...(note || {}), ...detail };
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
    if (!("requestIdleCallback" in window)) return;
    link.dataset.prefetched = "true";
    window.requestIdleCallback(() => {
      fetch(link.href, {
        method: "GET",
        credentials: "same-origin",
        cache: "force-cache",
        headers: { "X-Reverie-Prefetch": "1" },
      }).catch(() => undefined);
    }, { timeout: 1600 });
  }

  function warmApi(urlText) {
    const cached = readApiCache(urlText, 30000);
    if (cached) return;
    fetch(urlText, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
    })
      .then((resp) => resp.ok ? resp.json() : null)
      .then((data) => {
        if (data) writeApiCache(urlText, data);
      })
      .catch(() => undefined);
  }

  function warmTabData(pathname) {
    if (pathname === "/") {
      warmApi("/for-you?limit=3");
      return;
    }
    if (pathname === "/tasks") {
      warmApi("/notes?types=note,reminder&limit=60");
      return;
    }
  }

  const ONBOARDING_SEEN_KEY = "reverie_onboarding_seen";
  const onboardingSteps = [
    {
      key: "capture",
      route: "/",
      preview: "/static/onboarding/capture-plus.jpg",
      title: "Capture anything from anywhere",
      body: "Use the floating + button from any screen to add a memory, reminder, note, recommendation, screenshot, image, document, or voice input.",
      bullets: [
        "Type a note or reminder",
        "Speak using voice input",
        "Upload images, screenshots, or documents",
      ],
    },
    {
      key: "home",
      route: "/",
      preview: "/static/onboarding/home.png",
      title: "Your day at a glance",
      body: "Home gives you a quick summary of your most relevant reminders, tasks, and surfaced memories so you know what needs attention first.",
      bullets: [
        "See top reminders and tasks",
        "Review important surfaced memories",
        "Jump quickly into what needs attention",
      ],
    },
    {
      key: "search",
      route: "/search",
      preview: "/static/onboarding/search.png",
      title: "Find anything instantly",
      body: "Use Search to find saved memories, reminders, uploads, people, topics, and entities. Smart Search helps you ask natural questions.",
      bullets: [
        "Search across saved content",
        "Use Smart Search for natural questions",
        "Filter or narrow results when needed",
      ],
    },
    {
      key: "tasks",
      route: "/tasks",
      preview: "/static/onboarding/tasks.png",
      title: "Turn memories into action",
      body: "Use Tasks to review reminders and follow-ups detected from your memories. Track what is pending, completed, or skipped.",
      bullets: [
        "Review pending reminders",
        "Mark tasks completed or skipped",
        "Add updates when something changes",
      ],
    },
    {
      key: "account",
      route: "/account",
      preview: "/static/onboarding/account.png",
      title: "Manage your workspace",
      body: "Use Account to manage your Reverie workspace, privacy options, uploads, names, entities, topics, and account settings.",
      bullets: [
        "Manage names, entities, and topics",
        "Review privacy and uploads",
        "Log out or request account deletion",
      ],
    },
  ];

  let onboardingIndex = 0;
  let onboardingActive = false;
  let onboardingStartTimer = null;
  let onboardingStyleInstalled = false;

  function onboardingSeen() {
    try {
      return localStorage.getItem(ONBOARDING_SEEN_KEY) === "1";
    } catch (_) {
      return true;
    }
  }

  function setOnboardingSeen() {
    try {
      localStorage.setItem(ONBOARDING_SEEN_KEY, "1");
    } catch (_) {}
    getSessionInfo(false).then((session) => {
      const key = accountOnboardingKey(session);
      if (key) localStorage.setItem(key, "1");
    }).catch(() => undefined);
  }

  function accountOnboardingKey(session) {
    const user = session?.user || {};
    const identity = String(user.id || user.email || "").trim().toLowerCase();
    return identity ? `${ONBOARDING_SEEN_KEY}:${identity}` : "";
  }

  function accountOnboardingSeen(session) {
    const key = accountOnboardingKey(session);
    if (!key) return onboardingSeen();
    try {
      return localStorage.getItem(key) === "1";
    } catch (_) {
      return true;
    }
  }

  async function accountHasAnyMemory() {
    try {
      const response = await fetch("/notes?limit=1", {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) return true;
      const notes = await response.json().catch(() => []);
      return Array.isArray(notes) && notes.length > 0;
    } catch (_) {
      return true;
    }
  }

  function installOnboardingStyles() {
    if (onboardingStyleInstalled || document.getElementById("reverieOnboardingStyles")) return;
    onboardingStyleInstalled = true;
    const style = document.createElement("style");
    style.id = "reverieOnboardingStyles";
    style.textContent = `
      .reverie-onboarding-backdrop{position:fixed;inset:0;z-index:520;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:14px;background:rgba(2,6,14,.44);backdrop-filter:blur(2px);-webkit-backdrop-filter:blur(2px);overflow:hidden}
      .reverie-onboarding-preview-frame{width:min(300px,calc(100vw - 48px));height:min(47dvh,390px);border-radius:24px;overflow:hidden;border:1px solid rgba(219,234,254,.24);box-shadow:0 22px 62px rgba(0,0,0,.42);background:#050914}
      .reverie-onboarding-preview-frame.capture-preview{width:min(340px,calc(100vw - 34px));height:min(38dvh,310px)}
      .reverie-onboarding-preview-frame img{width:100%;height:100%;object-fit:cover;object-position:top center;display:block}
      .reverie-onboarding-card{position:relative;z-index:2;width:min(430px,calc(100vw - 34px));border-radius:24px;padding:17px;background:linear-gradient(180deg,rgba(17,25,42,.72),rgba(8,13,24,.68));border:1px solid rgba(219,234,254,.28);box-shadow:0 24px 70px rgba(0,0,0,.48);color:var(--text,#eef4ff);backdrop-filter:blur(18px) saturate(150%);-webkit-backdrop-filter:blur(18px) saturate(150%)}
      .reverie-onboarding-kicker{margin:0 0 8px;color:var(--muted,#aab6c8);font-size:.66rem;font-weight:800;letter-spacing:.15em;text-transform:uppercase}
      .reverie-onboarding-title{margin:0;color:var(--text,#eef4ff);font-size:1.08rem;line-height:1.15;letter-spacing:0}
      .reverie-onboarding-body{margin:9px 0 0;color:var(--muted,#aab6c8);font-size:.82rem;line-height:1.45}
      .reverie-onboarding-list{display:grid;gap:6px;margin:11px 0 0;padding:0;list-style:none;color:var(--text,#eef4ff);font-size:.8rem}
      .reverie-onboarding-list li{position:relative;padding-left:22px;line-height:1.45}
      .reverie-onboarding-list li:before{content:"";position:absolute;left:0;top:.58em;width:7px;height:7px;border-radius:50%;background:linear-gradient(135deg,var(--accent,#88d8ff),#c2b5ff);box-shadow:0 0 12px rgba(122,215,255,.42)}
      .reverie-onboarding-progress{display:flex;gap:6px;margin:13px 0 0}
      .reverie-onboarding-dot{width:7px;height:7px;border-radius:50%;background:rgba(148,163,184,.34)}
      .reverie-onboarding-dot.active{width:18px;background:linear-gradient(135deg,var(--accent,#88d8ff),#c2b5ff)}
      .reverie-onboarding-actions{display:flex;gap:8px;align-items:center;justify-content:space-between;margin-top:14px;flex-wrap:wrap}
      .reverie-onboarding-actions-left,.reverie-onboarding-actions-right{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
      .reverie-onboarding-button{min-height:36px;border-radius:999px;border:1px solid rgba(148,163,184,.18);padding:0 13px;background:rgba(148,163,184,.08);color:var(--text,#eef4ff);font:inherit;font-size:.78rem;font-weight:800;cursor:pointer}
      .reverie-onboarding-button.primary{color:#06111d;border-color:transparent;background:linear-gradient(135deg,var(--accent,#88d8ff),#c2b5ff)}
      .reverie-onboarding-button.link{border-color:transparent;background:transparent;color:var(--muted,#aab6c8);padding-inline:4px}
      .reverie-onboarding-button:disabled{opacity:.45;cursor:not-allowed}
      @media (max-width: 520px){.reverie-onboarding-backdrop{gap:9px;padding:9px 8px calc(12px + env(safe-area-inset-bottom,0px));justify-content:center}.reverie-onboarding-preview-frame{width:min(270px,calc(100vw - 54px));height:min(42dvh,340px);border-radius:22px}.reverie-onboarding-preview-frame.capture-preview{width:min(340px,calc(100vw - 18px));height:min(34dvh,270px)}.reverie-onboarding-card{border-radius:21px;padding:14px;width:min(420px,calc(100vw - 24px))}.reverie-onboarding-title{font-size:.98rem}.reverie-onboarding-body{font-size:.76rem}.reverie-onboarding-list{font-size:.74rem}.reverie-onboarding-actions{align-items:stretch}.reverie-onboarding-actions-left,.reverie-onboarding-actions-right{width:100%;justify-content:space-between}.reverie-onboarding-button{flex:1;min-height:34px}}
    `;
    document.head.appendChild(style);
  }

  function clearOnboardingHighlights() {
    document.querySelectorAll(".reverie-onboarding-highlight").forEach((node) => {
      node.classList.remove("reverie-onboarding-highlight");
    });
  }

  function closeBackgroundSheets() {
    window.ReverieCapture?.close?.();
    window.ReverieAccount?.close?.();
    document.body.classList.remove("quick-capture-open", "capture-sheet-open");
    clearOnboardingHighlights();
  }

  function renderOnboardingModal() {
    installOnboardingStyles();
    document.getElementById("reverieOnboardingOverlay")?.remove();
    const step = onboardingSteps[onboardingIndex];
    const overlay = document.createElement("div");
    overlay.className = "reverie-onboarding-backdrop";
    overlay.id = "reverieOnboardingOverlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "reverieOnboardingTitle");

    const dots = onboardingSteps.map((_, index) => (
      `<span class="reverie-onboarding-dot${index === onboardingIndex ? " active" : ""}" aria-hidden="true"></span>`
    )).join("");
    const bullets = step.bullets.map((bullet) => `<li>${bullet}</li>`).join("");
    const isFirst = onboardingIndex === 0;
    const isLast = onboardingIndex === onboardingSteps.length - 1;

    overlay.innerHTML = `
      <div class="reverie-onboarding-preview-frame${step.key === "capture" ? " capture-preview" : ""}" aria-hidden="true">
        <img src="${step.preview}" alt="" loading="eager" />
      </div>
      <section class="reverie-onboarding-card">
        <p class="reverie-onboarding-kicker">Step ${onboardingIndex + 1} of ${onboardingSteps.length}</p>
        <h2 class="reverie-onboarding-title" id="reverieOnboardingTitle">${step.title}</h2>
        <p class="reverie-onboarding-body">${step.body}</p>
        <ul class="reverie-onboarding-list">${bullets}</ul>
        <div class="reverie-onboarding-progress" aria-label="Tutorial progress">${dots}</div>
        <div class="reverie-onboarding-actions">
          <div class="reverie-onboarding-actions-left">
            <button class="reverie-onboarding-button" data-onboarding-action="back" type="button" ${isFirst ? "disabled" : ""}>Back</button>
            <button class="reverie-onboarding-button link" data-onboarding-action="skip" type="button">Skip tutorial</button>
          </div>
          <div class="reverie-onboarding-actions-right">
            <button class="reverie-onboarding-button primary" data-onboarding-action="${isLast ? "finish" : "next"}" type="button">${isLast ? "Finish" : "Next"}</button>
          </div>
        </div>
      </section>
    `;
    document.body.appendChild(overlay);
  }

  async function navigateToOnboardingRoute(route) {
    const target = new URL(route, window.location.origin);
    if (window.location.pathname === target.pathname && window.location.search === target.search) return;
    if (typeof navigateAppShell === "function" && isAppShellRoute(target)) {
      await navigateAppShell(target);
      return;
    }
    window.location.href = target.href;
  }

  function applyOnboardingBackground(step) {
    closeBackgroundSheets();
  }

  async function showOnboardingStep(index) {
    onboardingIndex = Math.max(0, Math.min(index, onboardingSteps.length - 1));
    const step = onboardingSteps[onboardingIndex];
    applyOnboardingBackground(step);
    renderOnboardingModal();
  }

  function finishOnboarding() {
    setOnboardingSeen();
    onboardingActive = false;
    document.getElementById("reverieOnboardingOverlay")?.remove();
    closeBackgroundSheets();
  }

  async function startOnboarding({ force = false } = {}) {
    if (onboardingActive) return;
    if (!force && onboardingSeen()) return;
    onboardingActive = true;
    await showOnboardingStep(0);
  }

  function maybeStartOnboarding({ delay = 500, checkEmptyAccount = false } = {}) {
    if (onboardingActive) return;
    if (!checkEmptyAccount && onboardingSeen()) return;
    window.clearTimeout(onboardingStartTimer);
    onboardingStartTimer = window.setTimeout(async () => {
      if (onboardingActive) return;
      const session = await getSessionInfo(false);
      if (!session?.authenticated) return;
      if (checkEmptyAccount) {
        const hasAnyMemory = await accountHasAnyMemory();
        if (!hasAnyMemory) {
          if (accountOnboardingSeen(session)) return;
          startOnboarding({ force: true });
          return;
        }
      }
      if (!onboardingSeen()) startOnboarding();
    }, delay);
  }

  function installOnboardingControls() {
    if (window.__reverieOnboardingControlsInstalled) return;
    window.__reverieOnboardingControlsInstalled = true;
    installOnboardingStyles();
    document.addEventListener("click", async (event) => {
      const action = event.target?.closest?.("[data-onboarding-action]")?.dataset?.onboardingAction;
      if (!action) return;
      event.preventDefault();
      if (action === "skip" || action === "finish") {
        finishOnboarding();
        return;
      }
      if (action === "back") {
        await showOnboardingStep(onboardingIndex - 1);
        return;
      }
      if (action === "next") {
        await showOnboardingStep(onboardingIndex + 1);
      }
    });
    document.addEventListener("keydown", (event) => {
      if (!onboardingActive || event.key !== "Escape") return;
      finishOnboarding();
    });
    document.addEventListener("click", (event) => {
      const replay = event.target?.closest?.("[data-replay-onboarding]");
      if (!replay) return;
      event.preventDefault();
      startOnboarding({ force: true });
    });
  }

  function installReplayTutorialAction() {
    document.querySelectorAll(".account-actions").forEach((actions) => {
      if (actions.querySelector("[data-replay-onboarding]")) return;
      const button = document.createElement("button");
      button.className = "account-action";
      button.id = actions.classList.contains("account-page-actions") ? "replayOnboardingBtn" : "";
      button.type = "button";
      button.dataset.replayOnboarding = "1";
      button.innerHTML = "<span>Replay Tutorial</span><small>See how Home, Capture, Search, Tasks, and Account work</small>";
      const privacyLink = actions.querySelector('a[href="/privacy"]');
      actions.insertBefore(button, privacyLink || actions.firstChild);
    });
  }

  function installFastNavigation() {
    document.querySelectorAll("a[href]").forEach((link) => {
      if (!isFastNavLink(link)) return;
      link.addEventListener("pointerenter", () => prefetchPage(link), { passive: true });
      link.addEventListener("touchstart", () => {
        prefetchPage(link);
        try {
          warmTabData(new URL(link.href, window.location.href).pathname);
        } catch (_) {}
      }, { passive: true });
      link.addEventListener("click", () => {
        try {
          warmTabData(new URL(link.href, window.location.href).pathname);
        } catch (_) {}
        document.documentElement.classList.add("route-loading");
      });
    });
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(() => {
        ["/tasks"]
          .filter((path) => path !== window.location.pathname)
          .forEach((path) => fetch(path, { credentials: "same-origin", cache: "force-cache" }).catch(() => undefined));
      }, { timeout: 2500 });
    }
  }

  function isAppShellRoute(url) {
    if (url.origin !== window.location.origin) return false;
    return ["/search", "/tasks", "/account"].includes(url.pathname);
  }

  function runDynamicScript(sourceScript) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      [...sourceScript.attributes].forEach((attr) => {
        if (attr.name !== "defer") script.setAttribute(attr.name, attr.value);
      });
      if (sourceScript.src) {
        script.onload = () => resolve();
        script.onerror = () => reject(new Error(`Could not load ${sourceScript.src}`));
        script.src = sourceScript.src;
      } else {
        script.textContent = sourceScript.textContent || "";
        resolve();
      }
      document.body.appendChild(script);
    });
  }

  function syncHeadAssets(nextDoc) {
    document.title = nextDoc.title || document.title;
    document.querySelectorAll('link[rel="stylesheet"]').forEach((link) => link.remove());
    nextDoc.querySelectorAll('link[rel="stylesheet"]').forEach((link) => {
      document.head.appendChild(link.cloneNode(true));
    });
  }

  async function navigateAppShell(url, replace = false) {
    document.documentElement.classList.add("route-loading");
    window.ReveriePageCleanup?.forEach?.((cleanup) => {
      try { cleanup(); } catch (_) {}
    });
    window.ReveriePageCleanup = [];
    try {
      const resp = await fetch(url.href, {
        credentials: "same-origin",
        cache: "no-store",
        headers: { "X-Reverie-App-Shell": "1" },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const html = await resp.text();
      const nextDoc = new DOMParser().parseFromString(html, "text/html");
      syncHeadAssets(nextDoc);
      const scripts = [...nextDoc.body.querySelectorAll("script")];
      scripts.forEach((script) => script.remove());
      document.body.className = nextDoc.body.className;
      document.body.innerHTML = nextDoc.body.innerHTML;
      if (replace) window.history.replaceState({ reverieShell: true }, "", url.href);
      else window.history.pushState({ reverieShell: true }, "", url.href);
      for (const script of scripts) {
        await runDynamicScript(script);
      }
      await window.ReveriePageInit?.({ fromAppShell: true, path: url.pathname });
      installReplayTutorialAction();
      window.scrollTo({ top: 0, behavior: "instant" });
    } catch (err) {
      console.warn("App shell navigation fell back to full navigation", err);
      window.location.href = url.href;
    } finally {
      document.documentElement.classList.remove("route-loading");
    }
  }

  function installAppShellNavigation() {
    if (window.__reverieAppShellInstalled) return;
    window.__reverieAppShellInstalled = true;
    document.addEventListener("click", (event) => {
      const link = event.target?.closest?.("a[href]");
      if (!link || link.target || link.hasAttribute("download")) return;
      const href = link.getAttribute("href") || "";
      if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) return;
      const url = new URL(link.href, window.location.href);
      if (!isAppShellRoute(url)) return;
      event.preventDefault();
      navigateAppShell(url);
    });
    window.addEventListener("popstate", () => {
      const url = new URL(window.location.href);
      if (isAppShellRoute(url)) navigateAppShell(url, true);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      installKeyboardInsetSync();
      installFastNavigation();
      installAppShellNavigation();
      installOnboardingControls();
      installReplayTutorialAction();
    }, { once: true });
  } else {
    installKeyboardInsetSync();
    installFastNavigation();
    installAppShellNavigation();
    installOnboardingControls();
    installReplayTutorialAction();
  }

  window.ReverieOnboarding = {
    start: startOnboarding,
    maybeStart: maybeStartOnboarding,
  };

  return {
    readApiCache,
    writeApiCache,
    clearApiCache,
    getSessionInfo,
    ensureSession,
    markSessionAuthenticated,
    isNativeShell,
    invalidateSession,
    navigateAppShell,
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
    hasCalendarTime,
    calendarActionLabel,
    addNoteToCalendar,
    shouldOfferCalendarPrompt,
    promptAddNoteToCalendar,
    supportsVoiceInput,
    installVoiceInput,
    fetchNoteDetail,
    setModalVisible,
    installFastNavigation,
    startOnboarding,
    maybeStartOnboarding,
  };
})();
