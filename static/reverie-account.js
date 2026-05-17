(function () {
  const shared = window.ReverieShared || {};
  const { setModalVisible, invalidateSession } = shared;

  const accountBackdrop = document.getElementById("mobileAccountBackdrop");
  const accountClose = document.getElementById("mobileAccountClose");
  const logoutBtn = document.getElementById("mobileLogoutBtn");
  const replayBtn = document.getElementById("replayOnboardingBtn");

  const profileCard = document.getElementById("profileCard");
  const profileAvatar = document.getElementById("profileAvatar");
  const profileDisplayName = document.getElementById("profileDisplayName");
  const profileEmail = document.getElementById("profileEmail");
  const profileProvider = document.getElementById("profileProvider");
  const profileTimezone = document.getElementById("profileTimezone");
  const profileLanguage = document.getElementById("profileLanguage");
  const profileForm = document.getElementById("profileForm");
  const profileNameInput = document.getElementById("profileNameInput");
  const profilePhoneInput = document.getElementById("profilePhoneInput");
  const profileTimezoneInput = document.getElementById("profileTimezoneInput");
  const profileLanguageInput = document.getElementById("profileLanguageInput");
  const profileSaveBtn = document.getElementById("profileSaveBtn");
  const profileStatus = document.getElementById("profileStatus");

  function openAccountSheet() {
    if (!accountBackdrop || typeof setModalVisible !== "function") return false;
    setModalVisible(accountBackdrop, true);
    return true;
  }

  function closeAccountSheet() {
    if (accountBackdrop && typeof setModalVisible === "function") {
      setModalVisible(accountBackdrop, false);
    }
  }

  window.ReverieAccount = {
    open: openAccountSheet,
    close: closeAccountSheet,
  };

  async function performLogout() {
    try {
      await fetch("/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
        credentials: "same-origin",
      });
    } catch (_) {}
    try {
      await window.ReverieNotifications?.setNotificationEnabled?.(false);
      localStorage.removeItem("reverie_email");
      localStorage.removeItem("reverie_seen_authenticated");
    } catch (_) {}
    invalidateSession?.();
    closeAccountSheet();
    window.location.href = "/";
  }

  function providerLabel(value) {
    const clean = String(value || "email").trim().toLowerCase();
    return clean === "google" ? "Google sign-in" : "Email and password";
  }

  function avatarInitial(profile) {
    const source = profile?.display_name || profile?.email || "R";
    return String(source).trim().charAt(0).toUpperCase() || "R";
  }

  function setProfileLoading(message) {
    if (profileStatus) profileStatus.textContent = message || "";
  }

  function renderProfile(profile, storageReady = true) {
    if (!profileCard || !profile) return;
    const displayName = String(profile.display_name || "").trim();
    const email = String(profile.email || "").trim();
    const timezone = String(profile.timezone || "Asia/Kolkata").trim();
    const language = String(profile.preferred_language || "English").trim();
    const provider = String(profile.auth_provider || "email").trim();

    if (profile.avatar_url && profileAvatar) {
      profileAvatar.innerHTML = "";
      const img = document.createElement("img");
      img.src = profile.avatar_url;
      img.alt = displayName || email || "Profile";
      profileAvatar.appendChild(img);
    } else if (profileAvatar) {
      profileAvatar.textContent = avatarInitial(profile);
    }

    if (profileDisplayName) profileDisplayName.textContent = displayName || "Reverie user";
    if (profileEmail) profileEmail.textContent = email || "No email available";
    if (profileProvider) profileProvider.textContent = providerLabel(provider);
    if (profileTimezone) profileTimezone.textContent = timezone || "Asia/Kolkata";
    if (profileLanguage) profileLanguage.textContent = language || "English";

    if (profileNameInput) profileNameInput.value = displayName;
    if (profilePhoneInput) profilePhoneInput.value = profile.phone_number || "";
    if (profileTimezoneInput) profileTimezoneInput.value = timezone || "Asia/Kolkata";
    if (profileLanguageInput) profileLanguageInput.value = language || "English";
    setProfileLoading(storageReady ? "Profile loaded." : "Profile table not installed yet. You can view account details, but edits need supabase_profiles.sql.");
  }

  async function loadProfile() {
    if (!profileCard) return;
    setProfileLoading("Loading profile...");
    try {
      const resp = await fetch("/profile", { credentials: "same-origin", cache: "no-store" });
      if (resp.status === 401) {
        renderProfile({ display_name: "", email: "", timezone: "Asia/Kolkata", preferred_language: "English", auth_provider: "email" }, false);
        setProfileLoading("Sign in on Home to manage your profile.");
        return;
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      renderProfile(data.profile, data.storage_ready !== false);
    } catch (err) {
      console.error(err);
      setProfileLoading("Could not load profile details.");
    }
  }

  async function saveProfile(event) {
    event.preventDefault();
    if (!profileForm) return;
    const payload = {
      display_name: profileNameInput?.value || "",
      phone_number: profilePhoneInput?.value || "",
      timezone: profileTimezoneInput?.value || "Asia/Kolkata",
      preferred_language: profileLanguageInput?.value || "English",
    };
    if (profileSaveBtn) profileSaveBtn.disabled = true;
    setProfileLoading("Saving profile...");
    try {
      const resp = await fetch("/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      renderProfile(data.profile, true);
      setProfileLoading("Profile saved.");
    } catch (err) {
      console.error(err);
      setProfileLoading(err.message || "Could not save profile.");
    } finally {
      if (profileSaveBtn) profileSaveBtn.disabled = false;
    }
  }

  document.addEventListener("click", (event) => {
    const accountLink = event.target.closest('a[href="#account"], a[href="/#account"]');
    if (accountLink && openAccountSheet()) event.preventDefault();
  });

  accountClose?.addEventListener("click", closeAccountSheet);
  accountBackdrop?.addEventListener("click", (event) => {
    if (event.target === accountBackdrop) closeAccountSheet();
  });
  logoutBtn?.addEventListener("click", performLogout);
  profileForm?.addEventListener("submit", saveProfile);
  replayBtn?.addEventListener("click", () => {
    window.ReverieOnboarding?.start?.({ force: true });
  });

  if (window.location.hash === "#account") {
    window.setTimeout(openAccountSheet, 240);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadProfile, { once: true });
  } else {
    loadProfile();
  }
})();
