const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM, VirtualConsole } = require('jsdom');
const source = fs.readFileSync(path.join(__dirname, '../addons/uno360x_workspace/static/src/js/partial_navigation.js'), 'utf8');
const origin = 'https://saas.example';

function html(title, changes = {}) {
    const identity = { user: '2', company: '1', lang: 'es_DO', revision: 'release1:tenant-a', ...changes };
    return `<!doctype html><title>UNO360X ${title}</title><div class="ux-app-shell" data-navigation="1"
      data-user="${identity.user}" data-company="${identity.company}" data-lang="${identity.lang}" data-revision="${identity.revision}">
      <aside class="ux-sidebar"><a href="/uno360x-resumen">Resumen</a><a href="/uno360x/area/inventory">Inventario</a></aside>
      <div class="ux-page"><header class="ux-topbar"><div class="ux-profile">Mi usuario</div>
      <form method="post" action="/uno360x/language/en_US"><input name="csrf_token" value="${identity.token || 'old'}"></form></header>
      <main class="ua-area"><h1>${title}</h1><a class="next" href="/uno360x/area/inventory">Inventario</a>
      <a class="tab" href="/uno360x/area/billing?selection=vendors">Proveedores</a>
      <a class="native" href="/odoo/customer-invoices/48">Factura</a>
      <form class="filters" method="get"><input name="q"><input name="selection" value="all"></form>
      ${identity.extra || ''}</main><footer class="ux-footer">UNO360X</footer></div></div>`;
}

function setup(t, { body = html('Facturas'), pathname = '/uno360x/area/billing', fetcher } = {}) {
    const errors = [];
    const console = new VirtualConsole();
    console.on('jsdomError', (error) => errors.push(error.message));
    const dom = new JSDOM(body, { url: origin + pathname, runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole: console });
    t.after(() => dom.window.close());
    const w = dom.window;
    let scroll = [0, 0];
    Object.defineProperty(w, 'scrollX', { get: () => scroll[0] });
    Object.defineProperty(w, 'scrollY', { get: () => scroll[1] });
    w.scrollTo = (x, y) => { scroll = [x, y]; };
    const calls = [];
    w.fetch = async (url, options) => {
        calls.push({ url, options });
        if (fetcher) return fetcher(url, options, calls.length);
        const u = new URL(url);
        return response(url, html(u.searchParams.get('selection') || u.pathname.split('/').pop(), { token: 'fresh' }));
    };
    w.eval(source);
    return { w, d: w.document, calls, errors };
}
function response(url, body, ok = true) {
    return { url, ok, headers: { get: () => 'text/html; charset=utf-8' }, text: async () => body };
}
const wait = (ms = 40) => new Promise((resolve) => setTimeout(resolve, ms));
function click(w, element, options = {}) {
    const event = new w.MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ...options });
    element.dispatchEvent(event);
    return event.defaultPrevented;
}

test('only the content changes; menu, header and footer nodes survive', async (t) => {
    const { w, d, calls } = setup(t);
    const nodes = ['.ux-sidebar', '.ux-topbar', '.ux-footer'].map((s) => d.querySelector(s));
    assert.equal(click(w, d.querySelector('.next')), true);
    await wait();
    assert.equal(d.querySelector('h1').textContent, 'inventory');
    for (const [i, selector] of ['.ux-sidebar', '.ux-topbar', '.ux-footer'].entries()) assert.equal(d.querySelector(selector), nodes[i]);
    assert.equal(w.location.pathname, '/uno360x/area/inventory');
    assert.equal(w.history.length, 2);
    assert.equal(d.querySelector('[name=csrf_token]').value, 'fresh');
    assert.equal(calls[0].options.cache, 'no-store');
    assert.equal(calls[0].options.credentials, 'same-origin');
    assert.equal(calls[0].options.body, undefined);
    assert.equal(d.querySelector('.ux-page').hasAttribute('aria-busy'), false);
});

test('GET filters serialize correctly without issuing writes', async (t) => {
    const { w, d, calls } = setup(t);
    d.querySelector('[name=q]').value = 'tornillo & cable';
    const event = new w.Event('submit', { bubbles: true, cancelable: true });
    d.querySelector('.filters').dispatchEvent(event);
    assert.equal(event.defaultPrevented, true);
    await wait();
    const url = new URL(calls[0].url);
    assert.equal(url.searchParams.get('q'), 'tornillo & cable');
    assert.equal(url.searchParams.get('selection'), 'all');
    assert.equal(calls[0].options.method, undefined);
});

