"""Journal entry testing: read a general ledger extract, group lines into journals,
and score every journal with rules and simple statistics.

All scoring is done by code, so the same file always gives the same scores and
every point can be traced to a rule. AI is only used later, to explain the
highest-risk journals in plain words."""
import csv
import io
import random
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

MAX_LINES = 300_000

FIELDS = {  # field -> header words that identify it
    "journal_id": ["journal id", "journalid", "journal no", "journal number", "je number", "je id", "je no", "document number",
                   "document no", "doc no", "docno", "voucher", "entry id", "entry no", "journal", "je"],
    "date": ["effective date", "posting date", "gl date", "document date", "entry date", "date"],
    "posted_at": ["posted at", "created at", "entered at", "created on", "entered on", "entry timestamp", "timestamp",
                  "posted on", "created date", "time"],
    "account": ["account number", "account no", "account code", "gl account", "account", "acct"],
    "account_name": ["account name", "account description", "account desc", "gl name"],
    "description": ["line description", "journal description", "description", "narration", "memo", "text", "desc"],
    "debit": ["debit amount", "debit", "dr"],
    "credit": ["credit amount", "credit", "cr"],
    "amount": ["amount", "value", "net amount", "local amount"],
    "user": ["created by", "entered by", "posted by", "preparer", "user id", "userid", "user"],
    "approver": ["approved by", "approver", "authorised by", "authorized by", "reviewed by"],
    "source": ["source", "journal type", "entry type", "origin", "module", "type"],
}

RULES = {
    "R01": ("Posted on a weekend", 10),
    "R02": ("Posted outside working hours", 8),
    "R03": ("Round amount", 8),
    "R04": ("Just below an approval limit", 12),
    "R05": ("Large entry at period end", 10),
    "R06": ("Manual entry", 6),
    "R07": ("Missing or vague description", 8),
    "R08": ("Sensitive words in description", 8),
    "R09": ("Not independently approved", 12),
    "R10": ("User who rarely posts", 8),
    "R11": ("Unusual account combination", 10),
    "R12": ("Amount far from normal for the account", 15),
    "R13": ("Possible duplicate", 10),
    "R14": ("Debits and credits do not balance", 15),
    "R15": ("Recorded long after its date", 8),
}
LIMITS = [5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000]
SENSITIVE = ["plug", "adjust", "reclass", "per cfo", "per ceo", "per management", "correction", "reverse", "reversal",
             "true-up", "true up", "write off", "write-off", "error", "balancing", "as instructed", "top side", "topside"]
VAGUE = {"", "na", "n/a", "none", "misc", "miscellaneous", "entry", "journal", "je", "test", "adj", "various", "-", "."}
DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%m-%d-%Y", "%d-%b-%Y", "%d %b %Y",
                "%Y%m%d", "%m/%d/%y", "%d.%m.%Y"]
TIME_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
                "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p"]


class LedgerError(ValueError):
    pass


def band(score: int) -> str:
    return "high" if score >= 40 else "medium" if score >= 20 else "low"


# ------------------------------------------------------------------ reading
def read_rows(raw: bytes, filename: str) -> tuple[list[str], list[list]]:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True).active
        rows = [list(r) for r in ws.iter_rows(values_only=True) if any(v not in (None, "") for v in r)]
    else:
        text = raw.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = [r for r in csv.reader(io.StringIO(text), dialect) if any((v or "").strip() for v in r)]
    if len(rows) < 2:
        raise LedgerError("The file needs a header row and at least one data row")
    if len(rows) - 1 > MAX_LINES:
        raise LedgerError(f"The file has more than {MAX_LINES:,} lines. Split it by period and upload in parts.")
    return [str(h or "").strip() for h in rows[0]], rows[1:]


def map_columns(header: list[str]) -> dict:
    """Match file columns to ledger fields by header name. Returns field -> column index."""
    norm = [re.sub(r"[^a-z0-9]+", " ", h.lower()).strip() for h in header]
    mapping, used = {}, set()
    for exact in (True, False):
        for field, words in FIELDS.items():
            if field in mapping:
                continue
            for w in words:
                hit = next((i for i, h in enumerate(norm) if i not in used and (h == w if exact else re.search(rf"\b{re.escape(w)}\b", h))), None)
                if hit is not None:
                    mapping[field] = hit
                    used.add(hit)
                    break
    missing = [f for f in ("journal_id", "date", "account") if f not in mapping]
    if "amount" not in mapping and not ("debit" in mapping and "credit" in mapping):
        missing.append("amount (or debit and credit)")
    if missing:
        raise LedgerError("Could not find these columns: " + ", ".join(missing) + ". Found headers: " + ", ".join(header[:20]))
    return mapping


