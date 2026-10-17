(() => {
  const player = document.querySelector('[data-run-player]');
  const update = document.querySelector('#shared-run-update');
  if (!player || !update) return;
  // Never replace a focused step or silently replay a caregiver's older action.
  // Poll only visible tabs; all writes remain native CSRF-protected forms.
  const poll = async () => {
    if (document.hidden) return;
    try {
      const response = await fetch(player.dataset.stateUrl, {headers: {'Accept': 'application/json'}, cache: 'no-store'});
      if (response.status === 401 || response.redirected || response.status === 403 || response.status === 404) {
        update.hidden = false;
        update.textContent = 'Your access or sign-in changed. Reload this page to continue.';
        clearInterval(timer);
        return;
      }
      if (!response.ok) return;
      const state = await response.json();
      if (String(state.version) !== player.dataset.version) update.hidden = false;
    } catch (_) { /* Offline progress is never presented as saved. Native forms show failures. */ }
  };
  const timer = setInterval(poll, 10000);
  document.addEventListener('visibilitychange', poll);
})();
