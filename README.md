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

## Geschiedenis (met terugwerkende kracht)
Elke deelnemer haalt bij Balans zijn eigen aFRR-kwartieren van de afgelopen ~26 uur op en deelt die met de pool. Je ziet dus meteen de activaties van iedereen, ook van vóór je meedeed (tot 48 uur bewaard zolang de anderen verbonden zijn).

Attributen op elke ledensensor en op **Eigen aFRR**:
- `kwartieren` – `[[start (unix s), "e"/"i"/"ie"/""], ...]`
- `export_24u`, `import_24u`, `afrr_24u` – aantal kwartieren in de laatste 24 uur

### Kaart: laatste 24 uur per uur
Markdown-kaart (🟩 export · 🟧 import · 🟨 beide · 🟦 aFRR zonder richting · ⬜ niets), oudste uur links:

```yaml
type: markdown
title: Pool-aFRR · laatste 24 uur
content: >-
  {% set nu = (now().timestamp() // 3600 * 3600) | int %}
  {% for s in states.sensor | selectattr('attributes.kwartieren', 'defined') | sort(attribute='name') %}
  **{{ s.name | replace('Pool aFRR ', '') }}** · {{ s.attributes.afrr_24u }} kw<br>
  {%- for i in range(23, -1, -1) %}{% set h0 = nu - i * 3600 %}{% set q = s.attributes.kwartieren | selectattr('0', 'ge', h0) | selectattr('0', 'lt', h0 + 3600) | map(attribute='1') | join %}{{ '🟨' if 'e' in q and 'i' in q else '🟩' if 'e' in q else '🟧' if 'i' in q else '🟦' if s.attributes.kwartieren | selectattr('0', 'ge', h0) | selectattr('0', 'lt', h0 + 3600) | list | count else '⬜' }}{% endfor %}

  {% endfor %}
```
