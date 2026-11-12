# Pool aFRR

Home Assistant-integratie voor een groep Balans Energie-gebruikers: deelt wie er op dit moment aFRR-export of -import heeft.

- Naar de pool gaat alleen: je naam, de richting (export/import) en het tijdstip.
- Je Balans-wachtwoord blijft in je eigen Home Assistant.

## Installeren
1. HACS → ⋮ → **Custom repositories** → URL van deze repository, type **Integration** → Add.
2. Zoek **Pool aFRR** in HACS → **Download** → herstart Home Assistant.
3. Instellingen → Apparaten & diensten → **Integratie toevoegen** → **Pool aFRR**.
4. Vul in: het pooladres, Balans e-mail + wachtwoord, je naam (zoals de beheerder je login aanmaakte) en de poolcode.

## Wat je krijgt (apparaat "Pool aFRR")
- **Pool** – export / import / beide / geen (van de anderen); namen als attribuut
- **Eigen aFRR** – je eigen status zoals gedeeld
- **Verbinding** – status van de poolverbinding (+ Balans-status als attribuut)
- per deelnemer een sensor met diens richting

## SOC (automatisch uit het BE-dashboard)
De integratie leest je accu-SOC uit je eigen Balans Energie-dashboard, met terugwerkende kracht (~25 uur). Per kwartier deelt hij de SOC bij de start en aan het eind, zodat iedereen ziet bij welke SOC een aFRR-actie liep. Anderen zien dat als attributen `soc`, `soc_kwartieren` (start) en `soc_kwartier_eind` op jouw ledensensor; de tijdlijnkaart toont in de tooltip bij welke SOC een aFRR-blok begon (bijv. `gestart 12:15 bij SOC 62% · dit kwartier 55→48%`).

Je hoeft niets in te stellen. Via **Configureren** kun je optioneel een reserve-SOC-sensor kiezen; die wordt alleen gebruikt als het dashboard 20 minuten geen SOC geeft.

## Hoeveel en wanneer (uit het BE-dashboard)
Een aFRR-vlag zegt alleen dát er in een kwartier aFRR was, niet hoeveel. Daarom deelt elke deelnemer per aFRR-kwartier ook:
- `energie_kwartieren`: netto export en import in kWh volgens het BE-dashboard (`[[start, export_kWh, import_kWh], ...]`). Het lopende en vorige kwartier worden elke minuut op 10-secondenresolutie bijgewerkt; oudere kwartieren komen met terugwerkende kracht mee (grover, tot ~25 uur).
- `vlag_start`: wanneer in het kwartier de export- of importvlag begon (`[[start, seconden_tot_export, seconden_tot_import], ...]`). Dit wordt live bijgehouden en is dus niet met terugwerkende kracht beschikbaar.

De tooltip toont dat als bijvoorbeeld `09:00–09:15 · export · export vanaf 09:00 · net export 0,20 kWh`. Zo zie je het verschil tussen een piepje en echte aFRR.

Netto betekent: wat er aan de meter het net op of af ging, inclusief huisverbruik en eventuele eigen regelacties.

## Geschiedenis (met terugwerkende kracht)
Elke deelnemer haalt bij Balans zijn eigen aFRR-kwartieren van de afgelopen ~26 uur op en deelt die met de pool. Je ziet dus meteen de activaties van iedereen, ook van vóór je meedeed (tot 48 uur bewaard zolang de anderen verbonden zijn).

Attributen op elke ledensensor en op **Eigen aFRR**:
- `kwartieren` – `[[start (unix s), "e"/"i"/"ie"/""], ...]`
- `export_24u`, `import_24u`, `afrr_24u` – aantal kwartieren in de laatste 24 uur