test('Back and Forward fetch fresh data and restore the outgoing scroll', async (t) => {
    const { w, d, calls } = setup(t);
    w.scrollTo(0, 250);
    click(w, d.querySelector('.tab'));
    await wait();
    w.history.back();
    await wait(80);
    assert.equal(w.location.search, '');
    assert.equal(d.querySelector('h1').textContent, 'billing');
    assert.equal(w.scrollY, 250);
    w.history.forward();
    await wait(80);
    assert.equal(w.location.search, '?selection=vendors');
    assert.equal(d.querySelector('h1').textContent, 'vendors');
    assert.equal(calls.length, 3);
});

test('native forms, POST and modified/new-tab clicks keep their normal navigation', async (t) => {
    const { w, d, calls } = setup(t);
    assert.equal(click(w, d.querySelector('.native')), false);
    assert.equal(click(w, d.querySelector('.next'), { ctrlKey: true }), false);
    const post = new w.Event('submit', { bubbles: true, cancelable: true });
    d.querySelector('.ux-topbar form').dispatchEvent(post);
    assert.equal(post.defaultPrevented, false);
    d.querySelector('.next').target = '_blank';
    assert.equal(click(w, d.querySelector('.next')), false);
    assert.equal(calls.length, 0);
});

test('a business form added to the central area prevents partial navigation', (t) => {
    const { w, d, calls } = setup(t);
    d.querySelector('main').insertAdjacentHTML('beforeend', '<form method="post"><input name="amount" value="99"></form>');
    assert.equal(click(w, d.querySelector('.next')), false);
    assert.equal(calls.length, 0);
});

for (const changes of [{ user: '3' }, { company: '2' }, { lang: 'en_US' }, { revision: 'release2:tenant-a' }, { revision: 'release1:tenant-b' }]) {
    test('changed session/context is never transplanted: ' + JSON.stringify(changes), async (t) => {
        const { w, d, errors } = setup(t, { fetcher: async (url) => response(url, html('PRIVATE OTHER CONTEXT', changes)) });
        click(w, d.querySelector('.next'));
        await wait();
        assert.equal(d.querySelector('h1').textContent, 'Facturas');
        assert(errors.some((message) => message.includes('navigation')));
    });
}

test('session expiry and changed permissions require a full authenticated page', async (t) => {
    for (const expiry of [true, false]) {
        const { w, d } = setup(t, { fetcher: async (url) => expiry ? response(origin + '/web/login', '<h1>Login</h1>') :
            response(url, html('Changed').replace('Inventario</a></aside>', 'New permission</a></aside>')) });
        click(w, d.querySelector('.next'));
        await wait();
        assert.equal(d.querySelector('h1').textContent, 'Facturas');
    }
});

test('a late response cannot overwrite the most recent navigation', async (t) => {
    const pending = [];
    const { w, d, calls } = setup(t, { fetcher: (url) => new Promise((resolve) => pending.push({ url, resolve })) });
    click(w, d.querySelector('.next'));
    click(w, d.querySelector('.tab'));
    pending[1].resolve(response(pending[1].url, html('Most recent')));
    await wait();
    pending[0].resolve(response(pending[0].url, html('OLD RESPONSE')));
    await wait();
    assert.equal(d.querySelector('h1').textContent, 'Most recent');
    assert.equal(calls[0].options.signal.aborted, true);
    assert.equal(w.history.length, 2);
});

test('server scripts and business forms are not imported or executed', async (t) => {
    for (const extra of ['<script>window.unwanted = true</script>', '<form method="post"></form>', '<iframe></iframe>']) {
        const { w, d } = setup(t, { fetcher: async (url) => response(url, html('Unsafe', { extra })) });
        click(w, d.querySelector('.next'));
        await wait();
        assert.equal(d.querySelector('h1').textContent, 'Facturas');
        assert.equal(w.unwanted, undefined);
    }
});

test('saved-filter navigation uses the same fresh-data mechanism', async (t) => {
    const { w, d, calls } = setup(t);
    const event = new w.CustomEvent('uno360x:navigate', { cancelable: true, detail: { url: '/uno360x/area/billing?q=filter' } });
    d.dispatchEvent(event);
    await wait();
    assert.equal(event.defaultPrevented, true);
    assert.equal(new URL(calls[0].url).searchParams.get('q'), 'filter');
});
