/* Progressive enhancement: server-validated forms remain the persistence boundary. */
(() => {
    const form = document.querySelector('#routine-builder');
    if (!form) return;
    const list = form.querySelector('#routine-step-list');
    const announcement = form.querySelector('#builder-announcement');
    const add = form.querySelector('#add-routine-step');
    const preview = form.querySelector('#routine-live-preview');
    let dirty = Boolean(document.querySelector('#builder-error'));
    let submitting = false;
    let dragged = null;
    const rows = () => [...list.querySelectorAll('[data-step-editor]')];
    const announce = text => { announcement.textContent = text; };
    const update = () => {
        const all = rows();
        all.forEach((row, index) => {
            row.querySelector('[data-step-number]').textContent = index + 1;
            row.querySelector('[data-step-heading]').textContent = `Step ${index + 1}`;
            for (const [name, suffix] of [['step_title','title'],['step_description','description'],['step_icon','icon']]) {
                const input = row.querySelector(`[name=${name}]`);
                input.id = `step-${index + 1}-${suffix}`;
                row.querySelector(`label[data-for=${suffix}]`).htmlFor = input.id;
            }
            const up = row.querySelector('[data-step-up]');
            const down = row.querySelector('[data-step-down]');
            const remove = row.querySelector('[data-step-remove]');
            up.disabled = index === 0;
            down.disabled = index === all.length - 1;
            remove.disabled = all.length === 1;
            up.value = `up:${index}`; down.value = `down:${index}`; remove.value = `remove:${index}`;
            for (const control of [up, down, remove]) control.setAttribute('aria-label', `${control.textContent.trim()} ${index + 1}`);
            row.querySelector('.step-drag-handle').hidden = false;
            row.querySelector('.step-drag-handle').setAttribute('aria-label', `Drag step ${index+1} to reorder`);
            const stepImage = document.querySelector(`#builder-icon-library [data-icon=${row.querySelector('[name=step_icon]').value}] svg`);
            if (stepImage) row.querySelector('.step-header-icon').replaceChildren(stepImage.cloneNode(true));
        });
        add.disabled = all.length >= 30;
        form.querySelector('#preview-name').textContent = form.elements.name.value.trim() || 'Your routine';
        form.querySelector('#preview-description').textContent = form.elements.description.value.trim() || 'A little structure, made for your day.';
        form.querySelector('#preview-category').textContent = form.elements.category.value.trim() || 'Your category';
        preview.className = `routine-preview-card tone-${form.elements.color.value}`;
        const image = document.querySelector(`#builder-icon-library [data-icon=${form.elements.icon.value}] svg`);
        if (image) preview.querySelector('.routine-visual').replaceChildren(image.cloneNode(true));
        const sequence = form.querySelector('#preview-steps');
        sequence.replaceChildren(...all.map(row => {
            const item = document.createElement('li');
            item.textContent = row.querySelector('[name=step_title]').value.trim() || 'A small step';
            return item;
        }));
    };
    const move = (row, direction) => {
        const sibling = direction === 'up' ? row.previousElementSibling : row.nextElementSibling;
        if (!sibling) return;
        if (direction === 'up') list.insertBefore(row, sibling);
        else list.insertBefore(sibling, row);
        dirty = true; update();
        row.querySelector(direction === 'up' && row.previousElementSibling ? '[data-step-up]' : '[name=step_title]').focus();
        announce(`Step moved to position ${rows().indexOf(row) + 1}.`);
    };
    add.hidden = false;
    add.addEventListener('click', event => {
        event.preventDefault();
        if (rows().length >= 30) return;
        const row = document.querySelector('#routine-step-template').content.firstElementChild.cloneNode(true);
        list.append(row); dirty = true; update();
        row.querySelector('[name=step_title]').focus();
        announce(`Step ${rows().length} added.`);
    });
    list.addEventListener('click', event => {
        const button = event.target.closest('[data-step-up],[data-step-down],[data-step-remove]');
        if (!button) return;
        event.preventDefault();
        const row = button.closest('[data-step-editor]');
        if (button.hasAttribute('data-step-up')) move(row, 'up');
        else if (button.hasAttribute('data-step-down')) move(row, 'down');
        else if (rows().length > 1) {
            const target = row.nextElementSibling || row.previousElementSibling;
            row.remove(); dirty = true; update();
            target.querySelector('[name=step_title]').focus();
            announce('Step removed. Your other steps are unchanged.');
        }
    });
    form.addEventListener('input', () => { dirty = true; update(); });
    form.addEventListener('change', () => { dirty = true; update(); });
    list.addEventListener('pointerdown', event => {
        const handle = event.target.closest('.step-drag-handle');
        if (!handle || event.button !== 0) return;
        event.preventDefault();
        handle.setPointerCapture(event.pointerId);
        dragged = handle.closest('[data-step-editor]');
        dragged.classList.add('step-is-dragging');
    });
    list.addEventListener('pointermove', event => {
        if (!dragged) return;
        const target = document.elementFromPoint(event.clientX,event.clientY)?.closest('[data-step-editor]');
        if (target && target !== dragged && target.parentElement === list) {
            const rect = target.getBoundingClientRect();
            list.insertBefore(dragged, event.clientY > rect.top + rect.height / 2 ? target.nextElementSibling : target);
            dirty = true; update();
        }
        if (event.clientY > innerHeight - 60) window.scrollBy(0, 18);
        if (event.clientY < 60) window.scrollBy(0, -18);
    });
    const finishDrag = () => {
        if (!dragged) return;
        dragged.classList.remove('step-is-dragging');
        announce(`Step moved to position ${rows().indexOf(dragged) + 1}.`);
        dragged.querySelector('.step-drag-handle').focus(); dragged = null;
    };
    list.addEventListener('pointerup',finishDrag);
    list.addEventListener('pointercancel',finishDrag);
    window.addEventListener('beforeunload', event => {
        if (dirty && !submitting) { event.preventDefault(); event.returnValue = ''; }
    });
    form.addEventListener('submit', () => {
        submitting = true;
        form.querySelector('#save-routine').disabled = true;
        form.querySelector('#save-routine').textContent = 'Saving…';
    });
    update();
})();
