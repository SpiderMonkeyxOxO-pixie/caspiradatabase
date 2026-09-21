"""Telemetry feed for the Caspira Solutions database infrastructure monitoring console.

Provides server inventory, performance metrics, alerts, backup records and
maintenance schedules for the environment hosted on behalf of Autofix Sdn Bhd.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

PROVIDER = "Caspira Solutions"

# Managed-services client roster. Each client has its own database estate,
# domain, region footprint and account tier — selectable from the sidebar.
CLIENTS = [
    {
        "name": "Autofix Sdn Bhd", "code": "autofix", "domain": "autofix.com.my",
        "industry": "Automotive Aftermarket Services", "hq": "Kuala Lumpur, Malaysia",
        "tier": "Enterprise", "regions": ["APAC", "EMEA"], "host_count": 16,
    },
    {
        "name": "Meridian Capital Group", "code": "meridian", "domain": "meridiancapital.com.sg",
        "industry": "Financial Services", "hq": "Singapore",
        "tier": "Enterprise", "regions": ["APAC", "EMEA", "AMER"], "host_count": 21,
    },
    {
        "name": "Northbridge Logistics Pte Ltd", "code": "northbridge", "domain": "northbridgelogistics.com",
        "industry": "Logistics & Supply Chain", "hq": "Sydney, Australia",
        "tier": "Mid-Market", "regions": ["APAC", "AMER"], "host_count": 9,
    },
    {
        "name": "Solara Health Partners", "code": "solara", "domain": "solarahealth.com.my",
        "industry": "Healthcare Services", "hq": "Penang, Malaysia",
        "tier": "Enterprise", "regions": ["APAC"], "host_count": 13,
    },
    {
        "name": "Veltrix Manufacturing Co.", "code": "veltrix", "domain": "veltrix-mfg.com",
        "industry": "Industrial Manufacturing", "hq": "Ho Chi Minh City, Vietnam",
        "tier": "Mid-Market", "regions": ["APAC", "EMEA"], "host_count": 11,
    },
    {
        "name": "Harborline Retail Group", "code": "harborline", "domain": "harborlineretail.co.id",
        "industry": "Retail & E-Commerce", "hq": "Jakarta, Indonesia",
        "tier": "Growth", "regions": ["APAC", "LATAM"], "host_count": 7,
    },
    {
        "name": "Kasturi Retail Sdn Bhd", "code": "kasturi", "domain": "kasturiretail.com.my",
        "industry": "Retail & Supermarkets", "hq": "Petaling Jaya, Malaysia",
        "tier": "Mid-Market", "regions": ["APAC"], "host_count": 8,
    },
    {
        "name": "Nusantara Fintech Sdn Bhd", "code": "nusantara", "domain": "nusantarafintech.com.my",
        "industry": "Financial Technology", "hq": "Kuala Lumpur, Malaysia",
        "tier": "Enterprise", "regions": ["APAC", "EMEA"], "host_count": 18,
    },
    {
        "name": "Cendekia Education Group", "code": "cendekia", "domain": "cendekia-edu.com.my",
        "industry": "Education Services", "hq": "Johor Bahru, Malaysia",
        "tier": "Growth", "regions": ["APAC"], "host_count": 6,
    },
    {
        "name": "Orkid Hospitality Sdn Bhd", "code": "orkid", "domain": "orkidhospitality.com.my",
        "industry": "Hotels & Hospitality", "hq": "Kota Kinabalu, Malaysia",
        "tier": "Mid-Market", "regions": ["APAC"], "host_count": 10,
    },
    {
        "name": "Tualang Plantations Bhd", "code": "tualang", "domain": "tualangplantations.com.my",
        "industry": "Agribusiness & Plantations", "hq": "Kuching, Malaysia",
        "tier": "Growth", "regions": ["APAC", "EMEA"], "host_count": 7,
    },
]

ENGINEERS = [
    "James Whitfield",
    "Wei Jian Tan",
    "Nurul Aisyah Rahman",
    "Sarah Mitchell",
    "Arjun Patel",
    "Mei Ling Wong",
    "Daniel Cooper",
    "Hafiz Ismail",
    "Emma Caldwell",
    "Yuki Tanaka",
]

# Server blueprint shared across clients — hostnames, IP addresses and region
# placement are derived per client in build_fleet() so each account looks distinct.
# Each client draws the first N entries (its host_count), so larger accounts
# simply carry more of the secondary/scaling tier below.
SERVER_BLUEPRINT = [
    {"name": "db-prod-01", "role": "Primary", "engine": "PostgreSQL", "version": "16.3",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 2048, "base_load": 0.55},
    {"name": "db-prod-02", "role": "Replica", "engine": "PostgreSQL", "version": "16.3",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 2048, "base_load": 0.35},
    {"name": "db-prod-03", "role": "Replica", "engine": "PostgreSQL", "version": "16.3",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 1024, "base_load": 0.30},
    {"name": "mysql-orders-01", "role": "Primary", "engine": "MySQL", "version": "8.0.37",
     "os": "Red Hat Enterprise Linux 9", "disk_capacity_gb": 1536, "base_load": 0.62},
    {"name": "mongo-events-01", "role": "Primary", "engine": "MongoDB", "version": "7.0.12",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 1024, "base_load": 0.48},
    {"name": "redis-cache-01", "role": "Cache", "engine": "Redis", "version": "7.2.5",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 256, "base_load": 0.40},
    {"name": "db-prod-04", "role": "Replica", "engine": "PostgreSQL", "version": "16.3",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 1024, "base_load": 0.28},
    {"name": "db-analytics-01", "role": "Replica", "engine": "PostgreSQL", "version": "16.3",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 2048, "base_load": 0.46},
    {"name": "mysql-orders-02", "role": "Replica", "engine": "MySQL", "version": "8.0.37",
     "os": "Red Hat Enterprise Linux 9", "disk_capacity_gb": 1536, "base_load": 0.41},
    {"name": "mysql-billing-01", "role": "Primary", "engine": "MySQL", "version": "8.0.37",
     "os": "Red Hat Enterprise Linux 9", "disk_capacity_gb": 1024, "base_load": 0.50},
    {"name": "mongo-events-02", "role": "Replica", "engine": "MongoDB", "version": "7.0.12",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 1024, "base_load": 0.43},
    {"name": "mongo-events-03", "role": "Replica", "engine": "MongoDB", "version": "7.0.12",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 512, "base_load": 0.33},
    {"name": "redis-cache-02", "role": "Cache", "engine": "Redis", "version": "7.2.5",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 256, "base_load": 0.37},
    {"name": "redis-sessions-01", "role": "Cache", "engine": "Redis", "version": "7.2.5",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 128, "base_load": 0.29},
    {"name": "db-prod-05", "role": "Replica", "engine": "PostgreSQL", "version": "16.3",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 1024, "base_load": 0.31},
    {"name": "mysql-inventory-01", "role": "Primary", "engine": "MySQL", "version": "8.0.37",
     "os": "Red Hat Enterprise Linux 9", "disk_capacity_gb": 1024, "base_load": 0.53},
    {"name": "mongo-audit-01", "role": "Replica", "engine": "MongoDB", "version": "7.0.12",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 512, "base_load": 0.24},
    {"name": "redis-queue-01", "role": "Cache", "engine": "Redis", "version": "7.2.5",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 128, "base_load": 0.34},
    {"name": "db-dr-standby-01", "role": "Replica", "engine": "PostgreSQL", "version": "16.3",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 2048, "base_load": 0.18},
    {"name": "mysql-reporting-01", "role": "Replica", "engine": "MySQL", "version": "8.0.37",
     "os": "Red Hat Enterprise Linux 9", "disk_capacity_gb": 1536, "base_load": 0.39},
    {"name": "db-prod-06", "role": "Replica", "engine": "PostgreSQL", "version": "16.3",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 1024, "base_load": 0.27},
    {"name": "mongo-config-01", "role": "Replica", "engine": "MongoDB", "version": "7.0.12",
     "os": "Ubuntu 22.04 LTS", "disk_capacity_gb": 128, "base_load": 0.16},
]

ALERT_TEMPLATES = [
    ("Critical", "Replication lag exceeded threshold (30s) on {server}"),
    ("Critical", "Disk usage above 90 percent on {server}"),
    ("Critical", "Connection pool exhausted on {server}"),
    ("Warning", "Connection pool utilization above 80 percent on {server}"),
    ("Warning", "Slow query detected on {server} (execution time over 2000ms)"),
    ("Warning", "Sustained CPU above 85 percent for 10 minutes on {server}"),
    ("Warning", "Memory utilization trending upward on {server}"),
    ("Info", "Scheduled backup completed successfully on {server}"),
    ("Info", "Nightly index maintenance completed on {server}"),
    ("Info", "Automated failover health check passed on {server}"),
    ("Info", "Security patch applied during maintenance window on {server}"),
]

MAINTENANCE_TEMPLATES = [
    "Quarterly index rebuild and statistics refresh",
    "Minor version upgrade and security patching",
    "Storage volume expansion",
    "Failover and disaster-recovery drill",
    "Connection pool and configuration tuning review",
    "TLS certificate rotation",
]


def _seeded_rng(seed_key: str) -> np.random.Generator:
    seed = abs(hash(seed_key)) % (2**32)
    return np.random.default_rng(seed)


def build_fleet(client: dict) -> list:
    """Builds a client-specific server inventory from the shared blueprint.

    Hostnames follow the client's domain, IP ranges and region placement are
    derived deterministically from the client code so each account's estate
    looks distinct but stays stable across reruns (until metrics are refreshed).
    """
    rng = _seeded_rng(f"fleet-{client['code']}")
    octet_a = int(rng.integers(10, 30))
    octet_b = int(rng.integers(0, 60))
    count = client.get("host_count", len(SERVER_BLUEPRINT))
    fleet = []
    for i in range(count):
        tmpl = SERVER_BLUEPRINT[i % len(SERVER_BLUEPRINT)]
        region = client["regions"][i % len(client["regions"])]
        ip_address = f"10.{octet_a}.{octet_b + i}.{int(rng.integers(10, 250))}"
        fleet.append({
            **tmpl,
            "hostname": f"{tmpl['name']}.{client['domain']}",
            "ip_address": ip_address,
            "region": region,
        })
    return fleet


def status_from_metrics(cpu, memory, disk, repl_lag):
    if cpu > 90 or memory > 92 or disk > 92 or repl_lag > 30:
        return "Critical"
    if cpu > 75 or memory > 80 or disk > 85 or repl_lag > 10:
        return "Warning"
    return "Healthy"


def generate_history(server: dict, hours: int = 24, jitter_seed: int = 0) -> pd.DataFrame:
    """Metric samples at 5-minute resolution over the given window."""
    rng = _seeded_rng(f"{server['name']}-{jitter_seed}")
    points = hours * 12
    now = datetime.now()
    timestamps = [now - timedelta(minutes=5 * (points - i)) for i in range(points)]

    base = server["base_load"]
    daily_cycle = np.sin(np.linspace(0, 2 * np.pi, points)) * 0.15
    noise = rng.normal(0, 0.05, points)
    load = np.clip(base + daily_cycle + noise, 0.05, 0.99)

    cpu = np.clip(load * 100 + rng.normal(0, 3, points), 1, 99)
    memory = np.clip((load * 0.8 + 0.15) * 100 + rng.normal(0, 2, points), 5, 97)
    disk = np.clip(40 + load * 28 + np.linspace(0, 6, points) + rng.normal(0, 1, points), 10, 98)
    connections = np.clip((load * 480 + rng.normal(0, 15, points)).round(), 5, 500)
    query_latency = np.clip(load * 60 + rng.normal(0, 6, points), 1, None)
    replication_lag = (
        np.clip(rng.normal(load * 4, 2.5, points), 0, None)
        if server["role"] == "Replica" else np.zeros(points)
    )
    iops = np.clip(load * 4500 + rng.normal(0, 200, points), 50, None)

    return pd.DataFrame({
        "timestamp": timestamps,
        "cpu_pct": cpu.round(1),
        "memory_pct": memory.round(1),
        "disk_pct": disk.round(1),
        "connections": connections.astype(int),
        "query_latency_ms": query_latency.round(1),
        "replication_lag_s": replication_lag.round(2),
        "iops": iops.round(0),
    })


def latest_snapshot(history: pd.DataFrame, server: dict) -> dict:
    last = history.iloc[-1]
    status = status_from_metrics(last.cpu_pct, last.memory_pct, last.disk_pct, last.replication_lag_s)
    uptime_pct = round(100 * (history["cpu_pct"].lt(90) & history["memory_pct"].lt(92) & history["disk_pct"].lt(92)).mean(), 3)
    disk_used_gb = round(server["disk_capacity_gb"] * last.disk_pct / 100, 1)

    # Rough capacity projection: linear trend of disk usage over the sampled window.
    disk_series = history["disk_pct"].to_numpy()
    if len(disk_series) > 12:
        slope_per_sample = (disk_series[-1] - disk_series[0]) / max(len(disk_series) - 1, 1)
        samples_per_day = 12 * 24
        slope_per_day = slope_per_sample * samples_per_day
        if slope_per_day > 0.01:
            days_to_full = round(max(0, (95 - last.disk_pct) / slope_per_day))
        else:
            days_to_full = None
    else:
        days_to_full = None

    return {
        "name": server["name"],
        "hostname": server["hostname"],
        "ip_address": server["ip_address"],
        "role": server["role"],
        "engine": server["engine"],
        "version": server["version"],
        "os": server["os"],
        "region": server["region"],
        "status": status,
        "cpu_pct": last.cpu_pct,
        "memory_pct": last.memory_pct,
        "disk_pct": last.disk_pct,
        "disk_capacity_gb": server["disk_capacity_gb"],
        "disk_used_gb": disk_used_gb,
        "connections": int(last.connections),
        "query_latency_ms": last.query_latency_ms,
        "replication_lag_s": last.replication_lag_s,
        "iops": int(last.iops),
        "uptime_pct_30d": uptime_pct,
        "days_to_disk_full": days_to_full,
        "last_updated": last.timestamp,
    }


def generate_alerts(snapshots: list, jitter_seed: int = 0, count: int = 18) -> pd.DataFrame:
    rng = _seeded_rng(f"alerts-{jitter_seed}")
    now = datetime.now()
    rows = []
    for i in range(count):
        severity, template = ALERT_TEMPLATES[rng.integers(0, len(ALERT_TEMPLATES))]
        server = snapshots[rng.integers(0, len(snapshots))]
        opened_minutes_ago = int(rng.integers(5, 60 * 24 * 3))
        opened = now - timedelta(minutes=opened_minutes_ago)

        if severity == "Info":
            state = "Resolved"
        else:
            roll = rng.random()
            state = "Open" if roll < 0.30 else ("Acknowledged" if roll < 0.65 else "Resolved")

        resolved = None
        if state == "Resolved":
            resolved = opened + timedelta(minutes=int(rng.integers(5, 240)))

        rows.append({
            "opened": opened,
            "severity": severity,
            "server": server["name"],
            "message": template.format(server=server["name"]),
            "status": state,
            "assigned_to": ENGINEERS[rng.integers(0, len(ENGINEERS))] if state != "Open" else "Unassigned",
            "resolved": resolved,
        })
    df = pd.DataFrame(rows).sort_values("opened", ascending=False).reset_index(drop=True)
    return df


def generate_backup_log(snapshots: list, jitter_seed: int = 0, days: int = 5) -> pd.DataFrame:
    rng = _seeded_rng(f"backups-{jitter_seed}")
    now = datetime.now()
    rows = []
    for s in snapshots:
        for d in range(days):
            run_time = now - timedelta(days=d, hours=int(rng.integers(0, 4)), minutes=int(rng.integers(0, 60)))
            duration = int(rng.integers(4, 50))
            size_gb = round(float(rng.uniform(2, 90)), 1)
            ok = rng.random() > 0.07
            rows.append({
                "timestamp": run_time,
                "server": s["name"],
                "type": "Full" if d % 7 == 0 else "Incremental",
                "result": "Success" if ok else "Failed",
                "duration_min": duration,
                "size_gb": size_gb,
                "destination": "s3://corp-db-backups/" + s["name"],
            })
    df = pd.DataFrame(rows).sort_values("timestamp", ascending=False).reset_index(drop=True)
    return df


def generate_maintenance_schedule(snapshots: list, jitter_seed: int = 0, count: int = 6) -> pd.DataFrame:
    rng = _seeded_rng(f"maintenance-{jitter_seed}")
    now = datetime.now()
    rows = []
    for i in range(count):
        server = snapshots[rng.integers(0, len(snapshots))]
        days_out = int(rng.integers(1, 30))
        start = (now + timedelta(days=days_out)).replace(
            hour=int(rng.integers(0, 4)), minute=0, second=0, microsecond=0
        )
        duration_hours = int(rng.integers(1, 5))
        rows.append({
            "scheduled_for": start,
            "server": server["name"],
            "description": MAINTENANCE_TEMPLATES[rng.integers(0, len(MAINTENANCE_TEMPLATES))],
            "duration_hours": duration_hours,
            "owner": ENGINEERS[rng.integers(0, len(ENGINEERS))],
            "change_ticket": f"CHG-{int(rng.integers(10000, 99999))}",
        })
    df = pd.DataFrame(rows).sort_values("scheduled_for").reset_index(drop=True)
    return df
