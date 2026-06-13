"""SysSimulator's documented blueprints as Keystone's ground-truth eval corpus.

Source: https://syssimulator.com/blueprints (component counts + documented monthly
cost bands). These are the references Keystone must eventually reproduce/validate
against. `v1_scope=True` marks single-region web/event/infra stacks the v1 analytical
engine can already model; the rest need the v2 discrete-event / multi-region engine.

Each entry: (key, name, category, components, cost_low, cost_high, v1_scope)
"""
from __future__ import annotations

BLUEPRINTS = [
    # --- Web App ---
    ("ecommerce", "E-Commerce Platform", "web_app", 6, 200, 800, True),
    ("serverless_api", "Serverless REST API", "web_app", 5, 10, 200, True),
    ("url_shortener", "URL Shortener", "web_app", 5, 20, 150, True),
    ("paste_bin", "Paste Bin", "web_app", 5, 15, 100, True),
    ("file_hosting", "File Hosting Service", "web_app", 6, 50, 500, True),
    ("blog_platform", "Blog Platform", "web_app", 6, 50, 300, True),
    ("hotel_reservation", "Hotel Reservation System", "web_app", 6, 100, 500, True),
    ("parking_lot", "Parking Lot System", "web_app", 6, 30, 150, True),
    ("image_hosting", "Image Hosting Service", "web_app", 7, 30, 300, True),
    ("twitter_clone", "Twitter / X Clone", "web_app", 9, 600, 3000, False),
    ("instagram_clone", "Instagram Clone", "web_app", 9, 500, 2500, False),
    ("proximity_service", "Yelp / Proximity Service", "web_app", 7, 200, 1200, True),
    ("spotify", "Spotify (Music Streaming)", "web_app", 9, 1000, 8000, False),
    # --- Event-Driven ---
    ("social_feed", "Social Media Feed", "event_driven", 8, 500, 2000, True),
    ("ci_cd", "CI/CD Pipeline", "event_driven", 5, 50, 300, True),
    ("task_queue", "Task Queue", "event_driven", 7, 80, 400, True),
    ("notification_system", "Notification System", "event_driven", 8, 100, 800, True),
    ("ticket_booking", "Ticket Booking System", "event_driven", 8, 300, 1500, True),
    # --- Real-Time ---
    ("realtime_chat", "Real-Time Chat", "real_time", 6, 300, 1200, False),
    ("leaderboard", "Leaderboard System", "real_time", 6, 50, 300, True),
    ("typeahead", "Typeahead / Autocomplete", "real_time", 6, 100, 600, True),
    ("ride_sharing", "Uber / Ride Sharing", "real_time", 8, 500, 3000, False),
    ("code_editor", "Online Code Editor", "real_time", 8, 300, 2000, False),
    ("stock_exchange", "Stock Exchange", "real_time", 8, 2000, 15000, False),
    ("google_docs", "Google Docs (Collaborative)", "real_time", 8, 500, 3000, False),
    ("slack_discord", "Slack / Discord", "real_time", 9, 800, 5000, False),
    # --- Microservices ---
    ("microservices", "Microservices Gateway", "microservices", 10, 800, 3000, True),
    ("payment_system", "Payment System", "microservices", 8, 600, 2000, True),
    ("food_delivery", "Food Delivery System", "microservices", 8, 400, 2000, True),
    ("digital_wallet", "Digital Wallet", "microservices", 8, 500, 3000, True),
    ("distributed_txn", "Distributed Transaction Coordinator", "microservices", 8, 400, 2000, False),
    # --- Data Pipeline ---
    ("video_streaming", "Video Streaming", "data_pipeline", 6, 500, 5000, False),
    ("iot_platform", "IoT Platform", "data_pipeline", 7, 400, 2500, False),
    ("search_engine", "Search Engine", "data_pipeline", 7, 300, 1500, True),
    ("web_crawler", "Web Crawler", "data_pipeline", 7, 200, 1500, True),
    ("google_maps", "Google Maps", "data_pipeline", 9, 1000, 10000, False),
    ("youtube", "YouTube", "data_pipeline", 10, 2000, 20000, False),
    ("dropbox", "Dropbox (File Sync)", "data_pipeline", 8, 500, 5000, False),
    ("ad_click_aggregation", "Ad Click Aggregation", "data_pipeline", 8, 800, 5000, False),
    ("ml_pipeline", "ML Feature Pipeline", "data_pipeline", 8, 1000, 10000, False),
    ("metrics_monitoring", "Metrics & Monitoring", "data_pipeline", 7, 150, 800, True),
    # --- Infrastructure ---
    ("rate_limiter", "Rate Limiter", "infrastructure", 6, 30, 200, True),
    ("kv_store", "Key-Value Store", "infrastructure", 7, 100, 500, True),
    ("id_generator", "Unique ID Generator", "infrastructure", 5, 50, 250, True),
    ("distributed_cache", "Distributed Cache", "infrastructure", 7, 200, 1000, True),
    ("api_gateway", "API Rate Limiting Gateway", "infrastructure", 8, 100, 600, True),
    ("kafka_broker", "Kafka (Message Broker)", "infrastructure", 8, 500, 3000, False),
    ("distributed_consensus", "Distributed Consensus (Raft)", "infrastructure", 8, 300, 1500, False),
    ("cdn_design", "CDN Design", "infrastructure", 9, 500, 10000, False),
    ("object_storage", "S3 Object Storage", "infrastructure", 8, 300, 5000, False),
    ("dns_system", "DNS System", "infrastructure", 7, 200, 2000, False),
    # --- AI Agents / MCP ---
    ("mcp_starter", "MCP Starter", "ai_agents", 6, 50, 250, True),
    ("mcp_rag_assistant", "RAG + MCP Assistant", "ai_agents", 6, 150, 900, True),
    ("multi_agent_supervisor", "Multi-Agent Supervisor", "ai_agents", 7, 300, 1800, True),
    ("mcp_tool_gateway", "MCP Tool Gateway", "ai_agents", 7, 300, 2200, True),
    ("agent_observability", "Agent Observability Stack", "ai_agents", 6, 120, 700, True),
]


def in_scope() -> list[tuple]:
    return [b for b in BLUEPRINTS if b[6]]


def out_of_scope() -> list[tuple]:
    return [b for b in BLUEPRINTS if not b[6]]


def summary() -> str:
    total = len(BLUEPRINTS)
    ins = len(in_scope())
    cats: dict[str, int] = {}
    for _, _, cat, *_ in BLUEPRINTS:
        cats[cat] = cats.get(cat, 0) + 1
    lines = [
        f"SysSimulator benchmark corpus: {total} blueprints "
        f"({ins} in v1 scope, {total - ins} need the v2 engine).",
        "By category: " + ", ".join(f"{k}={v}" for k, v in sorted(cats.items())),
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
    print("\nv1-scope blueprints (the Phase-1 eval targets):")
    for key, name, cat, comps, lo, hi, _ in in_scope():
        print(f"  - {name:34s} [{cat:14s}] {comps:2d} comp  ${lo:,}-${hi:,}/mo")
