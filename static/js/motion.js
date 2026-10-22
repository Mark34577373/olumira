/* Optional visual feedback only: no requests, routing, private storage or value tweening. */
(() => {
  'use strict';
  const root = document.documentElement;
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  const running = new Set();
  const allowed = element => !preference.matches && root.dataset.reducedMotion !== 'true' &&
    root.dataset.reducedEffects !== 'true' && root.dataset.motionPaused !== 'true' &&
    !element?.closest('.pref-reduced-motion');
  const play = (element, frames) => {
    if (!element || !allowed(element) || !element.animate) return;
    const animation = element.animate(frames, {duration:180,easing:'cubic-bezier(.2,.65,.3,1)'});
    running.add(animation);
    animation.finished.catch(() => {}).finally(() => running.delete(animation));
  };
  const feedback = element => play(element,[{opacity:.98},{opacity:1}]);
  const capture = list => new Map([...list.children].map(row => [row,row.getBoundingClientRect().top]));
  const reorder = (list, before) => {
    if (!allowed(list)) return;
    for (const row of list.children) {
      const old = before.get(row);
      const delta = old === undefined ? 0 : old - row.getBoundingClientRect().top;
      if (delta) play(row,[{transform:`translateY(${delta}px)`},{transform:'none'}]);
    }
  };
  window.OlumiraMotion = Object.freeze({allowed,feedback,capture,reorder});
  const cancel = () => {
    if (!allowed()) {
      for (const animation of running) animation.cancel();
      document.querySelectorAll('.motion-enter,.motion-settle').forEach(el => el.classList.remove('motion-enter','motion-settle'));
    }
  };
  preference.addEventListener('change',cancel);
  new MutationObserver(cancel).observe(root,{attributes:true,attributeFilter:['data-reduced-motion','data-reduced-effects','data-motion-paused']});
  const pause = document.querySelector('[data-motion-toggle]');
  if (pause) {
    try {root.dataset.motionPaused = String(localStorage.getItem('olumira.motionPaused.v1') === 'true');} catch (_) {}
    const label = () => {
      const paused = root.dataset.motionPaused === 'true';
      pause.textContent = paused ? 'Resume motion' : 'Pause motion';
      pause.setAttribute('aria-pressed',String(paused));
    };
    pause.hidden=false;label();
    pause.addEventListener('click',() => {
      root.dataset.motionPaused=String(root.dataset.motionPaused !== 'true');
      try {localStorage.setItem('olumira.motionPaused.v1',root.dataset.motionPaused);} catch (_) {}
      cancel();label();
    });
  } else {
    try {root.dataset.motionPaused = String(localStorage.getItem('olumira.motionPaused.v1') === 'true');} catch (_) {}
  }
  const visibility = () => {root.dataset.motionVisible=String(!document.hidden);};
  document.addEventListener('visibilitychange',visibility);visibility();
  const gardens = document.querySelectorAll('.garden-illustration');
  const enter = (el,index=0,settle=false) => {
    if (!allowed(el)) return;
    el.style.setProperty('--motion-order',Math.min(index,4));
    el.classList.add(settle?'motion-settle':'motion-enter');
  };
  document.querySelectorAll('.hero-copy > .public-eyebrow,.hero-copy > h1,.hero-description,.hero-copy > .public-actions,.hero-visual').forEach((el,i) => enter(el,i));
  document.querySelectorAll('.auth-card,.onboarding-actions').forEach(el => {if(!el.querySelector('[role=alert]')) enter(el);});
  // Broad care content never flies in; exact numbers, text and chart geometry stay unchanged.
  document.querySelectorAll('.stats-grid>.stat-card,.dashboard-grid>.dashboard-card').forEach((el,i) => enter(el,i));
  document.querySelectorAll('.premium-main>h1,.premium-main>.page-header,.premium-main>.content-heading,.premium-main>.routine-library-heading,.workspace-grid>.workspace-card,.task-card,.handoff-preview,.stat-value strong,.journal-chart,.unified-calendar,.notification-card,.ui-empty,.premium-empty,.observation-card,.board-use-heading').forEach(el => enter(el,0,true));
  const sections=document.querySelectorAll('.public-section,.public-showcase,.values-grid,.process-details>section,.closing-section,.public-steps>li');
  if ('IntersectionObserver' in window) {
    const observer=new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.target.matches('.garden-illustration')) {
        entry.target.dataset.gardenActive=String(entry.isIntersecting);
      } else if (entry.isIntersecting) {
        enter(entry.target);observer.unobserve(entry.target);
      }
    }),{threshold:.05});
    [...gardens,...sections].forEach(el => observer.observe(el));
  } else gardens.forEach(el => {el.dataset.gardenActive='true';});
  // No observer / no script: every section remains visible.
  document.addEventListener('submit',event => {
    const form=event.target;
    if (!(form instanceof HTMLFormElement) || form.method.toLowerCase()!=='get' || event.defaultPrevented) return;
    form.dataset.motionBusy='true';form.setAttribute('aria-busy','true');
    const status=document.querySelector('#operation-status');
    if (status) {status.hidden=false;status.textContent='Loading this view…';}
  });
  window.addEventListener('pageshow',() => {
    document.querySelectorAll('form[data-motion-busy]').forEach(form => {form.removeAttribute('aria-busy');delete form.dataset.motionBusy;});
    const status=document.querySelector('#operation-status');
    if (status && status.textContent==='Loading this view…') {status.hidden=true;status.textContent='';}
  });
})();