### Kaart: laatste 24 uur per kwartier
Vereist [button-card](https://github.com/custom-cards/button-card) (HACS). Per lid een balk van 96 kwartieren met tijdas; wijs (of tik) een kwartier aan voor tijd, richting en bij welke SOC het aFRR-blok begon.

Dashboard bewerken → kaart toevoegen → **Handmatig** → plak:

```yaml
type: custom:button-card
triggers_update: all
show_name: false
show_icon: false
show_state: false
tap_action: {action: none}
hold_action: {action: none}
styles:
  card: [{padding: 0}, {border-radius: 16px}, {cursor: default}]
  grid: [{grid-template-areas: '"body"'}, {grid-template-columns: 'minmax(0,1fr)'}]
  custom_fields:
    body: [{white-space: normal}, {overflow: visible}]
extra_styles: |
  .tl { position:relative; padding:15px 18px; text-align:left; }
  .tl-head { display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:6px; margin-bottom:10px; }
  .tl-title { font-size:18px; font-weight:650; color:var(--primary-text-color); }
  .tl-leg { font-size:12px; color:var(--secondary-text-color); display:flex; align-items:center; gap:6px; }
  .tl-leg i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-left:6px; }
  .tl-row { display:grid; grid-template-columns:110px minmax(0,1fr); column-gap:12px; align-items:center; margin:8px 0; }
  .tl-name { font-size:13px; font-weight:650; color:var(--primary-text-color); display:flex; flex-direction:column; }
  .tl-name small { font-weight:400; font-size:11px; color:var(--secondary-text-color); }
  .tl-name b.te { color:#3aa67a; } .tl-name b.ti { color:#e6814c; }
  .tl-bar { display:grid; grid-template-columns:repeat(96, minmax(0,1fr)); gap:1px; height:20px; pointer-events:auto; cursor:crosshair; touch-action:pan-y; }
  .tl-bar span { background:var(--divider-color); border-radius:1px; }
  .tl-bar span:nth-child(4n+1) { margin-left:1px; }
  .tl-bar span.hov { outline:2px solid var(--primary-text-color); position:relative; z-index:1; }
  .e { background:#3aa67a !important; } .i { background:#e6814c !important; } .b { background:#d9b23b !important; } .a { background:#7b8794 !important; }
  .tl-none { font-size:12px; color:var(--secondary-text-color); }
  .tl-ticks { position:relative; height:14px; font-size:10px; color:var(--secondary-text-color); }
  .tl-ticks span { position:absolute; transform:translateX(-50%); font-variant-numeric:tabular-nums; }
  .tl-tip { display:none; position:absolute; transform:translateX(-50%); z-index:5; pointer-events:none; white-space:nowrap;
    background:var(--card-background-color); color:var(--primary-text-color); border:1px solid var(--divider-color);
    box-shadow:0 2px 8px rgba(0,0,0,.18); border-radius:8px; padding:4px 8px; font-size:12px; font-variant-numeric:tabular-nums; }
  @media (max-width:600px) { .tl-row { grid-template-columns:minmax(0,1fr); } .tl-axis > div:first-child { display:none; } }
custom_fields:
  body: |
    [[[
    const Q = 900, N = 96;
    const end = Math.floor(Date.now() / 1000 / Q) * Q + Q;
    const start = end - N * Q;
    const tf = new Intl.DateTimeFormat('nl-NL', {timeZone: 'Europe/Amsterdam', hour: '2-digit', minute: '2-digit'});
    const t = s => tf.format(s * 1000);
    const kwh = v => v.toLocaleString('nl-NL', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' kWh';
    const extra = c => (c.f ? [Number.isFinite(c.f[1]) ? 'export vanaf ' + t(c.q + c.f[1]) : '', Number.isFinite(c.f[2]) ? 'import vanaf ' + t(c.q + c.f[2]) : ''].filter(x => x).map(x => ' · ' + x).join('') : '')
      + (c.e ? ' · net ' + ([Number.isFinite(c.e[1]) && c.e[1] >= 0.005 ? 'export ' + kwh(c.e[1]) : '', Number.isFinite(c.e[2]) && c.e[2] >= 0.005 ? 'import ' + kwh(c.e[2]) : ''].filter(x => x).join(' / ') || '0,00 kWh') : '');
    const label = d => d === 'ie' ? 'export + import' : d === 'e' ? 'export' : d === 'i' ? 'import' : 'aFRR';
    const cls = d => d === 'ie' ? 'b' : d === 'e' ? 'e' : d === 'i' ? 'i' : 'a';
    const rows = Object.values(states)
      .filter(s => s.entity_id.startsWith('sensor.pool_afrr_') && Array.isArray(s.attributes.kwartieren))
      .map(s => {
        const map = new Map(s.attributes.kwartieren.map(r => [r[0], r[1]]));
        const socs = new Map((s.attributes.soc_kwartieren || []).map(r => [r[0], r[1]]));
        const ends = new Map((s.attributes.soc_kwartier_eind || []).map(r => [r[0], r[1]]));
        const en = new Map((s.attributes.energie_kwartieren || []).map(r => [r[0], r]));
        const fs = new Map((s.attributes.vlag_start || []).map(r => [r[0], r]));
        const cells = Array.from({length: N}, (_, k) => { const q = start + k * Q; return {q, d: map.has(q) ? map.get(q) : null, soc: socs.get(q), soce: ends.get(q), e: en.get(q), f: fs.get(q)}; });
        let run = null;  // aaneengesloten aFRR-blok: SOC bij de start onthouden
        for (const c of cells) { if (c.d === null) { run = null; continue; } if (!run || run.d !== c.d) run = {from: c.q, d: c.d, soc: c.soc}; c.b = run; }
        const own = s.entity_id === 'sensor.pool_afrr_eigen_afrr';
        return {name: own ? 'Jij' : (s.attributes.friendly_name || '').replace(/^Pool aFRR\s*/, ''), own, now: s.state, soc: s.attributes.soc, cells};
      })
      .sort((a, b) => (b.own - a.own) || a.name.localeCompare(b.name));
    const tip = ev => {
      const root = ev.currentTarget.closest('.tl'); const box = root && root.querySelector('.tl-tip'); if (!box) return;
      const cell = ev.type === 'pointerleave' ? null : ev.target.closest('span[data-tip]');
      root.querySelectorAll('.tl-bar span.hov').forEach(x => x.classList.remove('hov'));
      if (!cell) { this._poolTip = null; box.style.display = 'none'; return; }
      cell.classList.add('hov');
      const name = cell.parentElement.dataset.name, text = cell.dataset.tip;
      box.innerHTML = '<b>' + name + '</b> · ' + text;
      const rr = root.getBoundingClientRect(), cr = cell.getBoundingClientRect();
      box.style.display = 'block';
      const x = Math.max(box.offsetWidth / 2 + 4, Math.min(rr.width - box.offsetWidth / 2 - 4, cr.left + cr.width / 2 - rr.left));
      const y = cr.top - rr.top - box.offsetHeight - 6;
      box.style.left = x + 'px'; box.style.top = y + 'px';
      this._poolTip = {name, text, k: Array.prototype.indexOf.call(cell.parentElement.children, cell), x, y};
    };
    const st = this._poolTip;
    const ticks = Array.from({length: N}, (_, k) => ({k, q: start + k * Q})).filter(x => x.q % 10800 === 0);
    return html`
    <div class="tl">
      <div class="tl-tip" style="display:${st ? 'block' : 'none'};left:${st ? st.x : 0}px;top:${st ? st.y : 0}px">${st ? html`<b>${st.name}</b> · ${st.text}` : ''}</div>
      <div class="tl-head"><span class="tl-title">Pool-aFRR · laatste 24 uur</span>
        <span class="tl-leg"><i class="e"></i>export <i class="i"></i>import <i class="b"></i>beide</span></div>
      ${rows.length ? rows.map(r => html`
        <div class="tl-row">
          <div class="tl-name">${r.name}<small>${[Number.isFinite(r.soc) ? 'SOC ' + r.soc + '%' : '', r.now !== 'geen' ? html`<b class="${r.now === 'export' ? 'te' : 'ti'}">nu ${r.now}</b>` : ''].filter(v => v).map((v, i) => i ? html` · ${v}` : v)}</small></div>
          <div class="tl-bar" data-name="${r.name}" @pointermove=${tip} @pointerdown=${tip} @pointerleave=${tip}>${r.cells.map((c, k) => html`<span class="${c.d === null ? '' : cls(c.d)}${st && st.name === r.name && st.k === k ? ' hov' : ''}" data-tip="${t(c.q)}–${t(c.q + Q)} · ${c.d === null ? 'geen aFRR' : label(c.d) + extra(c)}${c.b ? (Number.isFinite(c.b.soc) ? ' · gestart ' + t(c.b.from) + ' bij SOC ' + c.b.soc + '%' : '') + (Number.isFinite(c.soc) ? ' · dit kwartier ' + c.soc + (Number.isFinite(c.soce) && c.soce !== c.soc ? '→' + c.soce : '') + '%' : '') : (Number.isFinite(c.soc) ? ' · SOC ' + c.soc + '%' : '')}"></span>`)}</div>
        </div>`) : html`<div class="tl-none">Nog geen geschiedenis.</div>`}
      <div class="tl-row tl-axis"><div></div><div class="tl-ticks">${ticks.map(x => html`<span style="left:${x.k / N * 100}%">${t(x.q)}</span>`)}</div></div>
    </div>`;
    ]]]
```

### Eenvoudige kaart zonder extra’s (per uur)
Markdown-kaart (🟩 export · 🟧 import · 🟨 beide · 🟦 aFRR zonder richting · ⬜ niets), oudste uur links:

```yaml
type: markdown
title: Pool-aFRR · laatste 24 uur
content: >-
  {% set nu = (now().timestamp() // 3600 * 3600) | int %}
  {% for s in states.sensor | selectattr('attributes.kwartieren', 'defined') | selectattr('entity_id', 'search', '^sensor\\.pool_afrr_') | sort(attribute='name') %}
  **{{ s.name | replace('Pool aFRR ', '') }}**{{ ' · SOC ' ~ s.attributes.soc ~ '%' if s.attributes.soc is number else '' }}<br>
  {%- for i in range(23, -1, -1) %}{% set h0 = nu - i * 3600 %}{% set q = s.attributes.kwartieren | selectattr('0', 'ge', h0) | selectattr('0', 'lt', h0 + 3600) | map(attribute='1') | join %}{{ '🟨' if 'e' in q and 'i' in q else '🟩' if 'e' in q else '🟧' if 'i' in q else '🟦' if s.attributes.kwartieren | selectattr('0', 'ge', h0) | selectattr('0', 'lt', h0 + 3600) | list | count else '⬜' }}{% endfor %}

  {% endfor %}
```
