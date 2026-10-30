# CAPA Closure Monitor

A static, offline HTML dashboard for tracking CAPA (Corrective and Preventive Action) closure status across stores — KPIs, date presets (Daily / Weekly / Monthly / Custom), store/cluster/city filters, Open/Closed status filter, store table with search/sort/CSV export, and per-store report modals.

## Use it

Open `index.html` in any browser — no server needed.

## Refresh the data

Place new CSV exports at the paths referenced in `build_data.py`, then:

```
python build_data.py
```

This regenerates `data.js` from:

- `../Capa tasks/Pod Audit Tool - CAPA Tasks (2).csv` — CAPA task export
- `../Audit response/Pod Audit Tool - Audit Responses (2).csv` — audit responses export
- `../../Audit tracking - CAPA closures/Audits/` — all Audits exports (merged, deduped 1 per store+date)
- `../Cluster details/Daily Review-redline - WTD_39.csv` — pod → cluster mapping

Dedup rules (same as the main AUDIT tracker): one audit per store+date (latest
submission wins), CAPA rows tied to superseded audits dropped, one task per
auditId+questionNo (latest createdAt wins), and the kept audit's date is used
for every CAPA row. KPI cards count only audits with findings that got CAPA.
