(() => {
 const form=document.querySelector('[data-handoff-editor]'); if(!form)return;
 const textarea=form.elements.summary, preview=document.querySelector('[data-handoff-preview]'); let dirty=false;
 form.addEventListener('input',()=>{dirty=true;const share=document.querySelector('[data-share-reviewed]');if(share){share.disabled=true;share.textContent='Save new edits before sharing';}preview.textContent=textarea.value || 'Your reviewed handoff will appear here.';});
 form.addEventListener('submit',()=>{dirty=false;});
 window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
})();
