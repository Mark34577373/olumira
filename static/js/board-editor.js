/* Native forms own persistence. JavaScript only edits the draft until Save. */
(() => {
 const form=document.querySelector('#board-editor'); if(!form)return;
 const list=form.querySelector('#board-card-list'),add=form.querySelector('#add-board-card');
 const status=form.querySelector('#board-save-state'),announce=form.querySelector('#board-announcement');
 let dirty=form.dataset.dirty==='true',submitting=false,dragged=null;
 const rows=()=>[...list.querySelectorAll('[data-card-editor]')];
 const image=name=>document.querySelector(`#board-symbol-library [data-symbol="${name}"] svg`);
 const changed=()=>{dirty=true;status.textContent='Unsaved changes';};
 const update=()=>{
  const cards=rows();
  cards.forEach((row,i)=>{
   row.querySelector('[data-card-number]').textContent=`Card ${i+1}`;
   for(const field of ['label','spoken_text','symbol','color']){
    const input=row.querySelector(`[name=card_${field}]`);input.id=`card-${i+1}-${field}`;
    row.querySelector(`[data-for=${field}]`).htmlFor=input.id;
   }
   row.querySelectorAll('[data-card-action]').forEach(button=>{
    const action=button.dataset.cardAction;button.value=`${action}:${i}`;
    button.disabled=(action==='up'&&i===0)||(action==='down'&&i===cards.length-1)||(action==='copy'&&cards.length>=48);
    button.setAttribute('aria-label',`${{up:'Move up',down:'Move down',copy:'Duplicate',remove:'Remove'}[action]} card ${i+1}`);
   });
   const visual=row.querySelector('[data-card-visual]');visual.className=`board-edit-visual tone-${row.querySelector('[name=card_color]').value}`;
   visual.querySelector('[data-card-label]').textContent=row.querySelector('[name=card_label]').value.trim()||'Your card';
   const svg=image(row.querySelector('[name=card_symbol]').value);if(svg)visual.querySelector('svg').replaceWith(svg.cloneNode(true));
   row.querySelector('.board-drag-handle').hidden=false;
   row.querySelector('.board-drag-handle').setAttribute('aria-label',`Drag card ${i+1} to reorder`);
  });
  add.disabled=cards.length>=48;
  form.querySelector('#draft-board-title').textContent=form.elements.title.value.trim()||'Your board';
  const grid=form.querySelector('#draft-board-grid');grid.className=`picture-grid layout-${form.elements.layout.value}`;
  grid.replaceChildren(...cards.map(row=>{const card=document.createElement('div');card.className=`picture-card tone-${row.querySelector('[name=card_color]').value}`;const svg=image(row.querySelector('[name=card_symbol]').value);if(svg)card.append(svg.cloneNode(true));const label=document.createElement('strong');label.textContent=row.querySelector('[name=card_label]').value.trim()||'Your card';card.append(label);return card;}));
 };
 add.addEventListener('click',event=>{event.preventDefault();if(rows().length>=48)return;const row=document.querySelector('#board-card-template').content.firstElementChild.cloneNode(true);list.append(row);changed();update();row.querySelector('[name=card_label]').focus();announce.textContent='Card added.';});
 list.addEventListener('click',event=>{
  const button=event.target.closest('[data-card-action]');if(!button)return;event.preventDefault();const row=button.closest('[data-card-editor]'),action=button.dataset.cardAction;
  if(action==='copy'){if(rows().length>=48)return;const copy=row.cloneNode(true);copy.querySelector('[name=card_id]').value='';row.after(copy);changed();update();copy.querySelector('[name=card_label]').focus();}
  else if(action==='remove'){const next=row.nextElementSibling||row.previousElementSibling;row.remove();changed();update();(next?.querySelector('[name=card_label]')||add).focus();}
  else {const sibling=action==='up'?row.previousElementSibling:row.nextElementSibling;if(!sibling)return;if(action==='up')list.insertBefore(row,sibling);else list.insertBefore(sibling,row);changed();update();row.querySelector('[name=card_label]').focus();}
  announce.textContent=action==='remove'?'Card removed from this draft.':`Card ${action==='copy'?'duplicated':'moved'}. Save to keep changes.`;
 });
 form.addEventListener('input',()=>{changed();update();});form.addEventListener('change',()=>{changed();update();});
 list.addEventListener('pointerdown',event=>{const handle=event.target.closest('.board-drag-handle');if(!handle||event.button!==0)return;event.preventDefault();handle.setPointerCapture(event.pointerId);dragged=handle.closest('[data-card-editor]');dragged.classList.add('card-dragging');});
 list.addEventListener('pointermove',event=>{if(!dragged)return;const target=document.elementFromPoint(event.clientX,event.clientY)?.closest('[data-card-editor]');if(target&&target!==dragged&&target.parentElement===list){const rect=target.getBoundingClientRect();const after=event.clientY>rect.top+rect.height/2;list.insertBefore(dragged,after?target.nextElementSibling:target);changed();update();}if(event.clientY>innerHeight-60)window.scrollBy(0,16);if(event.clientY<60)window.scrollBy(0,-16);});
 const finish=()=>{if(!dragged)return;dragged.classList.remove('card-dragging');dragged.querySelector('[name=card_label]').focus();announce.textContent=`Card moved to position ${rows().indexOf(dragged)+1}.`;dragged=null;};
 list.addEventListener('pointerup',finish);list.addEventListener('pointercancel',finish);
 window.addEventListener('beforeunload',event=>{if(dirty&&!submitting){event.preventDefault();event.returnValue='';}});
 form.addEventListener('submit',()=>{submitting=true;form.querySelector('#save-board').disabled=true;status.textContent='Saving…';});update();
})();
