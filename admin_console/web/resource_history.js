/* Private resource history. Charts contain server measurements, not tenant data. */
(() => {
    'use strict';
    const metrics = { cpu: 'Procesador', memory: 'Memoria RAM', disk: 'Disco' };
    const NS = 'http://www.w3.org/2000/svg';
    const formatDate = (ts, clock = false) => new Intl.DateTimeFormat('es-DO', {
        timeZone: 'America/Santo_Domingo', day: '2-digit', month: 'short',
        ...(clock ? { hour: '2-digit', minute: '2-digit' } : {}),
    }).format(new Date(ts * 1000));
    const percent = (number) => Number.isFinite(number) ? number.toFixed(1) + '%' : 'Sin datos';
    let current = null;
    let resizeTimer;

    function svgElement(tag, attributes = {}, text) {
        const element = document.createElementNS(NS, tag);
        for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
        if (text !== undefined) element.textContent = text;
        return element;
    }

    function render(state, data) {
        const root = state.dialog;
        const points = data.points.filter((p) => ['ts', 'value', 'low', 'high'].every((k) => Number.isFinite(p[k])));
        const graph = root.querySelector('.history-graph');
        graph.replaceChildren();
        root.querySelector('.history-dates').textContent = formatDate(data.start) + ' — ' + formatDate(data.end);
        root.querySelector('.history-average').textContent = percent(data.summary?.average);
        root.querySelector('.history-peak').textContent = percent(data.summary?.high);
        root.querySelector('.history-latest').textContent = percent(data.latest?.value);
        const status = root.querySelector('.history-status');
        status.textContent = data.latest ? 'Última medición: ' + formatDate(data.latest.ts, true) + '.' : 'Todavía no hay mediciones para este recurso.';
        const availability = root.querySelector('.history-availability');
        availability.textContent = data.available_from ? 'Datos disponibles desde ' + formatDate(data.available_from, true) + '. Los períodos sin mediciones quedan en blanco.' :
            'El historial aparecerá al guardar las primeras mediciones.';
        const range = root.querySelector('.history-range');
        range.disabled = points.length < 2;
        range.max = String(Math.max(0, points.length - 1));
        range.value = range.max;
        root.querySelector('.history-detail').textContent = '';
        root.querySelector('.history-values tbody').replaceChildren();
        if (!points.length) return;

        const W = Math.max(360, Math.min(860, Math.round(graph.clientWidth || 860)));
        const H = 248, left = 45, right = W - 15, top = 16, bottom = H - 42;
        const x = (ts) => left + Math.max(0, Math.min(1, (ts - data.start) / (data.end - data.start))) * (right - left);
        const y = (value) => bottom - Math.max(0, Math.min(100, value)) / 100 * (bottom - top);
        const svg = svgElement('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img',
            'aria-label': metrics[state.metric] + ': porcentaje de uso de los últimos siete días. La línea representa promedios por hora y la banda sus mínimos y máximos.' });
        for (const value of [0, 25, 50, 75, 100]) {
            svg.append(svgElement('line', { x1: left, x2: right, y1: y(value), y2: y(value), class: 'history-grid' }));
            svg.append(svgElement('text', { x: left - 7, y: y(value) + 4, 'text-anchor': 'end', class: 'history-axis' }, value + '%'));
        }
        for (let index = 0; index < 4; index++) {
            const ts = data.start + (data.end - data.start) * index / 3;
            svg.append(svgElement('text', { x: x(ts), y: H - 13,
                'text-anchor': index === 0 ? 'start' : index === 3 ? 'end' : 'middle', class: 'history-axis' }, formatDate(ts)));
        }
        const segments = [];
        for (const point of points) {
            if (!segments.length || point.ts - segments.at(-1).at(-1).ts > data.bucket_seconds * 1.6) segments.push([]);
            segments.at(-1).push(point);
        }
        for (const segment of segments) {
            const band = segment.map((p, i) => `${i ? 'L' : 'M'}${x(p.ts)},${y(p.high)}`).join(' ') + ' ' +
                [...segment].reverse().map((p) => `L${x(p.ts)},${y(p.low)}`).join(' ') + ' Z';
            svg.append(svgElement('path', { d: band, class: 'history-band' }));
            svg.append(svgElement('path', { d: segment.map((p, i) => `${i ? 'L' : 'M'}${x(p.ts)},${y(p.value)}`).join(' '), class: 'history-line' }));
        }
        const cursor = svgElement('line', { y1: top, y2: bottom, class: 'history-cursor' });
        const marker = svgElement('circle', { r: 4.5, class: 'history-marker' });
        svg.append(cursor, marker);
        graph.append(svg);
        let selected = -1;
        function select(index, userSelection = false) {
            index = Math.max(0, Math.min(points.length - 1, index));
            if (userSelection) state.followLatest = index === points.length - 1;
            if (index === selected) return;
            selected = index;
            range.value = String(index);
            const point = points[index];
            state.selectedTime = point.ts;
            cursor.setAttribute('x1', x(point.ts)); cursor.setAttribute('x2', x(point.ts));
            marker.setAttribute('cx', x(point.ts)); marker.setAttribute('cy', y(point.value));
            root.querySelector('.history-detail').textContent = formatDate(point.ts, true) +
                ' · Promedio ' + percent(point.value) + ' · Mínimo ' + percent(point.low) + ' · Máximo ' + percent(point.high) +
                (point.used !== null && point.total ? ' · ' + bytes(point.used) + ' de ' + bytes(point.total) : '') +
                ' · ' + point.samples + ' mediciones.';
            range.setAttribute('aria-valuetext', formatDate(point.ts, true) + ', promedio ' + percent(point.value));
        }
        range.oninput = () => select(Number(range.value), true);
        svg.addEventListener('pointermove', (event) => {
            const box = svg.getBoundingClientRect();
            const pos = (event.clientX - box.left) / box.width * W;
            const ts = data.start + Math.max(0, Math.min(1, (pos - left) / (right - left))) * (data.end - data.start);
            let closest = 0;
            for (let i = 1; i < points.length; i++) if (Math.abs(points[i].ts - ts) < Math.abs(points[closest].ts - ts)) closest = i;
            select(closest, true);
        });
        let initial = points.length - 1;
        if (!state.followLatest && state.selectedTime != null) {
            initial = 0;
            for (let i = 1; i < points.length; i++) if (Math.abs(points[i].ts - state.selectedTime) < Math.abs(points[initial].ts - state.selectedTime)) initial = i;
        }
        select(initial);
        const body = root.querySelector('.history-values tbody');
        for (const point of [...points].reverse()) {
            const row = document.createElement('tr');
            for (const value of [formatDate(point.ts, true), percent(point.value), percent(point.low), percent(point.high)]) {
                const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
            }
            body.append(row);
        }
    }

    async function load(state, metric) {
        if (!metrics[metric]) return;
        if (state.metric !== metric) {
            state.selectedTime = null; state.followLatest = true;
            state.dialog.querySelector('.history-graph').replaceChildren();
            for (const selector of ['.history-average', '.history-peak', '.history-latest']) state.dialog.querySelector(selector).textContent = '—';
            for (const selector of ['.history-detail', '.history-availability']) state.dialog.querySelector(selector).textContent = '';
            state.dialog.querySelector('.history-range').disabled = true;
            state.dialog.querySelector('.history-values tbody').replaceChildren();
        }
        const version = ++state.version;
        clearTimeout(state.timer);
        state.metric = metric; state.data = null;
        state.dialog.querySelector('h2').textContent = metrics[metric] + ' · últimos 7 días';
        state.dialog.querySelectorAll('[data-metric]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.metric === metric)));
        state.dialog.querySelector('.history-status').textContent = 'Cargando mediciones…';
        try {
            const data = await api('/api/resources/history?metric=' + encodeURIComponent(metric));
            if (current !== state || state.version !== version || !state.dialog.open) return;
            if (data.metric !== metric || !Array.isArray(data.points)) throw new Error('Historial no disponible.');
            state.data = data;
            render(state, data);
        } catch (error) {
            if (current !== state || state.version !== version) return;
            if (!document.querySelector('#screen')) { state.dialog.close(); return; }
            state.dialog.querySelector('.history-status').textContent = error.message;
        } finally {
            if (current === state && state.dialog.open && state.version === version) state.timer = setTimeout(() => load(state, state.metric), 60000);
        }
    }

    function open(metric) {
        if (!metrics[metric]) return;
        if (current) { load(current, metric); return; }
        const dialog = document.createElement('dialog');
        dialog.id = 'resource-history-dialog'; dialog.className = 'history-dialog'; dialog.setAttribute('aria-labelledby', 'history-title');
        dialog.innerHTML = `<div class="history-heading"><div><h2 id="history-title">Historial de recursos</h2><p class="small history-dates">Últimos siete días · hora dominicana</p></div><button class="btn history-close" type="button" aria-label="Cerrar historial">Cerrar</button></div>
          <div class="history-tabs" aria-label="Recurso">${Object.entries(metrics).map(([key, name]) => `<button class="btn" type="button" data-metric="${key}" aria-pressed="false">${name}</button>`).join('')}</div>
          <div class="history-stats"><div><span>PROMEDIO</span><strong class="history-average">—</strong></div><div><span>PICO REGISTRADO</span><strong class="history-peak">—</strong></div><div><span>ÚLTIMA MEDICIÓN</span><strong class="history-latest">—</strong></div></div>
          <p class="small history-status" role="status"></p><div class="history-graph"></div>
          <label class="small history-range-label">Explorar las mediciones<input class="history-range" type="range" min="0" max="0" value="0" aria-label="Elegir una medición del historial" disabled></label>
          <p class="history-detail" aria-live="polite"></p><p class="small history-availability"></p>
          <p class="small">Línea: promedio por hora. Banda: mínimo y máximo registrados. Las mediciones no registran los picos que ocurran entre muestras.</p>
          <details class="history-values"><summary>Ver valores por hora</summary><div class="tablewrap"><table><thead><tr><th>FECHA</th><th>PROMEDIO</th><th>MÍNIMO</th><th>MÁXIMO</th></tr></thead><tbody></tbody></table></div></details>`;
        const state = { dialog, metric, version: 0, timer: null, data: null, selectedTime: null, followLatest: true };
        current = state;
        dialog.querySelector('.history-close').onclick = () => dialog.close();
        dialog.querySelectorAll('[data-metric]').forEach((button) => { button.onclick = () => load(state, button.dataset.metric); });
        dialog.addEventListener('close', () => {
            clearTimeout(state.timer); state.version++;
            if (current === state) current = null;
            dialog.remove(); document.querySelector(`[data-history="${state.metric}"]`)?.focus();
        });
        document.body.append(dialog); dialog.showModal(); load(state, metric);
    }
    document.addEventListener('click', (event) => {
        const card = event.target.closest('[data-history]'); if (card) open(card.dataset.history);
    });
    document.addEventListener('keydown', (event) => {
        if (!['Enter', ' '].includes(event.key)) return;
        const card = event.target.closest('[data-history]');
        if (card) { event.preventDefault(); open(card.dataset.history); }
    });
    window.addEventListener('hashchange', () => current?.dialog.close());
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => { if (current?.data) render(current, current.data); }, 150);
    });
})();
