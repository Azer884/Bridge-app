# How prices are worked out

Estimates are deterministic: the same job gives the same price every time, and no model is involved in any number.
The rates come from real Malaysian market data supplied by the team (`config/painting_prices_malaysia_2026.csv`,
the same data as `giser_painting_prices_malaysia_2026.xlsx`). The rate card sits in `config/business_config.example.json`
under `pricing.benchmark`, so a business can replace any value with its own.

## Rates used (RM per sq ft, converted from m2 with 1 m2 = 10.7639 sq ft)

| Item | Rate | Source in the data |
| ---- | ---- | ------------------ |
| Interior walls, paint and labour, two coats | 1.30 | PNT004, component of PNT001 |
| Interior walls, filling and sanding | 0.65 | PNT003, component of PNT001 |
| Interior walls, whole job (median) | 1.95, range 1.70 to 2.30 | PNT001, SRC001: 10 contractor quotes, 1,205 sq ft, Klang Valley, Sept to Oct 2026 |
| Ceiling, all-in | 1.20 | PNT009, SRC003 marketplace listing, scope not stated (medium-low confidence) |

The data notes that the RM1.30 and RM0.65 parts are already inside the RM1.95 median, so they are never added to it
again. A wall in good condition needs no filling and is priced at RM1.30; the study's scope (minor filling and sanding)
is RM1.95. The owner sees the typical market range (RM1.70 to RM2.30 per sq ft scaled to the job) next to the estimate.

## What is not in the data (marked "assumption" on every quote where it applies)

- Moderate surface condition: preparation at twice the minor rate.
- Economy and premium paint: 0.95 and 1.10 times the paint and labour rate. The data is for standard paint (Nippon Vinilex 5000).
- Height above 3 m: labour 1.2 times, for access.
- Areas outside Kuala Lumpur and Selangor: the Klang Valley rate is used and the quote says the owner must confirm it,
  because the data has no verified rate for other states.
- Markup is 0 in the example card because market rates are what customers already pay contractors.

## Not priced (the data says "quote required")

Doors and frames, gates, railings, timber varnishing, roofs, epoxy floors, feature or textured walls, anti-mould coatings,
waterproofing, crack repair, skim coats. The assistant passes these to the owner instead of guessing a price.

## Limits

The data is a small Klang Valley sample before SST. A real deployment replaces the rates with the business's own quotes
and checks other states against CIDB's N3C portal (SRC004 to SRC006 in the sheet).
