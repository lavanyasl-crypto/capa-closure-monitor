import csv, json, os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(ROOT, "..")

# Source exports (freshest snapshots). If filenames get auto-suffixed by the
# browser (e.g. " (1)"), drop the newest file here under these exact names.
CAPA_SRC = os.path.join(BASE, "Capa tasks", "Pod Audit Tool - CAPA Tasks (2).csv")
RESP_SRC = os.path.join(BASE, "Audit response", "Pod Audit Tool - Audit Responses (2).csv")
AUDITS_SRC = os.path.join(BASE, "..", "Audit tracking - CAPA closures", "Audits")
CLUSTER_SRC = os.path.join(BASE, "Cluster details", "Daily Review-redline - WTD_39.csv")
OUT = os.path.join(ROOT, "data.js")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def merge_audits_csv(audits_dir):
    """Merge every Audits export (recursing into backup folders), byte-dedup rows.
    Oldest file first (by mtime) so the newest snapshot wins ties downstream."""
    rows, seen = [], set()
    files = []
    for dirpath, _dirnames, filenames in os.walk(audits_dir):
        for fn in filenames:
            if fn.lower().endswith(".csv"):
                p = os.path.join(dirpath, fn)
                files.append((os.path.getmtime(p), p))
    files.sort()
    for _mt, p in files:
        for r in read_csv(p):
            key = "\x00".join(r.values())
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
    return rows


def date_only(ts):
    if not ts:
        return ""
    # Some exports (e.g. the 2026-10-22 Audits slice) use US slash format
    # (M/D/YYYY) instead of ISO; normalize so date-range filters parse it.
    ts = ts.strip()
    if "/" in ts:
        parts = ts.split()[0].split("/")
        if len(parts) == 3 and len(parts[2]) == 4:
            mo, d, y = parts
            return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
    return ts[:10]


def parse_dt(ts):
    try:
        return datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return None


cluster_by_pod = {}
for r in read_csv(CLUSTER_SRC):
    cluster_by_pod[r["Pod ID"]] = r["Cluster"]

CITY_CLUSTER = {
    "Hyderabad": "AP TG", "Kochi": "KA KL", "Thiruvananthapuram": "KA KL",
    "Thrissur": "KA KL", "Bangalore": "KA KL", "Mysore": "KA KL",
    "Pune": "WEST", "Mumbai": "WEST", "Bhopal": "WEST",
    "Chennai": "TN", "Kolkata": "EAST", "Delhi": "NORTH", "Bhathinda": "NORTH",
}


def cluster_for(store_id, city):
    c = cluster_by_pod.get(store_id)
    if c:
        return c
    return CITY_CLUSTER.get((city or "").strip(), "Unknown")


# ---------------- Audits: one per store+date (latest submission wins) ----------------
# Same rule as the main dashboard (github-dashboard/scripts/build-data.js):
# multiple submissions for the same store+day — resubmissions by the same
# auditor or a second auditor — count as ONE visit; keep the latest startedAt.
audits_rows = merge_audits_csv(AUDITS_SRC)
audit_groups = {}
for r in audits_rows:
    sid = r.get("storeId", "")
    d = date_only(r.get("auditDate", ""))
    if not sid or not d:
        continue
    audit_groups.setdefault(sid + "|" + d, []).append(r)

kept_audits = {}  # auditId -> audit record
for key, group in audit_groups.items():
    best, best_ms = group[0], -1
    for r in group:
        t = parse_dt(r.get("startedAt") or r.get("createdAt"))
        ms = t.timestamp() if t else 0
        if ms >= best_ms:
            best_ms, best = ms, r
    sid = best.get("storeId", "")
    city = best.get("storeLocation", "") or "Unknown"
    kept_audits[best.get("id", "")] = {
        "id": best.get("id", ""),
        "d": date_only(best.get("auditDate", "")),
        "s": sid,
        "c": city,
        "cl2": cluster_for(sid, city),
        "n": int(best.get("nonCompliantCount") or 0),
        "pc": int(best.get("partialCount") or 0),
        "na": int(best.get("naCount") or 0),
        "pct": round(float(best.get("scorePercent") or 0)),
        "startedAt": best.get("startedAt") or "",
    }

# ---------------- Recover audits missing from Audits.csv via Audit Responses ----------------
# The Audits export is sometimes a partial slice. For auditIds present only in
# responses (and not resubmissions of an existing raw audit), synthesize one
# audit per store+day, earliest submission.
resp_rows = read_csv(RESP_SRC)
raw_audit_ids = {r.get("id", "") for r in audits_rows}
resp_agg = {}
for r in resp_rows:
    aid = r.get("auditId", "")
    if not aid or aid in kept_audits or aid in raw_audit_ids:
        continue
    v = resp_agg.setdefault(aid, {
        "sid": r.get("storeId", ""), "city": r.get("storeLocation", ""),
        "firstCreated": r.get("createdAt", ""), "nc": 0, "pc": 0, "na": 0, "sc": 0, "mx": 0,
    })
    cr = r.get("createdAt", "")
    if cr and cr < v["firstCreated"]:
        v["firstCreated"] = cr
    resp = r.get("response", "")
    if resp == "Non Compliance":
        v["nc"] += 1; v["sc"] += 0; v["mx"] += 2
    elif resp == "Partially Complied":
        v["pc"] += 1; v["sc"] += 1; v["mx"] += 2
    elif resp == "Compliance":
        v["sc"] += 2; v["mx"] += 2
    elif resp == "NA":
        v["na"] += 1

