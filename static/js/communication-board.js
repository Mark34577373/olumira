/* Page-memory messages; only explicit saved phrases leave this page. */
(() => {
 const root=document.querySelector('#communication-board');if(!root)return;
 const grid=root.querySelector('#communication-picture-grid'),strip=root.querySelector('#phrase-strip');
 const focus=root.querySelector('#board-focus');focus.hidden=false;
 const setFocus=enabled=>{document.body.classList.toggle('board-focus-mode',enabled);focus.setAttribute('aria-pressed',String(enabled));focus.textContent=enabled?'Exit focus view':'Focus view';};
 setFocus(true);
 focus.addEventListener('click',()=>setFocus(!document.body.classList.contains('board-focus-mode')));
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!root.querySelector('dialog[open]')){setFocus(false);focus.focus();}});
 if(!strip)return; // Archived boards remain readable, without active controls.
 const written=root.querySelector('#phrase-written'),status=root.querySelector('#speech-status');
 const speakButton=root.querySelector('#speak-phrase'),stopButton=root.querySelector('#stop-speech'),replayButton=root.querySelector('#replay-speech');
 const enabled=root.querySelector('#speech-enabled'),voiceSelect=root.querySelector('#speech-voice'),rate=root.querySelector('#speech-rate');
 const removeLast=root.querySelector('#remove-last-word'),clear=root.querySelector('#clear-phrase'),saveOpen=root.querySelector('#save-phrase-open');
 const notice=root.querySelector('#board-access-notice');
 const synth=window.speechSynthesis,supported=!!synth&&typeof window.SpeechSynthesisUtterance==='function'&&['speak','cancel','getVoices'].every(k=>typeof synth[k]==='function');
 const switcher=root.querySelector('#active-communication-board');if(switcher)switcher.addEventListener('change',()=>{if(switcher.value)location.assign(switcher.value);});
 const simple=root.querySelector('#simplified-toggle');if(simple)simple.addEventListener('click',()=>{const active=root.classList.toggle('simplified-board');simple.setAttribute('aria-pressed',String(active));simple.textContent=active?'More controls':'Fewer controls';});
 const storageKey=`olumira.speechSettings.v1.${root.dataset.preferencesKey}`;
 let words=[],voices=[],lastSpoken='',sequence=0,access=true,settings={enabled:true,voice:'',rate:'1'};
 try{const saved=JSON.parse(localStorage.getItem(storageKey)||'null');if(saved&&typeof saved.enabled==='boolean'&&['0.8','1','1.15'].includes(saved.rate)&&typeof saved.voice==='string'&&saved.voice.length<=300)settings=saved;}catch(_){}
 if(root.dataset.profilePreferences==='true')settings={enabled:root.dataset.speechEnabled==='true',voice:root.dataset.voiceId,rate:root.dataset.speechRate};
 enabled.checked=settings.enabled;rate.value=settings.rate;
 const text=()=>words.map(word=>word.text).join(' ');
 const available=()=>supported&&enabled.checked&&voices.length>0&&access;
 const controls=()=>{speakButton.disabled=!words.length||!available();replayButton.disabled=!lastSpoken||!available();removeLast.disabled=clear.disabled=!words.length;if(saveOpen)saveOpen.disabled=!words.length||!access;};
 const stop=(message='Speech stopped. Your message is still here.')=>{sequence++;if(supported)synth.cancel();stopButton.disabled=true;status.textContent=message;};
 const update=()=>{
  strip.replaceChildren();
  if(!words.length){const p=document.createElement('p');p.textContent='Choose a picture to begin.';strip.append(p);}
  words.forEach((word,index)=>{const button=document.createElement('button');button.type='button';button.className='phrase-token';button.textContent=word.label+' ×';button.setAttribute('aria-label',`Remove word ${index+1}: ${word.label}`);button.addEventListener('click',()=>{words.splice(index,1);stop();update();const next=strip.querySelectorAll('button')[Math.min(index,words.length-1)];(next||clear).focus();});strip.append(button);});
  written.textContent=text();controls();
 };
 const speak=message=>{
  if(!available()){status.textContent=!supported?'Speech is unavailable in this browser. Your written message still works.':!enabled.checked?'Speech is off. Your written message stays visible.':'No local voice is available yet. Try another browser or device; your written message stays visible.';return;}
  const selected=voices.find(v=>v.voiceURI===voiceSelect.value)||voices[0];
  if(!selected?.localService)return; // Never fall back to an unreviewed remote voice.
  sequence++;const current=sequence;synth.cancel();
  const utterance=new SpeechSynthesisUtterance(message);utterance.voice=selected;utterance.lang=selected.lang;utterance.rate=Number(rate.value);utterance.volume=1;utterance.pitch=1;
  lastSpoken=message;status.textContent='Speaking…';stopButton.disabled=false;controls();
  utterance.onstart=()=>{if(current===sequence)status.textContent='Speaking…';};
  utterance.onend=()=>{if(current===sequence){status.textContent='Finished speaking. Your message is still here.';stopButton.disabled=true;}};
  utterance.onerror=()=>{if(current===sequence){status.textContent='Speech could not play. Your written message is still here. Try Speak or Replay again.';stopButton.disabled=true;}};
  try{synth.speak(utterance);}catch(_){utterance.onerror();}
 };
 const refreshVoices=()=>{
  if(!supported){status.textContent='Speech is unavailable in this browser. Pictures and your written message still work.';controls();return;}
  try {voices=synth.getVoices().filter(v=>v.localService===true);} catch (_) {voices=[];}
  voiceSelect.replaceChildren();
  if(!voices.length){const option=new Option('No local voice available','');voiceSelect.add(option);voiceSelect.disabled=true;status.textContent='No local voice is available yet. Pictures and your written message still work.';}
  else{voiceSelect.disabled=false;voices.forEach(v=>voiceSelect.add(new Option(`${v.name} (${v.lang})`,v.voiceURI)));voiceSelect.value=voices.some(v=>v.voiceURI===settings.voice)?settings.voice:voices[0].voiceURI;status.textContent=enabled.checked?(settings.voice&&!voices.some(v=>v.voiceURI===settings.voice)?'The preferred voice is unavailable here. A local voice is ready.':'Ready to speak. Choose a picture.'):'Speech is off.';}
  controls();
 };
 if(supported){if(typeof synth.addEventListener==='function')synth.addEventListener('voiceschanged',refreshVoices);else synth.onvoiceschanged=refreshVoices;}
 const saveSettings=()=>{settings={enabled:enabled.checked,rate:rate.value,voice:voiceSelect.value};try{localStorage.setItem(storageKey,JSON.stringify(settings));}catch(_){}stop(enabled.checked?'Speech preferences updated.':'Speech is off.');controls();};
 [enabled,rate,voiceSelect].forEach(el=>el.addEventListener('change',saveSettings));
 grid.addEventListener('click',event=>{
  const card=event.target.closest('[data-picture-card]');if(!card||card.disabled||!access)return;
  if(words.length>=40||(text().length+(words.length?1:0)+card.dataset.text.length)>1000){status.textContent='Your message is full. Remove a word or clear it before adding more.';return;}
  words.push({label:card.dataset.label,text:card.dataset.text});
  grid.querySelectorAll('[data-selected]').forEach(item=>delete item.dataset.selected);card.dataset.selected='true';update();if(enabled.checked)speak(card.dataset.text);
 });
 const useSaved=button=>{if(!access)return;words=[{label:button.textContent.trim(),text:button.dataset.text}];update();if(enabled.checked)speak(text());};
 root.querySelector('.quick-phrase-list').addEventListener('click',event=>{const button=event.target.closest('[data-saved-phrase]');if(button)useSaved(button);});
 speakButton.addEventListener('click',()=>speak(text()));replayButton.addEventListener('click',()=>speak(lastSpoken));stopButton.addEventListener('click',()=>stop());
 removeLast.addEventListener('click',()=>{words.pop();stop();update();});
 clear.addEventListener('click',()=>{words=[];lastSpoken='';stop('Message cleared.');update();grid.querySelector('[data-picture-card]')?.focus();});
 const dialog=root.querySelector('#save-phrase-dialog');
 if(saveOpen&&dialog){
  const form=dialog.querySelector('form');let pending=false;
  saveOpen.addEventListener('click',()=>{form.elements.text.value=text();dialog.showModal();form.elements.label.focus();});
  const close=()=>{dialog.close();saveOpen.focus();};root.querySelector('#cancel-save-phrase').addEventListener('click',close);
  form.addEventListener('submit',async event=>{
   event.preventDefault();if(pending)return;pending=true;const submit=form.querySelector('button[type=submit],button:not([type])');submit.disabled=true;
   let error=dialog.querySelector('[role=alert]');if(!error){error=document.createElement('p');error.setAttribute('role','alert');form.prepend(error);}error.textContent='Saving…';
   try{
    const response=await fetch(form.action,{method:'POST',body:new FormData(form),headers:{Accept:'application/json'},cache:'no-store'});
    if(response.redirected||!response.headers.get('Content-Type')?.includes('application/json'))throw new Error('Your sign-in or access may have changed. Reopen this board and try again.');
    const data=await response.json();if(!response.ok)throw new Error(data.error||'The phrase was not saved. Try again.');
    const list=root.querySelector('.quick-phrase-list');const empty=list.querySelector('p');if(empty)empty.remove();
    let button=list.querySelector(`[data-phrase-id="${data.id}"]`);if(!button){button=document.createElement('button');button.type='button';button.className='text-button';button.dataset.savedPhrase='';button.dataset.phraseId=data.id;list.append(button);}button.dataset.text=data.text;button.textContent=data.label;
    close();status.textContent='Phrase saved for this profile.';form.reset();form.elements.creation_key.value=crypto.randomUUID().replaceAll('-','');error.textContent='';
   }catch(exc){error.textContent=exc instanceof TypeError?'Connection interrupted. Your phrase has not been confirmed saved. Try again.':exc.message;}
   finally{pending=false;submit.disabled=false;}
  });
 }
 const checkAccess=async()=>{
  if(document.hidden)return;
  try{const response=await fetch(root.dataset.stateUrl,{cache:'no-store',headers:{Accept:'application/json'}});
   if(response.redirected||[401,403,404,409].includes(response.status)){
    access=false;words=[];lastSpoken='';stop('This board is no longer available.');update();grid.querySelectorAll('button').forEach(b=>b.disabled=true);notice.hidden=false;notice.textContent='Your sign-in, access, or board status changed. Exit this board and reopen it to continue.';clearInterval(timer);return;
   }
   if(!response.ok)throw new Error();const state=await response.json();
   if(String(state.version)!==root.dataset.version || String(state.preferences_version)!==root.dataset.preferencesVersion){grid.querySelectorAll('button').forEach(b=>b.disabled=true);notice.hidden=false;notice.textContent='A caregiver changed this board. Your current message is still visible. Reopen the board to load the latest pictures.';}
  }catch(_){notice.hidden=false;notice.textContent='Connection interrupted. You can use the pictures on this page. Reconnect before saving new phrases.';}
 };
 const timer=setInterval(checkAccess,30000);document.addEventListener('visibilitychange',checkAccess);
 window.addEventListener('pagehide',()=>{if(supported)synth.cancel();words=[];lastSpoken='';});
 update();refreshVoices();
})();
