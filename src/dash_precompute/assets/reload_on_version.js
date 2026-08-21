(() => {
  const versionMeta = document.querySelector('meta[name="place-twins-app-version"]');
  const loadedVersion = versionMeta?.content;
  let isCheckingVersion = false;
  let lastCheckAt = 0;

  const reloadIfServerChanged = async () => {
    const now = Date.now();
    if (!loadedVersion || isCheckingVersion || now - lastCheckAt < 1000) return;

    isCheckingVersion = true;
    lastCheckAt = now;

    try {
      const response = await window.fetch("/_place_twins/version", {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return;

      const serverVersion = (await response.json()).version;
      if (!serverVersion || serverVersion === loadedVersion) return;

      const reloadKey = `place-twins-reloaded:${serverVersion}`;
      if (window.sessionStorage.getItem(reloadKey)) return;
      window.sessionStorage.setItem(reloadKey, "true");
      window.location.reload();
    } catch (_error) {
      // A temporary server restart should not interrupt the current report.
    } finally {
      isCheckingVersion = false;
    }
  };

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") reloadIfServerChanged();
  });
  window.addEventListener("focus", reloadIfServerChanged);
})();
