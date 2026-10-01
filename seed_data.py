"""
Seed script: SQLite schema + fake client data for the LangGraph follow-up agent.

Usage:
    python seed_demo_data.py            # create DB if missing and seed
    python seed_demo_data.py --reset    # drop everything and re-seed

Creates 50 clients: 6 handcrafted edge cases + 44 generated (deterministic, same every run).
Dates are relative to "now", so some clients are always due for a follow-up.
"""
import random
import sqlite3
import sys
from datetime import datetime, timedelta

DB_PATH = "followup_agent.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    email             TEXT NOT NULL,
    company           TEXT,
    stage             TEXT NOT NULL,      -- proposal_sent | meeting_done | invoice_pending | quote_requested
    context           TEXT,               -- short note the LLM uses when drafting
    deal_value        REAL,
    currency          TEXT DEFAULT 'PKR',
    status            TEXT NOT NULL DEFAULT 'active',  -- active | replied | stopped | won | lost
    opt_out           INTEGER NOT NULL DEFAULT 0,
    follow_up_count   INTEGER NOT NULL DEFAULT 0,
    max_follow_ups    INTEGER NOT NULL DEFAULT 3,
    last_contacted_at TEXT,
    next_follow_up_at TEXT,
    gmail_thread_id   TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id  INTEGER NOT NULL REFERENCES clients(id),
    direction  TEXT NOT NULL,             -- sent | received
    subject    TEXT,
    body       TEXT NOT NULL,
    sent_at    TEXT NOT NULL
);
"""

now = datetime.now().replace(microsecond=0)


def ago(days=0, hours=0):
    return (now - timedelta(days=days, hours=hours)).isoformat(sep=" ")


def ahead(days=0, hours=0):
    return (now + timedelta(days=days, hours=hours)).isoformat(sep=" ")


# Each client: fields + list of (direction, subject, body, sent_at) messages.
CLIENTS = [
    {   # 1. Proposal sent 4 days ago, no reply -> DUE (first follow-up)
        "name": "Ayesha Khan", "email": "ayesha@brightlane.example.com", "company": "Brightlane Marketing",
        "stage": "proposal_sent", "deal_value": 250000, "currency": "PKR",
        "context": "Proposal for website redesign + SEO. She liked the portfolio on the call.",
        "status": "active", "opt_out": 0, "follow_up_count": 0, "max_follow_ups": 3,
        "last_contacted_at": ago(days=4), "next_follow_up_at": ago(hours=2), "gmail_thread_id": "thr_demo_001",
        "messages": [
            ("sent", "Website redesign proposal",
             "Hi Ayesha, thanks for your time today. Attached is the proposal for the redesign and SEO work. "
             "Happy to walk through any part of it.", ago(days=4)),
        ],
    },
    {   # 2. Invoice pending, one follow-up already sent -> DUE (second)
        "name": "Bilal Ahmed", "email": "bilal@nexatrade.example.com", "company": "Nexa Trading",
        "stage": "invoice_pending", "deal_value": 85000, "currency": "PKR",
        "context": "Invoice #1042 for landing page work, due 6 days ago. Usually pays late but is friendly.",
        "status": "active", "opt_out": 0, "follow_up_count": 1, "max_follow_ups": 3,
        "last_contacted_at": ago(days=3), "next_follow_up_at": ago(hours=5), "gmail_thread_id": "thr_demo_002",
        "messages": [
            ("sent", "Invoice #1042", "Hi Bilal, sharing invoice #1042 for the landing page project. "
             "Payment is due by the 22nd.", ago(days=9)),
            ("sent", "Re: Invoice #1042", "Hi Bilal, a quick reminder that invoice #1042 is now past due. "
             "Could you let me know when I can expect payment?", ago(days=3)),
        ],
    },
    {   # 3. Meeting done yesterday -> NOT due yet (future)
        "name": "Sarah Mitchell", "email": "sarah@corvidlabs.example.com", "company": "Corvid Labs",
        "stage": "meeting_done", "deal_value": 3200, "currency": "USD",
        "context": "Discovery call about an AI support chatbot. She needs to check budget with her CFO.",
        "status": "active", "opt_out": 0, "follow_up_count": 0, "max_follow_ups": 3,
        "last_contacted_at": ago(days=1), "next_follow_up_at": ahead(days=1), "gmail_thread_id": "thr_demo_003",
        "messages": [
            ("sent", "Great speaking today", "Hi Sarah, great speaking with you today. I'll send over a scope "
             "and timeline by Friday.", ago(days=1)),
        ],
    },
    {   # 4. Quote requested, 2 follow-ups done -> DUE (last one)
        "name": "Usman Tariq", "email": "usman@zenithbuild.example.com", "company": "Zenith Builders",
        "stage": "quote_requested", "deal_value": 120000, "currency": "PKR",
        "context": "Asked for a quote on a project-tracking dashboard. Went quiet after the quote.",
        "status": "active", "opt_out": 0, "follow_up_count": 2, "max_follow_ups": 3,
        "last_contacted_at": ago(days=7), "next_follow_up_at": ago(hours=1), "gmail_thread_id": "thr_demo_004",
        "messages": [
            ("sent", "Quote for dashboard", "Hi Usman, here is the quote for the dashboard we discussed.", ago(days=21)),
            ("sent", "Re: Quote for dashboard", "Hi Usman, just checking that the quote reached you.", ago(days=14)),
            ("sent", "Re: Quote for dashboard", "Hi Usman, following up once more. Happy to adjust scope if the "
             "budget is a concern.", ago(days=7)),
        ],
    },
    {   # 5. Client replied -> agent must STOP (reply detection demo)
        "name": "Fatima Noor", "email": "fatima@lumenstudio.example.com", "company": "Lumen Studio",
        "stage": "proposal_sent", "deal_value": 180000, "currency": "PKR",
        "context": "Branding + landing page proposal. She replied asking for a small discount.",
        "status": "active", "opt_out": 0, "follow_up_count": 1, "max_follow_ups": 3,
        "last_contacted_at": ago(days=2), "next_follow_up_at": ago(hours=3), "gmail_thread_id": "thr_demo_005",
        "messages": [
            ("sent", "Branding proposal", "Hi Fatima, attached is the branding and landing page proposal.", ago(days=8)),
            ("sent", "Re: Branding proposal", "Hi Fatima, following up on the proposal. Any questions?", ago(days=5)),
            ("received", "Re: Branding proposal", "Hi, thanks for the proposal. Is there any room on the price?", ago(days=2)),
        ],
    },
    {   # 6. Opted out -> agent must NEVER contact
        "name": "Daniel Reyes", "email": "daniel@orbitfreight.example.com", "company": "Orbit Freight",
        "stage": "proposal_sent", "deal_value": 5000, "currency": "USD",
        "context": "Asked not to be contacted again.",
        "status": "stopped", "opt_out": 1, "follow_up_count": 1, "max_follow_ups": 3,
        "last_contacted_at": ago(days=6), "next_follow_up_at": None, "gmail_thread_id": "thr_demo_006",
        "messages": [
            ("sent", "Logistics dashboard proposal", "Hi Daniel, sharing the proposal we discussed.", ago(days=10)),
            ("received", "Re: Logistics dashboard proposal", "Please stop emailing me about this. Thanks.", ago(days=6)),
        ],
    },
]


# ---------------------------------------------------------------------------
# Generated demo clients (deterministic: same data on every run)
# ---------------------------------------------------------------------------
CADENCE_DAYS = {
    "proposal_sent":   [3, 7, 14],
    "invoice_pending": [2, 5, 10],
    "meeting_done":    [2, 5, 10],
    "quote_requested": [3, 7, 14],
}
FIRST_NAMES = ["Hamza", "Zainab", "Omar", "Hina", "Saad", "Mariam", "Ali", "Noor", "Imran", "Sana",
               "James", "Emily", "Ravi", "Priya", "Lucas", "Chloe", "Ahmed", "Laiba", "Tom", "Anika",
               "Kashif", "Maryam", "Daniel", "Sofia", "Bilawal", "Rida", "Owen", "Mehak", "Farhan", "Iqra"]
LAST_NAMES = ["Sheikh", "Malik", "Raza", "Butt", "Qureshi", "Siddiqui", "Chaudhry", "Iqbal", "Hussain", "Javed",
              "Walker", "Patel", "Nguyen", "Brooks", "Ansari", "Baig", "Cooper", "Mirza", "Rehman", "Gill"]
COMPANY_A = ["Blue", "Prime", "Swift", "Urban", "Vertex", "Crest", "Nova", "Pixel", "Summit", "Delta",
             "Falcon", "Green", "Apex", "Metro", "Solar", "Atlas"]
COMPANY_B = ["Logistics", "Foods", "Traders", "Studio", "Clinic", "Textiles", "Solutions", "Realty",
             "Academy", "Motors", "Retail", "Ventures"]
SERVICES = ["website redesign", "mobile app", "SEO campaign", "branding package", "AI support chatbot",
            "analytics dashboard", "e-commerce store", "social media management"]
NOTES = ["Friendly and responsive on calls.", "Decision maker is the founder.", "Needs approval from finance.",
         "Comparing with two other vendors.", "Prefers short emails.", "Usually replies within a week.",
         "Budget is tight this quarter.", "Referred by an existing client."]
TOPIC = {"proposal_sent": "proposal", "invoice_pending": "invoice",
         "meeting_done": "next steps", "quote_requested": "quote"}
REPLIES = ["Thanks, can we jump on a quick call this week?", "Looks good, can you share a revised timeline?",
           "Is there any room on the price?", "We are reviewing internally and will get back to you soon."]
WON_REPLIES = ["Sounds great, let's go ahead. Please send the contract.", "Approved on our side, when can we start?"]


def generate_clients(n, seed_value=42):
    rng = random.Random(seed_value)
    kinds = (["active"] * 28 + ["replied"] * 6 + ["undetected_reply"] * 3 +
             ["optout"] * 3 + ["won"] * 2 + ["lost"] * 2)
    kinds = (kinds + ["active"] * n)[:n]
    rng.shuffle(kinds)

    used_emails = {c["email"] for c in CLIENTS}
    out = []
    for i, kind in enumerate(kinds, start=len(CLIENTS) + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        company = f"{rng.choice(COMPANY_A)} {rng.choice(COMPANY_B)}"
        email = f"{first.lower()}.{last.lower()}@{company.lower().replace(' ', '')}.example.com"
        if email in used_emails:
            email = email.replace("@", f"{i}@")
        used_emails.add(email)

        stage = rng.choice(list(CADENCE_DAYS))
        cadence = CADENCE_DAYS[stage]
        service = rng.choice(SERVICES)
        inv = rng.randint(1000, 1999)
        currency = rng.choices(["PKR", "USD"], weights=[7, 3])[0]
        value = round(rng.uniform(40_000, 400_000), -3) if currency == "PKR" else round(rng.uniform(800, 8000), -2)

        # how many follow-ups were already sent
        if kind == "lost":
            count = 3
        elif kind == "optout":
            count = 1
        elif kind == "won":
            count = rng.choice([1, 2])
        else:
            count = rng.choice([0, 0, 0, 1, 1, 1, 2, 2])
        gap = cadence[count] if count < len(cadence) else cadence[-1]

        # undetected replies are always overdue so the agent's check_reply node has to catch them
        days_since_last = gap + rng.randint(1, 2) if kind == "undetected_reply" else rng.randint(1, gap + 3)

        # sent timestamps, computed backwards from "now"
        sent = [None] * (count + 1)
        sent[count] = now - timedelta(days=days_since_last, hours=rng.randint(0, 6))
        for k in range(count, 0, -1):
            sent[k - 1] = sent[k] - timedelta(days=cadence[k - 1])

        subject = {"proposal_sent": f"Proposal: {service}", "invoice_pending": f"Invoice #{inv}",
                   "meeting_done": f"Great speaking today ({service})",
                   "quote_requested": f"Quote: {service}"}[stage]
        initial = {
            "proposal_sent": f"Hi {first}, attached is the proposal for {service}. Happy to walk through any part of it.",
            "meeting_done": f"Hi {first}, thanks for the call about {service}. I'll send a scope and timeline shortly.",
            "invoice_pending": f"Hi {first}, sharing invoice #{inv} for the {service} project. Payment is due within 7 days.",
            "quote_requested": f"Hi {first}, here is the quote for {service} as requested.",
        }[stage]
        follow_ups = [
            f"Hi {first}, just checking in on the {TOPIC[stage]}. Let me know if you have any questions.",
            f"Hi {first}, following up once more on the {TOPIC[stage]}. Happy to adjust the scope if that helps.",
            f"Hi {first}, closing the loop on this. Feel free to reach out whenever the timing is right.",
        ]

        messages = [("sent", subject, initial, sent[0].isoformat(sep=" "))]
        for k in range(1, count + 1):
            messages.append(("sent", f"Re: {subject}", follow_ups[k - 1], sent[k].isoformat(sep=" ")))

        received_at = sent[-1] + timedelta(hours=rng.randint(3, 20))
        if kind in ("replied", "undetected_reply"):
            messages.append(("received", f"Re: {subject}", rng.choice(REPLIES), received_at.isoformat(sep=" ")))
        elif kind == "won":
            body = "Payment has been sent, please confirm receipt." if stage == "invoice_pending" else rng.choice(WON_REPLIES)
            messages.append(("received", f"Re: {subject}", body, received_at.isoformat(sep=" ")))
        elif kind == "optout":
            messages.append(("received", f"Re: {subject}", "Please stop emailing me about this. Thanks.",
                             received_at.isoformat(sep=" ")))

        status = {"active": "active", "undetected_reply": "active", "replied": "replied",
                  "optout": "stopped", "won": "won", "lost": "lost"}[kind]
        prefix = {"proposal_sent": f"Proposal for {service}", "meeting_done": f"Discovery call about {service}",
                  "invoice_pending": f"Invoice #{inv} for {service}",
                  "quote_requested": f"Asked for a quote on {service}"}[stage]

        out.append({
            "name": f"{first} {last}", "email": email, "company": company, "stage": stage,
            "context": f"{prefix}. {rng.choice(NOTES)}", "deal_value": value, "currency": currency,
            "status": status, "opt_out": 1 if kind == "optout" else 0,
            "follow_up_count": count, "max_follow_ups": 3,
            "last_contacted_at": sent[-1].isoformat(sep=" "),
            "next_follow_up_at": (sent[-1] + timedelta(days=gap)).isoformat(sep=" ") if status == "active" else None,
            "gmail_thread_id": f"thr_demo_{i:03d}",
            "messages": messages,
        })
    return out


ALL_CLIENTS = CLIENTS + generate_clients(50 - len(CLIENTS))


def print_summary():
    conn = sqlite3.connect(DB_PATH)
    print("\nStatus breakdown:")
    for status, cnt in conn.execute("SELECT status, COUNT(*) FROM clients GROUP BY status ORDER BY 2 DESC"):
        print(f"  {status:<8} {cnt}")
    conn.close()


def seed(reset=False):
    conn = sqlite3.connect(DB_PATH)
    if reset:
        conn.executescript("DROP TABLE IF EXISTS messages; DROP TABLE IF EXISTS clients;")
    conn.executescript(SCHEMA)

    if conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0] > 0:
        print("Database already has data. Use --reset to re-seed.")
        conn.close()
        return

    for c in ALL_CLIENTS:
        msgs = c.pop("messages")
        cols = ", ".join(c.keys())
        marks = ", ".join("?" for _ in c)
        cur = conn.execute(f"INSERT INTO clients ({cols}) VALUES ({marks})", list(c.values()))
        for direction, subject, body, sent_at in msgs:
            conn.execute(
                "INSERT INTO messages (client_id, direction, subject, body, sent_at) VALUES (?,?,?,?,?)",
                (cur.lastrowid, direction, subject, body, sent_at),
            )
    conn.commit()
    conn.close()
    print(f"Seeded {len(ALL_CLIENTS)} clients into {DB_PATH}")


def get_due_clients():
    """Same query the daily scheduler will use to decide whom to run the graph for."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, name, company, stage, follow_up_count, max_follow_ups, next_follow_up_at
        FROM clients
        WHERE status = 'active'
          AND opt_out = 0
          AND follow_up_count < max_follow_ups
          AND next_follow_up_at IS NOT NULL
          AND next_follow_up_at <= datetime('now', 'localtime')
        ORDER BY next_follow_up_at
        """
    ).fetchall()
    conn.close()
    return rows


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
    print_summary()
    print("\nClients due for a follow-up right now:")
    for r in get_due_clients():
        print(f"  #{r['id']} {r['name']} ({r['company']}) | {r['stage']} | "
              f"{r['follow_up_count']}/{r['max_follow_ups']} sent")