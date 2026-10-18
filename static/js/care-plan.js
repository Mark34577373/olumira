(() => {
  const form = document.querySelector('[data-plan-wizard]'); if (!form) return;
  const steps = [...form.querySelectorAll('[data-wizard-step]')]; let index = 0, dirty = false;
  const back = form.querySelector('[data-wizard-back]'), next = form.querySelector('[data-wizard-next]');
  const review = form.querySelector('[data-plan-review]');
  function show(focus = false) {
    steps.forEach((step,i) => { step.hidden = i !== index; });
    back.hidden = index === 0; next.hidden = index === steps.length-1;
    form.querySelector('[data-wizard-status]').textContent = `Step ${index+1} of ${steps.length}`;
    review.replaceChildren();
    for (const name of ['title','description','priorities','goal_title']) {
      const control = form.elements.namedItem(name); if (control?.value) { const p=document.createElement('p'); p.textContent=control.value; review.append(p); }
    }
    for (const box of form.querySelectorAll('input[type=checkbox]:checked')) { const p=document.createElement('p'); p.textContent=box.parentElement.textContent.trim(); review.append(p); }
    if (focus) { steps[index].tabIndex = -1; steps[index].focus(); }
  }
  back.addEventListener('click',()=>{ index--;show(true); }); next.addEventListener('click',()=>{ index++;show(true); });
  // Hidden wizard inputs still validate; reveal the relevant section first.
  form.addEventListener('invalid',event=>{ const step=event.target.closest('[data-wizard-step]'); if(step){index=steps.indexOf(step);show();} },true);
  form.addEventListener('input',()=>{dirty=true;}); form.addEventListener('submit',()=>{dirty=false;});
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}}); show();
})();
