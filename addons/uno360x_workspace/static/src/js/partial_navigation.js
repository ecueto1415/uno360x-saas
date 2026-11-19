/* Keep the shared shell for read-only workspace pages. Never submit writes. */
(() => {
    'use strict';
    const areaPath = /^\/uno360x\/area\/(contacts|crm|sales|pos|billing|expenses|projects|purchases|inventory|maintenance|attendance|leave|reports)$/;
    const staticPaths = new Set(['/uno360x-resumen', '/uno360x-aplicaciones', '/uno360x-ayuda', '/uno360x-buscar']);
    const isRoute = (url) => url.origin === location.origin && !url.hash &&
        (areaPath.test(url.pathname) || staticPaths.has(url.pathname));

    function frame(doc) {
        const shell = doc.querySelector('.ux-app-shell[data-navigation="1"]');
        const page = shell?.querySelector('.ux-page');
        const header = page?.querySelector(':scope > .ux-topbar');
        const footer = page?.querySelector(':scope > .ux-footer');
        if (!header || !footer) return null;
        const nodes = [];
        for (let node = header.nextSibling; node && node !== footer; node = node.nextSibling) nodes.push(node);
        if (!nodes.length || nodes[nodes.length - 1].nextSibling !== footer) return null;
        return { shell, page, header, footer, nodes };
    }

    function readOnly(view) {
        if (!view) return false;
        return view.nodes.every((node) => {
            if (node.nodeType !== 1) return true;
            const elements = [node, ...node.querySelectorAll('*')];
            return elements.every((element) => {
                if (element.matches('script,iframe,object,embed,input[type=file],[contenteditable]:not([contenteditable="false"])')) return false;
                return element.tagName !== 'FORM' || element.method.toLowerCase() === 'get';
            });
        });
    }

    function identity(view) {
        return ['user', 'company', 'lang', 'revision'].map((key) => view.shell.dataset[key] || '').join('|');
    }

    function chromeSignature(doc) {
        // Permission/menu changes require a fresh shell rather than keeping stale controls.
        return JSON.stringify([
            ...[...doc.querySelectorAll('.ux-sidebar a, .ux-topbar a')]
                .map((a) => [a.getAttribute('href'), a.textContent.replace(/\s+/g, ' ').trim()]),
            doc.querySelector('.ux-topbar .ux-profile')?.textContent.replace(/\s+/g, ' ').trim(),
        ]);
    }

    let currentURL = location.href;
    let current = frame(document);
    if (!isRoute(new URL(currentURL)) || !readOnly(current)) return;
    let operation = 0;
    let pending;
    let scrollTimer;

    function remember() {
        if (location.href !== currentURL) return;
        history.replaceState({ ...history.state, uno360xNavigation: {
            url: currentURL, scroll: [window.scrollX, window.scrollY],
        } }, '', currentURL);
    }
    remember();
    window.addEventListener('scroll', () => {
        clearTimeout(scrollTimer);
        scrollTimer = setTimeout(remember, 120);
    }, { passive: true });

    function fallback(url, pop) {
        if (pop) location.replace(url.href);
        else location.assign(url.href);
    }

    async function visit(url, { pop = false, scroll = [0, 0] } = {}) {
        const mine = ++operation;
        pending?.abort();
        pending = new AbortController();
        const controller = pending;
        const timeout = setTimeout(() => controller.abort(), 15000);
        if (!pop) remember();
        current.page.setAttribute('aria-busy', 'true');
        document.dispatchEvent(new CustomEvent('uno360x:navigation-start'));
        const started = performance.now();
        try {
            const response = await fetch(url.href, {
                credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
                headers: { 'Accept': 'text/html', 'X-UNO360X-Navigation': 'content' },
            });
            if (mine !== operation) return;
            const destination = new URL(response.url);
            if (!response.ok || !isRoute(destination) || destination.pathname !== url.pathname ||
                !response.headers.get('content-type')?.includes('text/html')) throw new Error('Fresh page required');
            const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
            if (mine !== operation) return;
            const next = frame(doc);
            if (!readOnly(next) || identity(current) !== identity(next) ||
                chromeSignature(document) !== chromeSignature(doc)) throw new Error('Shell context changed');

            const replacement = document.createDocumentFragment();
            for (const node of next.nodes) replacement.appendChild(document.importNode(node, true));
            const range = document.createRange();
            range.setStartAfter(current.header);
            range.setEndBefore(current.footer);
            range.deleteContents();
            range.insertNode(replacement);
            document.title = doc.title;
            const sidebarLinks = current.shell.querySelectorAll('.ux-sidebar a');
            next.shell.querySelectorAll('.ux-sidebar a').forEach((fresh, index) => {
                sidebarLinks[index].className = fresh.className;
                if (fresh.hasAttribute('aria-current')) sidebarLinks[index].setAttribute('aria-current', fresh.getAttribute('aria-current'));
                else sidebarLinks[index].removeAttribute('aria-current');
            });
            for (const input of current.header.querySelectorAll('input[name="csrf_token"]')) {
                const action = input.form?.getAttribute('action');
                const freshForm = [...next.header.querySelectorAll('form')].find((f) => f.getAttribute('action') === action);
                const token = freshForm?.querySelector('input[name="csrf_token"]');
                if (token) input.value = token.value;
            }
            currentURL = destination.href;
            if (!pop) history.pushState({ uno360xNavigation: { url: currentURL, scroll } }, '', currentURL);
            current = frame(document);
            document.querySelectorAll('.ux-primary-item[open]').forEach((node) => { node.open = false; });
            current.shell.querySelector('.ux-sidebar')?.classList.remove('is-open');
            current.shell.querySelector('.ux-mobile-toggle')?.setAttribute('aria-expanded', 'false');
            const heading = current.page.querySelector('h1');
            if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
            window.scrollTo(...scroll);
            requestAnimationFrame(() => { if (mine === operation) window.scrollTo(...scroll); });
            const duration = performance.now() - started;
            performance.measure?.('uno360x-content-navigation', { start: started, end: performance.now() });
            document.dispatchEvent(new CustomEvent('uno360x:pagechange', { detail: { url: currentURL, duration } }));
        } catch (error) {
            if (mine === operation) fallback(url, pop);
        } finally {
            clearTimeout(timeout);
            if (mine === operation) {
                pending = null;
                current.page.removeAttribute('aria-busy');
            }
        }
    }

    function canVisit(url) {
        return isRoute(url) && isRoute(new URL(currentURL)) && readOnly(frame(document));
    }
    document.addEventListener('click', (event) => {
        if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const link = event.target.closest('a[href]');
        if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
        const url = new URL(link.href, currentURL);
        if (!canVisit(url)) return;
        event.preventDefault();
        visit(url);
    });
    document.addEventListener('submit', (event) => {
        const form = event.target;
        if (event.defaultPrevented || form.method.toLowerCase() !== 'get' ||
            (form.target && form.target !== '_self') || event.submitter?.hasAttribute('formmethod') ||
            event.submitter?.hasAttribute('formaction')) return;
        const url = new URL(form.action || currentURL, currentURL);
        if (!canVisit(url)) return;
        url.search = '';
        for (const [key, value] of new FormData(form)) url.searchParams.append(key, value);
        if (event.submitter?.name) url.searchParams.append(event.submitter.name, event.submitter.value);
        event.preventDefault();
        visit(url);
    });
    document.addEventListener('uno360x:navigate', (event) => {
        const url = new URL(event.detail.url, currentURL);
        if (!canVisit(url)) return;
        event.preventDefault();
        visit(url);
    });
    window.addEventListener('popstate', (event) => {
        const url = new URL(location.href);
        if (!canVisit(url) || !event.state?.uno360xNavigation) {
            fallback(url, true);
            return;
        }
        visit(url, { pop: true, scroll: event.state.uno360xNavigation.scroll || [0, 0] });
    });
})();
