/* Local wall-clock timers never call the completion API or persist private content. */
(() => {
 const states = new WeakMap();
 function render(node,state){
   const left=state.deadline===null ? state.remaining : Math.max(0,state.deadline-Date.now());
   node.dataset.timerState=state.deadline!==null ? 'running' : (left===0 ? 'finished' : 'paused');
   node.querySelector('[data-timer-output]').textContent=`${Math.ceil(left/1000)}s`;
   if(state.deadline!==null && left===0){state.remaining=0;state.deadline=null;node.dataset.timerState='finished';node.querySelector('[data-timer-status]').textContent='Time guide finished. Take the time you need; complete the step separately.';}
 }
 document.addEventListener('click',event=>{
   if(event.target.closest('[data-print-routine]')){window.print();return;}
   const button=event.target.closest('[data-timer-action]');if(!button)return;
   const node=button.closest('[data-local-timer]'); if(!node)return;
   const seconds=Number(node.dataset.localTimer);if(!Number.isInteger(seconds)||seconds<1||seconds>3600)return;
   let state=states.get(node);if(!state){state={remaining:seconds*1000,deadline:null};states.set(node,state);}
   if(button.dataset.timerAction==='start' && state.deadline===null){if(state.remaining===0)state.remaining=seconds*1000;state.deadline=Date.now()+state.remaining;node.querySelector('[data-timer-status]').textContent='Timer running. You can pause or reset at any time.';}
   if(button.dataset.timerAction==='pause' && state.deadline!==null){state.remaining=Math.max(0,state.deadline-Date.now());state.deadline=null;node.querySelector('[data-timer-status]').textContent='Timer paused.';}
   if(button.dataset.timerAction==='reset'){state.remaining=seconds*1000;state.deadline=null;node.querySelector('[data-timer-status]').textContent='Timer reset.';}
   render(node,state);
 });
 setInterval(()=>document.querySelectorAll('[data-local-timer]').forEach(node=>{const state=states.get(node);if(state)render(node,state);}),250);
})();
