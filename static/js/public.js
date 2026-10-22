/* Progressive enhancement: navigation remains fully available without scripts. */
(() => {
  const toggle = document.querySelector('.public-menu-toggle');
  const nav = document.querySelector('#public-navigation');
  if (!toggle || !nav) return;
  const mobile = window.matchMedia('(max-width: 900px)');
  const setOpen = open => {
    nav.hidden = mobile.matches && !open;
    toggle.setAttribute('aria-expanded', String(open));
  };
  const sync = () => {
    // A resize must not leave keyboard focus inside newly hidden navigation.
    toggle.hidden = !mobile.matches;
    if (mobile.matches && nav.contains(document.activeElement)) toggle.focus();
    setOpen(!mobile.matches);
  };
  toggle.addEventListener('click', () => setOpen(nav.hidden));
  nav.addEventListener('keydown', event => {
    if (event.key === 'Escape' && mobile.matches) {
      setOpen(false); toggle.focus();
    }
  });
  toggle.addEventListener('keydown', event => {
    if (event.key === 'Escape') setOpen(false);
  });
  mobile.addEventListener('change', sync);
  sync();
})();
