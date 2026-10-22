/* Optional in-place checklist. Native CSRF-protected POST remains the fallback. */
(() => {
  const root=document.querySelector('[data-checklist]');
  if (!root || !window.fetch || !window.AbortController) return;
  const forms=[...root.querySelectorAll('.task-form')];
  const status=root.querySelector('#checklist-status');
  if (!status || !forms.length) return;
  let pending=false,activeController=null;
  const switches=[...document.querySelectorAll('.workspace-context button')].filter(button=>!button.disabled);
  window.addEventListener('pagehide',()=>activeController?.abort());
  const announce=(text,error=false) => {
    status.setAttribute('role',error?'alert':'status');
    status.setAttribute('aria-live',error?'assertive':'polite');
    status.classList.toggle('checklist-error',error);
    status.textContent=text;
    root.querySelector('[data-checklist-reload]').hidden=!error;
  };
  const valid=data => data && data.workspace_id===root.dataset.workspace &&
    data.profile_id===root.dataset.profile && data.checklist_date===root.dataset.date &&
    Number.isInteger(data.total) && data.total===forms.length &&
    Number.isInteger(data.completed) && data.completed>=0 && data.completed<=data.total &&
    Number.isInteger(data.progress) && data.progress>=0 && data.progress<=100 &&
    Array.isArray(data.items) && data.items.length===data.total &&
    new Set(data.items.map(item=>item.id)).size===data.total &&
    data.items.every(item=>Number.isInteger(item.id) && typeof item.completed==='boolean' && forms.some(form=>Number(form.dataset.routineId)===item.id)) &&
    data.items.filter(item=>item.completed).length===data.completed;
  root.addEventListener('submit',async event => {
    const form=event.target;
    if (!forms.includes(form)) return;
    event.preventDefault();
    const button=form.querySelector('button');
    if (pending || button.disabled) return;
    pending=true;
    const available=forms.map(item=>item.querySelector('button')).filter(item=>!item.disabled);
    available.forEach(item=>item.setAttribute('aria-disabled','true'));
    switches.forEach(item=>{item.disabled=true;});
    form.setAttribute('aria-busy','true');
    announce('Saving this checklist change…');
    const controller=new AbortController();activeController=controller;
    const timeout=setTimeout(()=>controller.abort(),15000);
    try {
      const response=await fetch(form.action,{method:'POST',body:new FormData(form),headers:{Accept:'application/json'},redirect:'error',cache:'no-store',signal:controller.signal});
      if (!response.ok || !response.headers.get('Content-Type')?.includes('application/json')) throw new Error();
      const data=await response.json();
      if (!valid(data)) throw new Error();
      // Every visible state comes from the confirmed, authorized server response.
      for (const item of data.items) {
        const row=forms.find(candidate=>Number(candidate.dataset.routineId)===item.id);
        const control=row.querySelector('button');
        control.classList.toggle('completed',item.completed);
        control.setAttribute('aria-pressed',String(item.completed));
        control.setAttribute('aria-label',`Mark ${control.dataset.routineName} ${item.completed?'incomplete':'complete'}`);
        control.querySelector('.task-check').textContent=item.completed?'✓':'';
        row.elements.completed.value=String(!item.completed);
      }
      document.querySelectorAll('progress[data-checklist-progress]').forEach(progress=>{progress.value=data.progress;progress.textContent=`${data.progress}%`;});
      const value=document.querySelector('[data-checklist-stat]');
      if (value) {value.replaceChildren(document.createTextNode(String(data.progress)));const unit=document.createElement('small');unit.textContent='%';value.append(unit);}
      const ring=document.querySelector('.stats-grid .ring-value');
      if (ring) {ring.setAttribute('stroke-dasharray',`${data.progress} 100`);ring.style.visibility=data.progress?'visible':'hidden';}
      root.querySelector('.completion-badge').textContent=`${data.completed} of ${data.total}`;
      announce(`Saved. ${data.completed} of ${data.total} checklist activities complete.`);
      window.OlumiraMotion?.feedback(button);
    } catch (_) {
      // Never retry a toggle or claim success after a timeout / changed access.
      announce('This change is not confirmed. Try again, or reload to check your access and latest checklist.',true);
    } finally {
      clearTimeout(timeout);pending=false;activeController=null;
      switches.forEach(item=>{item.disabled=false;});
      available.forEach(item=>item.removeAttribute('aria-disabled'));
      form.removeAttribute('aria-busy');
    }
  },true);
})();