recovered_by_key = {}
for aid, v in resp_agg.items():
    if not v["sid"]:
        continue
    d = date_only(v["firstCreated"])
    if not d:
        continue
    key = v["sid"] + "|" + d
    if key in audit_groups:  # a kept real audit already covers this store+day
        continue
    prev = recovered_by_key.get(key)
    if prev is None or v["firstCreated"] < prev["firstCreated"]:
        recovered_by_key[key] = {"aid": aid, **v}

for rec in recovered_by_key.values():
    kept_audits[rec["aid"]] = {
        "id": rec["aid"], "d": date_only(rec["firstCreated"]), "s": rec["sid"],
        "c": rec["city"] or "Unknown", "cl2": cluster_for(rec["sid"], rec["city"]),
        "n": rec["nc"], "pc": rec["pc"], "na": rec["na"],
        "pct": round(100 * rec["sc"] / rec["mx"]) if rec["mx"] else 0,
        "startedAt": rec["firstCreated"],
    }

kept_audit_ids = set(kept_audits)

# ---------------- CAPA tasks: keep rows tied to kept audits, dedupe auditId+questionNo ----------------
name_by_store = {}
for r in resp_rows:
    if r.get("storeId") and r.get("storeName"):
        name_by_store.setdefault(r["storeId"], r["storeName"])

capa_rows = read_csv(CAPA_SRC)
best_by_key = {}  # auditId|questionNo -> row (latest createdAt wins)
skipped_audit = skipped_dupe = 0
for r in capa_rows:
    aid = r.get("auditId", "")
    if aid not in kept_audit_ids:
        skipped_audit += 1
        continue
    key = aid + "|" + r.get("questionNo", "")
    prev = best_by_key.get(key)
    if prev is None or (r.get("createdAt") or "") >= (prev.get("createdAt") or ""):
        best_by_key[key] = r
    else:
        skipped_dupe += 1

rows_out = []
for r in best_by_key.values():
    photos = " ".join(
        u.split("id=")[1].split("&")[0]
        for u in (r.get("photoUrls") or "").split(",")
        if "id=" in u
    )
    cphotos = " ".join(
        u.split("id=")[1].split("&")[0]
        for u in (r.get("closurePhotoUrls") or "").split(",")
        if "id=" in u
    )
    sid = r.get("storeId", "")
    sname = r.get("storeName", "") or name_by_store.get(sid, "")
    rows_out.append({
        "i": r.get("capaId", ""),
        "ai": r.get("auditId", ""),
        "s": sid,
        "n": sname,
        "c": r.get("storeLocation", "") or "Unknown",
        "cl2": cluster_for(r.get("storeId", ""), r.get("storeLocation", "")),
        "g": r.get("category", "") or "Unknown",
        "k": r.get("checkpoint", "") or "Unknown",
        "r": r.get("response", ""),
        "st": r.get("status", ""),
        # auditDate from the kept audit (canonical) — the CAPA sheet leaves it
        # blank on ~55% of rows and has IST/UTC day shifts on others.
        "ad": kept_audits[r.get("auditId", "")]["d"],
        "cr": (r.get("createdAt") or "")[:10],
        "du": (r.get("dueAt") or "")[:10],
        "cl": (r.get("closedAt") or "")[:10],
        "m": r.get("remark", ""),
        "cm": r.get("closureRemark", ""),
        "p": photos,
        "cp": cphotos,
        "cb": r.get("closedBy", ""),
    })

status_counts = {}
for t in rows_out:
    status_counts[t["st"]] = status_counts.get(t["st"], 0) + 1

audits_out = [
    {k: a[k] for k in ("id", "d", "s", "c", "cl2", "n", "pc", "na", "pct")}
    for a in kept_audits.values() if a["s"]
]

with open(OUT, "w", encoding="utf-8") as f:
    f.write("window.CAPA_DATA=")
    json.dump(rows_out, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";window.AUDIT_DATA=")
    json.dump(audits_out, f, ensure_ascii=False, separators=(",", ":"))

print(f"wrote {OUT}: {len(rows_out)} capa rows "
      f"({skipped_audit} dropped: superseded audits, {skipped_dupe} dropped: duplicate auditId+questionNo), "
      f"{len(audits_out)} deduped audits (1 per store+date), statuses {status_counts}, "
      f"{os.path.getsize(OUT)/1e6:.1f} MB")
