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

(() => {
    if (window.location.pathname !== "/uno360x/area/inventory") return;
    const url = new URL(window.location.href);
    if (url.searchParams.get("product_saved") !== "1") return;
    url.searchParams.delete("product_saved");
    window.history.replaceState(window.history.state, "", url);
})();

/* Prepare the invoice screen using the current user's session and permissions. */
(() => {
    const area = document.querySelector('.ua-area[data-area="billing"]');
    if (!area || navigator.connection?.saveData) return;
    const anchor = area.querySelector('.ua-table-panel a[href^="/odoo/"]');
    if (!anchor) return;
    const target = new URL(anchor.href, location.href);
    if (target.origin !== location.origin) return;

    let started = false;
    const prepare = async () => {
        if (started || document.hidden) return;
        started = true;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 12000);
        const context = {
            lang: area.dataset.lang,
            tz: area.dataset.tz || "UTC",
            allowed_company_ids: [Number(area.dataset.company)],
        };
        const options = { toolbar: false, load_filters: false };
        const actionId = target.pathname.match(/\/action-(\d+)/);
        if (actionId) options.action_id = Number(actionId[1]);
        const warmView = fetch("/web/dataset/call_kw/account.move/get_views", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            signal: controller.signal,
            priority: "low",
            body: JSON.stringify({
                jsonrpc: "2.0", method: "call", id: "uno360x-invoice-preparation",
                params: { model: "account.move", method: "get_views", args: [],
                    kwargs: { views: [[false, "form"]], options, context } },
            }),
        }).then((response) => response.ok ? response.json() : null);
        const warmAssets = fetch(target.href, {
            credentials: "same-origin", signal: controller.signal, priority: "low",
        }).then(async (response) => {
            if (!response.ok || !response.headers.get("content-type")?.includes("text/html")) return;
            const html = new DOMParser().parseFromString(await response.text(), "text/html");
            const urls = [...html.querySelectorAll("script[src],link[rel=stylesheet][href]")]
                .map((element) => element.src || element.href)
                .map((value) => new URL(value, location.href))
                .filter((url) => url.origin === location.origin && url.pathname.startsWith("/web/assets/"));
            for (const url of urls.slice(0, 4)) {
                if ([...document.querySelectorAll('link[rel=prefetch]')].some((link) => link.href === url.href)) continue;
                const link = document.createElement("link");
                link.rel = "prefetch";
                link.href = url.href;
                link.as = url.pathname.endsWith(".css") ? "style" : "script";
                document.head.appendChild(link);
            }
        });
        await Promise.allSettled([warmView, warmAssets]);
        clearTimeout(timeout);
    };
    const idle = () => {
        if ("requestIdleCallback" in window) requestIdleCallback(prepare, { timeout: 1500 });
        else setTimeout(prepare, 500);
    };
    if (document.readyState === "complete") idle();
    else window.addEventListener("load", idle, { once: true });
    area.addEventListener("pointerover", (event) => {
        if (event.target.closest('.ua-table-panel a[href^="/odoo/"]')) prepare();
    }, { passive: true });
})();
