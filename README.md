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
- `../Cluster details/Daily Review-redline - WTD_39.csv` — pod → cluster mapping
