(() => {
  const form = document.querySelector('[data-schedule-form]');
  const summary = document.querySelector('[data-schedule-summary]');
  if (!form || !summary) return;
  const update = () => {
    const data = new FormData(form);
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const repeats = {once: 'One time', daily: 'Every day', weekdays: data.getAll('weekdays').map(d => days[Number(d)]).join(', ') || 'Choose weekdays', weekly: 'Every week on the start weekday'};
    summary.textContent = `${repeats[data.get('frequency')]} at ${data.get('local_time')} · ${data.get('timezone')}, from ${data.get('start_date')}${data.get('end_date') ? ` through ${data.get('end_date')}` : ''}.`;
  };
  form.addEventListener('input', update);
  update();
})();
