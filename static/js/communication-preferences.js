(() => {
 const form=document.querySelector('#communication-preferences');if(!form)return;
 const preview=document.querySelector('#preferences-preview');
 const update=()=>{preview.className=`picture-grid layout-2 pref-size-${form.elements.card_size.value} pref-label-${form.elements.text_position.value}`;preview.classList.toggle('pref-hide-text',!form.elements.show_text.checked);preview.classList.toggle('pref-hide-symbols',!form.elements.show_symbols.checked);preview.classList.toggle('pref-high-contrast',form.elements.high_contrast.checked);};
 form.addEventListener('change',update);update();
 const list=document.querySelector('#profile-local-voices');
 const load=()=>{try{list.replaceChildren(...speechSynthesis.getVoices().filter(v=>v.localService).map(v=>new Option(v.name,v.voiceURI)));}catch(_) {}};
 if(window.speechSynthesis){load();speechSynthesis.addEventListener?.('voiceschanged',load);}
})();