def _num(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("$", "").replace(" ", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        return -float(s) if neg else float(s)
    except ValueError:
        return 0.0


def _date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()[:10].strip()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def _time(v) -> datetime | None:
    if isinstance(v, datetime):
        return v
    s = str(v or "").strip()
    for f in TIME_FORMATS:
        try:
            return datetime.strptime(s[:22].strip(), f)
        except ValueError:
            pass
    d = _date(s)
    return datetime(d.year, d.month, d.day) if d else None


def build_journals(header, rows, mapping) -> tuple[list[dict], dict]:
    def get(r, f):
        i = mapping.get(f)
        return r[i] if i is not None and i < len(r) else None

    groups, bad_dates = defaultdict(list), 0
    for r in rows:
        jid = str(get(r, "journal_id") or "").strip()
        if not jid:
            continue
        if "amount" in mapping:
            amt = _num(get(r, "amount"))
            debit, credit = (amt, 0.0) if amt >= 0 else (0.0, -amt)
        else:
            debit, credit = abs(_num(get(r, "debit"))), abs(_num(get(r, "credit")))
        groups[jid].append({
            "account": str(get(r, "account") or "").strip(), "account_name": str(get(r, "account_name") or "").strip(),
            "description": str(get(r, "description") or "").strip(), "debit": round(debit, 2), "credit": round(credit, 2),
            "_date": _date(get(r, "date")), "_posted": _time(get(r, "posted_at")),
            "_user": str(get(r, "user") or "").strip(), "_approver": str(get(r, "approver") or "").strip(),
            "_source": str(get(r, "source") or "").strip(),
        })
    journals = []
    for jid, lines in groups.items():
        first = lines[0]
        d = next((l["_date"] for l in lines if l["_date"]), None)
        if d is None:
            bad_dates += 1
        posted = next((l["_posted"] for l in lines if l["_posted"]), None)
        desc = next((l["description"] for l in lines if l["description"]), "")
        journals.append({
            "ref": jid, "date": d, "posted_at": posted, "user": first["_user"], "approver": first["_approver"],
            "source": first["_source"], "description": desc,
            "debit": round(sum(l["debit"] for l in lines), 2), "credit": round(sum(l["credit"] for l in lines), 2),
            "lines": [{k: v for k, v in l.items() if not k.startswith("_")} for l in lines],
        })
    info = {"lines": sum(len(j["lines"]) for j in journals), "journals": len(journals), "undated": bad_dates,
            "has": {f: f in mapping for f in ("posted_at", "user", "approver", "source", "description")}}
    return journals, info


# ------------------------------------------------------------------ scoring
def score_journals(journals: list[dict], info: dict) -> dict:
    """Adds score, band and hits to each journal. Returns summary statistics."""
    has = info["has"]
    amounts = sorted(j["debit"] for j in journals if j["debit"] > 0)
    p95 = amounts[int(len(amounts) * 0.95)] if amounts else 0
    user_count = Counter(j["user"] for j in journals if j["user"])
    by_account = defaultdict(list)
    pair_count, dup = Counter(), defaultdict(list)
    for j in journals:
        dr = sorted({l["account"] for l in j["lines"] if l["debit"] > 0})
        cr = sorted({l["account"] for l in j["lines"] if l["credit"] > 0})
        j["_pair"] = (tuple(dr[:3]), tuple(cr[:3]))
        pair_count[j["_pair"]] += 1
        dup[(j["date"], j["debit"], j["_pair"])].append(j["ref"])
        for l in j["lines"]:
            by_account[l["account"]].append(l["debit"] or l["credit"])
    acct = {}
    for a, vals in by_account.items():
        if len(vals) >= 8:
            med = statistics.median(vals)
            mad = statistics.median(abs(v - med) for v in vals)
            acct[a] = (med, mad)
    n = len(journals)
    rule_totals = Counter()
    for j in journals:
        hits = []

        def hit(rule, reason):
            hits.append({"rule": rule, "name": RULES[rule][0], "weight": RULES[rule][1], "reason": reason})

        amt, d, when = j["debit"], j["date"], j["posted_at"] or (datetime(j["date"].year, j["date"].month, j["date"].day) if j["date"] else None)
        if when and when.weekday() >= 5:
            hit("R01", f"Posted on {when:%A %d %b %Y}")
        if j["posted_at"] and (j["posted_at"].hour, j["posted_at"].minute) != (0, 0) and (j["posted_at"].hour < 6 or j["posted_at"].hour >= 20):
            hit("R02", f"Posted at {j['posted_at']:%H:%M}")
        if amt >= 1000 and amt % 1000 == 0:
            hit("R03", f"Total is a round {amt:,.0f}")
        lim = next((L for L in LIMITS if L * 0.95 <= amt < L), None)
        if lim:
            hit("R04", f"{amt:,.2f} is just under {lim:,}")
        if d and amt >= p95 > 0:
            nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
            if (nxt - d).days <= 3 or d.day <= 2:
                hit("R05", f"{amt:,.2f} is in the top 5% by value and dated {d:%d %b}, at a period end")
        if has["source"] and re.search(r"manual|spreadsheet|adj|upload|topside", j["source"], re.I):
            hit("R06", f"Source is '{j['source']}'")
        if has["description"]:
            desc = j["description"].lower().strip()
            if desc in VAGUE or len(desc) < 5:
                hit("R07", "No useful description" if not desc else f"Description is only '{j['description']}'")
            word = next((w for w in SENSITIVE if w in desc), None)
            if word:
                hit("R08", f"Description contains '{word}'")
        if has["approver"]:
            if not j["approver"]:
                hit("R09", "No approver recorded")
            elif j["approver"].lower() == j["user"].lower():
                hit("R09", f"Created and approved by the same user ({j['user']})")
        if j["user"] and n >= 50 and user_count[j["user"]] <= 2:
            hit("R10", f"{j['user']} posted only {user_count[j['user']]} journal(s) in this file")
        if n >= 50 and pair_count[j["_pair"]] <= 1 and len(j["lines"]) <= 6 and j["_pair"][0] and j["_pair"][1]:
            hit("R11", f"Debit {', '.join(j['_pair'][0])} against credit {', '.join(j['_pair'][1])} appears only once")
        worst = None
        for l in j["lines"]:
            v = l["debit"] or l["credit"]
            med, mad = acct.get(l["account"], (0, 0))
            if mad > 0:
                z = 0.6745 * (v - med) / mad
                if z > 6 and (worst is None or z > worst[0]):
                    worst = (z, l["account"], v, med)
        if worst:
            hit("R12", f"{worst[2]:,.2f} on account {worst[1]} is far above its usual {worst[3]:,.2f}")
        others = [r for r in dup[(j["date"], j["debit"], j["_pair"])] if r != j["ref"]]
        if others and amt > 0:
            hit("R13", f"Same date, amount and accounts as {', '.join(others[:3])}")
        if abs(j["debit"] - j["credit"]) > 0.01:
            hit("R14", f"Debits {j['debit']:,.2f} and credits {j['credit']:,.2f} differ")
        if d and j["posted_at"] and (j["posted_at"].date() - d).days > 30:
            hit("R15", f"Dated {d:%d %b %Y} but posted {(j['posted_at'].date() - d).days} days later")
        j["hits"] = hits
        j["score"] = min(100, sum(h["weight"] for h in hits))
        j["band"] = band(j["score"])
        for h in hits:
            rule_totals[h["rule"]] += 1
        del j["_pair"]
    bands = Counter(j["band"] for j in journals)
    dates = [j["date"] for j in journals if j["date"]]
    return {
        "lines": info["lines"], "journals": n, "undated": info["undated"], "columns_found": info["has"],
        "total_value": round(sum(j["debit"] for j in journals), 2),
        "bands": {b: bands.get(b, 0) for b in ("high", "medium", "low")},
        "rules": [{"rule": r, "name": RULES[r][0], "weight": RULES[r][1], "count": rule_totals.get(r, 0)} for r in RULES],
        "period": [min(dates).isoformat(), max(dates).isoformat()] if dates else None,
        "skipped_rules": [RULES[r][0] for r, need in (("R02", "posted_at"), ("R06", "source"), ("R07", "description"),
                                                      ("R09", "approver"), ("R10", "user")) if not info["has"][need]],
    }


# -------------------------------------------------------------- sample data
def sample_ledger(year: int = 2026, seed: int = 11) -> bytes:
    """A made-up general ledger with a few planted problems, for trying the module."""
    rng = random.Random(seed)
    users = ["JLEE", "MCHEN", "KBROWN", "PDIAZ", "ASMITH"]
    patterns = [("6100", "Office expenses", "2000", "Accounts payable", 400, 4000, "AP", "Vendor invoice"),
                ("1200", "Accounts receivable", "4000", "Revenue", 2000, 30000, "AR", "Customer invoice"),
                ("1000", "Cash", "1200", "Accounts receivable", 2000, 30000, "Cash", "Customer receipt"),
                ("6200", "Payroll expense", "1000", "Cash", 40000, 60000, "Payroll", "Payroll run"),
                ("6300", "Rent expense", "1000", "Cash", 12000, 12500, "AP", "Monthly rent"),
                ("2000", "Accounts payable", "1000", "Cash", 400, 4000, "Cash", "Vendor payment")]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Journal ID", "Effective Date", "Posted At", "Account", "Account Name", "Description", "Debit", "Credit",
                "Created By", "Approved By", "Source"])
    n = 0

    def add(d, t, dr, drn, cr, crn, amt, desc, user, appr, src):
        nonlocal n
        n += 1
        jid = f"JE{year % 100}{n:05d}"
        ts = f"{d} {t}"
        w.writerow([jid, d, ts, dr, drn, desc, f"{amt:.2f}", "", user, appr, src])
        w.writerow([jid, d, ts, cr, crn, desc, "", f"{amt:.2f}", user, appr, src])

    day = date(year, 1, 2)
    while day <= date(year, 12, 31):
        if day.weekday() < 5:
            for _ in range(rng.randint(1, 3)):
                dr, drn, cr, crn, lo, hi, src, desc = rng.choice(patterns)
                u = rng.choice(users[:4])
                a = rng.choice([x for x in users[:4] if x != u])
                add(day.isoformat(), f"{rng.randint(9, 17):02d}:{rng.randint(0, 59):02d}:00", dr, drn, cr, crn,
                    round(rng.uniform(lo, hi), 2), f"{desc} {rng.randint(1000, 9999)}", u, a, src)
        day += timedelta(days=1)
    planted = [
        (f"{year}-03-29", "23:41:00", "1200", "Accounts receivable", "4000", "Revenue", 250000.00, "Adjust revenue per CFO", "ASMITH", "ASMITH", "Manual"),
        (f"{year}-06-30", "21:15:00", "1200", "Accounts receivable", "4000", "Revenue", 99500.00, "Q2 true-up", "KBROWN", "", "Manual"),
        (f"{year}-09-30", "19:58:00", "1500", "Fixed assets", "6100", "Office expenses", 48000.00, "Reclass", "TEMP01", "KBROWN", "Manual"),
        (f"{year}-12-31", "22:30:00", "2400", "Accrued liabilities", "4000", "Revenue", 180000.00, "plug", "ASMITH", "ASMITH", "Spreadsheet upload"),
        (f"{year}-12-27", "10:12:00", "6400", "Consulting fees", "2000", "Accounts payable", 24900.00, "Consulting services", "MCHEN", "JLEE", "AP"),
        (f"{year}-12-27", "10:14:00", "6400", "Consulting fees", "2000", "Accounts payable", 24900.00, "Consulting services", "MCHEN", "JLEE", "AP"),
        (f"{year}-02-14", "11:05:00", "6500", "Suspense", "1000", "Cash", 75000.00, "", "PDIAZ", "JLEE", "Manual"),
        (f"{year}-01-15", "14:20:00", "6100", "Office expenses", "2000", "Accounts payable", 3200.00, "Late booked invoice", "JLEE", "MCHEN", "AP"),
    ]
    for p in planted:
        add(*p)
    text = out.getvalue()
    # make the last planted entry look backdated: posted in April for a January date
    text = text.replace(f"{year}-01-15 14:20:00", f"{year}-04-22 14:20:00")
    return text.encode()
