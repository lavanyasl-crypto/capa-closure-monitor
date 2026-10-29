import csv, json, io, os

SRC = os.path.join(os.path.dirname(__file__), "..", "Capa tasks", "Pod Audit Tool - CAPA Tasks (2).csv")
CLUSTER_SRC = os.path.join(os.path.dirname(__file__), "..", "Cluster details", "Daily Review-redline - WTD_39.csv")
OUT = os.path.join(os.path.dirname(__file__), "data.js")

with open(CLUSTER_SRC, encoding="utf-8-sig", newline="") as f:
    cluster_by_pod = {r["Pod ID"]: r["Cluster"] for r in csv.DictReader(f)}

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

RESP_SRC = os.path.join(os.path.dirname(__file__), "..", "Audit response", "Pod Audit Tool - Audit Responses (2).csv")

# The CAPA export leaves storeName blank on most rows; recover names from
# the responses export (and from the named CAPA rows) keyed by storeId.
name_by_store = {}
with open(RESP_SRC, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if r.get("storeId") and r.get("storeName"):
            name_by_store.setdefault(r["storeId"], r["storeName"])

rows_out = []
with open(SRC, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
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
            "ad": (r.get("auditDate") or "")[:10],
            "cr": (r.get("createdAt") or "")[:10],
            "du": (r.get("dueAt") or "")[:10],
            "cl": (r.get("closedAt") or "")[:10],
            "m": r.get("remark", ""),
            "cm": r.get("closureRemark", ""),
            "p": photos,
            "cp": cphotos,
            "cb": r.get("closedBy", ""),
        })
        if sid and sname:
            name_by_store.setdefault(sid, sname)

# ---- per-audit rollup from the responses export ----
# One record per auditId: date, store, city, cluster, nc/pc counts, score %.
audit_acc = {}
with open(RESP_SRC, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        a = audit_acc.setdefault(r["auditId"], {
            "sid": "", "city": "", "date": (r.get("createdAt") or "")[:10], "nc": 0, "pc": 0, "na": 0, "sc": 0, "mx": 0,
        })
        if not a["sid"] and r.get("storeId"):
            a["sid"] = r["storeId"]
        if not a["city"] and r.get("storeLocation"):
            a["city"] = r["storeLocation"]
        # Export uses: "Compliance", "Non Compliance", "Partially Complied", "NA"
        resp = r.get("response", "")
        if resp == "Non Compliance":
            a["nc"] += 1; a["sc"] += 0; a["mx"] += 2
        elif resp == "Partially Complied":
            a["pc"] += 1; a["sc"] += 1; a["mx"] += 2
        elif resp == "Compliance":
            a["sc"] += 2; a["mx"] += 2
        elif resp == "NA":
            a["na"] += 1

# store name fallback (only needed if responses export lacked it)
audits_out = []
for aid, a in audit_acc.items():
    if not a["sid"]:
        continue
    audits_out.append({
        "id": aid, "d": a["date"], "s": a["sid"], "c": a["city"] or "Unknown",
        "cl2": cluster_for(a["sid"], a["city"]),
        "n": a["nc"], "pc": a["pc"], "na": a["na"],
        "pct": round(100 * a["sc"] / a["mx"]) if a["mx"] else 0,
    })
audits_out = [a for a in audits_out if a["s"]]

with open(OUT, "w", encoding="utf-8") as f:
    f.write("window.CAPA_DATA=")
    json.dump(rows_out, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";window.AUDIT_DATA=")
    json.dump(audits_out, f, ensure_ascii=False, separators=(",", ":"))

print(f"wrote {OUT}: {len(rows_out)} capa rows, {len(audits_out)} audits, {os.path.getsize(OUT)/1e6:.1f} MB")
