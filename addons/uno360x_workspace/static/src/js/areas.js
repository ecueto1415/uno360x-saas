/* Browser preferences are isolated by company and user. No business writes. */
(() => {
    function setupAreas() {
        document.querySelectorAll('.ua-area').forEach((area) => {
            if (area.dataset.ready) return;
            area.dataset.ready = '1';
            const key = `uno360x:area:${area.dataset.company}:${area.dataset.user}:${area.dataset.area}`;
            const restore = area.querySelector('.ua-restore-filter');
            const status = area.querySelector('.ua-filter-status');
            try {
                if (restore && localStorage.getItem(key + ':filter')) restore.hidden = false;
            } catch {}
            area.querySelector('.ua-save-filter')?.addEventListener('click', () => {
                try {
                    localStorage.setItem(key + ':filter', location.pathname + location.search);
                    if (restore) restore.hidden = false;
                    if (status) status.textContent = 'Filtro guardado';
                } catch {
                    if (status) status.textContent = 'No se pudo guardar el filtro en este navegador';
                }
            });
            restore?.addEventListener('click', () => {
                try {
                    const target = localStorage.getItem(key + ':filter');
                    if (target && target.startsWith('/uno360x/')) location.assign(target);
                } catch {}
            });
            area.querySelectorAll('.ua-favorite').forEach((button) => {
                const favoriteKey = key + ':favorite:' + button.dataset.href;
                let marked = false;
                try { marked = localStorage.getItem(favoriteKey) === '1'; } catch {}
                const sync = () => {
                    button.textContent = marked ? '★' : '☆';
                    button.setAttribute('aria-pressed', String(marked));
                };
                sync();
                button.addEventListener('click', () => {
                    marked = !marked;
                    try { localStorage.setItem(favoriteKey, marked ? '1' : '0'); } catch {}
                    sync();
                });
            });
        });
    }
    function markPaid() {
        document.querySelectorAll('[name="payment_state"] .badge,[name="payment_state"].badge').forEach((node) => {
            node.classList.toggle('ua-native-paid', ['paid', 'pagada', 'pagado'].includes(node.textContent.trim().toLowerCase()));
        });
    }
    function addReturnLink() {
        const header = document.getElementById('ux-native-header');
        if (!header || header.querySelector('.ua-native-back')) return;
        let target = '';
        try { target = sessionStorage.getItem(`uno360x:return:${header.dataset.company}:${header.dataset.user}`) || ''; } catch {}
        if (!target.startsWith('/uno360x/area/')) return;
        const back = document.createElement('a');
        back.className = 'ua-native-back';
        back.href = target;
        back.textContent = '← Volver a la lista';
        header.append(back);
    }
    document.addEventListener('click', (event) => {
        const link = event.target.closest('.ua-area a[href^="/odoo/"]');
        if (!link) return;
        const area = link.closest('.ua-area');
        try {
            sessionStorage.setItem(`uno360x:return:${area.dataset.company}:${area.dataset.user}`, location.pathname + location.search);
        } catch {}
    });
    let pending = false;
    function schedule() {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => {
            pending = false;
            setupAreas();
            markPaid();
            addReturnLink();
        });
    }
    new MutationObserver(schedule).observe(document.documentElement, {subtree: true, childList: true});
    schedule();
})();
