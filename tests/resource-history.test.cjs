const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../admin_console/web/resource_history.js'), 'utf8');
const now = 2000000000;
const wait = () => new Promise((r) => setTimeout(r, 20));
function data(metric, empty = false) {
    return { metric, start: now - 604800, end: now, bucket_seconds: 3600,
        available_from: empty ? null : now - 18000,
        points: empty ? [] : [18000, 3600].map((delta, i) => ({ ts: now - delta, value: 20 + i * 10,
            low: 10, high: 60, samples: 6, used: 3000000000, total: 8000000000 })),
        summary: empty ? null : { average: 25, high: 60 }, latest: empty ? null : { ts: now - 20, value: 30 } };
}
function setup(t, fetcher) {
    const dom = new JSDOM('<div id="screen"><section data-history="cpu" tabindex="0">CPU</section><section data-history="memory" tabindex="0">RAM</section><section data-history="disk" tabindex="0">Disco</section></div>',
        { url: 'https://admin.example/#recursos', runScripts: 'outside-only', pretendToBeVisual: true });
    const w = dom.window;
    w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    w.HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new w.Event('close')); };
    w.bytes = (n) => (n / 1e9).toFixed(2) + ' GB';
    const calls = [];
    w.api = async (url, payload) => {
        calls.push({ url, payload });
        const metric = new URL(url, w.location.href).searchParams.get('metric');
        return fetcher ? fetcher(metric) : data(metric);
    };
    w.eval(source);
    t.after(() => { w.document.querySelector('dialog')?.close(); dom.window.close(); });
    return { w, d: w.document, calls };
}
test('click opens weekly graph, samples and recorded peak without writes', async (t) => {
    const { d, calls } = setup(t);
    d.querySelector('[data-history=memory]').click(); await wait();
    const dialog = d.querySelector('dialog');
    assert(dialog.open);
    assert.match(dialog.querySelector('h2').textContent, /Memoria RAM/);
    assert.equal(dialog.querySelector('.history-peak').textContent, '60.0%');
    assert.equal(dialog.querySelectorAll('.history-line').length, 2, 'missing hours must break the line');
    assert.equal(dialog.querySelectorAll('tbody tr').length, 2);
    assert.match(dialog.querySelector('.history-detail').textContent, /3.00 GB de 8.00 GB/);
    assert.equal(calls[0].payload, undefined);
    assert.equal(calls[0].url, '/api/resources/history?metric=memory');
});
test('keyboard and slider work; close restores card focus', async (t) => {
    const { w, d } = setup(t);
    const card = d.querySelector('[data-history=cpu]');
    card.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    await wait();
    const slider = d.querySelector('.history-range'); slider.value = '0'; slider.dispatchEvent(new w.Event('input'));
    assert.match(d.querySelector('.history-detail').textContent, /20.0%/);
    d.querySelector('.history-close').click();
    assert.equal(d.querySelector('dialog'), null); assert.equal(d.activeElement, card);
});
test('late metric response cannot replace a newer metric', async (t) => {
    let finishCPU;
    const { d } = setup(t, (metric) => metric === 'cpu' ? new Promise((resolve) => { finishCPU = resolve; }) : Promise.resolve(data(metric, true)));
    d.querySelector('[data-history=cpu]').click();
    d.querySelector('[data-metric=disk]').click(); await wait();
    finishCPU(data('cpu')); await wait();
    assert.match(d.querySelector('dialog h2').textContent, /Disco/);
    assert.equal(d.querySelectorAll('.history-line').length, 0);
    assert.match(d.querySelector('.history-status').textContent, /Todavía no hay mediciones/);
});
test('normal panel refresh does not remove the chart, and route change closes it', async (t) => {
    const { w, d } = setup(t);
    d.querySelector('[data-history=cpu]').click(); await wait();
    const modal = d.querySelector('dialog');
    d.querySelector('#screen').innerHTML = '<section data-history="cpu" tabindex="0">New CPU card</section>';
    assert.equal(d.querySelector('dialog'), modal);
    w.dispatchEvent(new w.HashChangeEvent('hashchange'));
    assert.equal(d.querySelector('dialog'), null);
});

test('exploring an older hour survives chart resizing', async (t) => {
    const { w, d } = setup(t);
    d.querySelector('[data-history=cpu]').click(); await wait();
    const slider = d.querySelector('.history-range'); slider.value = '0'; slider.dispatchEvent(new w.Event('input'));
    w.dispatchEvent(new w.Event('resize'));
    await new Promise((resolve) => setTimeout(resolve, 180));
    assert.equal(d.querySelector('.history-range').value, '0');
    assert.match(d.querySelector('.history-detail').textContent, /20.0%/);
});
