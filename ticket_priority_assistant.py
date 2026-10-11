import argparse
import csv
import re
from dataclasses import dataclass, field
from datetime import datetime

#configuration 
KEYWORD_RULES = [
    (r"\b(outage|down|crash(ed|ing)?|data loss|breach|security|hacked)\b", 40, "critical keyword"),
    (r"\b(cannot|can't|unable to|won't|not working|broken|fails?|failed|error)\b", 20, "blocking issue"),
    (r"\b(urgent|asap|immediately|emergency|critical|production)\b", 20, "urgency language"),
    (r"\b(payment|billing|charged|refund|invoice)\b", 15, "money-related"),
    (r"\b(slow|delay(ed)?|lag|intermittent)\b", 8, "degraded performance"),
    (r"\b(question|how do i|how to|feature request|suggestion|typo)\b", -10, "low-urgency request"),
]

TIER_POINTS = {"free": 0, "standard": 5, "premium": 12, "enterprise": 20}

#min users affected
IMPACT_STEPS = [(100, 25), (20, 15), (5, 8), (2, 3)]

# hours waiting -> bonus points (ticket aging)
AGE_STEPS = [(72, 15), (24, 8), (8, 3)]

# score thresholds -> priority
PRIORITIES = [
    (70, "P1", "Critical - respond within 1 hour"),
    (45, "P2", "High - respond within 4 hours"),
    (20, "P3", "Medium - respond within 1 business day"),
    (-999, "P4", "Low - respond within 3 business days"),
]

#model

@dataclass
class Ticket:
    id: str
    title: str
    description: str = ""
    customer_tier: str = "standard"
    users_affected: int = 1
    created_at: datetime | None = None
 
 
@dataclass
class Result:
    ticket: Ticket
    score: int = 0
    priority: str = "P4"
    sla: str = ""
    reasons: list[str] = field(default_factory=list)

#scoring
def score_ticket(ticket: Ticket, now: datetime | None = None) -> Result:
    now = now or datetime.now()
    res = Result(ticket)
    text = f"{ticket.title} {ticket.description}".lower()

    #keywords
    for pattern, points, label in KEYWORD_RULES:
        match = re.search(pattern, text)
        if match:
            res.score += points
            res.reasons.append(f"{label} '{match.group(0)}' ({points:+d})")

    #customer tier
    tier = ticket.customer_tier.lower()
    tier_pts = TIER_POINTS.get(tier, 0)
    if tier_pts:
        res.score += tier_pts
        res.reasons.append(f"{tier} customer ({tier_pts:+d})")

    #impact
    for threshold, pts in IMPACT_STEPS:
        if ticket.users_affected >= threshold:
            res.score += pts
            res.reasons.append(f"{ticket.users_affected} users affected ({pts:+d})")
            break

    #aging
    if ticket.created_at:
        hours = (now - ticket.created_at).total_seconds() / 3600
        for threshold, pts in AGE_STEPS:
            if hours >= threshold:
                res.score += pts
                res.reasons.append(f"waiting {hours:.0f}h ({pts:+d})")
                break

    #map score -> priority
    for threshold, name, sla in PRIORITIES:
        if res.score >= threshold:
            res.priority, res.sla = name, sla
            break
    return res
def prioritize(tickets: list[Ticket]) -> list[Result]:
    now = datetime.now()
    results = [score_ticket(t, now) for t in tickets]
    return sorted(results, key=lambda r: r.score, reverse=True)

#Input output

def parse_date(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
 
 
def load_csv(path: str) -> list[Ticket]:
    tickets = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                users = int(row.get("users_affected") or 1)
            except ValueError:
                users = 1
            tickets.append(Ticket(
                id=row.get("id", "?"),
                title=row.get("title", ""),
                description=row.get("description", ""),
                customer_tier=row.get("customer_tier") or "standard",
                users_affected=users,
                created_at=parse_date(row.get("created_at", "")),
            ))
    return tickets
 
 
def save_csv(results: list[Result], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "id", "title", "priority", "score", "sla", "reasons"])
        for i, r in enumerate(results, 1):
            w.writerow([i, r.ticket.id, r.ticket.title, r.priority, r.score,
                        r.sla, "; ".join(r.reasons)])
 
 
def print_report(results: list[Result]) -> None:
    print(f"\n{'#':<3} {'ID':<8} {'PRI':<4} {'SCORE':<6} TITLE")
    print("-" * 70)
    for i, r in enumerate(results, 1):
        print(f"{i:<3} {r.ticket.id:<8} {r.priority:<4} {r.score:<6} {r.ticket.title}")
        print(f"      -> {r.sla}")
        for reason in r.reasons:
            print(f"         - {reason}")
    print()


 #demo
def demo_tickets() -> list[Ticket]:
    now = datetime.now()
    h = lambda hours: datetime.fromtimestamp(now.timestamp() - hours * 3600)
    return [
        Ticket("T-101", "Production site is down",
               "Entire checkout crashed, customers cannot pay. Urgent!",
               "enterprise", 500, h(1)),
        Ticket("T-102", "Invoice shows wrong amount",
               "We were charged twice this month, please refund.",
               "premium", 1, h(30)),
        Ticket("T-103", "Dashboard loads slowly",
               "Reports are slow in the morning, intermittent lag.",
               "standard", 12, h(10)),
        Ticket("T-104", "How do I export to CSV?",
               "Quick question about exporting reports.",
               "free", 1, h(5)),
        Ticket("T-105", "Typo on pricing page", "Feature request: fix 'recieve'.",
               "free", 1, h(80)),
    ]

#main
def main() -> None:
    parser = argparse.ArgumentParser(description="Ticket Priority Assistant")
    parser.add_argument("csv_file", nargs="?", help="CSV file of tickets (omit for demo)")
    parser.add_argument("-o", "--output", help="write ranked results to this CSV")
    args = parser.parse_args()
 
    tickets = load_csv(args.csv_file) if args.csv_file else demo_tickets()
    results = prioritize(tickets)
    print_report(results)
 
    if args.output:
        save_csv(results, args.output)
        print(f"Saved ranked tickets to {args.output}")
 
 
if __name__ == "__main__":
    main()