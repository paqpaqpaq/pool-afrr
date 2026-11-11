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
