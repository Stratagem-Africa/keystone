# 14 — Blueprint reality check (2026-09-08)

Bifola asked whether the 56 reference designs match what those companies actually run. This is the
answer, from a 24-agent web-research pass: 12 researchers against primary sources, each followed by
a verifier that opened every cited URL and dropped anything that did not resolve or did not support
the claim it was attached to.

**27 of the 56 blueprints graded** (the most-published systems; the rest have no public
architecture to check against). **110 claims dropped** in verification.
**215 distinct sources survived.**

Interview-prep sites (ByteByteGo, Educative, unsourced Medium, YouTube system-design channels) were
BANNED as sources. They recycle the same textbook designs our blueprints may already be echoing, so
citing them would have proved nothing.

## Scoreboard

| | count |
|---|---|
| Shape — reasonable simplification | 14 |
| Shape — **misleading** | 13 |
| Numbers — plausible | 14 |
| Numbers — **implausible** | 7 |
| Numbers — no public figure exists | 6 |

"Misleading" has a precise meaning here and it is not "simplified". A simplification that leaves the
reader pointing at the right component is fine at L0. A design is misleading when **it would send
someone to optimise the wrong thing.**

## Per blueprint

### ride_sharing

- **shape:** misleading · **numbers:** no_public_figure

**What a reader would get wrong**

I re-derived every utilisation from the file itself before judging, and the researcher's numbers are
exact: loc 24,000/32,000 = 0.75 (matches declared peak_util), match 1,800/3,000 = 0.60, api
4,200/9,000 = 0.47, db 4,200/12,000 = 0.35, geo-cache 27,600/200,000 = 0.138, lb 28,200/100,000 =
0.28. Three defects survive verification, and they are defects rather than L0 simplifications
because each one moves the reader's answer to "what do I scale?"  (1) THE RIDE-REQUEST RATE IS
ARITHMETICALLY IMPOSSIBLE, AND IT IS UNDISCLOSED. The `workload` assumption's stated arithmetic is
internally correct (96,000 drivers / 4s = 24,000 pings/s, matching share 0.8), but its companion
figure is not: rider_request share 0.06 × 30,000 = 1,800 requests/s in ONE city = 155.5M rides/day,
against Uber's verified global "more than 40 million trips every day" (Q4 2025 release, 4 Feb 2026)
≈ 463 trips/s for the entire planet. One city is modelled at ~4x the whole world. It is also self-
inconsistent: 1,800 req/s over 96,000 drivers implies ~67 completed trips per driver per hour. At a
defensible ~50/s the business tiers sit at 1-3% util, so the design as published is a ~30x over-
provision of dispatch (5 instances) and the Postgres primary (12,000 rps). This is the clearest case
of pointing a reader at the wrong component, and unlike the blueprint's other gaps it carries no
caveat.  (2) THE GEO-INDEX TRAFFIC MIX IS INVERTED VERSUS THE ONLY PUBLISHED STATEMENT ABOUT UBER'S
ACTUAL GEO INDEX. The blueprint gives that component 24,000 writes/s against 3,600 reads/s — reads
are 0.15x writes, component 14% utilised, and the reader walks away believing the geo index is a
write-firehose sink with 7x headroom. Matt Ranney (Uber Chief Systems Architect), QCon London 2015,
reported by High Scalability 14 Sep 2015: "Design goal is to handle a million writes per second" AND
"The read goal is for many more reads than writes per second because everyone with an open app is
doing reads." Uber's own later geo-read services confirm the direction and are ~1-2 orders of
magnitude below the blueprint's flat 100,000 rps/instance: the geofence service ran 170k QPS on 40
machines at 35% CPU ≈ 4,250 QPS/machine, p95 <5ms / p99 <50ms, and was "Uber's highest queries per
second (QPS) service out of the hundreds we run in production" (24 Feb 2016); orders-near-you radius
search runs "thousands of queries per second" at P99 50ms on Pinot+H3, replacing a Cassandra design
that needed "hundreds of thousands" of lookups/s (20 Jul 2021). Fairness note: the `cache`
assumption honestly discloses that there is no spatial cost model and that a radius search costs
more than a point write. It does NOT disclose that reads should exceed writes — so the disclosure
covers the cost-model gap but not the actual proportion error, and the proportion error is what
keeps the component looking idle.  (3) THERE IS NO OUTBOUND TIER AND NO ASSUMPTION SAYING SO. All
five flows are inbound request/response. Uber's push platform post (18 Dec 2020) states that before
push, "80% of requests made to the backend API gateway were polling calls," and gives RAMEN at "over
70,000 QPS push messages per second" over "up to 600,000 concurrent streaming connections," later
"more than 1.5M concurrent connections and pushes over 250,000 messages per second" — carrying
exactly the state this blueprint computes ("pickup time, arrival time, and route lines on the
screen, or nearby drivers when you open the app"). The gRPC successor (16 Aug 2022) adds driver
offers with "a validity of 30 seconds" and p95 connect latency improved "by a minimum of 45%." A
tier that absorbed four-fifths of gateway load has no capacity, no cost and no caveat here. Every
other omission in this file (routing/ETA, payments, surge, batch dispatch, object-store byte cost)
IS disclosed — which is why this one reads as an oversight rather than a scoping choice.  WHAT IS
NOT A DEFECT, and I want this on record because the file is otherwise unusually disciplined: the
headline thesis ("a ride-sharing system is a location-ingest system with a marketplace attached") is
correct and directly supported by Ranney 2015. The 4-second ping cadence is real. The `match`
assumption pre-emptively concedes that real dispatch batches over a 2-5s window — Uber's own
marketplace page confirms it ("if we wait just a few seconds after a request, it can make a big
difference... we evaluate nearby drivers and riders in one batch") — so the 600/s, 45ms dispatch
figures are a disclosed modelling limit, not a hidden error, and should be kept. The `store` cost-
floor caveat is exemplary. I found NO public Uber figure for per_instance_rps or base_latency_ms on
any of the eight tiers; the anchors that exist are non-comparable (edge gateway "scaled up to 500K
QPS" globally, 19 May 2021; geofence 4,250 QPS/machine, 2016; CacheFront 6M RPS on ~3,000 Redis
cores ≈ 2k RPS/core, 15 Feb 2024; old fulfillment stack "only 20 online drivers/couriers per core",
29 Sep 2021). Against those the LB, queue, db and object-store figures sit in defensible bands.
Numbers verdict is therefore no_public_figure, not implausible — the one number contradicted by
evidence is the flat 100,000 rps charged to radius search, and that is a cost-model issue the file
already flags.

**Fix**

Three edits, all expressible in the existing engine — no new primitives.  (1) FIX THE ARITHMETIC IN
`workload` AND RE-SHARE THE FLOWS. State the check in the assumption itself: 1,800 req/s = 155.5M
rides/day versus Uber's global "more than 40 million trips every day" (Q4 2025, 4 Feb 2026). Move
the ping:request ratio from ~13:1 to ~400:1 — e.g. driver_ping 0.985, rider_request 0.006, match
0.006, trip_update 0.002, receipt 0.001 — and drop dispatch to 1 instance with a modest Postgres
primary. This makes the blueprint's own headline lesson ~30x stronger and arithmetically sound
instead of ~30x understated and impossible. It is the single highest-value edit.  (2) ADD THE READ
SIDE OF THE GEO INDEX. Add a `nearby_drivers` flow (rider app-open / map refresh) on lb → api →
cache, and give `match` a cache multiplier >1 for expanding-radius search, so reads exceed writes on
that component as Ranney describes. To price it without a spatial cost model, split the component
into `geo_write` (GEOADD-class, ~100,000 rps, 0.6 ms) and `geo_search`, sizing the latter from the
two verified real geo-read services: ~4,250 QPS/machine at 35% CPU with p95 <5ms / p99 <50ms (Uber
geofence, 24 Feb 2016) and P99 50ms at thousands of QPS (Uber Pinot+H3 orders-near-you, 20 Jul
2021). Cite both, and say plainly that geofence is a geo-config lookup rather than a driver radius
search so the reader knows the anchor is adjacent, not exact. This split is what moves the reported
bottleneck to where production actually put it.  (3) ADD A PUSH/STREAMING TIER, OR AT MINIMUM AN
ASSUMPTION EXCLUDING IT. One `push / streaming fan-out` component fed by trip_update and
driver_ping, with an assumption citing 1.5M concurrent connections / 250k messages per second and
the "80% of requests made to the backend API gateway were polling calls" line (18 Dec 2020). That
last figure is the strongest single piece of public evidence for this blueprint's own thesis and is
currently absent from a file that otherwise discloses its gaps well.  (4) OPTIONAL, SHAPE-HONESTY
ONLY: one sentence noting that real dispatch state is per-entity-serialized on a sharded stateful
service, not interchangeable stateless replicas — Ranney 2015, "They are building a stateful service
so stateless approaches to scaling won't work"; Ringpop application-level serialization (4 Feb
2016); measured at "only 20 online drivers/couriers per core" before the Spanner migration (29 Sep
2021). The engine cannot model this, so it belongs in assumptions, not components.  DO NOT CHANGE:
the per_instance_rps / base_latency_ms values (no public figures exist — say so rather than
inventing them), the disclosed 600/s-45ms dispatch approximation, or the `store` cost-floor caveat.

**Verified sources**

- https://highscalability.com/how-uber-scales-their-real-time-market-platform/
- https://www.infoq.com/presentations/uber-market-platform/
- https://www.uber.com/us/en/blog/go-geofence-highest-query-per-second-service/
- https://www.uber.com/en-GB/blog/orders-near-you/
- https://www.uber.com/us/en/blog/real-time-push-platform/
- https://www.uber.com/us/en/blog/ubers-next-gen-push-platform-on-grpc/
- https://www.uber.com/us/en/marketplace/matching/
- https://www.uber.com/gb/en/blog/ringpop-open-source-nodejs-library/
- https://www.uber.com/us/en/blog/h3/
- https://github.com/uber/h3
- https://www.uber.com/us/en/blog/schemaless-part-one-mysql-datastore/
- https://www.uber.com/us/en/blog/fulfillment-platform-rearchitecture/
- https://www.uber.com/ca/en/blog/building-ubers-fulfillment-platform/
- https://www.uber.com/us/en/blog/gairos-scalability/
- https://www.uber.com/us/en/blog/how-uber-serves-over-40-million-reads-per-second-using-an-integrated-cache/
- https://www.uber.com/blog/architecture-api-gateway/
- https://www.uber.com/us/en/blog/deepeta-how-uber-predicts-arrival-times/
- https://investor.uber.com/news-events/news/press-release-details/2026/Uber-Announces-Results-for-Fourth-Quarter-and-Full-Year-2025/default.aspx

### distributed_cache

- **shape:** misleading · **numbers:** no_public_figure

**What a reader would get wrong**

I DOWNGRADED 'wrong' to 'misleading'. A proxy-fronted sharded cache is a real production topology —
Meta's mcrouter is exactly that, and the blueprint labels the tier 'mcrouter/Envoy-style' — so the
shape is mismatched to the technology it names, not invented. But it IS a bottleneck defect,
confirmed by recomputation: lb 50.0%, proxy 75.0% (the declared bottleneck, matching peak_util
0.75), creplica 46.0%, cache primaries 6.8%, dbrep 67.5%, db 37.5%, q 25.0%. The reader is told to
scale a cache proxy tier that a Redis Cluster deployment does not have. The Redis Cluster
specification's first stated design goal is verbatim: 'High performance and linear scalability up to
1000 nodes. There are no proxies, asynchronous replication is used, and no merge operations are
performed on values.' The blueprint names components 3 and 4 explicitly 'Redis Cluster primary
shards' and 'Redis Cluster replica nodes (READONLY read scaling + failover)' — so it does claim
Redis Cluster for the cache tier while putting a memcached-family proxy in front of it. Compounding
this, 100% of GETs are routed to the READONLY replicas, which the spec says is legal but NOT the
default: 'Normally replica nodes will redirect clients to the authoritative master for the hash slot
involved in a given command, however clients can use replicas in order to scale reads using the
READONLY command. READONLY tells a Redis Cluster replica node that the client is ok reading possibly
stale data' — and the spec is explicit about the cost: 'Redis Cluster uses asynchronous replication
between nodes... There is always a window of time when it is possible to lose writes during
partitions.' That routing choice is what leaves the primaries at 6.8%, so the two tiers that could
actually bind — the primaries and the origin read replica at 67.5% on the 4% miss path — are shown
green or ignorable while an architecturally absent tier is named the constraint. The Kafka
invalidation bus adds a third layer of duplication: it fans writes to shards that Redis Cluster
already replicates asynchronously. ON NUMBERS, no_public_figure, and this is the sharpest finding.
The Redis node figures (100,000 ops/s) are well supported by redis.io's own benchmark page — 'SET:
180180.17 requests per second, p50=0.143 msec', 'LPUSH: 188323.91 requests per second, p50=0.135
msec', and '72144.87 requests per second' over a 100k random keyspace — so 100k is conservative and
fine. But the ONE number that determines the entire answer, the proxy's 25,000 ops/s per instance
(150,000 against 8 x 25,000 = exactly the declared 75%), has no public figure behind it. I checked:
Meta's mcrouter announcement (engineering.fb.com, 2014-09-15) says 'To a client, mcrouter looks like
a memcached server. To a server, mcrouter looks like a normal memcached client' and 'at peak,
mcrouter handles close to 5 billion requests per second' across 'thousands of cache servers across
dozens of clusters' — an aggregate only, with no per-instance rate published anywhere in it. The
blueprint does label the figure an assumption and calls it 'conservative', which is honest, but it
does not say that the declared bottleneck rests entirely on it. Two further gaps I verified as real
and structurally inexpressible in this model: stampede control (the Facebook memcache paper,
Nishtala et al., NSDI '13, introduces leases for exactly this, reporting that without leases a
susceptible key set drove 'a peak database query rate of 17K/s' versus '1.3K/s' with them) and
failure-path capacity (the same paper's Gutter pool 'accounts for approximately 1% of the memcached
servers in a cluster' and 'reduces the rate of client-visible failures by 99% and converts 10%-25%
of failures into hits each day'). Key-level skew is likewise unrepresentable — the paper notes 'a
single key can account for 20% of a server's requests' while the model spreads load uniformly across
3 shards. And nothing in the model represents memory, TTL or eviction, which is what actually sizes
a cache: the OSDI '20 Twitter study (Yang, Yue, Rashmi) of '153 in-memory cache clusters' found 'TTL
is an important and sometimes defining parameter of cache working sets'. ON PROPORTION I agree with
reasonable_simplification: 90/6/2/2 is a defensible teaching default, though real workloads are
bimodal rather than uniformly read-heavy — the same OSDI '20 abstract says 'many are far more write-
heavy or more skewed than previously shown', and twitter/cache-trace names them verbatim: 'write-
heavy workloads: cluster12, cluster15, cluster31, cluster37' among '54 clusters in Mar 2020'.

**Fix**

Pick one architecture and name it. If Redis Cluster: delete the proxy tier entirely, route GETs to
primaries by default (replicas only behind an explicit READONLY assumption that states the stale-
read consequence in the spec's own words), and drop the Kafka invalidation bus in favour of Redis's
built-in asynchronous replication. The bottleneck then honestly becomes the origin read replica on
the 4% miss path — which is the real and more useful lesson, since it is the tier a cache exists to
protect. If memcached: rename the cache tier to memcached, keep mcrouter, and either source the
25,000 ops/s figure or mark it ASSUMPTION with an explicit note that the declared bottleneck rests
entirely on an unsourced input. Either way, add TTL/memory as a stated sizing dimension so the
blueprint does not imply a cache is sized by rps.

**Verified sources**

- https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/
- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/
- https://engineering.fb.com/2014/09/15/web/introducing-mcrouter-a-memcached-protocol-router-for-scaling-memcached-deployments/
- https://www.usenix.org/conference/nsdi13/technical-sessions/presentation/nishtala
- https://www.usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf
- https://www.usenix.org/conference/osdi20/presentation/yang
- https://github.com/twitter/cache-trace

### dropbox

- **shape:** misleading · **numbers:** no_public_figure

**What a reader would get wrong**

SHAPE = MISLEADING, and I confirmed it by reproducing the engine's own arithmetic rather than taking
it on faith. The blueprint routes block downloads through the metadata tier: download_block = 0.25 x
40,000 = 10,000 rps charged to sync_api. Total sync_api load 18,000 / (16 x 1,500) = 0.75 — exactly
the declared peak_util, so the named bottleneck IS this wiring choice. Dropbox documents the
opposite: 'There are two types of servers relevant to this discussion: Block data server... Metadata
server' and 'The uploading client must talk directly with the blockserver in order to add these
blocks' (Streaming File Synchronization, 2014-07-10). Drago et al. independently MEASURED that
separation in the wild as three distinct client-facing subdomains — 'notifyX -> client notification,
client-lb/clientX -> meta-data control, dl-clientX -> Client storage', under the heading 'Clear
separation between storage and meta-data/client control' (IMC 2012 slides). Repoint block downloads
to their own tier and sync_api drops to 8,000/24,000 = 33% (50% if you also model the second commit
round trip). Notify, at 22,000/32,000 = 0.6875, then becomes the highest-utilised tier in the design
— the bottleneck FLIPS. That is decisive: this is not a simplification that leaves the teaching
point intact, it manufactures the teaching point, and it points the reader at the wrong tier. It
points them away from the exact tier Dropbox actually had to re-architect: 'Notification services
can now be implemented via streaming gRPC instead of an expensive long-poll method' (Nginx->Envoy,
2020-07-30). I am deliberately NOT counting the connection-vs-request modelling gap against the
blueprint — its `notify` assumption discloses that honestly and in detail ('the engine is an open
queueing network and cannot represent 10 million idle sockets... the real constraint on this tier is
file-descriptor/memory per connection, which this model does NOT capture'). That is exactly the
honesty the charter asks for. The defect is the block-path wiring, which is disclosed nowhere.
SECOND, SMALLER SHAPE ISSUE, correctly weighted as minor: the documented upload is commit -> 'need
blocks' -> upload -> commit again (two metadata round trips), modelled as one. NUMBERS = NO PUBLIC
FIGURE, and I am changing the researcher's 'plausible' to this because it is the more honest answer.
I opened every Dropbox source and NONE publishes per-tier rps or absolute latency. What exists is
aggregate or relative only: 'at least 300,000 requests per second' across '700M registered users'
(Atlas, 2021-03-04); Edgestore 'serving more than ten million requests per second' (2018-11-09);
Cape at '30K/s' events and '150K/s' jobs (deep dive, 2018-12-21); and for Magic Pocket strictly
deltas — 'a 2% increase in Magic Pocket's overall end-to-end write latency' (2022-12-08), with no
absolute figure anywhere in that post. So per_instance_rps 1,500/2,000 and base_latency_ms 12/4/25
cannot be graded against reality in either direction. Saying 'plausible' would imply a comparison I
could not actually make.

**Fix**

Two one-line flow edits, no new capacity math, and they flip the verdict to the right tier: (1) add
a `block_api` app_server and repoint download_block to it (cheaper alternative: drop
download_block's sync_api multiplier to ~0.1 to represent only the auth/blocklist lookup) — this
stops block traffic being charged to the metadata tier and moves the bottleneck onto notify, which
is where Dropbox's own history says it belongs; (2) set upload_block's sync_api multiplier to x2.0
for the documented commit -> need-blocks -> upload -> commit-again sequence. Optionally set
upload_block's store multiplier to x2.0, since 'Each block in MP is stored independently in at least
two separate zones' (Magic Pocket, 2016). Two lower-priority notes: the 10:1 block:commit ratio
(0.10 vs 0.01) implies a 40 MB average file, whereas Drago measured ~80% of storage flows carrying
<=10 chunks, so commit_batch is somewhat under-weighted; and add a one-line assumption that real
Dropbox metadata is sharded MySQL ('a service and abstraction over thousands of MySQL nodes',
2018-11-09), not one Postgres primary — cosmetic at this blueprint's 40k rps, where the primary sits
at 55%, but worth disclosing. Finally, add the caveat that Drago et al. measured client v1.2.52 in
2012 and Dropbox shipped a full sync-engine rewrite (Nucleus) on 2020-03-09, so the 2012
measurements evidence the tier SEPARATION, not today's internals.

**Verified sources**

- https://dropbox.tech/infrastructure/streaming-file-synchronization (2014-07-10) — opened; confirms verbatim '4MB blocks', 'Idle clients maintain a longpoll connection to a notification server', the per-namespace SFJ cursor (JID), the commit/'need blocks'/retry protocol, and separate block vs metadata servers
- https://dropbox.tech/infrastructure/inside-the-magic-pocket (2016-05-06) — opened; confirms 'up to 4 megabytes', 'a SHA-256 hash of the block', 'stored independently in at least two separate zones', 'The Block Index is a giant sharded MySQL cluster', and the Frontend dedup check on Put
- https://dropbox.tech/infrastructure/cross-shard-transactions-at-10-million-requests-per-second (2018-11-09) — opened; confirms Edgestore verbatim as 'a service and abstraction over thousands of MySQL nodes', 'more than ten million requests per second', and the caching layer absorbing 'upwards of 95% of client reads'
- https://dropbox.tech/infrastructure/how-we-migrated-dropbox-from-nginx-to-envoy (2020-07-30) — opened; confirms verbatim the move off 'an expensive long-poll method' to streaming gRPC, and 'tens of millions of open connections, millions of requests per second, and terabits of bandwidth'
- https://dropbox.tech/infrastructure/atlas--our-journey-from-a-python-monolith-to-a-managed-platform (2021-03-04) — opened; confirms 'at least 300,000 requests per second' and '700M registered users'
- https://dropbox.tech/infrastructure/introducing-cape (2017-05-17) — opened; confirms Kafka as transport, SFJ and Edgestore as change-event sources, and the four job types (previews/thumbnails, search indexing, third-party notification, audit indexing)
- https://dropbox.tech/infrastructure/cape-technical-deep-dive (2018-12-21) — opened; confirms '30 different event domains at a rate of 30K/s', '150K/s' jobs, '95% of events under 1 second'. NOTE: this page does NOT name Kafka/SFJ or the job types — those come from Introducing Cape, so the researcher's single-citation attribution had to be split across the two
- https://dropbox.tech/infrastructure/dropbox-traffic-infrastructure-edge-network (2018-10-10) — opened; confirms 'Dropbox has 20 PoPs around the world' and the GSLB tier
- https://dropbox.tech/infrastructure/optimizing-web-servers-for-high-throughput-and-low-latency (2017-09-06) — opened; confirms 'tens of gigabits per second while simultaneously processing tens of thousands latency-sensitive transactions'
- https://dropbox.tech/infrastructure/increasing-magic-pocket-write-throughput-by-removing-our-ssd-cache-disks (2022-12-08) — opened; confirms the '2% increase in Magic Pocket's overall end-to-end write latency' AND, importantly, that the post gives only relative deltas with no absolute latency or rps
- https://dropbox.tech/infrastructure/meet-chrono-our-scalable-consistent-metadata-caching-solution (2024-07-25) — opened; confirms Panda as the MVCC KV store and 'a key value (KV) cache system like Memcache or Redis' (both named as alternatives)
- https://dropbox.tech/infrastructure/rewriting-the-heart-of-our-sync-engine (2020-03-09) — opened; confirms the Nucleus rewrite shipped to all users, which dates the older sources
- https://research.spec.org/fileadmin/user_upload/documents/rg_cloud/DragoInsideDropbox.pdf — opened and text-extracted locally (the WebFetch returned raw PDF binary, so I ran pdftotext myself). This is the AUTHORS' IMC 2012 SLIDE DECK, not the paper — primary but a talk, and I am labelling it as such. Confirms the three subdomains, 'Clear separation between storage and meta-data/client control', 'Files are split in chunks of up to 4MB', '80%' of flows at '<= 10 chunks', 'download/upload ratio up to 2.4', notification connection 'Kept open', and client version v1.2.52 (2012)
- https://dropbox.github.io/dropbox-sdk-java/api-docs/v3.0.x/com/dropbox/core/v2/files/DbxUserFilesRequests.html — official Dropbox Java SDK. Fetched raw with curl and grepped, because the rendered fetch truncated. Confirms verbatim: 'A timeout in seconds... plus up to 90 seconds of random jitter added to avoid the thundering herd problem... Must be greater than or equal to 30 and be less than or equal to 480' and 'The timeout request parameter will default to 30L'
- https://help.dropbox.com/sync/lan-sync-overview — official; confirms LAN Sync forms 'a secure HTTPS connection directly to these other clients', 'UDP port 17500 for discovery' and 'TCP ports 17599-17609' for data

### ecommerce

- **shape:** misleading · **numbers:** no_public_figure

**What a reader would get wrong**

DEFECT (bottleneck-moving), on two grounds I verified. (1) NO EDGE TIER. Shopify's BFCM post (pub.
2025-11-20) reports actual BFCM 2024 production peaks: 'We peaked at 284 million requests per minute
on edge and 80 million on app servers' — 71.8% of requests never reach an app server. The blueprint
routes 100% of browse and search into the app tier, which is what manufactures its 80% app-tier
bottleneck. A reader asking 'how do I survive a flash-sale hour' is told, by the model's own
assumption block ('Ten instances is the sizing decision that keeps the tier at 80% at peak'), to add
app instances. The measured lever that removes ~70% of arrivals is not in the picture. (2) CHECKOUT
MIX IS 25-90x TOO HIGH, AND CHECKOUT IS NOT SEPARABLE. The blueprint sets checkout_order at 5% and
add_to_cart at 10% of 8,000 rps. Shopify's own scale test in the same post: 'By the fourth test, we
hit 146 million requests per minute and 80,000+ checkouts per minute' — 0.055% (the article does not
say which layer the 146M was measured at). Independently, Dynamo (SOSP 2007) reports the Shopping
Cart Service 'served tens of millions requests that resulted in well over 3 million checkouts in a
single day', i.e. ~10-30 cart operations per checkout, against the blueprint's 2:1. So the write
path is over-provisioned and the catalogue read path under-provisioned. Real systems also throttle
checkout at the edge rather than absorbing it: Shopify (2017-02-03) 'throttle users using a leaky
bucket algorithm built into our edge tier', serving a queue page 'cached in Nginx' — a lever the
fused 'Storefront + checkout API' tier cannot express. NOT DEFECTS, in fairness: serving
product_search from a read replica at 8,000 rps is a legitimate L0 simplification for a mid-size
retailer and does not move the bottleneck (the replica sits at ~16.5%) even though Dynamo §1 says
relational access for 'product catalog' scales poorly at Amazon's size; merging session and
catalogue cache is explicitly disclosed by the blueprint's own assumption, which I checked
arithmetically (5,600 browse + 1,200 search + 800 cart = the 7,600 req/s it names); and I decline
the researcher's demand for pod/shard routing — Shopify's Sorting Hat (2018-03-02) shards because it
is multi-tenant across millions of shops, which a single mid-size retailer's model has no reason to
copy. NUMBERS: no public figure exists for an m6i.large storefront instance's rps, so I will not
grade it implausible. But a provenance defect is verified: I counted the corpus myself and
per_instance_rps 8000 appears on a sql_db in 33 of 56 blueprints, 100000 on a cache in 26 of 56, and
8000 on a replica in 16 of 19 — these are shared class defaults, yet they are printed beside
specific instance names ('r7g.large', 'm6i.large x10'), which asserts a measurement the corpus does
not hold. For context on latency: Shopify's renderer, after a rewrite that made responses '4x to 6x
faster' (2020-08-20), still 'generates a response in less than ~45ms for 75% of storefront requests'
(2020-12-10) — the blueprint's 15 ms app base latency is optimistic against the only measured public
figure, though the scopes are not strictly comparable.

**Fix**

(1) Insert an edge/CDN full-page-cache component ahead of the app tier with an explicit, cited hit-
rate, so browse arrivals reach the app tier already reduced — Shopify's measured ratio is 284M edge
: 80M app req/min (BFCM 2024). (2) Re-weight the funnel: checkout well under 1% and add_to_cart
~1-2%, not 5% and 10%, citing the 80,000 checkouts/min against 146M req/min scale test and Dynamo's
~10-30:1 cart:checkout. (3) Split checkout out of the storefront tier, or at minimum state in the
bottleneck line that the real flash-sale control is an edge throttle on the checkout path (Shopify's
leaky bucket + Nginx-cached queue page, 2017), not more app instances. (4) Relabel every
per_instance_rps that is a class default as ASSUMPTION with a band, or cite a benchmark — 33/56
blueprints share sql_db 8000 and 26/56 share cache 100000, so the named instance types currently
imply grounding the corpus does not have.

**Verified sources**

- https://shopify.engineering/bfcm-readiness-2025
- https://shopify.engineering/surviving-flashes-of-high-write-traffic-using-scriptable-load-balancers-part-i
- https://shopify.engineering/simplify-batch-cache-optimized-server-side-storefront-rendering
- https://shopify.engineering/how-shopify-reduced-storefront-response-times-rewrite
- https://shopify.engineering/deconstructing-monolith-designing-software-maximizes-developer-productivity
- https://shopify.engineering/a-pods-architecture-to-allow-shopify-to-scale
- https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf
- https://www.amazon.science/publications/amazon-search-the-joy-of-ranking-products

### google_maps

- **shape:** misleading · **numbers:** plausible

**What a reader would get wrong**

TWO defects, both verified against primary sources; I downgraded the researcher's numbers verdict
from 'implausible' because most of this blueprint's figures are in fact the best-corroborated in the
corpus.  (1) THE DECLARED BOTTLENECK IS NOT A DETERMINATION. I recomputed every component myself and
reproduced the blueprint's own declared peak_util of 0.747 exactly: api 74.7%, cdn 72.0%, route
71.1%, db 70.0%, geo 66.7%, lb 37.3%, tiles 26.2%, q 8.0%, cache 5.6%. The top FIVE tiers sit inside
an 8.0-point band and the declared bottleneck leads the runner-up by 2.7 points — far inside the
uncertainty of per_instance_rps values the blueprint itself labels as assumptions. A reader is told
to 'add API frontends' (the most trivially horizontal tier in the design) when the model cannot
actually distinguish which of five tiers binds first. This is the strongest finding and it is pure
arithmetic, no external source needed.  (2) THE ROUTING TIER'S COST IS ATTACHED TO THE WRONG
MECHANISM. The blueprint asserts 45 ms is the cost of 'a contraction-hierarchies query over a
continental graph'. I extracted Table 1 of Bast et al. from the MSR-TR PDF: on exactly that instance
(Western Europe, 18.0M vertices, 42.5M arcs, single core of an Intel X5680 3.33 GHz) CH = 110.00
microseconds, CRP = 1,650.00, Arc Flags = 408.00, Dijkstra = 2,550,000.00. Table 2 adds path
retrieval and turn costs: CH 0.11 ms dist / 0.21 ms path without turns, 0.20/0.30 ms with arc-based
turns, 2.27/2.37 ms with the compact turn model; CRP 1.67/1.85 ms with the compact turn model. So
the named algorithm costs 0.2-2.4 ms — the blueprint's figure is 19x to 409x the cost of the
algorithm it names. Crucially I am NOT saying 45 ms is wrong for the TIER: a real traffic-aware
route response is plausibly tens of ms, because of a component the blueprint omits entirely. I
verified verbatim in arXiv:2108.11482 (CIKM 2021, DeepMind/Google): 'At serving time, the sequence
of supersegments that are in a proposed route are queried sequentially for increasing horizons into
the future', with 'a separate model for each horizon h', where 'segments are on average 50 - 100
meters long, and the supersegments contain on average about 20 road segments'. That is per-request
ML inference over the candidate path. So the value is defensible; the causal story is not. A reader
concludes path-search is expensive, builds the 60%-hit route cache to relieve it, and never
provisions the inference tier that actually earns the milliseconds.  I also verified the
researcher's negative claim, and found a better citation for it than they had. Bast et al. section
4: 'Although companies tend to be secretive about the actual algorithms they use, in some cases this
is public knowledge. TomTom uses a variant of Arc Flags... Microsoft's Bing Maps use CRP for routing
on road networks. OSRM... uses CH for queries. The Transfer Patterns algorithm has been in use for
public-transit journey planning on Google Maps since 2010.' So CH is documented for OSRM, CRP for
Bing; the only publicly-known Google Maps routing algorithm is Transfer Patterns, and only for
transit. Attributing CH to Google is uncited.  WHAT IS NOT A DEFECT, and deserves credit: the entire
tile path is strongly corroborated and should be upgraded from ASSUMPTION to GROUNDED. OSM's July
2025 operational figures (which I verified verbatim) are 92 billion tile requests/month, 36,770 rps
average, 70,669 rps peak hour, ~18 KB per tile, 1.26 PB/month, ~97% edge byte hit ratio and ~94%
request hit ratio, render-server local caches >95%. The blueprint assumes 28,800 tile rps, ~25 KB,
95% CDN hit, 1.8 PB/month. That is a near-exact match on four independent parameters. The shape of
the frontend is also right: Google's own security design doc states 'any internal service that must
publish itself externally uses the GFE as a smart reverse-proxy frontend. The GFE provides public IP
address hosting of its public DNS name, DoS protection, and TLS termination' — the blueprint's
lb+api pair. Both tile types are real per Google's docs ('generated by Google Maps Platform server-
side, then served to your web app' for raster; 'drawn at load time on the client-side using WebGL'
for vector). The probe bus is real: 'We then combine this database of historical traffic patterns
with live traffic conditions, using machine learning to generate predictions based on both sets of
data' (blog.google, 3 Sep 2020). The Redis cache figures (100,000 rps, 0.4 ms) are supported by
redis.io's own benchmark: 'SET: 180180.17 requests per second, p50=0.143 msec', and 72,144.87 rps
against a 100k random keyspace.  Secondary shape gap: the origin is modelled as a static object
store. Google states raster tiles are generated server-side, and OSM runs a renderd farm behind
Fastly (OSM wiki, ~1.5 PB/month and 118 billion requests/month for April 2026). The 'pre-rendered'
label makes this a defensible architectural choice rather than an error, but unlike the probe-
aggregation job — which the assumptions honestly flag as unmodelled — the tile-render/invalidation
workload is omitted without disclosure, so the design cannot answer what happens when the base map
changes. One naming nit: Google's geo database is built on S2 cells, not geohash — 'the core
geometric library on which Google's global geographic database is built' (Google Open Source Blog, 5
Dec 2017).

**Fix**

Four edits, none structural. (a) Add one honesty line to the bottleneck verdict: the top five
components span 8.0 points and the leader is ahead by 2.7, so the label identifies a CANDIDATE, not
a determination — this is the single highest-value fix and needs no research. (b) Split the routing
component: keep a cited sub-millisecond-to-low-ms path-search cost (Bast et al. 2016 Table 2: CH
0.21 ms with path retrieval, 0.30 ms with arc-based turns, 2.37 ms compact; CRP 1.85 ms with turns)
and add an explicit 'traffic-aware ETA inference' component citing arXiv:2108.11482, so the tens-of-
milliseconds lands on the tier that actually earns it. (c) Downgrade the CH-to-Google attribution to
ASSUMPTION and cite Bast et al. section 4, which documents CH for OSRM and CRP for Bing Maps, and
names Transfer Patterns as the only publicly-known Google Maps routing algorithm (transit only). (d)
Upgrade the tile-path assumptions from ASSUMPTION to GROUNDED against OSM's published July 2025
operational figures — 18 KB/tile, 94-97% edge hit, 36,770 rps average, 1.26 PB/month — which
corroborate the blueprint's 25 KB / 95% / 28,800 rps / 1.8 PB almost exactly. Optionally note that
OSM's measured peak:average ratio is 70,669/36,770 = 1.9, the only real map-shaped traffic ratio I
found.

**Verified sources**

- https://developers.google.com/maps/documentation/javascript/vector-map
- https://developers.google.com/maps/documentation/tile/2d-tiles-overview
- https://docs.cloud.google.com/docs/security/infrastructure/design
- https://opensource.googleblog.com/2017/12/announcing-s2-library-geometry-on-sphere.html
- https://github.com/google/s2geometry
- https://blog.google/products/maps/google-maps-101-how-ai-helps-predict-traffic-and-determine-routes/
- https://blog.google/products-and-platforms/products/maps/gemini-google-maps-navigation-updates/
- https://arxiv.org/abs/2108.11482
- https://arxiv.org/pdf/2108.11482
- https://arxiv.org/abs/1504.05140v1
- https://www.microsoft.com/en-us/research/wp-content/uploads/2014/01/MSR-TR-2014-4.pdf
- https://community.openstreetmap.org/t/technical-updates-to-the-tile-openstreetmap-org-service-openstreetmap-org-standard-layer/133421
- https://wiki.openstreetmap.org/wiki/Servers/Tile_Rendering
- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/

### instagram_clone

- **shape:** misleading · **numbers:** implausible

**What a reader would get wrong**

Two independently verified defects, both of which change where a reader thinks their bottleneck is.
(1) THE DECLARED BOTTLENECK IS RIGHT ONLY BECAUSE TWO LARGE ERRORS CANCEL. I re-ran the model's own
arithmetic: media workers 150/(18x12) = 69.4% (matches the file's peak_util 0.694), API tier
9300/(8x1800) = 64.6%. The bottleneck is declared on a 4.8-point margin. The media assumption says
one upload is '~4 image renditions, or a short-video transcode' and that a 2-vCPU instance clears
~12 of those per second — a budget of 0.167 CPU-seconds per upload. Meta's own published measurement
(engineering.fb.com, 4 Nov 2022) is '86.17 seconds of CPU time to transcode a 23-second video to
720p', i.e. 517x the budget; even their optimised path that merely repackages an existing encode is
'0.36s user 2.22s system' = 2.58 CPU-s, still 15x the budget. On the image path, Flickr's published
CPU figure (code.flickr.net, 25 Jun 2015) of 'over 225ms to resize a 2048px JPEG down to 1600px' x4
renditions = 0.9 CPU-s, 5.4x the budget. Meanwhile the 1% upload share is far too high: Instagram's
own 2016 figures are 4,200,000,000 likes every day (Carl Meyer, 'Instagram Under The Hood', Django
Under The Hood, Nov 2016 — I extracted the slide and read it: '4,200,000,000' over a heart, 'EVERY
DAY') against '95 million per day' photos and videos shared (TechCrunch, 21 Jun 2016, from
Instagram), a 44:1 likes-to-upload ratio where the blueprint gives engage:upload only 6:1. Fixing
either dial alone gives the wrong answer: correct the share to 0.1% and media workers fall to 6.9%
while the API tier binds at 63.7%; correct the capacity to Flickr's image figure and the 18-instance
fleet has 40 rps of real capacity against 150 rps of load — already 375% over, before any video
reaches it. A reader who trusts this sizes an 18-instance fleet that is either 10x too big or 4x too
small, and cannot tell which.  (2) THE UPLOAD PATH HAS NO FEED-DISTRIBUTION STEP, AND THAT OMISSION
IS UNDISCLOSED. upload_post is lb -> api -> store -> db -> q -> media and stops; nothing writes to
followers. Rick Branson (Instagram), 'Messaging at Scale at Instagram', PyCon US 2013, names the
async workload as 'Feed distribution, social sharing, spam and malicious user detection, search
indexing' on 'RabbitMQ & Celery' at 'thousands of tasks every second' — feed distribution is fan-
out-on-write and is the flagship async task. The blueprint instead reads the feed from Redis with a
15% fallthrough to replicas (fan-out-on-read). That is a legitimate architecture, but at the
modelled 150 uploads/s a modest 200 followers/post is 30,000 feed-row writes/s, 3.8x the entire
modelled Postgres primary capacity of 8,000 rps — and 200x the load the model puts on Kafka, which
sits at 0.167% utilisation. The component does not exist, so the engine cannot flag it. The scope
assumption explicitly excludes Stories, DMs, Reels and ranking but never mentions fan-out, so the
reader is not told that the largest scaling decision in a photo-social system has been silently
taken for them. This is a disclosure defect under the repo's own honesty charter, not merely a
simplification.  (3) COST, NOT BOTTLENECK: media_fetch (38%) against feed_scroll (42%) is 0.90 CDN
object GETs per feed API call. A feed response returns a batch of posts each needing at least one
image plus an avatar, so the real ratio is an order of magnitude higher. This is an internal-
consistency finding from the file itself (system_rps mixes API calls and CDN GETs into one
denominator), not a sourced claim — I found no published Instagram photo-fetches-per-feed-request
ratio. It does NOT move the bottleneck (raising media_fetch to 85% leaves the CDN at 8.5% and the
object store at 6.4%), but the blueprint prices egress off this volume and calls the GB/month 'the
engineering claim', so the delivery cost line is understated by roughly 10x.  What I am NOT counting
as a defect, in fairness at L0: modelling Kafka instead of Celery/RabbitMQ (a defensible stand-in);
one unsharded primary instead of thousands of logical Postgres shards (the DUTH deck's 'LOGICAL
SHARDS (PG SCHEMAS) -> PHYSICAL SERVERS' slides confirm the real design, but at 15k rps a single
primary is a fair simplification and the db assumption already discloses the single-writer choice
honestly); collapsing Memcached and Redis into one cache entity (the deck shows both, with multi-
region invalidators, but this does not change any utilisation); and the absent ML ranking tier,
which the scope assumption discloses explicitly and correctly.

**Fix**

Four input changes, no engine change.  (1) FIX THE CAPACITY AND THE SHARE IN THE SAME EDIT — they
currently cancel, so fixing one alone makes the model worse. Replace '12 uploads/s per 2-vCPU
instance' with a cited per-upload CPU cost and let the engine derive the fleet: ~0.9 CPU-s for four
image renditions (Flickr, 225ms per GraphicsMagick resize, 25 Jun 2015) or 86.17 CPU-s for a 23s
720p video transcode (Meta, 4 Nov 2022). At the same time cut upload share from 1% to ~0.1%.  (2)
SPLIT THE MEDIA ASSUMPTION IN TWO. 'four image renditions OR a short-video transcode' spans a 100x
range in CPU cost; one per_instance_rps cannot honestly cover both. Either drop the video clause and
model an image-only pipeline, or add a separate transcode component with its own rate. As written
the assumption's own words make its own number wrong by ~500x.  (3) ADD A FAN-OUT WORKER between the
queue and a feed store on upload_post, with an explicit followers-per-post multiplier, and put a
wide-column feed store behind feed_scroll. If the intent really is fan-out-on-read, say so in an
assumption naming the alternative and its write-amplification cost — this is the one change that
alters what a reader learns. Cite PyCon 2013's 'Feed distribution' as the real pattern.  (4) SPLIT
THE DENOMINATOR. system_rps mixes API calls and CDN object GETs, which makes every share
incomparable to any published figure. Either give the CDN tier its own rate, or set media_fetch to
~10x feed_scroll and re-derive egress. Also raise engage relative to upload toward Instagram's own
44:1 (4.2B likes/day vs 95M media/day, 2016) rather than 6:1.  Two secondary number corrections:
object store base_latency_ms 20 against AWS's own published 'consistent small object latencies ...
of roughly 100-200 milliseconds'; and note that 20,000 rps on one object store needs prefix
parallelism, since AWS publishes 'at least 3,500 PUT/COPY/POST/DELETE or 5,500 GET/HEAD requests per
second per partitioned Amazon S3 prefix' (this one is a disclosure note, not an error — there is no
limit on prefix count).

**Verified sources**

- https://engineering.fb.com/2022/11/04/video-engineering/instagram-video-processing-encoding-reduction/ — PRIMARY, 4 Nov 2022. Opened; confirms verbatim '86.17 seconds of CPU time to transcode a 23-second video to 720p' and the optimised '0.36 seconds' / 2.22s system repackaging path.
- https://us.pycon.org/2013/schedule/presentation/106/ — PRIMARY (talk by an Instagram engineer), PyCon US 2013. Opened; confirms Rick Branson, 'Messaging at Scale at Instagram', async use cases 'Feed distribution, social sharing, spam and malicious user detection, search indexing', 'Then: Gearman / Now: RabbitMQ & Celery', and 'thousands of tasks every second'.
- https://simpleisbetterthancomplex.com/media/2016/11/instagram.pdf — PRIMARY artifact on a third-party mirror: Carl Meyer, 'Instagram Under The Hood', Django Under The Hood 2016. Opened AND extracted the PDF directly; the 'Today!' slide reads Proxygen / Django & uWSGI / TAO / Cassandra / Everstore / Celery & RabbitMQ; separate slides show 'LOGICAL SHARDS (PG SCHEMAS) -> PHYSICAL SERVERS' over USERS/MEDIA/LIKES/COMMENTS, Memcached with per-datacenter Invalidators ('MULTI-REGION CACHE INVALIDATION'), and '500M+ Instagrammers'. Page 5 rendered to image confirms '4,200,000,000' + heart + 'EVERY DAY' (likes/day).
- https://techcrunch.com/2016/06/21/instagram-500-million/ — SECONDARY (news reporting Instagram's own announcement), 21 Jun 2016. Opened; confirms 500M MAU, 300M DAU, and '95 million per day' photos and videos shared. It does NOT contain any likes-per-day figure (see dropped_claims).
- https://engineering.fb.com/2013/06/25/core-infra/tao-the-power-of-the-graph/ — PRIMARY, 25 Jun 2013. Opened; confirms 'over a billion read requests and millions of write requests every second' and TAO as a graph store fronting MySQL.
- https://sigops.org/s/conferences/sosp/2013/papers/p167-huang.pdf — PRIMARY paper, Huang et al., SOSP 2013. Opened and text-extracted; confirms the request shares '65.5% browser cache, 20.0% Edge Cache, 4.6% Origin Cache, and 9.9% Backend storage', '~20 PoPs' ('as of this study there are nine high-volume Edge Caches'), and that 59.2% is specifically 'the observed hit ratio for San Jose' — a per-PoP measurement, not a global average.
- https://engineering.fb.com/2014/02/27/web/an-analysis-of-facebook-photo-caching-2/ — PRIMARY, 27 Feb 2014. Opened; confirms 'the Haystack backend only needs to serve 9.9% of requested photos' and 'increase the edge cache hit ratio from 59.2% to 67.7%'.
- https://engineering.fb.com/2019/01/17/developer-tools/spectrum/ — PRIMARY, 17 Jan 2019. Opened; confirms on-device resize/crop/recompress before upload and the sentence 'the content delivery network (CDN) will resize the image for the recipient anyway'.
- https://code.flickr.net/2015/06/25/real-time-resizing-of-flickr-images-using-gpus/ — PRIMARY, 25 Jun 2015. Opened; confirms 'takes over 225ms to resize a 2048px JPEG down to 1600px' (the CPU figure used to price image renditions).
- https://engineering.fb.com/2023/08/09/ml-applications/scaling-instagram-explore-recommendations-system/ — PRIMARY, 9 Aug 2023. Opened; confirms the four-stage retrieval / lightweight Two Tower / heavy MTML on ~100 candidates / reranking funnel and off-peak precomputation. Cited only to confirm the blueprint's scope exclusion is a real omission, honestly disclosed.
- https://www.cs.princeton.edu/~wlloyd/papers/tectonic-fast21.pdf — PRIMARY paper (author-hosted), Pan et al., FAST 2021. Opened and text-extracted; confirms Tectonic has been 'completely replacing Haystack, f4, and HDFS', and that pre-Tectonic blob storage 'was spread across Haystack and f4'.
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html — PRIMARY vendor docs, current. Opened; confirms 'at least 3,500 PUT/COPY/POST/DELETE or 5,500 GET/HEAD requests per second per partitioned Amazon S3 prefix', 'There are no limits to the number of prefixes in a bucket', and 'consistent small object latencies (and first-byte-out latencies for larger objects) of roughly 100-200 milliseconds'.

### kafka_broker

- **shape:** misleading · **numbers:** plausible

**What a reader would get wrong**

CONFIRMED, and it is a bottleneck error, not a simplification. I recomputed every tier from the
JSON: lb 55.6%, prod 68.8%, schema 59.4%, broker 71.4% (matches the declared peak_util 0.714), ctrl
14.1%, cons 68.8%, tier 36.4%, store 55.0%. Two independent errors push the same way. (a)
REPLICATION IS ABSENT FROM THE BROKER'S LOAD. AWS's own sizing equation is verbatim 'tEC2network =
tcluster/#brokers * (#consumer groups + r-1)' (AWS Big Data Blog, 2022-03-17, reviewed/updated Nov
2025), so at RF=3 with one consumer group a broker carries ~3x its client-visible ingress. The
blueprint charges the broker 200,000 client-visible msg/s against 14 x 20,000 = 280,000. Add the two
follower fetches on the 110,000 produce share and the broker is at roughly 420,000/280,000 = ~150% —
over capacity, not the comfortable 71% shown. The blueprint's own assumption partially discloses
this but scopes it to 'the disk path' and says 'Disk/IO capacity is NOT modelled'; AWS's equation is
about NETWORK and CPU, so the disclosure does not cover the actual shortfall. (b) THE TRAFFIC MIX IS
INVERTED. LinkedIn's own write-up (engineering.linkedin.com, 2015-03-20) states verbatim 'over 800
billion messages per day which amounts to over 175 terabytes of data' and 'Over 650 terabytes of
messages are then consumed daily' — 3.7:1 consume:produce. The blueprint is 55% produce / 40%
consume, i.e. 0.73:1, backwards. This one MOVES THE BOTTLENECK: re-run at 25/70 and the consumer
tier goes to ~148,000 against 16 x 8,000 = 128,000 (~116%), overtaking the broker as the binding
constraint. NOTE the 2015 figures are eleven years old; LinkedIn's 2019 update
(linkedin.com/blog/engineering, 2019-10-08) reports '7 trillion per day', 'over 100 Kafka clusters',
'more than 4,000 brokers', '7 million partitions' but does not restate the byte ratio. Two further
shape errors that do NOT move the bottleneck but do waste money and teach wrongly: the Schema
Registry is charged 5% of 200k msg/s (9,500 rps) when confluentinc/schema-registry's
CachedSchemaRegistryClient holds 'private final Cache<String, Cache<Integer, Schema>>
idToSchemaCache' and short-circuits with 'Schema cachedSchema = idSchemaMap.getIfPresent(id); if
(cachedSchema != null) { return cachedSchema; }' before any REST call — steady-state registry
traffic is near zero, so 4 instances at 59% util is provisioning for load that does not exist. And
tiered storage is charged one S3 GET per replayed 1 KB message (8,000 GET/s, 36% of four prefixes)
when AWS MSK states 'Data between brokers and the tiered storage moves within the VPC' and that
after the first bytes 'you can expect latencies that are similar to the primary storage tier' —
brokers fetch whole segments and consumers never address S3, so the model makes 'how many S3
prefixes' look like a design variable it is not. Finally admin_metadata runs lb -> ctrl -> broker,
which is backwards: Confluent's KRaft docs say 'The active controller handles all RPCs made from the
brokers' and that 'Client configurations are not impacted by Confluent Platform moving to KRaft';
clients address brokers, and Confluent's CFK docs say 'the client finds the address of the broker it
is interested in and connects directly to the broker to produce or consume data'. On SCALE NUMBERS I
grade plausible: 20,000 msg/s per broker sits between AWS's guidance (a three-node m7g.large cluster
at RF=3 with two consumer groups is held to '63 MB/sec' of cluster ingress, i.e. ~21 MB/s ~= 21,000
1KB msg/s per broker) and Confluent's OMB result on 3 x i3en.2xlarge, 1 KB messages, 100 partitions,
RF=3, acks=all, min.insync.replicas=2 reaching 605 MB/s peak (~200 MB/s per broker) with 'p99
Latency (ms) 5 ms (200 MB/s load)' (2020-08-21). But note the accounting mismatch: AWS's ~21k is
INGRESS ONLY and already nets out RF and consumer groups, whereas the blueprint spends its 20,000 on
produce AND consume with no RF. The per-broker number is defensible; the way it is charged is not.
One more missing dimension worth naming: MSK sizes brokers by PARTITIONS, not rps — its table gives
1,000 recommended (1,500 max for update operations) per kafka.m5.large or kafka.m7g.large — and
partition count appears nowhere in the model.

**Fix**

Three edits in priority order. (1) Charge the broker for replication: add an explicit follower-fetch
flow at share x(RF-1) of produce, or divide the broker's effective per-instance capacity by
(#consumer_groups + RF - 1), citing the AWS equation verbatim. Until this lands, the 71.4% headline
is the single most dangerous number in the blueprint. (2) Invert the produce/consume shares to
roughly 25/70 (or add a second consumer-group flow) and add an assumption citing LinkedIn's 175 TB
in vs 650 TB out, dated 2015 with the note that the 2019 update does not restate the ratio; then re-
derive the consumer tier's instance count, because it becomes the bottleneck. (3) Set the schema
visit_prob to ~0.0 with an assumption citing CachedSchemaRegistryClient's idToSchemaCache short-
circuit; change the tiered-storage visit from per-message to a segment-fetch rate citing MSK's in-
VPC broker-side fetch; and reverse admin_metadata to lb -> broker -> ctrl. Optionally add partitions
per broker as a stated sizing input (MSK: 1,000 per m5.large/m7g.large) since rps alone cannot size
a Kafka cluster.

**Verified sources**

- https://engineering.linkedin.com/kafka/running-kafka-scale
- https://www.linkedin.com/blog/engineering/open-source/apache-kafka-trillion-messages
- https://aws.amazon.com/blogs/big-data/best-practices-for-right-sizing-your-apache-kafka-clusters-to-optimize-performance-and-cost/
- https://docs.aws.amazon.com/msk/latest/developerguide/bestpractices.html
- https://docs.aws.amazon.com/msk/latest/developerguide/msk-tiered-storage.html
- https://docs.confluent.io/operator/current/co-loadbalancers.html
- https://docs.confluent.io/platform/current/kafka-metadata/kraft.html
- https://github.com/confluentinc/schema-registry/blob/master/client/src/main/java/io/confluent/kafka/schemaregistry/client/CachedSchemaRegistryClient.java
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html
- https://www.confluent.io/blog/kafka-fastest-messaging-system/

### rate_limiter

- **shape:** misleading · **numbers:** plausible

**What a reader would get wrong**

Two findings, and I separated them because they fail different tests. FINDING ONE — THE DECLARED
BOTTLENECK IS NOISE, AND IT IS OUT OF SCOPE. I recomputed every tier from the JSON and reproduce the
researcher's figures exactly: lb 74.925%, gateway 74.925%, limiter service 75.0%, Redis 75.0%,
protected upstream 77.4% (matching peak_util 0.774), policy DB 1.9%. Five tiers inside a 2.5-point
band. The engine names 'Protected upstream API' as the bottleneck, but any small change to any input
reorders the top five, so the reader takes a confident single-tier answer from what is really a
flat, uninformative result. Worse, the tier it names is the reader's own application — the thing
being protected — not the rate limiter being designed. This is the finding that meets the stated
defect standard: it misleads about where the bottleneck is. FINDING TWO — THE BLUEPRINT'S HEADLINE
LESSON IS CONTRADICTED BY THE REFERENCE IMPLEMENTATION OF THE PRODUCT IT NAMES. The assumption block
states: 'the 7% still costs the limiter and Redis a full round trip, and only the upstream is
spared. That is why rejecting traffic does not make a rate limiter free.' That is true for the
request that first trips a bucket and false for the sustained abuser that motivates building one.
The blueprint's gateway is 'Envoy API gateway (self-hosted)', and Envoy's own global rate limiting
docs prescribe the opposite design verbatim: 'Local rate limiting can be used in conjunction with
global rate limiting to reduce load on the global rate limit service. For example, a local token
bucket rate limit can absorb very large bursts in load that might otherwise overwhelm a global rate
limit service... The initial coarse grained limiting is performed by the token bucket limit before a
fine grained global limit finishes the job.' Envoy's own reference service goes further —
envoyproxy/ratelimit states 'Ratelimit optionally uses freecache as its local caching layer, which
stores the over-the-limit cache keys, and thus avoids reading the redis cache again for the already
over-the-limit keys.' Cloudflare does the same at the edge (blog.cloudflare.com, 2017-06-07): 'once
a server starts to mitigate a client, it will not even run another query for the subsequent requests
it might see from that source', with counters kept per-PoP ('we created a Twemproxy cluster inside
each of our PoPs') and incremented asynchronously. So the standard mitigation for the exact
fragility the blueprint elsewhere flags is the thing the blueprint teaches against. IMPORTANTLY, I
checked whether this moves the bottleneck and it does NOT: strip the 7% throttled share off Redis
and it falls from 75.0% to 69.8%, leaving the ordering unchanged. So this is a wrong taught rule,
not a misdirected reader — I am reporting it as a correctness defect in the lesson, and grading
shape 'misleading' on FINDING ONE, not this. ON SCALE NUMBERS I grade plausible and I TRIMMED the
researcher here. Its claim that a token bucket 'benchmarks nearer 70,000' rests on redis.io's line
'script load redis.call('set','foo','bar'): 69881.20 requests per second' — but that benchmarks
SCRIPT LOAD, i.e. repeatedly parsing and registering a script, not EVALSHA-executing a cached one.
redis.io publishes no EVALSHA or token-bucket benchmark, so the inference does not hold and I
dropped it. Its companion claim about 'thousands of gateway connections' is also not derivable from
the model, which has 4 gateways and 40 limiter instances. What IS verbatim and does apply as a
caution: 'an instance with 30000 connections can only process half the throughput achievable with
100 connections' and 'In many real world scenarios, Redis throughput is limited by the network well
before being limited by the CPU.' Against plain SET at 180,180 rps and 72,144 rps over a 100k random
keyspace, 100,000 ops/s for authoritative counter work is in-band and defensible. For context on
real rejection volumes, Stripe (2017-03-30) confirms the algorithm — 'We use the token bucket
algorithm to do rate limiting' implemented 'using Redis' — but runs FOUR distinct limiters (request
rate, concurrent requests, fleet usage load shedder, worker utilization load shedder) where this
model has one, and its published rejections are tiny relative to volume: 'millions of requests this
month alone' for the request limiter, '12,000 requests this month' for concurrent requests, 'Only
100 requests were rejected this month' for the worker utilization shedder. A fixed 7% throttle share
is a plausible teaching default but sits well above Stripe's steady state and well below
Cloudflare's attack case of 'as many as 400,000 requests per second to a single domain'.

**Fix**

Priority one, fix the flat result: either drop the protected upstream from the model or state
explicitly that it is out of scope, so the named bottleneck is a component of the rate limiter
itself; and where the top tiers sit within a few points of each other, the report should say so
rather than name one winner. Priority two, fix the lesson: add the local first-stage limiter as a
component in front of the shared Redis (Envoy's documented two-stage pattern) and give the
throttled_request flow cache(x0.05) or lower instead of x1.0, with an assumption citing
envoyproxy/ratelimit's freecache and Cloudflare's local mitigation cache. Then rewrite the
throttling assumption — the honest version is that the FIRST rejection costs a full round trip while
a sustained abuser is short-circuited locally, which is a sharper lesson than the one currently
there. Do NOT lower the Redis rate to ~70,000 on the strength of the script-load benchmark; that
figure measures script registration, not execution, and no published EVALSHA figure supports the
change.

**Verified sources**

- https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/other_features/global_rate_limiting
- https://github.com/envoyproxy/ratelimit
- https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
- https://stripe.com/blog/rate-limiters
- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/

### search_engine

- **shape:** misleading · **numbers:** plausible

**What a reader would get wrong**

Which tier fails first. The blueprint names the index shard fleet as the bottleneck at 78.5% and
shows the document store comfortable at 69.1%. I reproduced both figures exactly from the file
(index 6,910/8,800 = 0.785; db 6,910/10,000 = 0.691), so the ranking is decided by a ~9-point
margin. That margin is an artefact of an inconsistency inside the blueprint itself: the `index`
assumption explicitly declares that fan-out is folded into the capacity input ('a query scatter-
gathers across all 10 shards... the fan-out is folded into the capacity input and declared here
instead of being hidden'), and then the `db` assumption silently drops the same treatment, calling
the snippet phase 'a point lookup by document id' (singular) served by 'a single PostgreSQL node'.
The snippet phase is one lookup PER RESULT, not per query. I computed the sensitivity: the doc tier
passes the index tier at only k = 1.14 lookups per query and saturates (rho >= 1) at k = 1.47. So
for any realistic results-per-page the doc tier is the binding constraint, and at k = 10 it sits at
655%. This is not a simplification, it is an inverted verdict — and it inverts it on the largest
fleet in the real system. Barroso/Dean/Holzle (IEEE Micro, Mar-Apr 2003), which I extracted and
read: docservers are 'partition[ed]... by randomly distributing documents into smaller shards', with
'multiple server replicas responsible for handling each shard' behind 'a load balancer'; 'The
docserver cluster must have access to an online, low-latency copy of the entire Web. In fact,
because of the replication required for performance and availability, Google stores dozens of copies
of the Web across its clusters'; and 'Index servers typically have less disk space than document
servers'. Keystone models that fleet as instances: 1, kind: sql_db. Second, smaller defect: the
autocomplete share. The blueprint puts autocomplete at 5% of 20,000 rps against 18,600 searches/s =
0.054 autocomplete requests per search. Keystone's own typeahead blueprint states in its workload
assumption that 'a user typing an eight-character query issues five or six requests'. The two files
in the same library disagree by 102x on the same ratio, and Monaco (WTMC 2019) measured directly
that on Google, Baidu and Yandex 'an HTTP GET request is made upon each key press that results in a
visible change to the query input field'. Correcting the share to even 5x searches puts the query
frontend at 429% and relocates the bottleneck to the front door.

**Fix**

Two edits, both small. (1) Split 'Document store (titles, snippets, metadata)' from a single sql_db
into a docid-sharded, replicated doc-server fleet, and apply the fan-out convention the index row
already declares: state its capacity in QUERIES/s with the ~10-results-per-query fan-out folded in
and named in the assumption block. Sizing check to include: the tier passes the index fleet at k =
1.14 and saturates at k = 1.47, so a single node is unsound for any k > 1.5. (2) Delete the
autocomplete flow and point at the typeahead blueprint (cleaner than re-sizing it, and it is how the
real system is split), or raise the share to reflect per-keystroke traffic — either way the two
blueprints must stop contradicting each other by 102x. One further line worth adding: the 65%
result-cache hit rate sits above the top of the only Google-published band — Dean's WSDM 2009
keynote says cache servers 'cache both index results and doc snippets - hit rates typically 30-60%',
and names 'level of personalization' as one of the three drivers. The blueprint itself says this
number 'is the difference between 22 index machines and 63 of them'; I verified that at a 45% hit
rate the fleet goes 22 -> 34 nodes at the same 78.5% target. Not fatal, but it is the load-bearing
input and it is cited to nothing.

**Verified sources**

- https://static.googleusercontent.com/media/research.google.com/en//archive/googlecluster-ieee.pdf
- https://research.google/pubs/web-search-for-a-planet-the-google-cluster-architecture/
- https://static.googleusercontent.com/media/research.google.com/en//people/jeff/WSDM09-keynote.pdf
- https://www.barroso.org/publications/TheTailAtScale.pdf
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html

### slack_discord

- **shape:** misleading · **numbers:** plausible

**What a reader would get wrong**

SUSTAINED at 'misleading', and I can now state the failure threshold exactly. I recomputed every
utilisation from the JSON and reproduce the file's own headline (REST API 74%, gateway 70%), so the
numbers below are the model's, not an approximation of it.  DEFECT 1 — THE WORKLOAD ASSUMPTION
CONTRADICTS THE MODEL BY ~50x, AND THE CONTRADICTION IS WHAT PICKS THE BOTTLENECK. The assumption
reads: 'one message sent to a 200-member channel is one write and up to 200 gateway events, so the
fan-out flow is 55% of all work while sends are 15%.' The word 'so' presents 55/15 as the
consequence of the 200:1 example. But 55/15 of 40,000 ops/s is 22,000 events against 6,000 sends — a
fan-out ratio of 3.67:1. At the stated 200:1, 6,000 sends/s would be 1.2M events/s, not 22,000.  I
computed the tipping point: gateway utilisation equals the REST API's 74% at 26,640 arrivals, i.e.
23,440 fan-out events over 6,000 sends = a ratio of 3.91:1. So the model's entire verdict —
'bottleneck: REST API', 74% — holds only for fan-out below ~3.9 recipients per message. That is DM
traffic. Above it, the gateway binds. At a still-modest 20:1 the gateway takes 120,000 events/s
against 12 x 3,000 = 36,000 capacity, i.e. 333% utilisation, and the REST API is no longer in the
conversation.  Real anchors bracket the range and both sit above the threshold: WhatsApp's DM-heavy
peak is 2.08:1 (712K out / 342K in, 2014), and Discord's own worked example for a channel product is
1000:1 — 'If a server has 1000 people online, and they all were to say "I love jello" once, that's 1
million notifications' (25 Oct 2023). A blueprint named 'Slack / Discord' models the DM end of that
range while its own prose claims the channel end. The takeaway a reader carries is 'scale by adding
stateless REST API boxes'; both companies published the opposite.  DEFECT 2 — THE ONE TIER WHOSE
CAPACITY DOES NOT ADD IS THE ONE THAT WAS COLLAPSED, WITH NO CAVEAT. Slack's Channel Servers are
'stateful and in-memory, holding some amount of history of channels', owned via a consistent hash
ring whose managers (CHARMs) replace an unhealthy instance in 'under 20 seconds'; the send path is
Webapp -> Admin Server -> (hash-ring lookup) -> Channel Server -> every subscribed Gateway Server
worldwide -> clients (Sameera Thangudu, 11 Apr 2023). 'At peak times, about 16 million channels are
served per host.' On Discord's side the same role is the per-guild process, where 'publishing an
event from a large guild could take anywhere from 900ms to 2.1s' (6 Jul 2017), later relieved by
relays handling 'up to 15,000 connected sessions per relay' and by passive sessions, since 'around
90% of user-guild connections in large servers were passive' (25 Oct 2023). The blueprint collapses
all of this into 'Gateway servers (WebSocket fan-out to clients)', a stateless app_server pool of 12
whose capacity adds linearly — precisely the property the real tier lacks. You cannot add instances
to relieve one hot channel; you shard the actor.  What makes this a defect rather than an L0
simplification is that the SIBLING BLUEPRINT DOES IT RIGHT. realtime_chat's `db` assumption says in
as many words: 'A single hot conversation lands on one shard and the engine will not show that
hotspot.' slack_discord's `ws` and `db` assumptions carry no such hot-key caveat. The collapse is
defensible; collapsing it silently, in the one blueprint where fan-out is the whole product, while
the repo demonstrably knows how to write that caveat, is not.  DEFECT 3 — MISLABELLED STORE, AGAIN
WITHOUT THE SIBLING'S DISCLOSURE. The component is 'PostgreSQL message store (sharded by channel)'.
Slack runs MySQL under Vitess — 'median query latency is 2 ms, and our p99 query latency is 11 ms',
'2.3 million QPS at peak. 2M of those queries are reads and 300K are writes' (1 Dec 2020). Discord
runs 72 ScyllaDB nodes since May 2022, partitioned by 'the channel they're sent in, along with a
bucket, which is a static time window', with p99 insert improving from '5-70ms' to '5ms' (6 Mar
2023). No production system in this class chose Postgres. The shard key is exactly right; the
engine's kind is not. realtime_chat handles the identical situation honestly — 'Production chat
systems use a wide-column store (Cassandra/ScyllaDB) for this; sql_db is the closest kind Keystone
models' — and this file simply omits that sentence.  SCALE NUMBER I DERIVED MYSELF, WHICH THE
RESEARCHER MISSED. Discord runs 'more than 26 million WebSocket events to clients per second' on
'400-500 Elixir machines' (elixir-lang.org interview with Jake Heinz, 8 Oct 2020) = ~58,000 events/s
per machine, and that machine count covers sessions AND guild processes, so the true per-gateway
rate is higher still. The blueprint's gateway is 3,000 events/s per instance — roughly 19x
conservative against the only published comparable. This sharpens the researcher's 'two errors
cancel' claim into something checkable: fan-out understated ~50x against the file's own prose, per-
gateway capacity understated ~19x against Discord, and the plausible-looking 70% gateway utilisation
is the residue. I keep the numbers verdict at 'plausible' rather than 'implausible' only because
'instance' is undefined in the model and a Discord Elixir machine is a large cloud host — the two
are not strictly comparable.  DOWNGRADED — NOT DEFECTS. (i) The datastore read:write inversion
(model 2,100 replica reads against 6,480 writes = 0.32:1, versus Slack's 6.7:1) follows
arithmetically from the declared 65% cache hit rate, and the `cache` assumption already names the
cold-cache case as 'the scenario to test'. Defensible. (ii) The missing search index tier — 'search'
appears in the REST API name and 'search indexing' in the Kafka name with no index component — is
real but minor; search indexing is async off Kafka and would not move the binding constraint. (iii)
Flannel-style client bootstrap ('4 million simultaneous connections at peak and 600K client queries
per second', 31 May 2017) is a genuine missing edge tier, but as a bootstrap-path cost it does not
change which box saturates in steady state. (iv) Voice/video and push hand-off are explicitly
declared out of model.

**Fix**

Ordered by leverage. (a) and (b) are the ones that change what a reader believes. (a) Fix the
workload assumption's arithmetic. Either raise event-fanout to match the stated premise, or —
cheaper and more honest — say what the model actually encodes: 'Fan-out is modelled at 3.7 events
per send, i.e. ~4 online recipients per message, which is DM / small-channel traffic. Above ~3.9:1
the gateway tier, not the REST API, becomes the binding constraint; at 20:1 (still far below
Discord's documented 1000:1 for a 1,000-member channel) the gateway is at 333% and this model's
headline verdict is void.' State the 3.9 threshold explicitly — it is the number that makes the
model's own scope visible. (b) Add a hot-channel non-additivity caveat to the `ws` assumption,
mirroring the one realtime_chat already carries for `db`: 'These instances are modelled as a
stateless pool whose capacity adds. The real tier is not — Slack's Channel Servers are stateful, own
channels via a consistent hash ring, and are reassigned by CHARM on failure (11 Apr 2023); Discord's
per-guild process took 900ms-2.1s to publish for a large guild (6 Jul 2017) and was fixed by
sharding into relays of up to 15,000 sessions, not by adding instances (25 Oct 2023). Adding
instances does nothing for a single hot channel.' (c) Rename the store to 'Message store (sharded by
channel)' and append realtime_chat's disclosure verbatim in spirit: 'MySQL/Vitess at Slack, ScyllaDB
at Discord; sql_db is the closest kind Keystone models and the throughput figure is set
accordingly.' The shard key is already correct and should be kept. (d) Optional shape change, only
if (a)-(c) are not judged enough: insert a 'Channel/guild servers (stateful per-channel fan-out,
consistent-hash sharded)' app_server on the send path (api -> channel -> q) and as the source of the
event-fanout flow. (e) Re-derive the gateway per_instance_rps. 3,000 events/s sits ~19x below
Discord's published ~58,000 events/s per Elixir machine. If the figure is deliberately conservative
for a smaller instance class, say so in the assumption; right now it reads as measured.

**Verified sources**

- https://slack.engineering/real-time-messaging/
- https://slack.engineering/scaling-datastores-at-slack-with-vitess/
- https://slack.engineering/flannel-an-application-level-edge-cache-to-make-slack-scale/
- https://slack.engineering/migrating-millions-of-concurrent-websockets-to-envoy/
- https://slack.engineering/scaling-slacks-job-queue/
- https://discord.com/blog/how-discord-stores-trillions-of-messages
- https://discord.com/blog/maxjourney-pushing-discords-limits-with-a-million-plus-online-users-in-a-single-server
- https://discord.com/blog/how-discord-scaled-elixir-to-5-000-000-concurrent-users
- https://discord.com/blog/how-discord-reduced-websocket-traffic-by-40-percent
- https://elixir-lang.org/blog/2020/10/08/real-time-communication-at-scale-with-elixir-at-discord/
- https://www.erlang-factory.com/static/upload/media/1394350183453526efsf2014whatsappscaling.pdf

### social_feed

- **shape:** misleading · **numbers:** implausible

**What a reader would get wrong**

The bottleneck itself. The blueprint names the Feed materialiser and I confirmed the model is
arithmetically self-consistent about it (6,500 arrivals / 10 x 900 = 72.2%, exactly the stated
peak_util). But TWO independent errors each move the real constraint elsewhere, so a reader would go
and buy stream-consumer instances for a system whose actual limit is somewhere else. (1) TRAFFIC
MIX. 18% publish = 4,500 posts/s against only 18,000 feed reads/s — a 2.8:1 read:write ratio. Both
anchors are primary and both say that is off by one to two orders of magnitude: Krikorian's Twitter
deck gives '>300k qps poll-based timelines' against '~5K/sec daily average' tweets = 60:1, and
Facebook's TAO paper (USENIX ATC'13), from a random sample of 6.5 million requests over a 40-day
period, states 'Reads dominate, with only 0.2% of requests involving a write'. 4,500 posts/s is also
close to Twitter's ENTIRE global tweet rate in 2012 (~5K/s average, ~7K/s peak) while serving 6% of
Twitter's home-timeline QPS — the mix is not internally coherent as a single system. Worse,
engagement (8%) is set BELOW publish (18%), which is backwards: TAO's measured write breakdown is
assoc add 52.5% versus obj add 16.5%, i.e. edge/engagement writes outnumber object creations ~3:1. I
recomputed the corrected case: at ~95/1.5/3/0.5 the materialiser needs 1.25 instances instead of 10,
and the Feed read API becomes the constraint at 86.8% of 11 x 2,500. (2) AMPLIFICATION APPLIED TO
ONE TIER ONLY. The builder assumption puts the ~150x fanout into the materialiser's CAPACITY, which
is a defensible modelling choice — but the publish flow then visits the Redis feed tier at x1.0.
Carry the blueprint's own 150x through and the cache takes 4,500 x 150 = 675,000 writes/s plus
18,000 reads = 231.7% of its 3 x 100,000 capacity, versus the 8.2% the model shows: a 28x
understatement, and the real binding constraint in this design on its own stated assumptions. This
is why I grade the SHAPE misleading here and only a reasonable simplification for the sibling
twitter_clone: it is the same class of omission, but here it flips the bottleneck and there it does
not. (3) The corpus contradicts itself. The mix plus the amplification imply each materialiser
instance drives ~93,700 Redis writes/s (900 blended events/s, 69.2% of them 150-way fanouts). The
sibling twitter_clone blueprint states 8,000 writes/s for the same class of worker. That is 11.7x,
and needs no external source to be a defect. For fairness: the Kafka sizing is GOOD. 30,000 msg/s
per broker checks out against LinkedIn's published '>4,000 brokers', '>100 Kafka clusters' and '7
trillion per day' (Oct 2019), which divide to ~20,000 msg/s per broker on average. The engine-scope
assumption disclaiming consumer lag and backlog is also exactly the right disclosure and should be
kept.

**Fix**

(a) Fix the mix to roughly 95% read_feed / 1.5% publish_post / 3% engagement_event / 0.5%
archive_read — engagement ABOVE publish, per TAO's 52.5% assoc add vs 16.5% obj add. This drops the
materialiser from 10 instances to ~1-2 and moves the bottleneck to the Feed read API at ~87%, which
is the honest answer. (b) Either give the publish flow a cache visit multiplier reflecting the ~150x
fanout, or state the cache's true write rate in the cache assumption the way twitter_clone states
its worker's 8,000 writes/s. As written the blueprint's stated bottleneck is wrong on the
blueprint's own numbers. (c) Reconcile the ~93,700 writes/s per materialiser instance against
twitter_clone's 8,000 — two blueprints in one corpus should not disagree 12x on the same component.
(d) Add a 'Social graph service (follower lists)' component on the publish path before the
materialiser; the fan-out cannot happen without reading each author's follower list and that read is
the dominant cost driver. (e) One scope line would convert this design's single biggest unstated
assumption into a teachable trade-off: fan-out-on-write is the MINORITY published pattern.
Facebook's Multifeed (10 Mar 2015) builds News Feed at read time — 'each aggregator fanned out the
request to all the leaves to fetch data, rank and filter data', with 'usually 20 leaf servers ...
make up one full replica' — and LinkedIn's FollowFeed (31 Mar 2016) explicitly rejected
materialisation because 'data size with this model was 62 times greater than pull based
architecture', plus the cost of grandfathering every pre-materialised feed on each relevance-model
change. Note I did NOT keep the researcher's complaint that a 'Social Media Feed' with no CDN/media
path is a defect: media delivery would not touch the materialiser and cannot move the bottleneck, so
it is a fair L0 simplification, worth at most a scope line.

**Verified sources**

- https://engineering.fb.com/2015/03/10/production-engineering/serving-facebook-multifeed-efficiency-performance-gains-through-redesign/
- https://www.linkedin.com/blog/engineering/feed/followfeed-linkedin-s-feed-made-faster-and-smarter
- https://cs.uwaterloo.ca/~brecht/courses/854-Emerging-2014/readings/data-store/tao-facebook-distributed-datastore-atc-2013.pdf
- https://www.slideshare.net/slideshow/raffi-krikorian-twitter-timelines-at-scale/24040648
- https://junchengyang.com/publication/tos21-twemcache.pdf
- https://github.com/twitter/cache-trace/blob/master/stat/2020Mar.md
- https://www.linkedin.com/blog/engineering/open-source/apache-kafka-trillion-messages
- https://www.vldb.org/pvldb/vol9/p1281-sharma.pdf

### spotify

- **shape:** misleading · **numbers:** plausible

**What a reader would get wrong**

TWO defects survive verification; everything else is a fair L0 simplification.  (1) THE
BROWSE/SEARCH JOURNEY — upheld as misleading, not downgraded. The blueprint names a component 'Read
replicas (catalogue browse, search backing)' and routes browse_search onto it at x0.2. I recomputed
from the file: 0.10 x 20,000 = 2,000 rps into lb/api/cache, x0.2 = 400 rps against 2 x 8,000 =
16,000 capacity = 2.5% utilisation. That teaches a builder that catalogue search scales by adding
PostgreSQL read replicas and will never be their constraint. Spotify's own answer is a dedicated
retrieval tier: 'Search at Spotify relied mostly on term matching' via 'our Elasticsearch cluster',
with dense Natural Language Search added 'as an additional source' and 'a final-stage reranking
model that takes the top candidates from each retrieval source' (Spotify Engineering, 2022-03-17 —
note this post is scoped to PODCAST EPISODE search, which is the honest reading of it). A neural
reranker is a genuinely expensive dedicated tier; modelling it as a 2.5%-utilised replica point-read
points at the wrong bottleneck for that flow. This is NOT an omission hiding behind a disclaimer —
the blueprint's scope assumption excludes 'Recommendations/ML ranking' but affirmatively CLAIMS
search, in both the API component name and the replica name. A positive misstatement, so I did not
downgrade it. Underneath it, the catalogue store is also wrong-shaped: Spotify's user DB was
PostgreSQL with 'writes only took place in London. On a single machine' and cut over to Cassandra
('The final switch was made on May 11th', 2015) precisely because that single writer was a scaling
ceiling and a SPOF; today 'petabytes reside in Bigtable for online use-cases' (Spotify Engineering,
2026-07-27).  (2) A FALSIFIABLE STATED-AS-FACT ASSUMPTION. The engine assumption says segmented
HLS/DASH delivery 'is what real players use'. Spotify's own engineering blog contradicts this for
the very system being modelled: 'We store each encoded music track as a file... the Spotify app will
fetch the file in chunks from a nearby server with HTTP GET range requests. A typical chunk size is
512kB' (2018-08-31). In a repo whose charter bans overclaimed statements, an assumption asserted as
fact and falsified by the modelled company's own primary source is a defect regardless of accuracy
tier.  WHAT I DID NOT UPHOLD, in fairness to the blueprint: - PROPORTION is a reasonable
simplification and is better than the researcher gave it credit for. I checked its internal
coherence: playback_start 0.05 x 20,000 = 1,000 track starts/s against 160,000 concurrent listeners
= one start per listener per 160 s (~2.7 min), which is realistic for ~3.5-min tracks with skipping,
and consistent with Kreitz & Niemela's measured '39% of playbacks in Spotify are by random access'.
browse_search at 2 actions per play is plausible. The audio share of 0.80 is wrong only as a
consequence of defect (2), and correcting it does NOT move the bottleneck (see below), so it is a
simplification, not a misleading defect. - The single-writer SQL primary is not a defect. It is
historically what Spotify ran, and the blueprint's own assumption block explicitly flags it as a
SPOF whose flag is 'correct about failover, not about capacity' — which is exactly the lesson
Spotify learned from the Sept-2013 London/Ashburn cable break that 'resulted in a major drop in new
users during a week'. Good teaching, honestly caveated. - Kafka as the play-event bus is dated
(Spotify 'killed the existing Kafka-based system' in February 2017 for Google Cloud Pub/Sub) but the
SHAPE — durable event bus into consumers doing royalty attribution — is exactly right: 'EndSong
Event... which is used to pay royalties to labels and artists' (2019-11-12). Reasonable
simplification. - The collapsed perimeter (one ALB vs Spotify's three LB clusters —
generic/API/payments on nginx+HAProxy with dyn.com DNS steering, plus the access-point tier holding
the client's long-lived TCP connection) is a fair L0 simplification: it does not move the reader's
bottleneck. - I DOWNGRADED the researcher's latency claim. They wrote that real median playback
latency is 265 ms 'not the ~53 ms the blueprint's playback_start path sums to'. The path sum is
right (1.0+10.0+0.4+5.0+20.0+2.0+15.0 = 53.4 ms base) but the comparison is unfair: the paper's own
text says 'it is likely that the median playback latency measures the time needed for DRM together
with local processing time', and it is a client-side end-to-end measurement from 2010 in which 55.4%
of bytes came from local cache. It is not comparable to a server-path sum, and I do not count it as
a defect.  SCALE NUMBERS: NO PUBLIC SPOTIFY FIGURE EXISTS for any per_instance_rps in this file (CDN
100k, API 2k, Postgres 8k, replica 8k, Kafka 30k, consumers 800, object store 20k) or for the
CDN/LB/cache/db latencies. I state that rather than guessing; they are generic-infrastructure
plausible and I cannot refute them. Exactly ONE number here is checkable against a Spotify primary
and it is low: object store base_latency_ms = 20.0, where Spotify says of that same storage class
'GCS delivers 30-100ms per request' (2026-07-27). The impact is small (the object store carries only
3% of audio plus 10% of playback_start), so this is a precision defect, not a bottleneck defect. The
97% CDN hit rate is asserted as fact with no Spotify figure behind it.

**Fix**

Four surgical changes, none needing new engine capability. Ranked by whether they move the
bottleneck.  (1) MOVES THE BOTTLENECK — split the mislabelled component. Replace 'Read replicas
(catalogue browse, search backing)' with (a) a search/retrieval tier (inverted index + final-stage
rerank) fed from the catalogue store, and (b) if a SQL replica is kept at all, relabel it
'account/entitlement reads' only. Rename the SQL primary to 'Account & entitlements primary (single
writer)' so it stops claiming to hold the catalogue. Cite Spotify Engineering 2022-03-17 for the
retrieval tier, and say plainly that the post is about podcast-episode search. Give the rerank tier
a per_instance_rps materially below the replica's 8,000 so the browse journey stops reading as free.
(2) DOES NOT MOVE THE BOTTLENECK BUT IS A FACTUAL ERROR — correct the audio assumption to Spotify's
published figure. Change 'one GET per ~10 s of audio, ~160 KB per segment' to 'HTTP GET range
requests, typical chunk 512 kB (Spotify Engineering, 2018-08-31), ~25.6 s of audio at the 160 kbit/s
High tier'. I verified the arithmetic: 512 KB / 20 KB/s = 25.6 s, so 160,000 listeners produce
~6,250 audio rps, not 16,000, and the audio share falls from 0.80 to ~0.61 (or ~0.55 at the
blueprint's stated 128 kbit/s ladder average). STATE EXPLICITLY IN THE REPORT WHAT DOES NOT CHANGE,
because this is the honesty-preserving half of the fix: bytes/s = listeners x bitrate is invariant
of chunk size, so the 'egress is the entire bill' conclusion is untouched; and the API still takes
0.20 x 20,000 = 4,000 rps against 3 x 2,000 = 6,000 capacity, so the 66.7% control-plane bottleneck
survives unchanged — I recomputed this and it is exactly the file's declared peak_util. Separately,
DELETE the sentence 'Segmented delivery ... is what real players use' and replace it with 'segmented
delivery is what this engine can express', which is the claim the repo can actually defend.  (3)
Ground the one checkable latency and de-fact the one invented one. Raise object store
base_latency_ms from 20.0 to 50 (band 30-100) citing Spotify Engineering 2026-07-27, 'GCS delivers
30-100ms per request'. Relabel the 97% CDN hit rate as ASSUMPTION, not fact — no Spotify figure
exists — and support the concentrated-hot-set reasoning with the measured popularity distribution
instead: '88% of the track accesses were within the most popular 12% of the library', and, for
server-side requests specifically, '79% of accesses being within the most popular 21%' (Kreitz &
Niemela, IEEE P2P'10).  (4) Add a one-line honesty caveat for client-side caching, and correct the
storage figure. The model derives '160,000 concurrent listeners' from server request rate while
ignoring the client cache entirely. Kreitz & Niemela measured '8.8% of data came from servers, 35.8%
from the peer-to-peer network, and the remaining 55.4% were cached data' (the P2P overlay was
retired in 2014; the local cache and prefetch were not — clients 'start downloading the next track
when 30 seconds or less remain of the current track'). Note that this makes the listener count a
LOWER bound, i.e. the model errs in the safe direction for capacity but understates the user base it
implies. Also, the same paper gives a directly usable primary datapoint the researcher missed:
clients 'normally make between zero and ten server requests for a track', with 'the mean size being
440 kB' — remarkably close to the modern 512 kB chunk, and worth citing as independent corroboration
of fix (2). Finally, the 1.2 PB storage assumption (100M tracks x 3 encodings x 4 MB) undercounts:
Spotify's quality page lists ~24/96/160/320 kbit/s on apps plus AAC 128/256 on web, and 24-bit/44.1
kHz FLAC shipped 2025-09-10. Either state ~5 PB or write out the encoding ladder so the reader can
see what is and is not counted.

**Verified sources**

- https://engineering.atspotify.com/2018/08/smoother-streaming-with-bbr — PRIMARY. Opened; confirms verbatim 'We store each encoded music track as a file, copied on HTTP servers across the world', 'fetch the file in chunks from a nearby server with HTTP GET range requests. A typical chunk size is 512kB', and the Varnish VCL 'set client.socket.congestion_algorithm = "bbr"' on audio-fa-bbr.spotify.com. This is the source that falsifies the blueprint's segmented-delivery assumption.
- https://engineering.atspotify.com/2015/6/user-database-switch — PRIMARY (2015). Opened; confirms 'Reads were distributed over all data centers, but writes only took place in London. On a single machine.', 'The final switch was made on May 11th', the Sept-2013 London/Ashburn cable break that 'resulted in a major drop in new users during a week', and the 75M active-user context.
- https://engineering.atspotify.com/2022/03/introducing-natural-language-search-for-podcast-episodes — PRIMARY (2022). Opened; confirms 'Search at Spotify relied mostly on term matching' via Elasticsearch, NLS added 'as an additional source', and a final-stage reranker over 'top candidates from each retrieval source'. CAVEAT I am recording: the post is scoped to podcast-episode search, so it evidences Spotify's retrieval architecture, not a claim that music catalogue search is identical.
- https://engineering.atspotify.com/2015/10/designing-the-spotify-perimeter — PRIMARY (2015, dated). Opened; confirms '3 clusters to handle different kinds of requests' (web / API / payments), nginx + HAProxy, dyn.com DNS steering to the closest datacenter, 'around 50 services behind web load balancers', and 'around 7,000 servers in the production network running more than 100 different services'.
- https://engineering.atspotify.com/2020/02/how-spotify-aligned-cdn-services-for-a-lightning-fast-streaming-experience — PRIMARY (2020). Opened; confirms 'Spotify's CDN solution with Akamai and AWS for business-critical content, such as audio streaming' and Fastly standardised for images/cover art/client updates.
- https://engineering.atspotify.com/2019/11/spotifys-event-delivery-life-in-the-cloud — PRIMARY (2019). Opened; confirms 'more than 8M e/s' at peak, 'over 500 distinct Event Types', 'over 350 TB of events (raw data)' daily, '~2500 VMs', 'close to 15 different microservices', the EndSong royalty event, and that Kafka was killed in February 2017 in favour of Google Cloud Pub/Sub.
- https://engineering.atspotify.com/2021/10/changing-the-wheels-on-a-moving-bus-spotify-event-delivery-migration — PRIMARY (2021). Opened; confirms 'nearly 8M' e/s peak, 'nearly 70TB' compressed daily, '600+' event types.
- https://engineering.atspotify.com/2024/5/data-platform-explained-part-ii — PRIMARY (2024). Opened; confirms 'more than 1 trillion events per day', 'over 1800 different event types', 'more than 38,000 actively scheduled pipelines'.
- https://engineering.atspotify.com/2026/7/indexing-the-data-lake-for-online-point-queries — PRIMARY (2026-07, most current). Opened; confirms 'GCS delivers 30–100ms per request' and 'At Spotify, petabytes reside in Bigtable for online use-cases — but exabytes sit in the GCS data lake.' This is the only source that lets me grade any latency number in the file.
- https://kreitz.se/spotify-p2p10/spotify-p2p10.pdf — PRIMARY, peer-reviewed (Kreitz & Niemela, IEEE P2P'10, 2010). WebFetch could not parse the PDF, so I extracted the text myself with pdftotext and read the passages. Personally confirmed: 'Approximately 39% of playbacks in Spotify are by random access'; 'Most playbacks (61%) occur in a predictable sequence'; 'an initial request to the server asking for approximately 15 seconds of music, using the already open TCP connection'; 'clients throttle their requests such that they do not get more than approximately 15 seconds ahead'; 'start downloading the next track when 30 seconds or less remain'; '8.8% of data came from servers, 35.8% from the peer-to-peer network, and the remaining 55.4% were cached data'; 'the median latency was 265 ms, the 75th percentile was 515 ms, and the 90th percentile was 1047 ms'; stutter 1.0% normal / 1.8% with prefetch disabled; '88% of the track accesses were within the most popular 12% of the library'; '79% of accesses being within the most popular 21%'; and 'between zero and ten server requests for a track... the mean size being 440 kB'. DATE CAVEAT: 2010, and the P2P overlay it describes was retired in 2014 — the cache/prefetch/latency findings are what survive.
- https://engineering.atspotify.com/2013/03/backend-infrastructure-at-spotify — PRIMARY (2013, dated). Opened; confirms the sanctioned stores are 'Cassandra, PostgreSQL and memcached'. Redis is NOT mentioned, so the blueprint's 'Redis catalogue + playlist cache' is a generic stand-in, not Spotify's stack. The post does NOT describe an access-point tier or a service count — the researcher did not claim it did.
- https://engineering.atspotify.com/2015/01/personalization-at-spotify-using-cassandra — PRIMARY (2015). Opened; confirms the Entity Metadata Store and User Profile Store Cassandra clusters fed by Kafka, Storm topologies and Crunch/Hadoop.
- https://engineering.atspotify.com/2018/12/bigtable-autoscaler-saving-money-and-time-using-managed-storage — PRIMARY (2018). Opened, and it only PARTLY supports what it was cited for: it confirms Spotify is 'moving to Google Cloud managed databases' and operates Bigtable, but it contains NO Cassandra-to-Bigtable migration narrative and NO cluster/node counts. See dropped_claims.
- https://support.spotify.com/us/article/audio-quality/ — PRIMARY official doc. Opened; confirms Low ~24, Normal ~96, High ~160, Very high ~320 kbit/s on apps; web player AAC 128 (Free) / AAC 256 (Premium); Lossless 'up to 24-bit/44.1kHz FLAC'.
- https://newsroom.spotify.com/2025-09-10/lossless-listening-arrives-on-spotify-premium-with-a-richer-more-detailed-listening-experience/ — PRIMARY. Opened; confirms 'up to 24-bit/44.1 kHz FLAC' and a 2025-09-10 rollout start.
- https://newsroom.spotify.com/company-info/ — PRIMARY official. Opened; confirms 'over 100 million tracks... 777 million users, including 300 million subscribers, in 184 markets'. CAVEAT: the page carries no as-of date, so cite it as undated-current, not as a quarter.
- https://www.fastly.com/blog/spotify-on-diagnosing-cascading-errors — SECONDARY (vendor blog). Opened. It reports on and quotes Niklas Gustavsson, Principal Engineer at Spotify — that named Spotify engineer is the primary it stands on. Confirms verbatim the access-point chain: 'a client talks to an access point (a perimeter service that manages authentication and does content routing), which in turn talks to production storage, which talks to a proxy which talks to master storage', and 'After moving many petabytes of data to GCS, they made the switch to GCS as their origin'.
- https://www.infoq.com/presentations/evolution-spotify-arch/ — SECONDARY (InfoQ). Opened. It is InfoQ's transcript of the primary it reports on: a QCon.ai talk of 2019-06-18 by Emily Samuels and Anil Muppalla of Spotify. Confirms the Home evolution: 2016 batch (Hadoop + Word2Vec + Cassandra, 24-hour refresh) → 2017 services → 2018-on streaming, with Google Cloud Pub/Sub and Dataflow/Apache Beam writing to Bigtable for shelf services.
- BANNED-SOURCE CHECK: PASSED. I checked every one of the 18 cited URLs. None is an interview-prep site, ByteByteGo/Educative/Exponent, an unsourced Medium post, or a YouTube system-design tutorial. Sixteen are Spotify primary sources (engineering blog, official support doc, newsroom) or a peer-reviewed IEEE paper; the two secondaries (Fastly, InfoQ) are both correctly labelled and each names the primary it reports on.

### ticket_booking

- **shape:** misleading · **numbers:** implausible

**What a reader would get wrong**

Which component to scale. The researcher's harsh verdict SURVIVES verification, and I found a third
defect it missed.  DEFECT 1 — THE CDN OFFLOADS NOTHING, AND THAT ALONE CREATES THE NAMED BOTTLENECK.
Verified in /tmp/bp/ticket_booking.json: the browse flow is cdn(x1.0), lb(x1.0), app(x1.0),
cache(x1.0), replica(x0.12). Every one of the 7,200 browse rps passes the CDN AND reaches the app
tier. App load = 7,200+560+240 = 8,000 against 6x2,000 = 12,000 = 66.7%, which is exactly the
declared bottleneck and peak_util. The blueprint already owns the notation for expressing a hit rate
— its cache assumption states an '~88% hit rate on browse' and encodes it as replica(x0.12) — so the
omission is an oversight, not a convention. I computed the flip point rather than guessing a hit
rate: the app tier falls below the payment tier's 46.7% at any CDN hit rate above roughly 33%. Even
a deliberately pessimistic 50% edge hit on event pages and seat maps moves app to 36.7% and hands
the bottleneck to the payment tier. So the reader buys app servers they do not need. (The
researcher's specific 90% figure is unsourced — I am keeping the finding and dropping the number.)
DEFECT 2 — THE PSP TIER IS PRICED BY ITS OWN CONNECTION POOL, NOT THE THIRD PARTY'S CEILING. 8,000 x
7% = 560 charges/s. The pay assumption names the dependency as 'Stripe/Adyen-class'. Stripe's own
rate-limit page documents a live-mode global limit of 100 requests per second per account, 25
requests per second for individual endpoints, a 429 with a Stripe-Rate-Limited-Reason header, and
names 'a sudden increase in charge volume, such as a flash sale' as a cause, telling you to contact
support in advance. 560/s is 5.6x the global limit and 22x the per-endpoint default. The model
prints that tier at 46.7% — comfortable — because 3x400 rps is the tier's own capacity. The
blueprint does say in prose that the PSP limit is 'a HARD 429 ceiling, not the graceful slowdown
this queueing model shows', which is real mitigation, but the printed utilisation contradicts the
prose and readers read the number. That is why numbers stays implausible rather than dropping to
plausible.  DEFECT 3 — MISSED BY THE RESEARCHER, VERIFIED IN THE FILE. The db assumption asserts the
seat-inventory primary is '~3,000 writes/s — deliberately the lowest capacity in the design'. It is
not. The payment tier's total capacity is 3x400 = 1,200, and its per-instance figure is 400 — both
below the db's 3,000. The same assumption then says the db 'is the component a flash sale actually
breaks', but at 560 book/s the db sits at 18.7% while the payment tier sits at 46.7%; in the flash
sale the blueprint itself tells you to model, where browsing collapses into buying, the payment tier
saturates first and then hits the external 429 wall. The blueprint's stated story about its own weak
point is wrong against its own component list.  WHAT THE SOURCES CONFIRM ABOUT THE MISSING FRONT
DOOR. Ticketmaster's Smart Queue has fans 'sign in with their Ticketmaster accounts and join the
virtual waiting room before the sale', enter 'at a rate that minimizes check-out errors and
maximizes sell-through', and leads with 'Keep bots out'. Cloudflare's Waiting Room requires a
proxied DNS record or proxied load balancer and is configured by total_active_users and
new_users_per_minute (both must exceed 200); session_duration is 1-30 minutes, default 5, but is
OPTIONAL, not a required knob as the research stated. Shopify hit the same wall (2017-02-03 and
2017-02-05, Emil Stolarsky): a leaky-bucket throttle in the edge tier with an Nginx-cached queue
page, later a PID-controlled fairness threshold on signed first-attempt timestamps, after a Kylie
Cosmetics sale 'took down not just her store, but all others on the database shard' because 'every
checkout session created a new record in MySQL and, exacerbating that, every step in the flow
modified that same record'. On spike magnitude, the X-Engine SIGMOD '19 paper measures Singles' Day
2018 at 'about 122 times' the previous second, 'up to 491,000 sales transactions per second which
translate to more than 70 million database transactions per second'. Monzo planned for 1,000
arrivals/s against a writer that drained at ~60/s. HOWEVER — the blueprint has an explicit
waiting_room assumption saying no front door is modelled and that 'every real high-demand ticketing
system has one'. Given that disclosure and the L0 standard, the missing waiting room is a disclosed
simplification, NOT the defect. The defects are the CDN, the PSP ceiling and the false 'lowest
capacity' claim, all three of which are undisclosed and all three of which point the reader at the
wrong component.

**Fix**

1. Give the CDN a stated, non-zero hit rate in the browse flow using the notation the file already
uses for Redis, e.g. cdn(x1.0), lb(x0.5), app(x0.5), cache(x0.5), replica(x0.06) with the assumed
edge hit rate written out. Any value above ~33% moves the bottleneck off the app tier, so the point
is to state one, not to pick 90%. 2. Correct the db assumption: the payment tier (1,200 rps total,
400 per instance) is the lowest-capacity component, not the 3,000 rps seat-inventory primary.
Rewrite the 'this is the component a flash sale actually breaks' sentence to match the file's own
numbers. 3. Declare the external PSP ceiling as a modelled constraint (e.g. psp_max_rps: 100, citing
docs.stripe.com/rate-limits) and make the report flag any flow whose call rate exceeds it, rather
than leaving the warning in prose while printing 46.7%. 4. Optional: model the waiting room as a
component whose capacity is new_users_per_minute (Cloudflare's own required knob), so the flash-sale
what-if has somewhere to absorb a 122x arrival spike instead of scaling app servers.

**Verified sources**

- https://docs.stripe.com/rate-limits
- https://business.ticketmaster.com/smart-queue/
- https://developers.cloudflare.com/waiting-room/
- https://developers.cloudflare.com/waiting-room/reference/configuration-settings/
- https://shopify.engineering/surviving-flashes-of-high-write-traffic-using-scriptable-load-balancers-part-i
- https://shopify.engineering/surviving-flashes-of-high-write-traffic-using-scriptable-load-balancers-part-ii
- https://users.cs.utah.edu/~lifeifei/papers/sigmod-xengine.pdf
- https://monzo.com/blog/2019/01/14/crowdfunding-technology-backend-architecture
- https://docs.stripe.com/payments/place-a-hold-on-a-payment-method
- https://docs.stripe.com/strong-customer-authentication

### digital_wallet

- **shape:** reasonable_simplification · **numbers:** no_public_figure

**What a reader would get wrong**

Nothing that changes where the wall is. I am DOWNGRADING the researcher's numbers verdict from
'plausible' to 'no_public_figure': I could not find a single published figure comparable to any
per_instance_rps or base_latency_ms in this file, and saying 'plausible' implies external
corroboration that does not exist.  VERIFIED FROM THE FILE. Wallet API 12,000 / (8x2,000=16,000) =
75%, matching the declared bottleneck and peak_util. Ledger service (0.18+0.07)x12,000 = 3,000 /
4,800 = 62.5%. Ledger primary 3,000 / 5,000 = 60%. Replicas 3,390 / 12,000 = 28%. Kafka ~3,000 msg/s
against 75,000, which the q assumption already discloses as deliberate over-provisioning. The model
is internally consistent and its assumptions say what they assume.  THE ONE REAL GAP, CONFIRMED AS A
CORPUS INCONSISTENCY RATHER THAN A BOTTLENECK ERROR. Risk / AML / sanctions screening appears only
as a Kafka consumer named inside the q assumption, so it carries no capacity, no latency and no
cost, while the sibling payment_system models exactly that work synchronously (6 instances, 300 rps
each, 25 ms). The wallet moves 3,000 money events/s — more than payment_system's 900 — with zero
modelled screening. That understates the cost and the latency of the transfer path, but it does not
move the bottleneck, because a stateless screening tier scales by adding instances. Reasonable
simplification with a disclosure gap, not a defect by the stated standard.  WHAT THE SOURCES
ACTUALLY SUPPORT. Monzo (2016-09-19, Oliver Beattie) confirms the shape the blueprint chose: they
'respond to payment networks within tens of milliseconds to approve or decline a transaction', with
enrichment, notifications and feed insertion happening after. Monzo's 2019-01-14 crowdfunding write-
up (Robin Bilgil) confirms they took ledger work off the critical path behind NSQ and drained it
through 'a singleton crowdfunding-investment ... with a rate-limiter of around ~60 per second' while
planning for 'a sharp peak of 1,000 investments per second'. That is a deliberately serialised one-
off flow, NOT a general wallet ledger capacity, so it cannot be used to validate or refute the 1,200
rps ledger service or the 5,000 rps primary — I am explicitly not treating it as a comparable
figure. Uber LedgerStore confirms production wallet-class ledgers are sharded and append-only, which
is context for the payment_system finding above, not a contradiction of anything this file claims.
The replica-staleness, hot-account-row and burst caveats in this blueprint are honest and correctly
scoped.

**Fix**

1. Add a risk/compliance app_server on the p2p_transfer and top_up paths, reusing payment_system's
own risk sizing, so the reader sees that screening costs money and latency even though it is not the
wall — and so the two money blueprints stop disagreeing about whether screening is synchronous. 2.
Fix the duplicated assumption subject: 'db' appears twice in the assumptions array (capacity, then
storage), which will collide in any subject-keyed rendering. 3. Label the per_instance_rps figures
in this file as ASSUMPTION rather than leaving them unmarked — I could not corroborate any of them
against a published figure, and the corpus rule is that unevidenced numbers say so.

**Verified sources**

- https://monzo.com/blog/2016/09/19/building-a-modern-bank-backend
- https://monzo.com/blog/2019/01/14/crowdfunding-technology-backend-architecture
- https://www.uber.com/en-US/blog/dynamodb-to-docstore-migration/
- https://www.uber.com/en-US/blog/how-ledgerstore-supports-trillions-of-indexes/
- https://docs.stripe.com/api/idempotent_requests

### file_hosting

- **shape:** reasonable_simplification · **numbers:** implausible

**What a reader would get wrong**

SHAPE = REASONABLE SIMPLIFICATION and I am holding it there. As a generic web file host (LB -> app
-> cache/db/object store/queue, bytes bypassing the app tier via presigned URLs) the wiring is fair
for L0, and the missing pieces the researcher listed — chunking/dedup, CDN, read replicas, async
workers — are either disclosed in the blueprint's own assumptions or would not move the bottleneck.
The blueprint even concedes the CDN point in prose. No shape defect to sustain. PROPORTION = WRONG,
and this is the real defect. The design bills itself as a 'sync-and-share file service' with 'sync
fan-out to the user's other devices' across '~1M active users', then gives sync_poll 3% = 90 rps. I
checked this against Dropbox's OFFICIAL SDK contract rather than a guess: the longpoll timeout
defaults to 30s and 'Must be greater than or equal to 30 and be less than or equal to 480', plus up
to 90s jitter. At the documented DEFAULT hold, 1M resident clients generate ~33,333 poll returns/s —
370x the modelled figure and 11x the entire 3,000 rps system budget. Even at the most charitable
bound the API permits (480s max + 90s max jitter), it is ~1,754/s: still 19x the modelled flow and
58% of the whole budget rather than 3%. Inverting it: 90 rps sustains 1M clients only at a ~3.1-hour
poll interval, which the documented API does not allow. So the one flow that would actually saturate
this design is understated by between one and two orders of magnitude under every legal parameter
value. A reader sizing a real sync product from this would under-provision the poll path
catastrophically and never learn they need a connection-holding tier. There is also a corpus-
internal contradiction I verified by reading both files: dropbox.json puts polls at 55% and
file_hosting.json at 3%, for the same class of traffic. Both cannot be right. COMPOUNDING TAUTOLOGY
(verified, and I re-derived it): every flow visits app at x1.0, and the app tier's 4,200 rps
capacity is the lowest of any component (cache 40,000, LB 30,000, queue 15,000, db 8,000, store
5,500). So 3,000/4,200 = 0.714 and 'bottleneck = File API' is forced by the wiring, not discovered.
Cache sits at 3.6% and queue at 3%, so the model's advice collapses to 'add stateless app servers' —
while the blueprint's own cost assumption says egress is the largest line and the engine never
treats egress as a constrained resource. NUMBERS = IMPLAUSIBLE. I am upgrading this from the
researcher's 'plausible' because a headline figure is directly contradicted by the vendor's own doc
for the exact product this blueprint prices. The object store's base_latency_ms of 25 sits against
AWS's published 'consistent small object latencies (and first-byte-out latencies for larger objects)
of roughly 100-200 milliseconds' — 4-8x optimistic, on the path both download_file and upload_file
traverse at x1.0. It does not move the bottleneck (the engine ranks by utilisation, not latency) but
it materially understates reported end-to-end latency on the dominant byte paths. Separately, the
5,500 rps is real but MISAPPLIED: it is AWS's per-PREFIX GET/HEAD figure, and the same paragraph
says 'There are no limits to the number of prefixes in a bucket' and that 10 prefixes scale reads to
55,000/s. Modelling it as a fixed single-instance ceiling installs a wall that does not exist, and
applying a GET number to a mixed GET+PUT load understates the write side, which caps at 3,500 per
prefix. At the current 1,350 store ops/s (24.5% util) neither bites, but both would at ~4x this
scale. IN FAIRNESS, VERIFIED CORRECT: the cost rates are exactly right against the live AWS pricing
page ($0.09/GB egress after the first 100 GB, $0.005/1,000 PUT = $5.00/M, $0.0004/1,000 GET =
$0.40/M), and the blueprint's flagging that one API-gateway-shaped request rate cannot honestly
represent both is a genuinely good piece of honesty. The presigned-URL decision and the 'BYTES DO
NOT FLOW THROUGH THE APP TIER' assumption are also correct against AWS's documented pattern and are
the single most important sizing call in the design.

**Fix**

One number and one component, in priority order. (1) Raise sync_poll's share to something
arithmetically consistent with the stated 1M user base and a legal hold interval — at any value the
API permits it is the DOMINANT flow, not 3% — and rebalance the other shares against it. If you
would rather not re-scope the blueprint, the honest alternative is to drop 'sync' and 'sync fan-out
to the user's other devices' from the summary and present this as a web/share-oriented file host
with no resident client. What you cannot do is keep the sync claim and the 3%. (2) If you keep the
sync claim, add a `notify` app_server component and route sync_poll to it instead of the general
File API, mirroring dropbox.json, plus dropbox.json's excellent one-line assumption that the real
constraint on that tier is connections, not requests — that disclosure is the best thing in the
sibling blueprint and should be reused verbatim. (3) Raise the object store's base_latency_ms from
25 toward AWS's published ~100-200 ms for S3 Standard small objects, or state explicitly that 25 ms
assumes an Express-class store that the $0.09/GB cost model does not price. (4) Annotate the 5,500
rps as AWS's per-prefix GET/HEAD figure that scales with prefix count, noting PUT caps at 3,500 per
prefix, rather than presenting it as a fixed ceiling. (5) Worth a look while you are in there:
download_file does an uncached db(x1.0) read while list_folder over the same objects is 75% cached —
the most frequent per-object metadata lookup bypasses the cache entirely, which looks unintended.

**Verified sources**

- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html — opened; confirms verbatim 'at least 3,500 PUT/COPY/POST/DELETE or 5,500 GET/HEAD requests per second per partitioned Amazon S3 prefix', 'There are no limits to the number of prefixes in a bucket', the 10-prefix/55,000 reads example, and 'consistent small object latencies... of roughly 100-200 milliseconds'
- https://aws.amazon.com/s3/pricing/ — opened; confirms $0.09/GB egress after the first 100 GB, $0.005 per 1,000 PUT/COPY/POST/LIST, $0.0004 per 1,000 GET for S3 Standard (US East). The blueprint quotes all three correctly
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html — opened; supports the presigned-URL pattern in substance ('A presigned URL can be entered in a browser or used by a program to download an object'; upload 'without requiring another party to have AWS security credentials'). See dropped_claims: the researcher's verbatim quote is NOT on this page, though the substance survives
- https://dropbox.github.io/dropbox-sdk-java/api-docs/v3.0.x/com/dropbox/core/v2/files/DbxUserFilesRequests.html — official Dropbox Java SDK, fetched raw and grepped. The load-bearing source for the poll-rate arithmetic: default 30s, range 30-480s, plus up to 90s jitter
- https://dropbox.tech/infrastructure/introducing-cape (2017-05-17) — opened; confirms the post-upload async pipeline is real and matches this blueprint's queue (previews/thumbnails, search indexing, notification delivery, audit indexing), Kafka-backed, sourced from SFJ/Edgestore
- https://dropbox.tech/infrastructure/cape-technical-deep-dive (2018-12-21) — opened; confirms the 30K/s events, 150K/s jobs, p95 <1s rates for that pipeline
- https://dropbox.tech/infrastructure/streaming-file-synchronization (2014-07-10) — opened; confirms 4MB content-addressed chunking with a server-side 'need blocks' check, i.e. the dedup mechanism this blueprint omits
- https://dropbox.tech/infrastructure/inside-the-magic-pocket (2016-05-06) — opened; confirms SHA-256 block keying and the Block Index dedup check
- https://research.spec.org/fileadmin/user_upload/documents/rg_cloud/DragoInsideDropbox.pdf — authors' IMC 2012 slide deck (text-extracted locally); confirms 'download/upload ratio up to 2.4', a BYTE ratio measured in 2012 on client v1.2.52. I am flagging that this is bytes, not requests, and an upper bound — so it makes the blueprint's 2:1 request ratio directionally reasonable but does NOT strictly validate it

### image_hosting

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

THE DECLARED BOTTLENECK IS DECIDED BY A 4.0-POINT MARGIN ON THE LEAST-SUPPORTED INPUT IN THE FILE,
AND FLIPS ON A 20% CHANGE TO IT. I re-ran the model's arithmetic: derivative workers 80/(6x20) =
66.7% (matches peak_util 0.667), Image API 1880/(2x1500) = 62.7%. The only input feeding the
declared bottleneck is the 1% upload share. I swept it: at 0.8% the resize fleet drops to 53.3% and
the Image API becomes the binding constraint at 62.1%; at 0.5% resize is 33.3% against API 61.3%; at
0.075% resize is 5.0%. So a one-fifth reduction in the single most uncertain number in the blueprint
reverses the tool's answer, and every piece of evidence I could verify points that direction rather
than upward. This is the defect: not that 1% is provably wrong, but that the blueprint presents a
bottleneck as a finding when it is an artefact of an undefended input, with no band or caveat saying
so.  The directional evidence, honestly graded: the only public read:write ratio I could source for
a consumer image host is Imgur's — 'nearly 2 billion images every day' against '1.5 million new
images', i.e. ~1,333:1 or uploads at ~0.075% of serves, against the blueprint's 90:1. But that is a
Fastly vendor case study reporting its customer's own figures, and it carries NO DATE, so I will not
lean on the precise 13x multiple the way the researcher did. The dated primary I can lean on is
Flickr (5 Jan 2017): 'as many as twenty-five million photos' uploaded a day across 'over two hundred
million active users' — an upload rate per user far below what a 1%-of-requests share implies. Treat
1% as an upload-stress scenario, not a steady state.  SECOND DEFECT, MODEST AND INTERNAL: the upload
flow is lb -> app -> store -> db -> resize with every hop at x1.0, so a 90ms derivative job is
modelled INLINE with the upload request. That is inconsistent with the sibling instagram_clone
blueprint, which correctly puts Kafka between api and media workers, and it charges 90ms of resize
work to upload p99. It does not move the bottleneck at 66.7% utilisation, so I grade it a real but
non-misleading defect.  WHERE I DOWNGRADE THE RESEARCHER, in fairness at L0. (a) SHAPE: eager
derivative generation at upload is a legitimate, once-industry-standard pattern — it is precisely
what Flickr did before 2015 ('In the past we stored many sizes of every photo to make serving fast',
'eleven different resizes per photo'). Every production host I verified has since moved to lazy on-
demand generation (Wikimedia: 'As the thumb sizes are arbitrary, it is not possible to pregenerate
them either, therefore the only way to handle this is to generate them on demand and cache them';
Flickr 2015: 'maintain our largest resize, usually 2048px wide, as a source image and create any
other moderate or large-sized resizes on-the-fly'; imgix 2017: rendered at the rendering cluster on
first request then cached; Meta 2019: the CDN resizes for the recipient). But choosing the older
pattern is a simplification, not a defect — the defect is only that it is never named as a choice
while being the declared bottleneck. Hence reasonable_simplification, not misleading. (b) NUMBERS: I
keep 'plausible'. The 20 uploads/s x 4 derivatives = 80 resizes/s per 2-vCPU worker implies 25ms of
CPU per resize, 9x optimistic against Flickr's published 225ms GraphicsMagick figure — but that
figure is a large 2048->1600px resize on 2015 GraphicsMagick, and thumb/small/medium derivatives on
a modern library are genuinely much cheaper. Optimistic, within L0 tolerance, but it should carry an
ASSUMPTION label. (c) The 85% CDN hit rate against Meta's measured 59.2% San Jose edge hit ratio
would move object-store utilisation only from 2.8% to ~8%. Not a defect; the researcher was right to
decline that one, and I agree.

**Fix**

Two input edits, one component addition, two labels.  (1) THE ONE EDIT THAT CHANGES THE ANSWER:
either move upload share from 1% to ~0.1%, or keep 1% and relabel it in the workload assumption as a
DELIBERATE UPLOAD-STRESS SCENARIO rather than a steady-state mix. Either way, add a sentence stating
that at a realistic consumer mix the Image API tier, not the derivative workers, is the binding
constraint — because the margin is only 4.0 points and the bottleneck flips at 0.8% upload share.
Cite Imgur's 1.5M new against ~2B served per day, flagged as an undated vendor case study, and
Flickr's dated 'as many as twenty-five million photos' a day across 'over two hundred million active
users'.  (2) INSERT A QUEUE between 'Image API' and 'Derivative workers' on the upload flow, so
derivative generation is asynchronous. This matches the sibling instagram_clone blueprint and every
production stack I verified; without it the model charges 90ms of resize latency to upload p99 and
makes worker saturation fail uploads rather than back up.  (3) ADD ONE ASSUMPTION naming eager-vs-
lazy derivative generation as a design choice with its trade-off, citing Flickr's 2015 move away
from eleven pre-generated sizes to on-demand resizing from a single 2048px source, and Wikimedia's
'not possible to pregenerate them ... generate them on demand and cache them'.  (4) LABEL AS
ASSUMPTION, not as bare figures: per_instance_rps for the CDN edge (150,000), the load balancer
(25,000) and the Image API (1,500). I searched and found NO public figure for any of the three.
Imgur's '8,000 requests per second' is fleet-wide with no instance count, so it cannot calibrate a
per-instance value. Also label the 80 resizes/s per 2-vCPU worker as ASSUMPTION and note it is ~9x
optimistic against the only published CPU resize figure (Flickr, 225ms).  (5) TWO SECONDARY NUMBER
NOTES: object store base_latency_ms 25 against AWS's own 'roughly 100-200 milliseconds' for small
objects; and 20,000 rps on one bucket requires prefix parallelism (AWS publishes 5,500 GET/HEAD per
partitioned prefix, with no limit on prefix count). Optionally, charge the manage_image path for CDN
purge plus N derivative deletions rather than a single store hit — minor, does not move any
utilisation.

**Verified sources**

- https://code.flickr.net/2015/06/25/real-time-resizing-of-flickr-images-using-gpus/ — PRIMARY, 25 Jun 2015. Opened twice; confirms 'takes over 225ms to resize a 2048px JPEG down to 1600px', GPU 'under 16ms' (2048->1600) and 'under 10ms' (2048->640), 'roughly 35ms additional I/O time per resize', 'each resize server can perform over 300 resizes per second', 'eleven different resizes per photo which, in sum, use nearly as much storage as the original photo', and the eager->lazy transition: 'In the past we stored many sizes of every photo to make serving fast' -> 'maintain our largest resize, usually 2048px wide, as a source image and create any other moderate or large-sized resizes on-the-fly from this source'.
- https://code.flickr.net/2017/01/05/a-year-without-a-byte/ — PRIMARY, 5 Jan 2017. Opened; confirms 'an average of 3.25 megabytes of storage each', 'over 80 terabytes of data' on a high-upload day, 'over two hundred million active users', and daily uploads of 'as many as twenty-five million photos' (NOT the 27 million the researcher claimed — see dropped_claims).
- https://wikitech.wikimedia.org/wiki/Media_storage — PRIMARY operator docs, current. Opened; confirms verbatim 'As the thumb sizes are arbitrary, it is not possible to pregenerate them either, therefore the only way to handle this is to generate them on demand and cache them', and the path LVS -> Varnish -> ATS -> Swift -> (404) -> Thumbor -> written back to Swift.
- https://wikitech.wikimedia.org/wiki/Thumbor — PRIMARY operator docs, current. Opened; confirms Thumbor generates thumbnails dynamically on request rather than pre-generating in bulk.
- https://diff.wikimedia.org/2017/11/17/the-journey-to-thumbor-part-2-thumbnailing-architecture/ — PRIMARY, 17 Nov 2017, Gilles Dubuc (Wikimedia Performance Team). Opened; confirms Nginx -> Varnish -> Swift -> Thumbor, generation triggered when Swift cannot locate a thumbnail, and write-back: 'Thumbor saves that thumbnail in Swift. Varnish, as it sees the response go through, keeps a copy as well.'
- https://www.imgix.com/2017/07/24/what-happens-image-request — PRIMARY vendor description of its own system, 24 Jul 2017. Opened; confirms CDN edge -> CDN shield + rendering cluster -> source (Amazon S3), with derivatives rendered on first request then cached at the edge.
- https://www.fastly.com/customers/imgur — SECONDARY, vendor case study reporting Imgur's own figures; NO DATE on the page (I checked). Opened; confirms 'nearly 2 billion images every day', '1.5 million new images', '8,000 requests per second' for Imgur's API, and 'more than 40,000 requests per second' observed by Fastly. Used only directionally because it is undated and vendor-published.
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html — PRIMARY vendor docs, current. Opened; confirms the 3,500 write / 5,500 GET-HEAD per partitioned prefix figures, unlimited prefixes, and 'roughly 100-200 milliseconds' small-object latency.
- https://sigops.org/s/conferences/sosp/2013/papers/p167-huang.pdf — PRIMARY paper, SOSP 2013. Opened and text-extracted; the 59.2% edge hit ratio is confirmed as San Jose's observed per-PoP figure, and the 9.9% backend share is confirmed. Used to test (and clear) the blueprint's 85% CDN hit-rate assumption.
- https://engineering.fb.com/2014/02/27/web/an-analysis-of-facebook-photo-caching-2/ — PRIMARY, 27 Feb 2014. Opened; confirms the 59.2% -> 67.7% edge hit ratio sentence and the 9.9% Haystack share.
- https://engineering.fb.com/2019/01/17/developer-tools/spectrum/ — PRIMARY, 17 Jan 2019. Opened; confirms client-side transcoding and 'the content delivery network (CDN) will resize the image for the recipient anyway', supporting the lazy/edge-resize pattern the blueprint does not name.

### notification_system

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

The most honest of the three, and closest to production shape — LinkedIn's Air Traffic Controller
(2018-03-01) is the same Kafka+Samza spine partitioned by recipient so 'all notifications for a
specific recipient are routed to the same host', with RocksDB local state because reads 'only take a
couple of milliseconds to compete, while remote calls can take from 10ms to 100ms', processing 'over
a billion requests per day'. Two findings survive. (1) A SELF-CONTRADICTION IN THE FILE, which I
verified by arithmetic rather than taking on trust: the workload assumption says '600 ingested
events/s become 9,600 individual device deliveries/s', and ingest is share 0.05 of 12,000 rps =
600/s — but the fanout flow is share 0.10 = 1,200 events/s. Fan-out workers are therefore sized
against twice the events the model says are ingested, inflating that stage to 60% utilisation
instead of 30%. It does not move the bottleneck (delivery workers are at 9,600/(15x800) = exactly
the stated 80%), but it would misdirect fan-out sizing by 2x. (2) THE HEADLINE CONTRADICTS THE
PROSE. The model names your own delivery fleet as the ceiling, while the blueprint's own boundary
assumption says 'In production the provider's rate limit, not your sender fleet, is usually the real
ceiling.' The published ceilings are the same order of magnitude as the whole fleet: FCM's HTTP v1
default is '600k messages per minute' per project — 10,000/s — serving 'HTTP status code 429
RESOURCE_EXHAUSTED' above it, plus 'up to 240 messages per minute and 5,000 messages per hour to a
single device' on Android; SES sandbox is '1 email per second' and '200 emails per 24-hour period'
with production rate that 'varies based on your specific use case'; APNs publishes no number at all
and says 'Do not assume a specific number of streams'. I correct the researcher here: their '9,600
sends/s is 96% of FCM's quota' assumes the entire fleet is FCM push, but it is a 'push/SMS/email'
fleet, so the push slice is a fraction of 9,600 — the correct statement is that FCM's project
ceiling is the same order of magnitude as the whole fleet's throughput, not that it binds at 96%.
Under this repo's charter that is still a headline number shipped without its binding assumption
attached. The other gaps — relevance/preference gating (LinkedIn's ATC drops, sends in-app only, or
pushes; Concourse (2018-05-25) fans out then scores 'millions of candidate notifications per second'
at '~500 k QPS at peak', with 'superactors (such as Bill Gates)' generating millions of candidates
from one activity), retry/backoff (FCM: 'Wait at least 10 seconds before retrying a failed request';
'ramp from 0 to the max RPS across a 60 second time-window'), and token invalidation — are all
disclosed in the blueprint's own quiet_hours and boundary assumptions, so they are stated shortfalls
rather than hidden ones. Uber's RAMEN (2020-12-18) confirms the separate decision service pattern:
'Fireball is a microservice responsible for solving the problem of when to push a message?' at 'more
than 1.5M concurrent connections and pushes over 250,000 messages per second'. The delivery-worker
figure (800 sends/s at 60 ms = 48 in-flight) is internally coherent and consistent with APNs' 'You
can establish multiple connections to APNs servers to improve performance'; no published per-worker
figure exists to contradict it.

**Fix**

(1) Set the fanout flow share to 0.05 so the fan-out stage sees the 600 events/s the assumptions
claim — this is a straight correctness bug in a committed reference file. (2) Make the provider
ceiling first-class instead of prose: add a capacity-bounded 'push provider quota' component at
FCM's published 10,000 msg/s so the simulation reports it beside the sender fleet, or attach it to
the bottleneck line as a named external constraint the reader cannot scale by adding instances — and
note that APNs publishes no limit while SES's default is 1/s in sandbox, so a single homogeneous
'sender' fleet hides three wildly different ceilings. (3) Optionally add a pass-rate multiplier on
the deliver path so the delivery fleet is not sized off undropped fan-out candidates.

**Verified sources**

- https://www.linkedin.com/blog/engineering/messaging-notifications/air-traffic-controller-member-first-notifications-at-linkedin
- https://www.linkedin.com/blog/engineering/messaging-notifications/concourse-generating-personalized-content-notifications-in-near
- https://www.uber.com/us/en/blog/real-time-push-platform/
- https://firebase.google.com/docs/cloud-messaging/throttling-and-quotas
- https://firebase.google.com/docs/cloud-messaging/scale-fcm
- https://developer.apple.com/library/archive/documentation/NetworkingInternet/Conceptual/RemoteNotificationsPG/CommunicatingwithAPNs.html
- https://docs.aws.amazon.com/ses/latest/dg/quotas.html

### payment_system

- **shape:** reasonable_simplification · **numbers:** implausible

**What a reader would get wrong**

Where the wall is, via the ledger fan-out — but the researcher overstated the case and I am
correcting two of its claims.  VERIFIED FROM THE FILE (/tmp/bp/payment_system.json). At system_rps
3000: authorise 900, refund 150, payment-status 600 (ledger visited at x0.25 = 150), settlement 750.
Ledger load = 900+150+150+750 = 1,950 against 9,000 capacity = 21.7%, i.e. the 4.6x headroom the
researcher describes. Auth tier = 1,050 / (7x250=1,750) = 60%, matching the declared bottleneck and
peak_util 0.6. Risk tier = 900/1,800 = 50%. The arithmetic in the research is correct.  CORRECTION 1
(researcher too harsh): it claims '600 rps of reads land on the single ledger primary' for payment-
status. False — the flow is ledger(x0.25), so 150 rps land there. Dropped.  CORRECTION 2 (researcher
invented a magnitude): the proposed 'x4 postings per money event -> 82%, x8 -> 162%' is
arithmetically right given those multipliers, but no source I could open gives a postings-per-
payment figure, and I could not resolve the Stripe Ledger blog it leaned on. Treat x4/x8 as
illustrative, not evidence.  WHAT SURVIVES AND IS LOAD-BEARING. The ledger's reported 4.6x headroom
rests entirely on an unstated modelling choice — that one money event equals one ledger operation —
while the blueprint's own sibling contradicts it. digital_wallet.json prices the identical component
('Ledger primary (PostgreSQL, single writer, ACID)') at 5,000 rps and states the reason in its own
words: 'lower than a plain OLTP primary because every posting is a multi-row double-entry
transaction with a uniqueness constraint on the idempotency key.' payment_system prices 'Double-
entry ledger (single ACID primary)' at 9,000 rps and applies no fan-out at all. Both cannot be
right, and the reader is never told which assumption they are buying. That is a corpus contradiction
I verified in the tree, not an external claim.  SECOND VERIFIED POINT — the ledger assumption states
a choice as a law: 'a double-entry ledger needs a single writer for correctness.' Production ledgers
at this scale do not do that. Uber's LedgerStore, 'an immutable, ledger-style database storing
business transactions' and the store behind its payment platform, runs on sharded Docstore after
migrating 250 billion records / ~300TB off DynamoDB (2021-11-10), and supports over 2 trillion
indexes across tens of billions of financial transactions per quarter (2024-04-04). Stripe's own
transaction store, DocDB, runs 'more than 2,000 database shards' at 'more than 5 million database
queries per second' (Jimmy Morzaria, Stripe, QCon SF — SECONDARY: InfoQ transcript, the primary is
the talk). A learner will read 'needs a single writer' as a correctness requirement rather than a
scale-limited simplification.  SHAPE — NOT a defect at L0. The missing 3DS/SCA challenge (mandatory
in the EEA since 2019-09-14 per Stripe's own SCA page, producing a requires_action out-of-band step,
not one synchronous round trip) and the missing auth/capture split (Stripe documents 7 days for
online card CITs, 5 days / exactly 4 days 18 hours for Visa, 2 days for most card-present brands,
with funds moving at capture) are real divergences from a Stripe-class processor, but neither moves
the bottleneck, and the blueprint's compliance assumption declares chargebacks/PCI/fraud rules out
of scope. Downgraded to reasonable_simplification.  WEBHOOKS — real but minor. Stripe's docs confirm
retries 'for up to three days with an exponential back off in live mode', that it 'doesn't guarantee
the delivery of events in the order that they're generated', and that receivers should 'process
incoming events with an asynchronous queue'. So 1 event = 1 outbound HTTP call understates the
dispatcher (600 rps against 6x200=1,200, i.e. 50%). It does not unseat the 60% auth tier, so it is a
disclosure gap, not a misdirection.  OBSERVATION, UNSOURCED: refund at 5% of all ops = 150/s against
900 authorisations/s is a 1-in-6 refund ratio. I found no public figure for card refund rates and
make no claim, but the ratio is worth a stated assumption.

**Fix**

1. State the postings-per-money-event assumption explicitly instead of leaving it at an implicit
x1.0 in authorise/refund/settlement, and reconcile it with the 9,000 vs 5,000 rps split for the same
component across payment_system and digital_wallet. Pick one and cite the reasoning in both files;
do not adopt the researcher's x4 as if it were sourced. 2. Reword the ledger assumption from 'a
double-entry ledger needs a single writer for correctness' to a choice with its cost, citing Uber
LedgerStore on sharded Docstore and Stripe DocDB's 2,000+ shards. 3. Add a sentence to the webhook
assumption that Stripe-class retries run up to 3 days and are unordered, so dispatcher load is above
1 call per event. 4. Optional, low priority: name the SCA/3DS challenge and the auth-vs-capture gap
in the compliance assumption, so a reader knows the modelled 'authorise' conflates authorisation
with money movement.

**Verified sources**

- https://docs.stripe.com/api/idempotent_requests
- https://docs.stripe.com/payments/place-a-hold-on-a-payment-method
- https://docs.stripe.com/strong-customer-authentication
- https://docs.stripe.com/webhooks
- https://stripe.com/blog/rate-limiters
- https://www.uber.com/en-US/blog/dynamodb-to-docstore-migration/
- https://www.uber.com/en-US/blog/how-ledgerstore-supports-trillions-of-indexes/
- https://www.infoq.com/presentations/docdb-online-database/

### proximity_service

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

ONE load-bearing defect, and I verified both its input figures and its arithmetic personally.  THE
WRITE SHARE IS FABRICATED AND IT DECIDES THE ANSWER. The blueprint declares 4% review writes and 3%
owner updates. I pulled the actual figures out of Yelp's Q4 2024 shareholder letter PDF (Key
Financial and Operational Metrics, in thousands): Cumulative Reviews 265,288 (2022), 287,364 (2023),
308,100 (2024); Active Claimed Local Business Locations 6,321 / 7,056 / 7,736. So Yelp added 20.74
million reviews across all of 2024 = 0.66 reviews per second on average. The blueprint's 4% of 6,000
rps is 240 review-writes/s at peak; at the blueprint's OWN stated peak:average ratio of 3 that is
~80/s average, or 2.52 billion reviews per year — about 122x Yelp's real rate. Owner updates at 3%
(180/s peak, ~60/s average) work out to 245 edits per claimed location per year, i.e. every claimed
business editing its listing once every 1.5 days against 7.74 million locations.  And it is load-
bearing, not cosmetic. I recomputed the shipped model and reproduced its declared peak_util of 0.628
exactly: geo 62.8%, api 56.3%, lb 10.8%, replica 8.3%, store 8.0%, db 5.2%, cache 2.7%. Re-running
with writes at a realistic share and the read shares renormalised to 100% gives geo 55.5% and api
55.8% — the declared bottleneck FLIPS to the API tier, and the two are then within 0.3 points of
each other. The headline finding of this blueprint is an artifact of an invented write share. That
is exactly the standard the brief sets: it sends a reader to size a SQL primary and a re-index path
for ~420 writes/s that do not exist, and to optimise the geo index on the strength of a verdict the
model cannot support.  I DOWNGRADED the researcher's shape verdict from 'wrong'-adjacent framing to
reasonable_simplification. The two big omissions are disclosed in the assumptions ('Sharding the geo
index by region, and ranking/personalisation of results, are OUT of this reference'), and disclosure
is the honest L0 path. I also specifically checked and REJECTED one mechanism the researcher
implied: moving owner_update off the synchronous path onto async CDC would NOT flip the bottleneck
by itself, because the re-index work still lands on the geo tier in a load model — CDC decouples
latency, not capacity. The sync edge misrepresents failure coupling (a re-index stall becomes owner-
write latency, the opposite of how Yelp decoupled it), which is worth a note but does not change the
answer.  The tension worth flagging honestly: Yelp names scoring as the bottleneck of this exact
tier — 'In our case, scoring was the bottleneck since we rely on many features to rank the results'
and 'we could horizontally scale by adding more shards which meant we got more parallelism out of
Elasticsearch at query time since each shard had fewer businesses to score' (29 Jun 2017). The
blueprint excludes ranking by declared scope and then declares that same tier the bottleneck. The
exclusion is honest; the combination is self-undermining. The 2017 post also documents the scatter-
gather the blueprint collapses: a coordinator 'figures out the corresponding geographical shard'
then 'the request would be broadcast to all the microshards' and merges — so one logical search is N
physical queries, a fan-out multiplier the capacity arithmetic does not carry.  ON THE NUMBERS, the
decisive one has NO public corroboration and this should be stated in the blueprint. I confirmed
Yelp discloses only RELATIVE results: 'We improved our 50th, 95th and 99th percentile timings by
30-50% after migrating to Nrtsearch' and 'we reduced our infrastructure costs by migrating to
Nrtsearch - as much as 40% for some use-cases' (21 Sep 2021), with no absolute QPS or latency
anywhere in either post. So the 400 rps / 30 ms geo-index figure that decides the verdict is
uncorroborated. The Redis figure IS supportable and can be upgraded to GROUNDED: redis.io's own
benchmark reports 'SET: 180180.17 requests per second, p50=0.143 msec' and 72,144.87 rps against a
100k random keyspace. Nothing I found contradicts any figure, hence 'plausible' rather than
'no_public_figure'.  Secondary teaching nit, well sourced: naming the index 'quadtree / geohash
cells' teaches the encoding the Lucene line abandoned. Elastic's BKD geo_shapes post documents an
8-vertex polygon rasterising to '1,105,889 terms in the inverted index' under the quadtree approach
versus 'a total of eight triangle terms' under BKD, with prefix-tree support removed for geo_point
in ES 6.0 and BKD made the geo_shape default in 7.0; Lucene 6.0 introduced block k-d trees (15 Feb
2016). Uber replaced square grids with H3 in production for pricing and marketplace optimisation (27
Jun 2018).

**Fix**

(a) Cut write_review to ~0.02% and owner_update to ~0.01% of requests, citing the Yelp Q4 2024
shareholder-letter metrics (Cumulative Reviews 287,364k -> 308,100k = 20.7M added in 2024, i.e.
0.66/s; Active Claimed Local Business Locations 7,736k), renormalise the read shares to 100%, and
re-run. (b) Then state plainly in the verdict that geo (55.5%) and api (55.8%) are within 0.3
points, so this model does NOT determine a bottleneck. (c) Add an honesty line that the decisive
figure — 400 rps and 30 ms per geo-index instance — has no public corroboration, because Yelp
publishes only relative gains (p50/p95/p99 improved 30-50%; cost down up to 40%) and never absolute
QPS or latency. (d) Move the owner_update -> geo edge onto an async CDC hop citing Yelp's Kafka data
pipeline, noting explicitly that this changes failure coupling, not capacity. (e) Rename the
component to something like 'search / geo index tier (Lucene BKD geo_distance + scoring)' with an
assumption noting geohash prefix trees were superseded by BKD in Lucene 6 / ES 6-7 and by H3 at
Uber. (f) Upgrade the Redis assumption (100k rps, 0.4 ms) to GROUNDED against redis.io's benchmark.
(g) Optional: note the peak:average ratio of 3 is slightly conservative against the only real map-
shaped measurement found, OSM's 70,669 peak / 36,770 average = 1.9 (July 2025).

**Verified sources**

- https://engineeringblog.yelp.com/2017/06/moving-yelps-core-business-search-to-elasticsearch.html
- https://engineeringblog.yelp.com/2021/09/nrtsearch-yelps-fast-scalable-and-cost-effective-search-engine.html
- https://engineeringblog.yelp.com/2016/07/billions-of-messages-a-day-yelps-real-time-data-pipeline.html
- https://s24.q4cdn.com/521204325/files/doc_financials/2024/q4/Yelp-Q4-2024-Letter-to-Shareholders.pdf
- https://www.sec.gov/Archives/edgar/data/1345016/000134501626000019/yelp-20251231.htm
- https://www.fastly.com/customers/yelp
- https://www.elastic.co/blog/lucene-points-6-0
- https://www.elastic.co/blog/bkd-backed-geo-shapes-in-elasticsearch-precision-efficiency-speed
- https://www.uber.com/en-US/blog/h3/
- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/
- https://community.openstreetmap.org/t/technical-updates-to-the-tile-openstreetmap-org-service-openstreetmap-org-standard-layer/133421

### realtime_chat

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

SUSTAINED, but narrowed — this is a good blueprint and I downgraded two of the researcher's
complaints.  VERIFIED AGAINST PRIMARY SOURCE (Rick Reed, Erlang Factory SF, 7 Mar 2014 — I extracted
the PDF text locally rather than trusting a summary; all figures are verbatim slide text): '465M
monthly users / 19B messages in & 40B out per day / 147M concurrent connections / 230K peak
logins/sec / 342K peak msgs in/sec, 712K out'; hardware slide '~ 550 servers + standby gear / ~150
chat servers (~1M phones each) / 2x2690v2 Ivy Bridge 10-core (40 threads total) / 64-512 GB RAM / >
11,000 cores'; 'FreeBSD 9.2 / Erlang R16B01 (+patches)'.  WHAT THE BLUEPRINT GETS RIGHT (worth
stating, because it is the control case for slack_discord). Its deliver:send ratio is 12,000/6,400 =
1.875. WhatsApp's published peak out:in is 712/342 = 2.08, and its daily 40B/19B = 2.11. The
blueprint is within 11% of the real system on the single most important proportion in a chat model.
Its gateway rate of 5,000 frames/s per instance sits against WhatsApp's (342K + 712K) / 150 chat
servers = ~7,027 frames/s per chat server — the same order of magnitude, 1.4x conservative. And its
workload assumption already discloses the group-chat multiplier ('a 200-member group is 200
deliveries for one send'). This is the honesty discipline slack_discord fails to apply.  DEFECT 1 —
CONNECT RATE UNDERSTATED ~7x. The blueprint puts connect at 3% of ops: 600/s against 6,400 sends/s,
a ratio of 0.094. WhatsApp's published peak is 230K logins/sec against 342K msgs in/sec — a ratio of
0.67. I confirm this does NOT move the modelled bottleneck (the WS gateway stays at 76%; connect and
deliver both traverse the gateway, so re-cutting the share between them leaves gateway arrivals
unchanged). By this repo's own fairness standard that makes it a proportion inaccuracy, not a
bottleneck-misleading defect. It still matters because reconnect churn is the documented failure
mode in this class: Reed's own outage slide reads 'Not always successful: 2/22 outage / Began with
back-end router glitch / Mass node disconnect/reconnect / Resulted in a novel unstable state /
Unsuccessful in stabilizing cluster (esp. pg2) / Full stop & restart (first time in years)', and
Slack built Flannel partly because 'Reconnection storms are resource intensive' (Bing Wei, 31 May
2017). A reader sizes their TLS/session-establishment path for a trickle.  I DROPPED the
researcher's supporting number here. They claimed the LB 'would still only reach ~16% at WhatsApp's
ratio'. Recomputing on the blueprint's own 2 x 30,000 LB: at connect share 0.15 the LB reaches 6.7%,
and at WhatsApp's full 0.67 ratio it reaches 8.8%. Not 16%. The conclusion (LB is nowhere near
binding) survives; the figure does not.  DEFECT 2 — THE TWO HALVES OF THE GATEWAY SIZING STORY
DISAGREE ~5.5x. This one I confirm in full. The 'ws' assumption sets 'roughly 100k sockets per
instance' and the model provisions 5 instances = 500,000 sockets to carry 6,400 sends/s, implying
every connected user sends a message every 78 seconds. WhatsApp's published figures give 342,000
msgs/s over 147M connections = one message per connection per 430 seconds. At that real chattiness,
6,400 sends/s implies ~2.75M live sockets and ~27 gateway instances at the blueprint's own 100k
density, not 5. This is mitigated — not cured — by an unusually honest disclosure already in the
file: 'The v1 engine has no notion of held connections, so it charges the gateway per FRAME
(~5,000/s per instance) and cannot tell you when you run out of sockets. Size for connections
separately.' Because the limitation is named explicitly, this is a disclosed L0 limitation rather
than a lie, which is why the shape verdict stays at reasonable_simplification.  I DOWNGRADED the
researcher's headline shape complaint. They faulted the blueprint for lacking 'a stateful per-
conversation fan-out owner', calling it a missing tier in both blueprints. That is true of Discord
(guild process) but NOT of WhatsApp, which is the primary source for this blueprint. Reed's System
Overview slide draws phones connecting directly to a pool of chat servers, with 'Offline storage',
'mms' and 'Account/Profile/Push/Group' as separate boxes — there is no per-conversation actor tier
and no load balancer on the message path. For a DM-shaped chat system the blueprint's shape is a
fair match to the best-documented real system of that shape. The blueprint's own 'lb' assumption
already states the LB is on connect and REST only, 'not on every message', which is exactly right.
The researcher's other two 'missing components' are also disclosed, not defects: offline delivery is
named in the 'delivery' assumption (though Reed does list it as a real bottleneck — 'Offline storage
I/O bottleneck / I/O bottleneck writing to mailboxes / Add write-back cache with variable sync
delay'), and push hand-off plus E2EE device fan-out are explicitly declared out of model.

**Fix**

Two text edits and one number; no component or flow-path change — the shape is sound. (a) Raise the
connect flow share from 0.03 to 0.15, taking the 0.12 from `deliver` (0.60 -> 0.48) so the shares
still sum to 1.0 and the send rate is untouched. The researcher's version of this fix omitted the
rebalance and would have left the shares summing to 1.12. Ground it on Reed, Erlang Factory SF, 7
Mar 2014: '230K peak logins/sec' against '342K peak msgs in/sec'. Verify after the edit that the
bottleneck is still the WS gateway at 76% — it should be, since connect and deliver both traverse
`ws`. (b) Append to the existing 'ws' assumption: 'At WhatsApp's published rate of one message per
connection per ~430s (342K msgs/s over 147M connections, Erlang Factory SF 2014), 6,400 sends/s
implies ~2.75M live sockets, i.e. ~27 instances at 100k each, not the 5 modelled here — the instance
count in this model is set by frame throughput only.' (c) Optional, cheap: add one clause to the
'delivery' assumption noting that WhatsApp draws offline storage as its own tier and names it a
production I/O bottleneck, so folding it into the shared log hides that failure mode.

**Verified sources**

- https://www.erlang-factory.com/static/upload/media/1394350183453526efsf2014whatsappscaling.pdf
- https://www.erlang-factory.com/upload/presentations/558/efsf2012-whatsapp-scaling.pdf
- https://www.erlang-factory.com/sfbay2014/rick-reed
- https://blog.whatsapp.com/1-million-is-so-2011
- https://slack.engineering/flannel-an-application-level-edge-cache-to-make-slack-scale/
- https://discord.com/blog/how-discord-scaled-elixir-to-5-000-000-concurrent-users
- https://highscalability.com/how-whatsapp-grew-to-nearly-500-million-users-11000-cores-an/

### task_queue

- **shape:** reasonable_simplification · **numbers:** no_public_figure

**What a reader would get wrong**

I DOWNGRADED the researcher's shape verdict. The missing pieces it named — a relay/outbox stage,
retries, a dead-letter queue, visibility timeouts, scheduled jobs, priority classes — are real and
confirmed (Uber's Cherami, 2016-12-06, publishes the standard component set of input host, storage
host, output host, controller and frontend, with configurable redelivery limits before messages move
to a dead-letter queue; Sidekiq's Best Practices wiki says verbatim 'Sidekiq will execute your job
**at least** once, not **exactly** once' and 'Sidekiq makes no exactly-once guarantee at all'), and
the blueprint honestly discloses retries/DLQ as absent. None of them changes where the reader thinks
the bottleneck is, so per the L0 teaching standard they are simplifications, not defects. THE REAL
DEFECT IS THE PROPORTION, and it is confirmed. Recomputed from the JSON: lb 5.8%, api 58.3%, q
12.5%, worker 75.0% (the declared bottleneck), db 41.3%, cache 2.5%, store 15.0%. The traffic mix is
30% submit / 30% execute / 40% status = 1.33 status polls per job. That is only self-consistent
because the blueprint assumes a 40 ms mean job — i.e. jobs that finish faster than any client's poll
interval. Slack's job queue (slack.engineering, published 2017-12-06, updated 2020-06-25) reports
jobs running from milliseconds to several minutes at 'over 1.4 billion jobs at a peak rate of 33,000
per second', and Celery's own task guide advises 'it is better to split the problem up into many
small tasks rather than have a few long running tasks' while warning 'Polling the database for new
states is expensive' — 40 ms is at the extreme bottom of the real range, and work that cheap does
not need a durable queue at all. The hazard is that job duration and poll ratio are ONE hidden
assumption presented as two independent ones. The blueprint's assumption block does flag the 200
jobs/s worker figure as 'the input most worth replacing with your own measurement', which is honest
— but it does NOT say that replacing it forces the traffic shares to change too. Move to a 2-second
job with 1-second polling and polls-per-job goes from 1.33 to ~2, while worker capacity falls from
200 jobs/s to ~4 (8 concurrent / 2 s), which is a 50x capacity collapse against a 1.5x traffic-mix
change. The bottleneck stops being a tier you can scale and becomes an input you mis-set. A reader
who takes 'Job workers (executors), 75%' at face value and adds workers has acted on a number that
is an artefact of the 40 ms assumption, not a result. Secondary and quieter: the submit path is api
-> db(x1.0) -> q(x1.0), a dual write with no shared transaction — a crash between the two loses or
orphans a job. Slack's JQRelay exists precisely to make the DB-side write and the broker handoff one
recoverable path. Both tiers show green (41% and 12.5%), so nothing in the output signals that the
design's real risk is correctness, not capacity. On SCALE NUMBERS: no_public_figure is correct and I
confirmed it. Neither Sidekiq nor Celery nor Slack nor Uber publishes a per-worker jobs/s rate — job
cost is workload-specific by orders of magnitude. The one figure that IS publicly checkable is the
Redis status cache at 80,000 ops/s, which is conservative against redis.io's published 'SET:
180180.17 requests per second, p50=0.143 msec' and '72144.87 requests per second' over a 100k random
keyspace.

**Fix**

Decouple job duration from poll ratio and state them as two explicit, separately-derived
assumptions: mean job duration, and polls per job = job_duration / poll_interval. Then re-run the
reference at a queue-shaped duration (seconds, not 40 ms) and let the shares fall out of it, so a
reader changing the duration sees the mix change with it. Add one component — a relay/outbox worker
between the Postgres job row and the broker — so submit reads api -> db -> relay -> q rather than a
dual write, citing Slack's JQRelay. Neither edit is urgent for bottleneck accuracy; the first is
urgent for the blueprint's honesty about which of its numbers are load-bearing.

**Verified sources**

- https://slack.engineering/scaling-slacks-job-queue/
- https://www.uber.com/en-US/blog/cherami-message-queue-system/
- https://github.com/sidekiq/sidekiq/wiki/Best-Practices
- https://docs.celeryq.dev/en/stable/userguide/tasks.html
- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/

### twitter_clone

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

NOT the bottleneck — that stays correctly on the fanout workers, and I confirmed the model is self-
consistent there (240 posts/s against 8 x 40 rps = 75.0%, exactly the stated peak_util; and 8,000
cache writes/s / 200 followers = 40 posts/s, so the worker capacity encodes the amplification
honestly). The defect is one internally contradictory number. The cache assumption states 'at ~10k
rps it uses ~5% of its request capacity'. I reproduced that: modelled cache arrivals are 6,600 +
2,880 + 480 = 9,960, i.e. 4.98% of 2 x 100,000. But it is only 5% because the fan-out write into the
timeline cache — the entire point of a fan-out-on-write design — is not an edge in the graph.
post_tweet's path is lb-api-db-q-fanout-store; the cache never appears. Carry the blueprint's OWN
fanout assumption through (240 posts/s x ~200 followers = 48,000 writes/s) and the tier runs at
57,960 rps = 29.0% of capacity, ~6x the stated figure, and flips from read-dominated to 82.8%
writes. Twitter's own production cache measurements say exactly this about pre-materialised timeline
caches: the ACM TOS'21 / OSDI'20 Twemcache paper names 'opportunistic pre-computation' — 'caches
storing recent user activities ... read when a query asks for recent events from a particular user'
— as a main cause of write-heavy caching, reports 'more than 35% of all Twemcache clusters are
write-heavy', and I read the released trace table directly: cluster15 is set:1.00 with mean object
frequency 1.0, and clusters 12/31/32/38/39 run set ratios of 0.80-0.98 with mean frequency 1.0-1.3.
So a reader sizes a 'read cache' from read traffic and gets a write-bound tier. This does not move
the bottleneck verdict, which is why I grade shape a reasonable simplification rather than
misleading — but a stated number that the blueprint's own other assumption contradicts by 6x is a
defect on this repo's no-bare-numbers standard, not a simplification. Secondary point: the summary
calls this 'a microblog where posting fans out into per-user timeline caches' with no date. That is
Twitter's 2012-13 design. X's own open-sourced code (2023) has home-mixer call timelineranker, whose
README states it 'calls the Search Index's super root to fetch a list of Tweets' and calls UTEG, 'to
power both the For You and Following Home Timelines' — i.e. in-network candidates are retrieved at
READ time now, with the root README putting '~50% of posts' on that search candidate source.

**Fix**

Two edits, neither of which changes the bottleneck. (a) Put the timeline cache on the post_tweet
path after the fanout worker (or, if the graph must stay literal, state the write rate in the cache
assumption the way the worker assumption already states its 8,000 writes/s). Then correct the cache
assumption from '~5% of its request capacity' to ~29% and note the tier is ~83% writes — as it
stands the blueprint contradicts itself. (b) Add a 'Social graph service (follower lists)' component
on post_tweet between the queue and the fanout worker: every fan-out must read the author's follower
list, and this tier is named in Krikorian's own 2012 deck (alongside Timeline Service, Ingester,
Earlybird, Blender, BatchCompute) AND is still called by timelineranker in X's 2023 open-sourced
code ('Timeline Ranker calls Social Graph Service to obtain the follow graph and user states').
Right now the read amplification that drives the whole design is invisible. (c) Note that the
~200-follower fanout is ~2.7x the only published ratio: Krikorian's deck gives both '30b deliveries
/ day' and 'over 400 million tweets a day', which divide to ~75 deliveries per tweet. (d) Optional,
cheap, and high teaching value: date the summary to Twitter's 2012-13 fan-out-on-write timeline and
add one scope line pointing at X's read-time Earlybird/UTEG path. I explicitly did NOT keep two
criticisms the researcher made of this blueprint. First, that 2 Redis instances is wrong because the
Twemcache paper says clusters run '20 to thousands of instances' — that 20-instance floor is real
and I verified it ('at most 5% of instances can fail at any moment. This dictates the number of
instances of each cluster to be at least 20'), but it is a Twitter-scale provisioning rule and does
not transfer to a 12k-rps teaching model, where 2 nodes is ordinary. Second, that per_instance_rps
100,000 is refuted by the traced range: I read the raw trace table and the range is genuinely
0.22-26.40 kqps, but that is measured LOAD on lightly-loaded provisioned instances, not a capacity
ceiling, so it neither confirms nor refutes 100,000. No public capacity ceiling found for
Redis/Twemcache, and none found for a per-worker timeline-write rate either — Krikorian's deck gives
only the aggregate '~300k deliveries / sec', and GraphJet's 'one million graph edges per second' is
in-memory edge ingest, a different workload. Say 'no public figure found' rather than grading those.

**Verified sources**

- https://www.slideshare.net/slideshow/raffi-krikorian-twitter-timelines-at-scale/24040648
- https://highscalability.com/the-architecture-twitter-uses-to-deal-with-150m-active-users/
- https://github.com/twitter/the-algorithm
- https://github.com/twitter/the-algorithm/blob/main/timelineranker/README.md
- https://junchengyang.com/publication/tos21-twemcache.pdf
- https://github.com/twitter/cache-trace/blob/master/stat/2020Mar.md
- https://www.infoq.com/presentations/Twitter-Timeline-Scalability

### typeahead

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

Nothing that meets the stated bar — I am overturning the researcher here, in the blueprint's favour.
Their case was that base_latency_ms = 8.0 on the FST shard tier is ~11x Elastic's published 0.72 ms
for a plain completion, and that 'fix the service time and the shard tier stops being the
bottleneck'. The first half is true; the second half is false, and it is false for a reason I
checked in the engine rather than inferred. simulation.py:268 states the model: 'Utilisation rho =
arrival / capacity, where capacity = per_instance_rps * instances.' base_latency_ms feeds only the
M/M/c sojourn term (simulation.py:398), never rho. So changing 8.0 -> 0.72 leaves the shard tier at
76.8% and does not touch the bottleneck ranking at all. The number that sets the verdict is
per_instance_rps = 2,000, and that one checks out: Elastic's own benchmark (Reelsen, 22 Aug 2013,
2.1M Wikipedia titles) measures 0.72 ms per plain completion, and Elastic's current docs say 'Each
shard runs the search on a single CPU thread' with a search pool of int((cores*3)/2)+1 — so ~1,389
rps per thread, and 2,000 rps per instance is about two threads' worth. Plausible, not implausible.
Two things I did verify as real but below the defect bar. (1) The bottleneck margin is razor-thin
and undeclared: shard tier 76.8% vs Suggest API 75.0%, a 1.8-point gap, so the 'bottleneck' field
here is far less robust than in the other two blueprints and nothing says so. (2) The workload
assumption credits 'client-side debouncing (150-250 ms)' for holding 60,000 keystrokes/s down, and
the only direct measurement of production engines contradicts the mechanism: Monaco (WTMC 2019, co-
located with IEEE S&P 2019) inspected page source and found 'Google, Baidu and Yandex use callbacks
on input events, DuckDuckGo uses a callback on keyup events, and Bing uses a polling mechanism with
100 ms timer', with 'an HTTP GET request... made upon each key press that results in a visible
change to the query input field'. But raising system_rps scales every tier proportionally, so it
under-provisions the whole design without relocating the bottleneck — a scale caveat, not a
misdirection. The blueprint's biggest real lever, the 40% CDN edge-hit rate, IS honestly declared
('if personalised suggestions defeat edge caching, origin load nearly doubles overnight'), and I
confirmed the arithmetic: with the edge hit gone the Suggest API goes to 125% and saturates. Google
officially confirms the personalization risk (blog.google, 8 Oct 2020: predictions factor in 'the
language of the searcher or where they are searching from'), and Dean's WSDM 2009 keynote
independently names 'level of personalization' as a cache-hit-rate driver. That is the charter
working as intended.

**Fix**

No defect to fix; three optional improvements, in priority order. (1) Add one line to the `trie`
assumption noting the 1.8-point margin over the Suggest API tier, so a reader does not over-trust
the bottleneck field — this is the only thing here I would actually ask for. (2) Make the FST tier
sizeable by the constraint the blueprint already, correctly and honestly, identifies as the real one
('it has no memory model, so it cannot tell you when the index outgrows the box, which is the actual
failure mode'): Elastic's measured 82 MB FST over 2.1M Wikipedia titles is 41 bytes/entry, which
turns that declared gap into a computable suggestions-count input. (3) Correct the debounce sentence
to cite the measured per-keystroke behaviour (Monaco 2019) rather than an assumed 150-250 ms client
debounce, and note that 60,000 keystrokes/s is therefore a floor. If the 8.0 ms base_latency_ms was
chosen to cover fuzzy matching, say so — Elastic measured 0.72 ms plain, 1.14 ms fuzzy edit-
distance-1, 4.14 ms fuzzy edit-distance-2 — which would also let the `quality` assumption's
fuzziness caveat become an explicit input. None of these change a verdict.

**Verified sources**

- https://www.elastic.co/blog/you-complete-me
- https://www.elastic.co/guide/en/elasticsearch/reference/current/size-your-shards.html
- https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-threadpool.html
- https://vmonaco.com/papers/Feasibility%20of%20a%20Keystroke%20Timing%20Attack%20on%20Search%20Engines%20with%20Autocomplete.pdf
- https://vmonaco.com/publications/
- https://blog.google/products/search/how-google-autocomplete-predictions-work/
- https://github.com/LinkedInAttic/cleo
- https://static.googleusercontent.com/media/research.google.com/en//people/jeff/WSDM09-keynote.pdf

### url_shortener

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

SIMPLIFICATION, not a bottleneck defect — I checked the arithmetic both ways. The missing piece is
real: every redirect at the one shortener with public volumes is also a write. High Scalability
(2014-07-14, SECONDARY, reporting Sean O'Connor's talk 'Lessons Learned Building Distributed Systems
at Bitly', Bacon 2014) states: 'When a bitly URL is decoded into an HTTP redirect a message is sent
to multiple services: an archive services that saves it to HDFS and S3, a real-time analytics
service, longer term history analytics, an annotation service.' That pipeline is most of their fleet
— '400 servers. Not all 400 servers are handling redirects. ~30 servers handle all incoming traffic
from the outside world including shortens, redirects, api requests, web ui, etc. The rest of the 400
are dedicated to various services either storing and organizing user data or providing various forms
of processing and analysis'. NSQ, built at Bitly, describes itself as 'A realtime distributed
messaging platform designed to operate at scale, handling billions of messages per day.' The
blueprint models zero writes on a 9,900 rps read path, so a learner takes away 'a shortener is a
pure-read cache problem'. PROPORTION is also off by 10x: the blueprint asserts 99:1 read:write,
while Bitly's measured figures are '6 billion clicks a month' against '600 million shortens a month'
= 10:1. I recomputed the model at 10:1 — creates rise from 100/s to ~909/s, DB load to ~1,818/s (23%
of 8,000), and the app tier stays the bottleneck at 69.4%. So both corrections leave the bottleneck
call intact: this is a sizing and mental-model defect, not a wrong-bottleneck defect, and I grade it
as a simplification per the stated standard. Key generation is genuinely absent — Georgiev &
Shmatikov (arXiv:1604.02734, 2016-04-10): 'Short URLs can be generated sequentially, randomly, using
a combination of the two (as in the case of bit.ly), or by hashing the original URL', with 'The
tokens in bit.ly URLs are between 4 and 7 characters long' over a 62-character alphabet giving '62^4
+ 62^5 + 2 · 62^6 ≈ 1.2 · 10^11' against bitly's claim 'to have shortened over 26 billion URLs' —
but nothing in a lb→app→db insert hints that ID allocation is where write concurrency bites. NUMBERS
hold: redis.io's own benchmark page records '72144.87 requests per second' for randomised SET over
100k keys and 'SET: 180180.17 requests per second / LPUSH: 188323.91 requests per second' without
pipelining, so a 100,000 rps ceiling for one Redis node is in the right band (note the page does not
state the hardware for the 72k figure — it says only 'a Linux box'). No public figure exists for a
t4g.medium redirect handler's 1,200 rps. Minor artefact I found myself: the redirect path serialises
visit_prob as 0.09999999999999998, a float-subtraction residue baked into a committed golden.

**Fix**

Restate the ratio with provenance: either adopt ~10:1 citing Bitly's 6B clicks : 600M shortens per
month, or keep 99:1 but tag it ASSUMPTION with a band and note that the only public measurement
contradicts it by 10x. Then add one queue component on the redirect path at visit_prob 1.0 (the
click event) — the cheapest way to make the read path's write cost visible inside the v1 engine's
modelling scope — and optionally a note that ID allocation/collision retry is unmodelled. Also clean
the 0.09999999999999998 to 0.1.

**Verified sources**

- https://highscalability.com/bitly-lessons-learned-building-a-distributed-system-that-han/
- https://github.com/nsqio/nsq
- https://arxiv.org/pdf/1604.02734
- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/

### video_streaming

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

Only one thing, and it is smaller than the researcher argued. The blueprint sets playback_start at
4% of 20,000 rps = 800 starts/s against its own stated ~72,000 concurrent streams, which implies a
90-second average viewing session -- implausible for VOD. The effect is that the model UNDERSTATES
its own headline lesson ('the control plane is genuinely small'): a reader is told the control plane
is ~10% of request volume when for real VOD sessions it is far less. This errs in the SAFE direction
(you over-provision a control plane that is already 44% utilised) and does NOT move the bottleneck:
I recomputed every row, and cutting playback_start to 0.4% leaves the Edge CDN as the binding
constraint at ~76% (from 69.2%) while the app tier merely falls to ~30%. This is a teaching-clarity
flaw, not a wrong-bottleneck defect.  I DOWNGRADED the researcher's second complaint. It argued the
demand-driven 2% origin miss is wrong because Netflix uses proactive pre-positioned fill. Netflix's
own doc does say exactly that (verified verbatim), but the researcher graded a generic VOD blueprint
against Netflix specifically. This blueprint explicitly models a BOUGHT CDN contract -- its own cdn
assumption says 'treat this row as the contract you bought, not a machine you own' -- and demand-
driven fill is CORRECT for a bought CDN (CloudFront/Fastly). Proactive fill is what you get only if
you build your own CDN, as Netflix did. Notably Google, which also runs its own edge, states the
OPPOSITE of Netflix: 'GGC servers cache content dynamically, according to local user demand... We
don't pre-fill the caches in any way.' So there is no single 'real' fill model to be wrong about.
Worth one clarifying sentence, not a defect.  Two small numeric notes I found independently: (a)
base_latency_ms 25.0 on the object store is optimistic against AWS's own published figure of
'roughly 100-200 milliseconds' first-byte-out; immaterial here since that row runs at 7.5%. (b) The
blueprint calls 5,500 GET/s the S3 'ceiling', but AWS words it as a floor -- 'at least ... 5,500
GET/HEAD requests per second per partitioned prefix' with 'no limits to the number of prefixes in a
bucket' -- so the row is a self-imposed key-layout constraint, not a store limit.

**Fix**

(a) Drop playback_start from 0.04 to ~0.004 (a 30-minute session at 0.25 seg/s is ~450 segments per
start) and give the freed share to segment_fetch; this makes the blueprint's own 'the control plane
is small' lesson land harder rather than weaker. (b) Add one sentence to the cdn assumption
distinguishing demand-driven fill (what the 2% correctly models for a bought CDN) from proactive
pre-positioned fill (what an operator of its own CDN can do), noting that under the latter the
origin row is sized by nightly catalogue delta rather than peak miss -- and that Netflix and Google
made opposite choices here. (c) Reword the store assumption from 'ceiling' to AWS's own framing: a
per-partitioned-prefix floor that scales with prefix count. (d) Optionally raise object-store
base_latency_ms toward AWS's documented 100-200 ms.  WORTH PRESERVING -- a grounding win the
researcher missed: this blueprint's two load-bearing video numbers are exactly confirmed by a
primary Netflix-authored source. Huang, Johari, McKeown, Trunnell & Watson (SIGCOMM '14, two authors
at Netflix) states 'each chunk containing a fixed duration of video (four seconds per chunk in our
service)' -- matching the blueprint's 4-second segments -- and its Figure 9 caption reads 'the
average chunk size is 1.5MB (4s times 3Mb/s)', matching the blueprint's 1.5 MB/segment exactly. The
derived 26,000 req/s ~ 300 Gbps checks out (26,000 x 1.5 MB = 312 Gbps), and that is the right order
of magnitude against Netflix's real ~200 Gbps storage appliance. Date this: the SIGCOMM figures are
2014.

**Verified sources**

- https://openconnect.netflix.com/Open-Connect-Overview.pdf
- https://openconnect.netflix.com/en/appliances/
- https://yuba.stanford.edu/~huangty/sigc040-huang.pdf
- https://papers.freebsd.org/2021/eurobsdcon/gallatin-netflix-freebsd-400gbps.files/gallatin-netflix-freebsd-400gbps-slides.pdf
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html
- https://support.google.com/interconnect/answer/7658593
- https://help.netflix.com/en/node/306

### web_crawler

- **shape:** reasonable_simplification · **numbers:** implausible

**What a reader would get wrong**

Which tier fails first, again — and here the cause is one un-cited input. The blueprint declares the
fetcher fleet the bottleneck at 78.2% (I reproduce it: 2,970/3,800 = 0.782) and puts the dedupe tier
at 14.8%, i.e. effectively free. That rests on the `dedupe` assumption: '~10 URL-seen checks per
page against a 100,000 ops/s Redis node gives ~10,000 pages/s per node.' The only fully-disclosed
measurement of this quantity contradicts it. Lee, Leonard, Wang & Loguinov (IRLbot, WWW 2008,
Beijing), which I extracted and read: over 41 days on a single server on a 1 gb/s backbone the
crawler 'parsed out 394,619,023,142 links' from 'N = 6,380,051,942 unique HTML pages' — 61.9 links
per page (the paper's own analytical model uses l = 59 links/page) — and found 41,502,195,631 unique
pages, i.e. 6.5 genuinely new URLs per page. Every extracted link must be checked against the seen-
set before you know whether it is new; that is the entire purpose of the paper's DRUM structure, and
the paper names it as 'the first performance bottleneck we faced... the complexity of verifying
uniqueness of URLs'. At 61.9 checks/page the Redis tier carries 1,616 pages/s per node, so 2 nodes =
3,231 pages/s against 2,970 pages/s of demand = 91.9% utilisation. Dedupe, not fetch, becomes the
binding constraint — which is exactly what the crawler literature says. Note the precision of this:
the SAME ~10 figure is correct in the neighbouring `q` (frontier) assumption, because the frontier
enqueues only NEWLY DISCOVERED URLs and IRLbot measured 6.5 of those per page. So the defect is
specifically the dedupe row confusing 'new URLs' with 'links checked'. Secondary, non-bottleneck-
relocating: the `store` assumption's '~100 KB/page compressed' yields 778 TB/month at 3,000 pages/s;
Common Crawl CC-MAIN-2026-34 (August 2026) publishes 2.14 billion pages in 84.78 TiB of compressed
WARC = 42.5 KB/page, which puts the same crawl near 339 TB. The blueprint overstates its own
dominant cost line by ~2.3x. Also internally inconsistent: the store row is labelled 'WARC batches'
but the flow charges 1 PUT per page (41.6% of the 2-prefix S3 ceiling); CC-MAIN-2026-34 packs 2.14e9
pages into 100,000 WARC files = ~21,400 pages per object, at which rate the PUT line is nil.

**Fix**

Change one input and one sentence. In the `dedupe` assumption replace '~10 URL-seen checks per page'
with a cited measured figure — IRLbot: 61.9 links extracted per page, of which 6.5 are new — which
drops the row from 10,000 to ~1,616 pages/s per node and correctly moves the bottleneck from fetch
(78.2%) to dedupe (~92%). Leave the `q` frontier assumption alone: its ~10 enqueues/page is the
right quantity (new URLs) and is conservative against IRLbot's measured 6.5. Then two consistency
fixes: (a) reconcile the store row — either charge one PUT per WARC batch or drop the 'WARC batches'
label, and re-derive the storage line from a cited page size (Common Crawl's measured 42.5 KB
compressed/page, or IRLbot's 21.2 KB average HTML page) instead of the un-cited 100 KB; (b) add one
line to the assumptions stating that DNS is folded into the fetch row's 250 ms, because Najork &
Heydon (Compaq SRC Research Report 173, 26 Sep 2001) record that 'DNS name resolution is a well-
documented bottleneck of most web crawlers' and that before their custom multithreaded resolver
'performing DNS lookups accounted for 70% of each thread's elapsed time. Using our custom resolver
reduced that elapsed time to 14%.' Omitting DNS as a tier is defensible at L0; omitting it silently
is not, given the blueprint declares every other gap. The other shape gaps (robots.txt cache as a
component, a memory model for the seen-set, a politeness-backlog input) are genuine L0
simplifications and I would not call them defects — the blueprint already declares politeness as the
real constraint the engine cannot express.

**Verified sources**

- http://irl.cs.tamu.edu/people/hsin-tsang/papers/www2008.pdf
- http://www.cs.cornell.edu/courses/cs685/2002fa/mercator.pdf
- https://data.commoncrawl.org/crawl-data/CC-MAIN-2026-34/index.html
- https://commoncrawl.org/latest-crawl

### youtube

- **shape:** reasonable_simplification · **numbers:** implausible

**What a reader would get wrong**

The size of the bottleneck the blueprint itself names -- this one is a genuine defect and I
confirmed it two independent ways.  The transcode assumption states 'A rendition task is ~2 s of
encode work, so a worker sustains ~0.5 tasks/s.' I verified the arithmetic: 20 uploads/s x 6
renditions = 120 tasks/s against 320 workers x 0.5 = 160/s capacity = the stated 75% util. That
means the entire 6-rendition transcode of an uploaded video costs 12 CPU-seconds REGARDLESS OF VIDEO
LENGTH -- not physical for any video longer than a few seconds.  I re-derived the real floor more
conservatively than the researcher did, because it used Google's VP9 figure without applying the
paper's own codec discount. ASPLOS '21 (Google) says a 2-second 1080p VP9 chunk 'could be encoded in
10 seconds' needing '5-6 chunks concurrently' for real time = ~5 CPU-sec per video-second per
output; the same paper says VP9 software is '6-8x slower and more expensive than H.264', so the
CHEAPEST published software case is ~0.7 CPU-sec per video-second per output. Multi-output
transcoding does not rescue this: the paper measures 'MOT throughput is 1.2-1.3x higher than SOT' --
it saves the decode, not the encodes. So a 10-15 minute upload costs roughly 600-2,500 CPU-seconds
for a six-rung ladder versus the model's 12: the fleet is undersized by roughly 50-250x. That is two
orders of magnitude, not the researcher's 2,250x, but the conclusion survives at every point in the
range. A reader provisions a transcode farm ~100x too small and reads a 48-second time-to-publish
where Google reports 'minutes to hours'.  Decisive corroboration needing no external source: the
corpus contradicts itself. Sibling blueprint video_streaming.json states the correct rule outright
-- 'Transcoding itself is a BATCH workload (minutes of GPU/CPU per title) and is not modelled... a
transcode farm is sized against a backlog-drain deadline instead. The queue row here models job
submission only.' youtube.json violates its own corpus's stated rule by pricing that batch work per-
second.  Second, independent finding the researcher missed: the named bottleneck is not robust. I
computed every row -- Watch/API tier 71.4%, object store 72.2%, transcode fleet 75.0%. Three rows
within 4 percentage points, and the object store's 72.2% rests entirely on an unsourced 96% CDN hit
rate. Any of the three flagged issues flips which component a reader optimises. A model whose top
three rows are that tightly clustered should not assert a single bottleneck without a sensitivity
note.  I DROPPED the researcher's claim that the miss rate is '2.5-7x understated' because Google
publishes 70-90%. That is not comparable: Google's 70-90% is offload at the in-ISP GGC tier ONLY,
with Edge PoPs behind it absorbing more, so end-to-end origin offload is higher than 70-90%. The
structural point stands (Google's edge is two tiers, the blueprint has one, and Google explicitly
does not pre-fill GGC), but the quantification does not follow from that source.  On shape I am
gentler than the researcher, which marked proportion 'misleading'. The traffic mix itself
(90/6/2/1/1) has no source contradicting it, and the omissions -- chunk/GOP sharding, sharded
metadata, single CDN tier -- are defensible L0 teaching simplifications that individually do not
move the bottleneck. The one materially missing component is the recommender: YouTube's watch/home
surface is driven by a two-stage candidate-generation + ranking DNN (Covington/Adams/Sargin, RecSys
2016 -- now 10 years old, so treat as directional), and the blueprint serves watch_page from Redis
plus a SQL read replica. I have no published figure for its compute cost, so I claim only that it is
unmodelled and likely material -- which matters precisely because the top three rows are 4 points
apart.

**Fix**

Re-derive the transcode row from encode work rather than an invented task rate. Either (preferred,
and consistent with the corpus's own stated rule in video_streaming.json) drop the transcode fleet
out of the per-second request model entirely and size it as a batch backlog-drain, leaving job
submission on the queue row; or state encode cost explicitly as CPU-seconds per video-second per
rendition (published software floor ~0.7 for H.264 1080p, ~5 for VP9), multiply by an assumed
average video length, and raise the worker count to the resulting order of magnitude. Remove or
heavily caveat the '48 s time-to-publish' -- Google publishes 'minutes to hours' for upload.  Add a
sensitivity note that Watch/API (71.4%), object store (72.2%) and transcode (75.0%) sit within 4
points, so the declared bottleneck is not robust; cite the 96% hit rate as an assumption with no
source behind it. Add a mid-tier cache row or an assumption line naming the two-tier edge (in-ISP
GGC in front of Edge PoPs in front of the data centre), noting Google states it does not pre-fill
GGC. Add one assumption line naming the recommendation/ranking service as the real cost of a watch
page. Optionally note that real YouTube metadata was never PostgreSQL: MySQL sharded behind the
Vitess routing proxy from 2010, built precisely because replicas and then the primary ran out of
capacity -- the failure mode this blueprint's single primary would hit.

**Verified sources**

- https://gwern.net/doc/cs/hardware/2021-ranganathan.pdf
- https://support.google.com/interconnect/answer/9058809
- https://support.google.com/interconnect/answer/7658593
- https://cloud.google.com/blog/products/networking/understanding-google-cloud-network-edge-points
- https://vitess.io/docs/22.0/overview/history/
- https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/
- https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol


---

# Round 2 — the remaining 29 (2026-09-12)

Round 1 graded the 27 most-published systems. This is every blueprint that was left: the ones with
thinner public records, and the MCP/agent stacks that have no published production architecture at
all. For those the correct answer is "no public figure exists" — they were judged against the
documented behaviour of the primitives they are built from (Redis, Postgres, pgvector, published
provider rate limits) and graded as reasoned constructions, not observed ones.

**29 graded · 99 claims dropped in verification · 214 sources survived.**

| | count |
|---|---|
| Shape — matches | 5 |
| Shape — reasonable simplification | 14 |
| Shape — **misleading** | 10 |
| Numbers — plausible | 12 |
| Numbers — **implausible** | 15 |
| Numbers — no public figure exists | 2 |

## Per blueprint

### code_editor

- **shape:** misleading · **numbers:** implausible

**What a reader would get wrong**

THE STRONGEST CONFIRMED FINDING IN EITHER FILE IS ONE NUMBER: `runner` base_latency_ms = 120 with 3
concurrent slots. I verified it is indefensible from two primary sources. Firecracker (Agache et
al., NSDI '20, 25-27 Feb 2020) says a microVM 'boots to application code in less than 125ms' — so
120 ms is approximately the BOOT FLOOR of an empty sandbox, before any user code compiles or runs.
The only user-visible figure a real operator of this product publishes is Replit's (31 Jan 2021)
'99th percentile session boot time dropped from ~2 minutes to ~15 seconds', and that is the number
AFTER their fix. A 'run my code' service time of 120 ms covers none of the actual work.  I re-
derived the consequences myself rather than taking them on trust, and the researcher overstated two
of them:  - CONFIRMED: at the blueprint's own 400 runs/s, capacity 28 x 3 = 84 concurrent slots
gives 84 runs/s at 1 s per run -> 476% utilisation, versus the engine's reported 57.1%. At 2 s/run
it is 952%. - CORRECTED: the researcher says the runner is 'a comfortable 17.1 points behind at
57.1%'. The engine's 17.1-pt margin is over `app` at 59.3%; the runner is THIRD, 19.2 points behind.
Minor, but it misstates what the engine said. - CORRECTED: the researcher claims that even after
cutting the run share 10x to 40 runs/s the tier is 'still ~143%, still the binding tier'. That is
arithmetically wrong — 40 runs/s against 84 slots at 1 s/run is 47.6%, comfortably below collab. The
claim treats one instance as one concurrent slot and ignores the declared 3. What actually survives:
the runner binds at any duration >= 1 s at the blueprint's own share, and is still ~95% at a 5x
share cut with 1 s runs, but it is NOT robust to a 10x share cut at 1 s. The verdict flip is real
but conditional on the run-share assumption, and that conditionality must be stated. - DROPPED:
'sandbox density is ~100x too thin per Firecracker'. The paper's 'Each worker runs hundreds or
thousands of MicroVMs (each providing a single slot)' describes RESIDENT single-tenant slots, most
of them idle holding memory — the paper's own model moves slots through init/idle/busy. It is not a
count of concurrently-executing sandboxes. 3 simultaneous compile-and-run jobs per host is
conservative, not 100x wrong.  WHAT MAKES IT MISLEADING RATHER THAN MERELY IMPRECISE: the `runner-
headroom` assumption attaches genuinely good reasoning — 'Headroom is the feature on a Run button' —
to a number that cannot support it. A reader is told they hold deliberate 55% headroom on the one
tier that is over capacity, and the engine's rps model structurally cannot see the difference: a
request occupying a slot for seconds is not the same object as one returning in 3 ms. That is the
textbook 'optimise the wrong component' failure.  SHAPE — CONFIRMED. Neither documented leader uses
this split. Replit, verbatim: 'We must ensure that there is only a single container per repl at
anytime. The container is used to facilitate multiplayer features, so its important that every user
in the repl connects to the same container' — one long-lived container IS both collaboration host
and sandbox. StackBlitz (20 May 2021) removes the server runner entirely: 'All code execution
happens inside the browser's security sandbox, not on remote VMs or local binaries', explicitly
contrasting itself under a heading 'What about Code Spaces/Sandbox/Repls/…?'. The blueprint presents
a third shape as if it were standard. The Kafka dispatch hop compounds it: at 400/16,000 = 2.5% it
renders placement as free, whereas Replit routes replit.com/@user/repl -> repl-it-web -> Eval ->
Controlplane -> Conman (18 Mar 2024) and AWS's equivalent is 'a custom high-volume ... low-latency
(<10ms 99.9th percentile latency) stateful router'. Scheduling is a stateful placement lookup, not a
durable log. Same phantom `cache(x1.0)` on the edit path as the Docs file, and the same missing
ownership component.  PROPORTION — WRONG, and here the researcher's strongest evidence needs no
proxy. Opens at 6% = 1,200/s against a documented 30-minute default idle timeout (GitHub Codespaces:
'By default this period is 30 minutes'; Gitpod/Ona: 'workspaces stop following 30 minutes without
user input', configurable to 24 hours) gives 1,200 x 1,800 = 2.16M concurrent workspaces — roughly
100x Replit's published 'tens of thousands of Repls at any one time'. That is primary-source against
primary-source with no Yjs proxy involved. The heartbeat route agrees (800 presence/s at a 15 s
renewal caps ~12,000 sessions -> a 10-second workspace session). Separately I verified that `save-
file` at 8% = 1,600/s supplies 1,600 of the 2,020 rps that make Postgres look 25% busy; calling it
implausible for a sync-persisted editor is reasonable engineering judgement, not a sourced claim, so
I flag it as a soft note.  NUMBERS. `runner` 25 rps / 120 ms / 3 concurrent: proven above, the
single most consequential number in either file. `store` base_latency_ms = 25 contradicts AWS's
published 'roughly 100–200 milliseconds' for small objects by 4-8x. `collab` 2,200 rps: no published
counterpart found — 'no public figure' is the honest label, not 'too low'. The Eg-walker measurement
(EuroSys '25, C1 = 652k events, OT 365 ms / Eg-walker 56.1 ms / reference CRDT 52.5 ms / Yjs 84.1 ms
on a Ryzen 7950x pinned to one core, ~0.56 us/event) is real and I verified every figure in the
paper PDF — but it CANNOT be used to say a server tier should sustain millions of ops/s: the paper
explicitly states 'We do not use the server-based Jupiter algorithm [44] or the popular OT library
ShareDB [21]', and it measures a whole-trace batch merge, not a server's per-op transform-and-
broadcast loop. Use it only for what it proves — the merge algorithm is not the cost — which Figma
independently corroborates by winning '>10x faster serialization'. cache/db/lb/cdn figures are
generic but unobjectionable.

**Fix**

1. Stop modelling the runner as a request rate; model it as a concurrency pool with declared
concurrent sandboxes per instance and a stated run DURATION. Cite the bounds honestly: Firecracker's
<125 ms is the microVM boot floor, Replit's p99 session boot is 15 s, and a real compile-and-run is
seconds. Then re-run — and publish the sensitivity, because the verdict depends on the run-share
assumption as well as the duration. 2. Replace `base_latency_ms: 120` with a stated breakdown of
what it covers — cold start vs warm reuse vs actual execution. A single 120 ms figure for 'run my
code' is the defect. 3. Justify 3 concurrent sandboxes per instance with a stated CPU/memory budget
per sandbox, or change it. Do NOT raise it toward Firecracker's 'hundreds or thousands' — that
figure counts resident idle slots, not concurrent executions, and importing it would introduce a
second error. 4. Fix the mix from a stated session-duration assumption. Anchor it on the documented
30-minute default idle timeout (Codespaces/Gitpod) and sanity-check the result against Replit's
published 'tens of thousands of Repls at any one time' — the current open share fails that check by
~100x. Derive presence from a stated heartbeat interval, labelled as a proxy. Cut `run-code` sharply
and state the editor-events-per-run ratio explicitly, since the runner verdict now rides on it. 5.
Offer the observed shapes as first-class: one long-lived container per workspace that is both
collaboration host and sandbox (Replit), with browser-side execution (StackBlitz WebContainers) as
the variant that removes the tier. If the split tiers are kept, say in an ASSUMPTION that the split
is a construction, not an observed design. 6. Replace the Kafka dispatch hop with a
placement/scheduler component on the run path carrying its own latency and capacity budget, citing
Firecracker's '<10ms 99.9th percentile' stateful router and Replit's Eval -> Controlplane -> Conman
path. 7. Remove `cache(x1.0)` from `edit-sync`, add a workspace-ownership component, and correct
`store` base_latency_ms to 100-200 ms — the same three corrections as google_docs.json, since the
files share a skeleton.

**Verified sources**

- https://replit.com/blog/killing-containers-at-scale
- https://replit.com/blog/regional-goval
- https://replit.com/blog/eval
- https://blog.stackblitz.com/posts/introducing-webcontainers/
- https://www.usenix.org/system/files/nsdi20-paper-agache.pdf
- https://docs.github.com/en/codespaces/setting-your-user-preferences/setting-your-timeout-period-for-github-codespaces
- https://ona.com/docs/configure/workspaces/workspace-lifecycle
- https://www.figma.com/blog/making-multiplayer-more-reliable/
- https://www.figma.com/blog/how-figmas-multiplayer-technology-works/
- https://www.figma.com/blog/rust-in-production-at-figma/
- https://arxiv.org/abs/2409.14252
- https://github.com/yjs/y-protocols/blob/master/src/awareness.js
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html

### dns_system

- **shape:** misleading · **numbers:** implausible

**What a reader would get wrong**

CONFIRMED, and the strongest of the three findings. The blueprint puts a Redis answer-cache and a
Postgres read replica on the authoritative query path, and the engine's top two tiers are both
artifacts of that invented path. I reproduced the engine exactly: ns 49,900/75,000 = 66.53% (engine
says 0.6653), cache 49,900/80,000 = 62.38%, margin 4.16 pts (engine says 4.16), rr 1,995 rps. So the
runner-up tier at 62.4% is a component no published authoritative DNS server has on its query path,
and 1,995 rps of replica traffic models a lookup that never happens. NSD's docs name it as 'designed
with a pure philosophy that prioritises raw performance' at 'hundreds of thousands or even millions
of queries per second' with no database backend; PowerDNS is the one authoritative server with a
real SQL backend and its own performance page says cache memory 'is handled by malloc in your libc'
with zero mention of Redis or memcached. Even Cloudflare, the one major KV-backed authoritative
stack, is a LOCAL read not a network hop: the Quicksilver v2 post (2025-07-10) says v1 had each
server keep 'a full copy of the data'. The blueprint is also internally self-contradictory — its own
ns assumption says 'Knot/NSD serving pre-signed zones from memory', while its flow sends every query
from ns to Redis to Postgres. NUMBERS: 25,000 qps per 2-vCPU instance is 12,500/core. Lencse's peer-
reviewed RFC-8219 benchmark (IEEE Access 2020) measures 177,735 qps on a SINGLE core, and >1.5 Mqps
/ >2.5 Mqps for Knot and NSD on 16- and 32-core hosts, with BIND and YADIFA — the slow pair — unable
to exceed 260,000 qps. The blueprint's rating is ~14x below a single core. Its own hedge
('Conservative: published figures on larger hardware are considerably higher') does not cure this,
because the engine's named bottleneck IS that hedged number. I also confirm the two constraints that
actually bind a 50k-qps anycast authoritative service are absent: per-POP packet rate (Cloudflare
auto-mitigated 2.14 Bpps / 3.8 Tbps, 'predominantly leverage UDP on a fixed port', 2024-10-02) and
zone-propagation staleness (Cloudflare 2017: 'new DNS data actually available to 99% of our global
PoPs in under 5s').

**Fix**

1) Delete `cache` and `rr` from the query flow; make it `edge -> ns` and state in an assumption that
the zone is resident in RAM (NSD/Knot) — this also removes the blueprint's contradiction of its own
ns assumption. If you want the DB-backed shape instead, rename `ns` to PowerDNS and fold its packet
cache into nameserver service time rather than modelling it as a component. 2) Re-rate `ns` to
~150,000-200,000 per 2-vCPU instance (conservative even against Lencse's measured 177,735 qps/core).
Note the ordering dependency: at 150k the fleet drops to 11.09%, but `edge` only becomes the top
tier at 41.65% if fix (1) has also removed the phantom 62.38% cache — do both or neither. 3) Re-rate
`edge` in packets/s with explicit DDoS headroom. 60,000 qps/POP is only 1.2x the 50,000 fleet rate,
which over-provisions nothing and directly contradicts the edge assumption's claim that anycast POPs
are 'deliberately over-provisioned to absorb reflection/amplification floods'. 4) Replace the Kafka
`q` throughput tier with a propagation-latency budget (Cloudflare's <5s to 99% of PoPs), or relabel
it as DNS NOTIFY + IXFR. Note SIDN distributes the .nl zone to its 80+ anycast partners as 'an
updated copy of the .nl zone file every half an hour' — a periodic file copy, not a message bus. 5)
Route zone_update through its own control-plane ingress, not the UDP/53 anycast edge. 6) The 160 B
egress figure matches an unsigned A response but the file says zones are pre-signed: use ~195 octets
for ECDSA P-256 or ~747 for RSA-4096 (Huston, APNIC 2021-10-18), or drop the DNSSEC claim. 7) Keep
the workload assumption — 50k qps is well calibrated against .nl's ~4 billion queries/day (~46k qps
average) across 80+ servers, and the 99.75/0.2/0.05 split errs generously toward writes, which is
the safe direction. Note the proportion verdict stands at reasonable_simplification: `api` sits at
12.5% and `db` at 1.25%, so the write mix never approaches binding and cannot misdirect a reader.

**Verified sources**

- https://nsd.docs.nlnetlabs.nl/
- https://doc.powerdns.com/authoritative/performance.html
- https://blog.cloudflare.com/how-we-made-our-dns-stack-3x-faster/
- https://blog.cloudflare.com/quicksilver-v2-evolution-of-a-globally-distributed-key-value-store-part-1/
- https://www.sidnlabs.nl/en/news-and-blogs/our-dns-infrastructure-in-focus
- https://en.blog.nic.cz/2019/12/10/epic-dns-benchmarking/
- https://www.hit.bme.hu/~lencse/publications/IEEE-Access-2020-AuthDNS-revised.pdf
- https://www.knot-dns.cz/benchmark-400G/
- https://blog.cloudflare.com/how-cloudflare-auto-mitigated-world-record-3-8-tbps-ddos-attack/
- https://blog.apnic.net/2021/10/18/dnssec-with-rsa-4096-keys/

### food_delivery

- **shape:** misleading · **numbers:** plausible

**What a reader would get wrong**

COMPONENT SHAPE IS GENUINELY WELL SUPPORTED — I verified every load-bearing source myself. Lyft's
RedisConf17 deck (Daniel Hochman) shows the courier geo-index literally as `pipeline.zset(geohash,
user_id, now_seconds())` with `pipeline.zremrangebyscore(geohash, -inf, now_seconds() - 30)`,
scaling '2015: 1 cluster of 3 instances' to '2017: 50 clusters with a total of 750 instances'. So
'Redis holds courier positions, Postgres never sees a GPS point' is a real, load-bearing pattern,
not a textbook invention. Uber's DISCO and 'drivers that send update every 4 seconds' are confirmed
via HighScalability's report of Matt Ranney's 14 Sep 2015 talk (SECONDARY, reporting a named Uber
Chief Systems Architect talk). DoorDash's Kafka spine is confirmed by InfoQ's recording of Allen
Wang (DoorDash Data Platform tech lead, QCon Plus, 9 Jun 2023): Iguazu scaled 'from processing just
a few billion events to hundreds of billions of events per day'. I am NOT downgrading on component
shape.  I AM grading `misleading` on two independent grounds, both of which land on the single
output this model produces — the named bottleneck, which wins by 1.79 points.  DEFECT 1: THE TRAFFIC
MIX IS SELF-CONTRADICTORY BY 1-2 ORDERS OF MAGNITUDE (I re-derived this from the blueprint's own
assumptions). Little's Law on its stated cadences: 900 orders/s x 900 s (15-min delivery) = 810,000
deliveries in flight. At 'customers poll every 5 s while waiting' that is 162,000 polls/s; the
blueprint allocates 3,750 — 43x short. At a 30-min delivery, 324,000 polls/s — 86x short. Courier
pings at 1-per-4-s with 3 orders batched per courier: 67,500/s against an allocated 6,000 — 11x
short; unbatched at 30 min, 405,000/s — 68x short. The most generous case I could construct (10-min
deliveries, 3 orders batched) still gives 45,000 pings/s + 108,000 polls/s = 153,000/s against the
blueprint's 9,750 — 15.7x short. Read backwards: 6,000 pings/s at one per 4 s is 24,000 couriers on-
job, which sustains 13 orders/s (30 min, unbatched) to 80 orders/s (15 min, 3 batched) — not 900.
This flips the verdict rather than merely perturbing it. Because dispatch share (0.05) is pinned to
order share (0.06), the mix inflates dispatch load in lockstep with orders. In a self-consistent
mix, tracking is >99% of requests, the tracking tier is pegged far past 100%, and dispatch sits near
1%. The engine names dispatch over tracking by 1.79 percentage points (71.43% vs 69.64%) — a margin
far inside the error bar on two unsourced per_instance_rps values, and on the wrong side of the
arithmetic. The blueprint's own headline insight ('the thing people underestimate about this
product' is that tracking dominates) is correct and matches Uber's verified 'At some point, 80% of
requests made to the backend API gateway were polling calls' — and then it under-applies that
insight by one to two orders of magnitude.  DEFECT 2, UNDISCLOSED: DISPATCH IS A PERIODIC BATCH
SOLVE, NOT A REQUEST SERVICE. I opened the full text of the DoorDash deployed-dispatch paper (Wu,
Hou, Xie, arXiv 2606.13604v1) and it states verbatim 'serving hundreds of millions of daily
inferences at a 20-second cadence', 'The system executes approximately three runs per minute',
wrapping a 'combinatorial assignment optimizer' over 'approximately 4,000 geographic regions';
deliberate delay is a FEATURE (batching +0.495 pp, p<0.001, in their switchback test). The blueprint
models this as a synchronous 350 rps/instance service with a 40 ms request. There is no public per-
instance rps figure for an assignment service because real ones are not sized in rps at all. A
learner told to 'add dispatch instances' is reaching for a lever that does not exist; the real
levers are cadence, zone size, and how long you delay assignment to batch. The blueprint discloses
the polling-vs-streaming simplification honestly (good) and does not disclose this one.  SCALE, FOR
CONTEXT (verified, not a defect on its own): DoorDash's 8-K of 15 Feb 2024 says 'Total Orders
increased 23% Y/Y to 574 million' in Q4 2023 = 72.2 orders/s mean, so roughly 220-360/s at peak
hour. The blueprint's 900 orders/s is ~2.5-4x DoorDash's global peak — high, but inside a teaching
reference's licence.  NUMBERS: `plausible`, with one named exception. Redis at 40,000 rps/instance
is defensible against Lyft's verified 10-15M QPS on 750 instances (~15-20k/instance); Postgres at
8,000 rps is fine; no public figure exists for the app-tier per_instance_rps values, which is the
honest answer. The exception is the dispatch pair (350 rps/instance, 40 ms) — it is the one figure
contradicted by a primary source describing the only published production dispatch system, and it is
the figure that produces the headline.

**Fix**

1) Derive the flow shares from Little's Law instead of asserting them: pick a delivery duration and
a batching factor, compute in-flight deliveries from the order rate, then derive ping and poll
volumes from the stated 4 s / 5 s cadences. Either drop the order share to ~0.001-0.004 (13-60
orders/s at 15,000 rps), or keep 900 orders/s and let system_rps rise to the ~150k-400k rps the
tracking fan-out actually implies — and say which choice you made and why. 2) Stop modelling
dispatch as a request-rate service. Either lift it out of the request-path model and describe it in
prose as a periodic batch optimiser (citing the verified 20-second cadence / ~3 runs per minute /
~4,000 regions), or model it as N regions x 3 solves per minute with a per-solve service time in
seconds, so the capacity lever reads as 'cadence and zone size' rather than 'instance count'. 3) Add
a dispatch assumption matching the honesty of the existing streaming caveat: 'assignment is modelled
as a request service; real dispatch is a periodic combinatorial solve whose cost tracks region count
and queue depth, not arrival rate.' 4) Keep the single-Postgres SPOF disclosure exactly as written —
do NOT add a 'DoorDash abandoned Postgres here' counter-example, because I could not verify that
claim from any source I could open (see dropped_claims). 5) State that the engine's 1.79-point
dispatch-over-tracking margin is smaller than the uncertainty on either per_instance_rps, so the
blueprint should not present a single named bottleneck at all until the mix is fixed.

**Verified sources**

- https://arxiv.org/abs/2606.13604 and https://arxiv.org/html/2606.13604v1 — Wu, Hou, Xie, 'Multi-Agent Reinforcement Learning from Delayed Marketplace Feedback for Objective-Weight Adaptation in Three-Sided Dispatch'. PRIMARY (deployed DoorDash system). I opened the full HTML; confirmed verbatim: 'serving hundreds of millions of daily inferences at a 20-second cadence', 'The system executes approximately three runs per minute', 'combinatorial assignment optimizer', 'approximately 4,000 geographic regions', batching +0.495 pp (p<0.001) all-day and +0.600 pp (p=0.010) at dinner.
- https://www.uber.com/en-GB/blog/real-time-push-platform/ — Uber Engineering, PRIMARY. Confirmed verbatim: 'At some point, 80% of requests made to the backend API gateway were polling calls'; 'more than 1.5M concurrent connections and pushes over 250,000 messages per second'; the earlier SSE-based RAMEN peaked at 'over 70,000 QPS push messages per second... up to 600,000 concurrent streaming connections'. Timeline confirmed: RAMEN on SSE 2015, reboot 2017, gRPC from late 2019, post published Dec 2020.
- https://www.slideshare.net/slideshow/redisconf17-lyft-geospatial-at-scale-daniel-hochman/77087313 — Daniel Hochman (Lyft), RedisConf17, the speaker's own deck. PRIMARY. Confirmed: 'pipeline.zset(geohash, user_id, now_seconds())', 'pipeline.zremrangebyscore(geohash, -inf, now_seconds() - 30)', '2015: 1 cluster of 3 instances' -> '2017: 50 clusters with a total of 750 instances', 10-15M QPS.
- https://highscalability.com/how-uber-scales-their-real-time-market-platform/ — SECONDARY: HighScalability reporting Matt Ranney (Chief Systems Architect, Uber), 'Scaling Uber's Real-time Market Platform', 14 Sep 2015. Confirmed verbatim: 'The logic to match all of supply and demand is a service called DISCO (dispatch optimization)'; 'The write rate is derived from drivers that send update every 4 seconds as they move around'; 'Design goal is to handle a million writes per second'. NOTE: a 2015 architecture, likely superseded.
- https://www.infoq.com/presentations/doordash-event-system/ — SECONDARY: InfoQ recording of Allen Wang (Tech Lead, Data Platform, DoorDash), QCon Plus, recorded 9 Jun 2023. Confirmed: Iguazu scaled 'from processing just a few billion events to hundreds of billions of events per day with four nines of delivery rate', on Kafka + Apache Flink.
- https://www.sec.gov/Archives/edgar/data/1792789/000162828024005043/dashq42023ex991-pressrelea.htm — DoorDash Q4 2023 results, SEC EDGAR 8-K exhibit, 15 Feb 2024. PRIMARY. Confirmed verbatim: 'Total Orders increased 23% Y/Y to 574 million'.
- https://www.cockroachlabs.com/blog/doordash-cockroachdb-massive-scale/ — SECONDARY: Cockroach Labs reporting Michael Czabator (DoorDash storage infrastructure) at RoachFest 2023, published 7 Feb 2024. Confirmed SCALE FIGURES ONLY: 'About 1.2 million queries per second at daily peak hours', 'About 2,300 total nodes spread across 300+ clusters', 'About 1.9 petabytes of data on disk'. This page does NOT say DoorDash migrated off Postgres — see dropped_claims.

### google_docs

- **shape:** misleading · **numbers:** implausible

**What a reader would get wrong**

I re-derived the engine's arithmetic from the file and it is internally correct: edit-op 24,600 +
presence 1,800 = 26,400 into collab against 14 x 2,500 = 35,000 -> 75.43%; the 15.43-pt margin is
over `app` at 60.0%. The defects are in what that number measures, not how it was computed.  (1)
CONFIRMED, AND THE LOAD-BEARING ONE. The headline utilisation measures a resource the blueprint
itself says is not the sizing driver. The `collab` assumption reads 'Instance count therefore tracks
CONCURRENT DOCUMENTS, not raw op rate' — yet the engine reports 75.4% of an OP-RATE ceiling and 15
points of headroom. A reader acting on that ('I can take ~33% more ops before this tier binds') is
applying the wrong lever by the blueprint's own account. Figma's published design supports the
assumption, not the metric: 'each document lives exclusively on one specific worker' (rust-in-
production, 2 May 2018), 'multiplayer holds the state of the file in-memory' (Tsung, 20 Oct 2022),
'a design file is mapped to one instance of Multiplayer' (Goel, 21 Nov 2019). The binding resources
on that tier are in-memory bytes per open file, open socket count, and broadcast bandwidth.  (2)
CONFIRMED. No document-to-instance ownership component exists, despite a stickiness assumption that
requires one. Figma needed an explicit '(lock UUID, file key)' entry to ensure 'only one Multiplayer
instance is writing to the journal at a time' precisely to avoid split-brain. The blueprint draws
sticky routing as a load-balancer property. This is the hard part of the category and it is absent.
(3) CONFIRMED BUT TEMPERED. Durability for edits is only `store(x0.01)` — a snapshot per ~100 ops.
That is the checkpoint-only design Figma ran and then replaced in Oct 2022 because it could lose 'up
to 60 seconds of work on the server-side if multiplayer crashes'. The blueprint DOES disclose the
cadence in its `store` assumption; what it does not disclose is the consequence (bounded data loss).
I verified the researcher's flip: routing edits through the queue at x1.0 gives (24,600+600)/16,000
= 157.5%, past collab. But Figma explicitly batches journal writes ('batching allows less frequent
journal writes'), so at a realistic 5:1 batch the tier lands ~31% and does not flip. The honest
finding is that the durable-write tier is UNMODELLED and is a live contender under plausible
batching, not that it certainly binds.  (4) CONFIRMED, SECONDARY. `edit-op` routes 100% of ops
through Redis for 'hot document state'. No primary source puts per-op document state in a shared
cache: Google's 2010 post keeps 'the current state of the document as of the last processed change'
on the server; Figma keeps it in the multiplayer process's memory. It also contradicts the
blueprint's own stickiness assumption — if every editor of a doc is already on one instance, a
shared cache has nothing to do on the per-op path. This misleads about MECHANISM, not bottleneck
location (the tier sits at 29,400/200,000 = 14.7%), so I grade it below (1)–(3).  (5) PROPORTION —
real flag, weaker than claimed. Presence at 6% = 1,800 ops/s and opens at 6% = 1,800/s. If presence
is a heartbeat, y-protocols' `outdatedTimeout = 30000` with renewal at half that (15 s) caps
concurrency at ~27,000 sessions, and Little's law then gives a 15-second average document session —
absurd. I verified that arithmetic. Two caveats the researcher did not surface: Google Docs does not
use Yjs, so the 15 s floor is a reasoned proxy from a documented primitive, not an observed Docs
figure; and 'presence-cursor' may mean cursor-movement messages, which are typing-driven and carry
no floor. Credit where due: the researcher correctly showed the error is self-correcting for the
verdict — folding opens into presence gives collab 28,200/35,000 = 80.6% and app 30%, so the named
tier binds harder.  (6) NUMBERS. `collab` per_instance_rps = 2,500: I searched and found NO
published counterpart in any primary source; it is unanchored, and by the blueprint's own assumption
it may be a documents-per-instance proxy rather than an op rate, which the engine cannot
distinguish. `store` base_latency_ms = 30 is PROVEN wrong against AWS's own guidance — 'consistent
small object latencies ... of roughly 100–200 milliseconds' — i.e. 3-6x optimistic, and Figma
reports whole-file checkpoints taking '~4 seconds or more' for the worst 5% of files. That single
proven contradiction is what carries the implausible verdict. The 30,000 rps object store implies
~6-10 partitioned prefixes (3,500 PUT / 5,500 GET each) that nothing declares, but at 2,286 rps
actual it does not bite today.

**Fix**

1. Relabel `collab`'s capacity honestly, and make it the top correction. Either model the tier as
concurrent documents with a stated memory-per-document figure, or keep an rps figure and attach a
GAP saying no vendor publishes one — citing that Figma's own win was '>10x faster serialization'
(May 2018), i.e. the cost is serialization and socket handling, not the merge algorithm. Do not
report an op-rate utilisation on a tier whose own assumption says instances track documents. 2. Add
a document-ownership component (lock/registry) traversed by `open-doc` at x1.0, with an assumption
citing Figma's '(lock UUID, file key)' lock and the split-brain problem it solves. 3. Add a durable
journal between `collab` and storage carrying the edit stream BATCHED, with the batch ratio stated
as its own assumption, and keep the snapshot as `store(x0.01)` — Figma runs journal + checkpoint
together. Report the durable-write tier as a contender whose utilisation swings with the batch
ratio, rather than asserting a flip. 4. Remove `cache(x1.0)` from `edit-op`. Keep Redis on
`presence-cursor`, `open-doc` and `list-and-permissions` and rename it 'presence + session routing'.
5. State a session-duration assumption and derive the mix from it: pick an average session, get
concurrency from the open rate by Little's law, get presence from a stated heartbeat interval (cite
y-protocols' 30 s timeout / 15 s renewal as a PROXY, labelled as such). Today's 82/6/6/4/2 implies a
15-second session and will not survive that derivation. 6. Correct `store` base_latency_ms to
100-200 ms against AWS's published figure, and add an assumption that a whole-file checkpoint is a
multi-second operation at p95. 7. Add an explicit collaborators-per-document factor as its own
ASSUMPTION with a range. The blueprint's `collab` assumption already says the 2,500 figure 'covers
the transform ... plus broadcast to the other editors on that document' — so fan-out is folded in,
not omitted — but the reader cannot see how sensitive the tier is to that factor. Discord's 2017
post is the right citation for why it matters.

**Verified sources**

- https://idl.uw.edu/future-scholarly-communication/files/2010-GoogleDocs-OT.pdf
- https://drive.googleblog.com/2010/09/whats-different-about-new-google-docs_22.html
- https://svn.apache.org/repos/asf/incubator/wave/whitepapers/operational-transform/operational-transform.html
- https://www.figma.com/blog/how-figmas-multiplayer-technology-works/
- https://www.figma.com/blog/making-multiplayer-more-reliable/
- https://www.figma.com/blog/rust-in-production-at-figma/
- https://www.figma.com/blog/under-the-hood-of-figmas-infrastructure/
- https://arxiv.org/abs/2409.14252
- https://discord.com/blog/how-discord-scaled-elixir-to-5-000-000-concurrent-users
- https://github.com/yjs/y-protocols/blob/master/src/awareness.js
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html

### hotel_reservation

- **shape:** misleading · **numbers:** plausible

**What a reader would get wrong**

THE HEADLINE CLAIM IS EXACTLY BACKWARDS, AND I CONFIRMED IT BY RE-RUNNING THE ENGINE'S OWN
ARITHMETIC. The blueprint writes in capitals: 'THE AUTHORISATION TIER IS THE BOTTLENECK AT 80%, NOT
THE APP TIER.' Its search:book ratio is 0.75/0.06 = 12.5:1.  I extracted the IATA report text myself
(WebFetch could not parse the PDF; I downloaded it and ran pdftotext) and confirmed every quoted
line verbatim: 'Far from the 100- to 300-to-1 observed with airlines' own websites, the look-to-book
ratios for OTAs or MSEs are in the best case 1,000-to-1 but more commonly above 10,000-to-1'; 'an
average look-to-book ratio in the range of 5,000- to 10,000-to-1 should be achievable'; 'It seems
that 1,000 to 1 is achievable for simple domestic itineraries'; 'it is widely expected that the
ratio will remain in the several thousands to 1'. Provenance confirmed from the document itself:
March 2019, IATA-commissioned, study by 'Jean Philippe Mesure, independent consultant from ITS4T,
who conducted more than 25 interviews with leading industry actors'.  CAVEAT I MUST ADD THAT THE
RESEARCH DID NOT: the IATA figures are AIRLINE NDC distribution, not hotel — that is a cross-domain
transfer and should be stated as one. The hotel-native anchor is stronger and points the same way:
Booking.com reports 'over 8 billion requests per day, with peaks of 100,000 requests per second' and
'sell around one billion reservations per year' — 8e9 requests/day against 1e9/365 = 2.74e6
reservations/day is 2,920 requests per reservation. On either anchor the blueprint is 8x to 800x too
booking-heavy.  THE RE-RUN, WHICH I DID MYSELF: every flow in this blueprint traverses `app`, so app
utilisation is 2000/(4x650) = 76.92% REGARDLESS of the mix. Only `pay` is sensitive to the booking
share. Holding search at 1,500 rps: at 100:1 the pay tier falls to 10.0% utilisation; at 300:1,
3.33%; at 1,000:1, 1.0%; at 10,000:1, 0.1%. So under EVERY published look-to-book ratio — including
the most booking-heavy figure in the literature, an airline's own website — the payment tier is
nowhere near the constraint and the app/search tier is the sole binding resource. The engine's
verdict wins by 3.08 points (80.00% vs 76.92%), a margin smaller than the uncertainty on a single
unsourced per_instance_rps, and the correction runs the wrong way by a factor of 8 at absolute
minimum. This is the textbook case of a design sending a learner to optimise the wrong component, so
`misleading` stands despite the honest ASSUMPTION labelling — the label asserts the inverted claim
rather than hedging it.  SECOND CHECK, SAME DIRECTION (my arithmetic): 120 booking attempts/s is
10.37M/day, i.e. 3.8x Booking.com's ENTIRE global reservation rate, served here by four m6i.large
instances and one Postgres primary.  THIRD, A STRUCTURAL GAP THE ASSUMPTIONS DO NOT FLAG: there is
no price-check hop and no hold hop, although the DB is literally labelled 'inventory, holds,
reservations'. Expedia's Rapid lodging docs confirm the normal path is Shop -> Price Check -> Book,
with Price Check defined as 'Confirms the price returned by the Shop response. Use this API to
verify a previously-selected rate is still valid before booking', plus explicit hold-and-resume
('Some inventory isn't eligible for hold and resume') and expiring tokens. For an OTA there is also
a supplier/CRS call in the booking path that is slower and more rate-limited than any card acquirer;
the blueprint models the acquirer as the only external dependency, which is the LESS constraining of
the two.  WHAT IS RIGHT AND SHOULD BE KEPT — the cache-in-front-of-a-replica shape for availability
genuinely matches how hotel ARI flows. Google's official docs confirm 'ARI feeds aren't queried for
specific prices or itineraries. Instead, you push messages when your pricing model has new or
changed data', with 'an account-level maximum update rate of 400 messages per second', prices
'visible to users within 15 to 20 minutes', and 'Prices stay in the cache indefinitely until
updated'. And 30 ms of own-work per search sits comfortably inside Google's confirmed live-pricing
budget, 'typically up to 4000 milliseconds' with deadlines configurable as low as 500 ms. The caveat
that the engine models throughput and not lock contention is exactly the right disclosure and should
survive untouched.  NUMBERS: `plausible`. No public per-instance figure exists for a hotel search
API or a payment-authorisation service — that is the honest answer for app (650 rps / 30 ms) and pay
(50 rps / 150 ms); the 150 ms acquirer round trip is in a defensible band; Redis 40,000 and Postgres
8,000 are fine. One figure needs a footnote rather than a correction: the 150 auth/s 'contracted
acquirer rate limit' is 6x Stripe's published per-endpoint default and 1.5x its global live-mode
default — Stripe's own table reads 'Global API rate limit — Live mode: 100 requests per second' and
'Individual API endpoints (unless otherwise noted): 25 requests per second'. Achievable only as a
negotiated enterprise limit, which the blueprint should say.

**Fix**

1) Set the booking share from a published look-to-book ratio and cite it. Even the most generous
figure in the literature (100:1, an airline's own website) drops book_room from 0.06 to ~0.0075 and
moves the bottleneck to the app tier; the hotel-native Booking.com anchor (~2,900 requests per
reservation) is stronger still. Re-run and let the engine say so — 'a booking funnel is a search-
capacity problem' is both a more useful and a more defensible design lesson than the current one. 2)
If you want to keep a payment-constrained case, make it a separate flash-sale what-if with the
booking share raised deliberately and LABELLED as such, not the default mix. 3) Add the two missing
hops on the booking path — a price-check/re-validate call before book, and a hold with a TTL. Both
are documented in Expedia's public Rapid API and they are the mechanism that makes hotel inventory
hard. 4) Say explicitly whether this is an OTA or a single chain's own booking engine; if OTA, add a
supplier/CRS component in the booking path, because it changes which external dependency binds. 5)
Footnote the 150 auth/s ceiling against Stripe's published 100 rps global / 25 rps per-endpoint
live-mode defaults so a reader knows it assumes a negotiated contract. 6) If you cite the look-to-
book evidence, cite IATA honestly as an AIRLINE NDC figure transferred to hotel, paired with the
Booking.com hotel-side figure. Do NOT add the overbooking / yield-management citation the research
proposed — I could not verify it (see dropped_claims).

**Verified sources**

- https://www.iata.org/contentassets/6de4dce5f38b45ce82b0db42acd23d1c/ndc-scalability-report.pdf — IATA / ITS4T, 'Addressing NDC scalability challenges in the leisure market', March 2019, study by Jean Philippe Mesure (ITS4T) from 25+ industry interviews. PRIMARY. I downloaded the PDF and extracted the text directly; all look-to-book quotes confirmed verbatim, as were the date and authorship. NOTE: airline NDC distribution, not hotel — a cross-domain transfer, so pair it with the Booking.com figure.
- https://www.apollographql.com/blog/how-booking-com-orchestrated-their-service-architecture-with-apollo-federation — SECONDARY: Apollo GraphQL reporting Sanver Tarmur (Senior Software Engineer, Booking.com) at GraphQL Summit 2024. Confirmed verbatim: 'over 8 billion requests per day, with peaks of 100,000 requests per second', '120 million active clients across iOS, Android, and Web', 'sell around one billion reservations per year', 'support 140 service connections'.
- https://developers.google.com/hotels/hotel-prices/dev-guide/ari-overview — Google, official docs. PRIMARY. Confirmed verbatim: 'ARI feeds aren't queried for specific prices or itineraries. Instead, you push messages when your pricing model has new or changed data'; 'There is an account-level maximum update rate of 400 messages per second'.
- https://developers.google.com/hotels/hotel-prices/dev-guide/delivery-mode — Google, official docs. PRIMARY. Confirmed: 'Your prices should be served by Google and visible to users within 15 to 20 minutes after a message has been received'; for Changed Pricing, 'Prices stay in the cache indefinitely until updated'.
- https://developers.google.com/hotels/hotel-prices/dev-guide/query-messages — Google, official docs. PRIMARY. Confirmed: 'All Live pricing query requests have a response time limit which is typically up to 4000 milliseconds', with a worked example at DeadlineMs 500.
- https://developers.expediagroup.com/rapid/lodging/shopping/about-shopping-api — Expedia Group, official developer docs. PRIMARY. Confirmed: the Shop -> Price Check -> Book sequence; 'Confirms the price returned by the Shop response. Use this API to verify a previously-selected rate is still valid before booking'; 'maximum of 250 properties per request'; 'Some inventory isn't eligible for hold and resume'; 'Tokenized request links will expire after a short period. If a token link returns an HTTP 503 error, the link has likely expired'.
- https://docs.stripe.com/rate-limits — Stripe, official docs. PRIMARY. Confirmed from the rate-limit table: 'Global API rate limit — Live mode: 100 requests per second'; 'Individual API endpoints (unless otherwise noted): 25 requests per second'.

### id_generator

- **shape:** misleading · **numbers:** implausible

**What a reader would get wrong**

SHAPE and NUMBERS confirmed as misleading/implausible; I am DOWNGRADING the researcher's separate
'proportion: misleading' to reasonable_simplification (see below). The file welds two mutually
exclusive ID algorithms together and then puts the wrong one's database on Snowflake's hot path.
Snowflake's whole reason to exist is that generation needs no coordination: Twitter's archived 2010
README specifies 'sequence number - 12 bits - rolls over every 4096 per machine', giving each worker
4,096 IDs/ms locally, so `db(x0.001)` on the generate flow models a segment fetch a Snowflake node
never performs. Block allocation is the OTHER algorithm — Flickr's ticket servers (2010-02-08,
REPLACE INTO + LAST_INSERT_ID(), two MySQL boxes split odd/even via auto-increment-offset) and
Leaf's segment mode, whose README makes leaf.segment.enable and leaf.snowflake.enable independently
switchable alternatives (segment uses a MySQL leaf_alloc table; snowflake uses ZooKeeper for workId
and touches no database). The `rep` decode path compounds it: decoding a Snowflake ID is a shift and
a mask on the client. NUMBERS are where the real damage is: 6,000 rps on 2 vCPU = 3,000/core against
Leaf's published 'On the basis of 4C8G VM, through the company RPC method, QPS pressure test results
are nearly 5w/s, TP999 1ms' = 12,500/core, and below Twitter's own 2010 floor of 'minimum 10k ids
per second per process'. I reproduced the engine: app 50,000/72,000 = 69.44% (engine 0.6944), lb
50.00%, margin 19.44 pts (engine 19.44). Re-rate app to 25,000 and utilisation falls to 16.67%, the
L4 load balancer becomes the top tier at 50.00%, and the honest teaching answer emerges — at 50k rps
an ID service is network-bound, not CPU-bound. A 19.44-pt margin reads as high confidence in a
ranking that one corrected number reverses; that is a bottleneck-location error and the reason shape
stays misleading. WHY I DOWNGRADED PROPORTION: the researcher's arithmetic on the mix is right — I
verified that at 1,000-ID blocks and 48,500 generate rps the real allocation rate is 48.5/s, so the
separate 2% reserve_block flow at 1,000 rps double-counts it at 20.6x, and it contradicts the file's
own db assumption ('touched once per 1,000 IDs on the hot path (visit_prob 0.001) because each node
buffers a block locally'). But the effect is confined to `db`, which moves from ~1.3% to 13.11% and
is never near binding either way, and `rep` sits at 1.25%. The mix error alone would not send anyone
to optimise the wrong component, so by the stated fairness rule it is a reasonable_simplification
with an internal-consistency defect, not a misleading proportion. CREDIT: the clock-skew assumption
is the most valuable sentence in the file and is exactly right — Snowflake's real failure modes are
correctness failures no utilisation number will surface.

**Fix**

1) Pick one algorithm and say which. If Snowflake: delete `db` from the generate_id path entirely
and keep `coord` only for worker-id leasing at startup plus heartbeat (Leaf uses ZooKeeper for
exactly this; the file's honest note that the 5% per-request visit is a modelling stand-in for a
startup concern is fine). If segment/ticket-server: drop the Snowflake framing, model Leaf's block
fetch from leaf_alloc, and cite Flickr as the ancestor. 2) Re-rate `app` to ~25,000 rps/instance for
2 vCPU, from Leaf's measured ~50,000 QPS at TP999 1ms on a 4C8G VM. Expect the bottleneck to move to
the L4 load balancer at 50.00% — the correct and more useful answer. 3) Fix `reserve_block`: derive
its share from block size and generate rate (~48.5 allocations/s = ~0.1% of system traffic at
1,000-ID blocks), not an independent 2% that contradicts the file's own visit_prob 0.001. 4) Delete
`rep` and the decode_id replica visit, or relabel it honestly as an unrelated metadata lookup that
is not part of ID generation. 5) Add the algorithmic ceiling as a first-class assumption — it is the
only capacity number here with a hard source: 4,096 IDs/ms/worker for Twitter Snowflake (~49M/s
across 12 nodes) versus Sonyflake's explicit trade of '2^8 IDs per 10 msec at most in a single
instance' = 25,600/s/machine (307k/s across 12 nodes) from its 39/8/16 bit layout. The bit layout
you choose can itself be the binding constraint. 6) Say plainly that the LB-plus-service-nodes shape
is the 2010 Twitter shape and that the repo was archived on 2021-09-18 ('We have retired the initial
release of Snowflake'), that Instagram put generation inside Postgres to avoid running a service at
all ('We've delegated ID creation to each table inside each shard, by using PL/PGSQL', because 'the
additional complexity required to run an ID service was a point against it'), and that modern
practice is an embedded library. 7) Keep the clock-skew assumption verbatim.

**Verified sources**

- https://github.com/twitter-archive/snowflake/tree/snowflake-2010
- https://github.com/twitter-archive/snowflake
- https://github.com/sony/sonyflake
- https://github.com/Meituan-Dianping/Leaf/blob/master/README.md
- https://instagram-engineering.tumblr.com/post/10853187575/sharding-ids-at-instagram
- https://code.flickr.net/2010/02/08/ticket-servers-distributed-unique-primary-keys-on-the-cheap/

### kv_store

- **shape:** misleading · **numbers:** implausible

**What a reader would get wrong**

THE BOTTLENECK IS AN INVENTED COMPONENT, AND THE MARGIN THAT CROWNS IT IS NOISE. This is the most
serious blueprint in the cluster and I confirm it, with the read-fan-out finding strengthened by a
source the researcher cited but did not fully use.  I reproduce all five contenders exactly: q
45,000/60,000 = 75.00%; replica (50,000 + 90,000 + 15,000) = 155,000/208,000 = 74.52%; coord
250,000/336,000 = 74.40%; lb 248,750/350,000 = 71.07%; primary 45,250/64,000 = 70.70%. Margin 0.48
pts.  (1) NO DYNAMO-LINEAGE STORE HAS A SHARED REPLICATION-LOG TIER ON THE WRITE PATH. Three primary
sources, three different mechanisms, none of them a central queue: - Cassandra's architecture doc:
"If a hint is stored, the coordinator will later attempt to replay the hint and deliver the mutation
to the replicas" — coordinator-local. - Dynamo (SOSP'07): "Nodes that receive hinted replicas will
keep them in a separate local database that is scanned periodically" — node-local on the replacement
node; and the coordinator "replicates these keys at the N-1 clockwise successor nodes," i.e.
straight to the preference list. - DynamoDB (ATC'22): "The replication group uses Multi-Paxos for
leader election and consensus... Upon receiving a write request, the leader of the replication group
for the key being written generates a write-ahead log record and sends it to its peer (replicas),"
with log replicas that "do not store key-value data" living on log nodes inside the group. Bundling
a node-local commitlog, node-local hinted handoff, and a downstream CDC bus into one shared 2-node
tier manufactures a chokepoint the real systems deliberately avoid — and the engine names it the
bottleneck. A reader is sent to shard a Kafka cluster that should not be on that path. This alone
justifies shape_verdict = misleading under the stated test.  (2) THE READ FAN-OUT IS WRONG ON THE
TIER NAMED AFTER IT, AND THE PRIMARY SOURCES BRACKET IT FROM BOTH SIDES. The tier is "Follower
replicas (quorum reads)" modelled at replica(x0.25) — a 25% miss times ONE replica read, which is
R=1. - Cassandra: "For read operations, the coordinator generally only issues read commands to
enough replicas to satisfy the consistency level" — QUORUM at RF=3 is 2, so x0.5. - Dynamo is
stronger still and the researcher missed it: "for a get() request, the coordinator requests all
existing versions of data for that key from the N highest-ranked reachable nodes in the preference
list for that key, and then waits for R responses" — fan-out is N=3, i.e. x0.75. Dynamo's common
config is stated as "The common (N,R,W) configuration used by several instances of Dynamo is
(3,2,2)." So the model is 2x low against Cassandra and 3x low against Dynamo. I recomputed the
correction conservatively, leaving scan at its modelled x4: replica = 100,000 + 90,000 + 15,000 =
205,000/208,000 = 98.6% — already 23.6 pts clear of the named bottleneck. With scan at x8 it is
105.8% (over capacity). The verdict flips either way; the x8 is not needed to reach the conclusion.
The blueprint gets the WRITE fan-out right (leader x1 + followers x2 = RF 3), matching Cassandra's
"Write operations are always sent to all replicas, regardless of consistency level" — which makes
the read-side error the more striking.  (3) THE MARGIN CANNOT SUPPORT A VERDICT. Five tiers inside
4.3 points, named on a 0.48-pt gap. To the engine's credit its own `contenders` list names all five;
the headline still picks one. The correct report line is "no single bottleneck — five tiers within 5
points, any can bind first under skew."  (4) THE FOLLOWER COUNT CONTRADICTS THE BLUEPRINT'S OWN RF.
It states "Replication factor 3... one leader write plus TWO follower writes." 8 leader shards x 2 =
16 follower roles. The blueprint has 26, with no stated reason. This is why I grade numbers as
implausible: not the per-instance rates, but the instance counts, which are internally inconsistent
with the design's own stated replication factor.  (5) THE CACHE IS LOAD-BEARING AND DYNAMODB
PUBLISHED THE WARNING. "Since the configuration information about partition replicas rarely changes,
the cache hit rate was approximately 99.75 percent. The downside is that caching introduces bimodal
behavior. In the case of a cold start where request routers have empty caches, every DynamoDB
request would result in a metadata lookup, and so the service had to scale to serve requests at the
same rate as DynamoDB." The blueprint's own cold-cache note already lands 200k on a 208k tier (96%);
with the corrected quorum fan-out a cold cache puts 200,000x2 + 90,000 + 15,000 = 505,000 against
208,000 — roughly 243%. (Caveat I add: DynamoDB's was a metadata cache on routers, not a row cache,
so the analogy is structural rather than exact. Separately, a shared centralised row cache in front
of a partitioned store is not native to either system — DAX is an optional bolt-on and Cassandra's
row cache is off by default.)  (6) PER-SHARD RATE, FAIRLY LABELLED. AWS publishes verbatim:
"throttling will occur if a single partition receives more than 3000 read operation or more than
1000 write operations," and adaptive capacity can deliver "up to the partition maximum of 3,000 RCUs
and 1,000 WCUs" to one key. 8,000 rps/shard is defensible for a self-hosted node — this is a
labelling gap, not an implausible figure (see dropped_claims).

**Fix**

1. Delete the shared replication-log component or split it honestly: a node-local commitlog + hints
costed onto `primary`/`replica`, and a separate downstream CDC/streams bus that is NOT on the put
critical path. Re-run; the bottleneck will then land on a component that exists in the systems being
taught. 2. Fix the read fan-out to match the tier's own name: get -> replica(x0.5) for Cassandra
RF=3/QUORUM, or x0.75 for the Dynamo get() behaviour (coordinator reads all N reachable, waits for
R). If CL=ONE is intended, rename the tier — right now the name and the number disagree and the
difference is the entire verdict. 3. Derive the follower count from the stated RF: 8 shards x 2 =
16. If 26 is deliberate read headroom, say so and show the arithmetic; do not leave a number
contradicting the blueprint's own RF=3 sentence. 4. When five tiers sit within 4.3 points, have the
report print "no single bottleneck — five tiers within 5 points, any of them can bind first under
skew" rather than naming one on a 0.48-pt margin. 5. Promote the cold-cache case to a first-class
what-if with the corrected fan-out (~243% of the follower tier) and cite the DynamoDB MemDS
bimodality experience as the reason a 75%-hit shared cache is a hazard rather than headroom. 6. Put
AWS's published per-partition ceiling (3,000 reads / 1,000 writes) next to the 8,000 rps/shard
assumption and say explicitly that the managed-service figure is an admission-control quota, not a
hardware limit — so the comparison informs rather than alarms.

**Verified sources**

- https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf
- https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html
- https://www.usenix.org/system/files/atc22-elhemali.pdf
- https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/burst-adaptive-capacity.html

### metrics_monitoring

- **shape:** misleading · **numbers:** implausible

**What a reader would get wrong**

I independently reproduced every engine figure from the JSON: ingest 77.34%, writer 76.15%, q
73.33%, query 66.67%, lb 66.67%, store 62.25%, cache 54.00%. Margin 1.19pts. The researcher's
reproduction is exact.  (1) SHAPE — the query path never touches the writer, and I confirm this is
misleading, but for a more precise reason than the researcher gave. Mimir's own docs state verbatim:
"Queriers read recent data from ingesters and older data from long-term object storage via store-
gateways" (ingester component doc, verified), with blocks uploaded "every two hours by default" and
RF=3. The blueprint's dashboard_query and alert_eval go lb → query → cache → store only. Grafana
names this exact coupling as the reason it built ingest storage: "In classic architecture, ingester
nodes are highly stateful. They combine in-memory data with local write-ahead logs (WALs) and
participate in both writes and reads. This can lead to heavy queries disrupting live writes"
(verified verbatim).  Precision the researcher overstated: adding writer(x1.0) to both query flows
at the SHIPPED numbers moves the writer only from 76.15% to 76.92% — the bottleneck ranking does not
flip. The harm is not in the static verdict; it is that the coupling is structurally inexpressible
under what-if, which is the engine's primary use. A reader asking "what if query load grows 100x?" —
the exact question this tool exists to answer, and the exact failure Grafana documents — gets a
writer tier that never moves. At 400,000 q/s with the edge present the writer hits 153% and is the
unambiguous #1. That is why I keep "misleading" rather than downgrading: the blueprint is not just
simplified, it is unable to express the documented failure mode of its own subject.  (2) BOTTLENECK
IS AN ARTEFACT — confirmed, with one correction. Flip A holds and I re-derived it: Mimir's capacity-
planning doc gives verbatim "CPU: 1 core every 25,000 samples per second" (distributor), "1 core for
every 300,000 series in memory" (ingester), "1 core for every 10 queries per second" (querier and
store-gateway), "1 core for every 250 queries per second" (query-frontend), and "rules evaluation is
computationally equal to queries execution, so the querier resources recommendations apply to ruler
too." 400,000 samples/s = 16 distributor cores; 4,000 q/s = 400 querier cores. The read tier is ~25x
the distributor tier on published sizing while the engine names a write component. The ingester leg
needs an assumed scrape interval to convert samples/s to active series, so the "~36 cores of write
path" figure is a derivation, not a citation — but the conclusion is robust across any plausible
interval.  Flip B is directionally right and numerically wrong as stated. The researcher's 90.6%
sums 1,980 block writes and 3,000 block reads and grades the total against AWS's GET-only ceiling of
5,500/s. Graded per axis, neither clears the receiver (1,980 PUT vs 3,500 = 56.6%; 3,000 GET vs
5,500 = 54.5%); graded as a combined figure against the PUT ceiling it is 142%. The engine only
accepts one capacity per component, so some mixing is forced — but the specific "90.6%, well clear
of the receiver" line is a mixed-axis artefact. The underlying finding survives intact and is the
one that matters: the store's unsourced 8,000 rps on instances=1 exceeds BOTH published S3 per-
prefix ceilings, and correcting it to either published figure moves the store from 62% into or past
contention. The #1 ranking is unstable under a correction the blueprint's own GAP note half-
anticipates.  (3) UNIT MIX — confirmed. Prometheus docs verify "max_samples_per_send: 2000" and
"capacity: 10000" as defaults, and that remote write batches. 400,000 samples/s is ~200 HTTP req/s
at the LB, against 600,000 req/s of declared capacity — 3,000x over-provisioned, arithmetic
verified.  PROPORTION — wrong, confirmed. Grafana's 500M-active-series test ran against "10,000
queries per minute" (~167 q/s) with 100+ distributors, 100+ ingesters, 100+ queriers, 50 store-
gateways, 30 compactors, 20 query-frontends — all verified verbatim. The blueprint's 100:1
write:query ratio is roughly 1,000x more query-heavy than that deployment. And I verified the
Monarch paper directly from the PDF text rather than trusting the summary: "Approximately 95% of all
queries are standing queries (including alerting queries)... they only issue ad hoc non-standing-
queries very occasionally" (p.10). Also verified in the PDF: 950B time series, 750TB memory, 2.2
TB/s ingested July 2019, >6M QPS, median root query latency 79ms, 99.9%ile 6s. The blueprint's 60:40
alert:dashboard split contradicts this, and pricing an alert at ~12x cheaper than a dashboard
contradicts Mimir's ruler==querier statement. Standing-query load is under-weighted in both share
and unit cost.  CREDIT, verified: the spine (LB → receiver → Kafka → TSDB writer → object store +
cached query tier) is a current shape, not a fantasy — Mimir's ingest storage is exactly this. Alert
eval on the query tier matches HRT, whose post I verified says query nodes run "recording rules,
alerts, and ad-hoc queries" while shards handle ingest. The query engine's 600 rps at 60ms implies
~17 q/s/core, within 2x of Mimir's documented 10 — that number is fine. The GAP note on store bytes
is correct and well written, and the cardinality caveat is honest.  NUMBERS — implausible,
confirmed. Writer at 10,000 samples/s/instance vs Mimir's measured ~250,000/ingester (verified:
"about 1 billion / 20s = 50 million samples per second", "600 ingesters", RF=3 → 150M writes / 600 =
250k) is 25x low. Receiver at 8,000 vs 25,000/core is ~3x low. Store capacity exceeds the published
ceiling of its own primitive. Cache at 20,000 rps/Redis node: no public figure found, and it is not
load-bearing.

**Fix**

1. Add the missing edge — give both query flows a writer(x1.0) hop before store. State plainly in
the report that this is about what-if fidelity, not the static ranking: at the shipped mix it moves
the writer 76.15%→76.92%, but it is the only way the documented "heavy queries disrupt live writes"
failure becomes expressible at all. 2. Re-proportion. Grafana's comparable 500M-series deployment
carried ~167 q/s; Monarch reports ~95% of queries are standing. Suggested: ingest 0.9995, alert_eval
0.00045, dashboard_query 0.00005. 3. Price a rule evaluation like a query. Mimir: "rules evaluation
is computationally equal to queries execution." Give alert_eval a cache/store fan-out comparable to
dashboard_query. 4. Re-base per-instance numbers on Mimir's capacity-planning doc and cite it,
turning four ASSUMPTIONs into GROUNDED: distributor 25,000 samples/s/core; ingester 300,000 in-
memory series/core (drive the writer off active series, not sample rate); querier and store-gateway
10 q/s/core; query-frontend 250 q/s/core. 5. Resolve the write-path unit mix — either declare the
file in samples/s and drop the LB's request-scale capacity, or introduce remote write's documented
2,000-samples-per-request batching factor so lb/ingest are sized in HTTP requests (~200/s). 6. For
store, set instances to the real block-ULID prefix fan-out, or keep instances=1 and use the
published per-prefix ceilings — but grade READ and WRITE separately (5,500 GET/s, 3,500 PUT/s) and
say which binds. Do not sum 1,980 writes and 3,000 reads against the GET number; that overstates the
correction. Either honest treatment still shows the current 8,000 is unsourced and above both
ceilings. 7. Optional teaching value: add a compactor/downsampler. Thanos does 5m after 40h and 1h
after 10d, and its docs say downsampling "can increase the size of your storage a bit (~3x)" —
counterintuitive and worth a line. 8. Restate the verdict honestly: with a 1.19-point margin over
two contenders whose capacities are unsourced, the correct line is "three tiers are effectively
tied; the ranking is set by assumed per-instance rates, not by structure."

**Verified sources**

- https://www.vldb.org/pvldb/vol13/p3181-adams.pdf — VLDB 2020; verified by extracting the PDF text directly, not from a summary. Confirms 950B series, 750TB memory, 2.2TB/s, >6M QPS (all July 2019), ~95% standing queries, median root latency 79ms / 99.9%ile 6s.
- https://grafana.com/docs/mimir/latest/manage/run-production-environment/planning-capacity/ — all six per-core rules and the ruler==querier statement confirmed verbatim.
- https://grafana.com/docs/mimir/latest/references/architecture/components/ingester/ — "Queriers read recent data from ingesters"; 2-hour block upload; RF=3 default.
- https://grafana.com/docs/mimir/latest/get-started/about-grafana-mimir-architecture/about-ingest-storage-architecture/ — "participate in both writes and reads. This can lead to heavy queries disrupting live writes" confirmed verbatim; Kafka between distributors and ingesters.
- https://grafana.com/blog/how-we-scaled-our-new-prometheus-tsdb-grafana-mimir-to-1-billion-active-series/ — 50M samples/s, 1,500 replicas, ~7,000 cores, 30TiB RAM, 600 ingesters, RF=3.
- https://grafana.com/blog/scaling-grafana-mimir-to-500-million-active-series-on-customer-infrastructure-with-grafana-enterprise-metrics/ — 100+ distributors/ingesters/queriers, 50 store-gateways, 30 compactors, 20 query-frontends, 10,000 queries per MINUTE.
- https://prometheus.io/docs/practices/remote_write/ — max_samples_per_send default 2000, capacity default 10000, batching confirmed.
- https://thanos.io/tip/components/compact.md/ — 5m downsampling after 40h, 1h after 10d, and the ~3x storage growth note.
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html — 3,500 PUT/COPY/POST/DELETE and 5,500 GET/HEAD per partitioned prefix; "There are no limits to the number of prefixes in a bucket."
- https://www.uber.com/en-IN/blog/m3/ — aggregates 500M metrics/s, persists 20M/s.
- https://www.hudsonrivertrading.com/hrtbeat/scaling-prometheus/ — query nodes run "recording rules, alerts, and ad-hoc queries"; shards handle ingest.

### parking_lot

- **shape:** misleading · **numbers:** implausible

**What a reader would get wrong**

THE CAUSAL STORY IS INVERTED, AND IT IS THE BLUEPRINT'S HEADLINE SENTENCE. The pay assumption says
the exit payment path is the bottleneck at 75% 'which is the right answer for a parking system,
because a queue at the exit barrier is a physical traffic jam.' I ran the numbers against a measured
primary source and the claim does not survive.  I downloaded and read Crommelin's 1972 paper in full
(the City of Irvine hosts a document headed 'Retyped Verbatim From the Original'). Table 4, 'PARKING
CONTROL SERVICE RATE', gives exiting via 'Casher, variable fee w/gate' at 19.5 sec/veh average
headway, 150 veh/hr design, 185 veh/hr maximum; coded-card/token-operated gate exit 9.0 s (320/400);
coin gate 20.4 s (140/175); entering ticket dispenser w/gate 5.5 s easy approach (520/650) or 9.5 s
sharp turn (305/380).  MY ARITHMETIC: 60 payments/s across 500 lots is 0.12/s per lot = 432 paid
exits per hour per lot. At Crommelin's measured 150 veh/hr design rate that needs ~2.9 exit-pay
lanes per lot running flat out. Each of those lanes serves one vehicle every 19.5 SECONDS, while the
modelled backend hop has a 120 ms service time — the physical serialiser is 162x slower than the
software the model blames. A backend at 75% utilisation cannot produce a queue at any individual
barrier, because no individual barrier ever sees more than 0.12 authorisations per second. The
engine's verdict wins by 3.57 points (75.00% vs 71.43%), inside the error bar on two unsourced
per_instance_rps values, and the mechanism it names is wrong by two orders of magnitude.  The
documented fix confirms the inversion. Crommelin, verbatim: the cashier-variable-fee strategy 'has a
capacity of approximately 150 vehicles per hour. Another approach might be to have the parker pay
his fee to the cashier before entering his car and then utilize a token operated gate as a means of
exit control. This control strategy would have over twice the capacity of a cashier lane itself.' No
amount of backend payment capacity buys that. A learner who takes this blueprint at face value
scales a service that is not the constraint and leaves the actual constraint — lane count and human
transaction time — untouched. The disclaimer does not rescue it, because the disclaimer is where the
inverted claim is asserted.  THE ONE CHECKABLE NUMBER IS WRONG BY 10-25x. base_latency_ms 120 for a
component explicitly described as 'blocks on the card terminal' is contradicted by Stripe's own
Terminal docs, confirmed verbatim: 'An authorization normally takes a few seconds to complete.' And
the real serialising resource is physical, also verbatim: 'A reader can process only one payment at
a time' — so the correct unit is readers-per-lane and seconds-per-authorisation, not a per-instance
rps ceiling on a backend service. (Curiously the 80 auth/s portfolio ceiling is coincidentally sane:
500 lots x ~2.9 exit-pay lanes at 19.5 s/veh is ~74 veh/s. The magnitude lands; the mechanism does
not.)  A PORTFOLIO AGGREGATE DRESSED AS A FACILITY. The workload is defined across ~500 lots but the
bottleneck claim ('a queue at the exit barrier') is a single-facility physical phenomenon. It also
runs entry (75/s), exit (65/s) and payment (60/s) peaks simultaneously, whereas Crommelin's design
guidance, confirmed verbatim, is that 'it is adequate to assume for design purposes that the morning
inbound peak flows are approximately equal to the evening outbound peak flows' — equal in magnitude,
at opposite ends of the day. Across 500 lots that can average out, but then it is no longer a
statement about any barrier. (The entry side does check out physically: 75/s across 500 lots is 540
veh/hr/lot against Crommelin's 520 design veh/hr for a ticket dispenser with gate, so ~1 entry lane
per lot at design rate. Sane.)  WHERE I CORRECT THE RESEARCH RATHER THAN CONFIRM IT: the 55%
availability-polling share is indeed an unsourced assertion, but SFpark does NOT cleanly rebut it.
SFpark's confirmed 'Every 60 seconds, the garage car counting program automatically sends the
following data to the SFpark data warehouse' governs SENSOR-TO-CENTRE INGEST (500 lots would be 8.3
pushes/s). The blueprint's 275 rps is CONSUMER READS from display boards and a mobile app — a
genuinely different quantity that nobody publishes. The right verdict on the 55% is 'no public
figure exists; label it as a construction', not 'SFpark proves it is 33x too high'.  WHAT THE
BLUEPRINT GETS RIGHT, AND I VERIFIED: the cache-drift failure mode is real, and the one published
production system mitigates it PHYSICALLY — 'the SFMTA requires garages to count manually the number
of cars in the garage at least once per day, and update the car count to match the manual count.'
The 3-broker Kafka quorum-not-capacity note is honest, the ALB-cost caveat is correct, and scoping
out ANPR, barrier hardware and offline gate behaviour is the right call, clearly stated.  NUMBERS:
`implausible`. The only per-instance figure checkable against a primary source — the 120 ms card-
terminal hop — is contradicted by Stripe Terminal's own documentation by 10-25x, and it is the
figure that produces the bottleneck. The 500 rps workload, the 350 rps/instance app tier and the 55%
availability share have NO public counterpart at all: no commercial parking operator publishes a
backend request rate, and the shape here is a reasoned construction, not an observed one. Saying so
plainly is worth more than an unmarked guess.

**Fix**

1) Make the serialising resource the physical one. Model the exit lane / card reader (one payment at
a time, a few seconds per authorisation, 19.5 s/veh measured headway at a variable-fee lane) rather
than a backend service with an rps ceiling — or at minimum state plainly in the pay assumption that
the modelled ceiling is a backend contract limit and that the real exit queue is governed by lane
count and human transaction time, giving Crommelin's measured numbers. 2) Raise base_latency_ms for
the payment hop from 120 ms to seconds, citing Stripe Terminal's 'An authorization normally takes a
few seconds to complete', and adjust per_instance_rps consistently. 3) Separate the two levels:
model ONE facility (a few vehicles per minute, where the design question is how many lanes) or model
the 500-lot PORTFOLIO (where the design question is central capacity and the barrier queue is
explicitly out of scope). Stop letting a portfolio-aggregate rps justify a per-barrier claim. 4)
Stagger the flow shares so entry and exit peaks are not simultaneous, or say explicitly that the mix
is a portfolio average across lots peaking at different hours, citing Crommelin's equal-magnitude /
opposite-time-of-day guidance. 5) Label the 500 rps workload, the 350 rps/instance app tier and the
55% availability-read share as unsourced constructions — and label them honestly: nobody publishes a
commercial parking backend, and SFpark's 60-second figure covers sensor ingest, not consumer reads,
so it does not substitute for the missing data. 6) Add pay-on-foot as the what-if variant. It is the
documented, measured fix ('over twice the capacity of a cashier lane itself') and it makes the
reference teach the right lesson: the lever is WHERE the payment happens, not how many backend
instances run it.

**Verified sources**

- https://www.sfmta.com/sites/default/files/reports-and-documents/2018/05/sfpark_dataguide_garagedata.pdf — SFpark Garage Data Guide, SFMTA, 26 Sep 2013. PRIMARY. Downloaded and text-extracted directly; confirmed verbatim: 'The garage revenue-control vendor keeps track of how many cars are in the garage at any given time using equipment on each entry/exit lane', the three-step loop-counter/ticket/gate cycle, 'Every 60 seconds, the garage car counting program automatically sends the following data to the SFpark data warehouse', and 'the SFMTA requires garages to count manually the number of cars in the garage at least once per day, and update the car count to match the manual count'. Also confirmed: 16th & Hoff capacity 58 (70 Fri-Sat), 189 total entries on the sample day; Fifth & Mission capacity 2,585.
- https://www.sfmta.com/sites/default/files/reports-and-documents/2018/08/sfpark_dataguide_parkingsensordata.pdf — SFpark Parking Sensor Data Guide, SFMTA, 4 Sep 2013. PRIMARY. Downloaded and text-extracted; confirmed verbatim: 'Sensors look for about ten seconds of stability after a change of status before making a determination that a vehicle has either arrived or departed'; 'The parking sensor network for SFpark includes over 8,200 spaces'; the equipment-table Total row reads 8,228 spaces with sensors and 11,917 total sensors; sensors relay via pole-mounted repeaters to gateways.
- https://legacy.cityofirvine.org/civica/filebank/blobdload.asp?BlobID=10063 — Robert W. Crommelin, P.E., 'Entrance-Exit Design and Control for Major Parking Facilities', Los Angeles Parking Association 'Seminar '72', Biltmore Hotel, Los Angeles, 5 Oct 1972. PRIMARY (the hosted document is headed 'Retyped Verbatim From the Original'). Downloaded and text-extracted; confirmed Table 4 in full, including exiting 'Casher, variable fee w/gate' 19.5 s/veh, 150 design / 185 max veh/hr; 'Coded-card/token-operated gate' 9.0 s (320/400); entering 'Ticket Dispenser w/gate' 9.5 s sharp turn (305/380) and 5.5 s easy direct approach (520/650); coin gate 20.4 s (140/175). Also confirmed verbatim: the pay-before-returning-to-car passage ('over twice the capacity of a cashier lane itself'), the equal morning-inbound / evening-outbound peak guidance, and the M/M/1 reservoir formula q = i^2/(1-i) with traffic intensity i = v/s. NOTE: a 1972 source — human transaction headway is the slowest-moving quantity here, but contactless payment has plausibly shortened the variable-fee exit since.
- https://docs.stripe.com/terminal/payments/collect-card-payment.md?terminal-sdk-platform=server-driven — Stripe Terminal, official docs. PRIMARY. Confirmed verbatim: 'An authorization normally takes a few seconds to complete'; 'A reader can process only one payment at a time' (the terminal_reader_busy error); 'After payment method collection you must authorize the payment or cancel collection within 30 seconds'; the flow is asynchronous and webhook-driven.
- https://docs.stripe.com/rate-limits — Stripe, official docs. PRIMARY. Confirmed: live-mode global 100 requests per second; individual API endpoints 25 requests per second.

### stock_exchange

- **shape:** misleading · **numbers:** implausible

**What a reader would get wrong**

The parts list is genuinely right — gateway/session layer, pre-trade risk, single-writer per-symbol
matcher, sequenced journal, market-data publishers, RDBMS of record, audit archive is what a real
venue is made of. But one load-bearing connection is wired backwards and the capacity that decides
the verdict is implausible, so `misleading` on shape stands.  (1) Risk is the most horizontally
scalable thing in the system and is named bottleneck only because it was given an implausible per-
instance figure. A 15c3-5 pre-trade check is a handful of limit comparisons against in-memory state
— the regulation requires controls to "Prevent the entry of orders that exceed appropriate pre-set
credit or capital thresholds in the aggregate for each customer" and to "Prevent the entry of
erroneous orders, by rejecting orders that exceed appropriate price or size parameters, on an order-
by-order basis", under "the direct and exclusive control of the broker or dealer". At SIX the entire
path — network boundary in, validate, process, acknowledge or fill, and back out — averages 10.6
microseconds, so the risk check is a sub-microsecond slice inside that. The blueprint charges it
5,000 rps/instance and 0.6 ms (600 us): I verified that is 56.6x the whole SIX round trip for one
inline check. Give risk any defensible figure and it vanishes — 20,000/instance puts it at 16.67%,
50,000/instance at 6.67%. The 0.00-pt tie is then resolved correctly and the matching engine stands
alone, which is the right answer.  (2) The matcher is the real constraint, for a reason the model
cannot represent. The matcher assumption says the two shards' capacities "genuinely add (disjoint
symbols)" — true only if symbol volume is uniform, which it never is. I confirmed the sensitivity:
at a 60/40 split of order flow the hot shard is at 80%, at 70/30 it is 93.3%, at 80/20 it is 106.7%
and over capacity — while the model still reports 66.67%. This is the single-writer constraint that
defines exchange engineering: you cannot add instances inside a symbol range, so the answer to a hot
shard is re-partitioning, not scaling out. The uniform-distribution premise is unstated and is the
biggest unmodelled risk in the file.  (3) Market data is wired backwards. It is modelled as a pull
path — 45% of a fixed 50,000 inbound request budget arriving through the order gateway. Real venues
publish it. SIX documents that "Where no matching occurs, one ITCH output is generated for each
input OUCH message to notify the resulting change to the order book" and that "ITCH messages are
sent to many parties, typically via broadcast protocols", with its diagram legend distinguishing
"One-to-one message flow" (order entry) from "One-to-many message flow" (market data). Nasdaq's feed
list confirms market data ships as a published stream with a channel count and a per-feed bandwidth
recommendation (NASDAQ TotalView-ITCH 4.1: 61 Mb current, 67 Mb new). Two consequences. First, the
md tier's load should be driven by the order rate (20,000/s book events -> 55.6%) and should MOVE
when order flow moves; frozen at 22,500/s, the reader cannot discover the coupling that defines the
system. Second, the fan-out multiplier is absent entirely: the same 20,000 events/s to 10 unicast
subscribers is 555.6% of the md tier, to 50 is 2,777.8% — precisely why real venues multicast, at
which point the binding resource becomes bytes on the wire, which this engine does not model. The md
tier's 62.5% is a coincidence of arithmetic, not a mechanism.  (4) Routing market data through the
order gateway also inflates the gateway: strip that leg and gw drops from 41.67% to 22.92%. Not
verdict-changing, but 45% of the gateway's modelled load is traffic that in reality never touches
it.  (5) Kafka sits synchronously in the order acknowledgement path at 1.0 ms. LMAX does journal in
the order path — but on an in-process ring buffer, measured in the Disruptor paper (Thompson,
Farley, Barker, Gee, Stewart, May 2011) at 25,998,336 ops/s unicast on Nehalem 2.8GHz and 52 ns mean
latency on a three-stage pipeline — not a broker at a millisecond. Fowler (12 July 2011) documents
the Business Logic Processor handling 6 million orders per second on a single thread, entirely in-
memory. I confirmed the modelled place-order path totals 2.25 ms, which is 212x the 10.6 us measured
at SIX and 87x the 26 us NYSE publishes for Binary (NYSE Pillar, 19 Sept 2019: FIX ~592us -> ~32us,
Binary ~96us -> ~26us, 92% improvement at the 99th percentile). The engine assumption honestly
disclaims microsecond TAIL determinism; it does not disclaim that the MEAN is two orders of
magnitude off, and a reader planning a latency budget from that column would be badly misled. This
does not move the bottleneck — the engine ranks by utilisation — but latency is the property an
exchange is actually judged on.  (6) The place:cancel mix of 28:12 is 2.33 new orders per cancel.
The SEC's analysis of Q2 2013 data found that "at most, only a few percent of all orders and quotes
for shares posted by market participants result in trade executions", with "More than one third of
all orders stay in force for at least 5 seconds" and "nearly 100% of all orders are either canceled
or result in a trade within 10 minutes" — so nearly every order ends in a cancel and roughly 1:1 is
more realistic. I confirmed this does NOT change the verdict (both flows traverse the same
components; only db x0.05 differs), so it is free honesty rather than a defect.  Net: the reader's
takeaway is "add risk servers" — the one move in this system that buys nothing. The real answers are
re-partition the matcher and get the market-data fan-out onto multicast before the bytes bind.  The
50,000 msg/s workload framing is the strongest thing in the file and should be kept: UTP Tape C
peaked at 636,500 quote messages/second in March 2026, so "a mid-tier venue, national markets run
10-100x this" is accurate and citable.

**Fix**

1) Re-size the risk tier or fold it into the gateway. Set per_instance_rps to >=50,000 and
base_latency_ms to a few microseconds for an inline limit check, citing 15c3-5 for what the check
actually is and SIX's 10.6 us end-to-end for the budget it must fit inside. This alone breaks the
0.00-pt tie in the correct direction and makes the matching engine the sole named bottleneck.  2)
Add a stated symbol-distribution assumption to the matcher, because "two shards add" is the load-
bearing claim in the file. Say explicitly that capacities add only under uniform symbol volume, and
give the sensitivity: 60/40 -> hot shard 80%, 70/30 -> 93%, 80/20 -> over capacity. That single line
converts the blueprint from a capacity sketch into the lesson an exchange designer actually needs.
3) Rewire market data to be derived, not requested. Feed the md publishers from the journal rather
than the gateway, set their rate to the order+cancel rate times a stated ITCH-messages-per-order
multiplier (SIX documents ~1:1 when trade-to-order ratios are low), and add an explicit subscriber
fan-out factor with a note that multicast collapses N unicast sends to one and moves the constraint
to bytes/s, which this engine does not model. Remove the md leg from the order gateway path.  4)
Move Kafka off the synchronous acknowledgement path, or relabel it as the asynchronous post-
trade/event journal, stating that the in-path journal in published single-writer designs (LMAX) is
an in-process ring buffer at nanosecond cost, so 1.0 ms is not an exchange's order-path figure.  5)
Extend the engine assumption's disclaimer from tail determinism to the mean: the modelled 2.25 ms
order path is 87-212x published venue figures (SIX 10.6 us, NYSE Pillar 26 us binary / 32 us FIX),
and even against the crypto framing Coinbase advertises sub-millisecond matching.  6) Rebalance
place:cancel toward roughly 1:1, citing the SEC finding that only a few percent of orders ever
execute. It changes no verdict, so it is free honesty — and it is the classic way textbook exchange
designs get the mix wrong.  7) Keep the 50,000 msg/s framing and add the UTP Tape C citation
(636,500 peak quote msg/s, March 2026) to support it at no cost.

**Verified sources**

- https://www.six-group.com/dam/download/the-swiss-stock-exchange/trading/trading-platform/x-stream-inet-performance-measurement-details.pdf
- https://www.nyse.com/data-insights/nyse-pillar-migration-adding-efficiency-to-the-marketplace
- https://martinfowler.com/articles/lmax.html
- https://lmax-exchange.github.io/disruptor/disruptor.html
- https://www.utpplan.com/DOC/UTP_Website_Statistics_2026-Q1-March.pdf
- https://www.sec.gov/about/speed-equity-markets
- https://www.sec.gov/marketstructure/datavis/ma_exchange_canceltotrade.html
- https://www.law.cornell.edu/cfr/text/17/240.15c3-5
- https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/bandwidthreport.pdf
- https://www.marketsmedia.com/coinbase-upgrades-derivatives-platform-with-new-matching-engine/

### ad_click_aggregation

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

VERDICT IS FALSE PRECISION (confirmed). Engine names the collector at 0.7424 over the aggregator at
0.7299 — a 1.25-point margin I reproduced exactly. That margin exists only because the file gives
the stateless collector 6,000 rps/instance and the windowed aggregator 12,000. Neither number has a
citation; both are ASSUMPTION provenance. Swapping them flips the named bottleneck. A user is told
'add collectors' on the strength of a 1.25-point gap between two invented numbers.  I DID NOT
confirm the researcher's stronger claim that the ratio is inverted. Their evidence (Zalando's
RocksDB seek cost, Photon's IdRegistry) is all about STATEFUL JOINS. This blueprint's aggregator is
explicitly 'windowed in-memory counting' — no join, no state backend. In-memory counting genuinely
can outrun an HTTP endpoint that terminates TLS, parses a beacon and produces to Kafka. The defect
is that the margin is unsupportable, not that it points the wrong way.  THE HARDEST COMPONENT IN
EVERY PUBLISHED SYSTEM IS ABSENT (confirmed, and this is the real finding). There is no
impression/click join and no dedup. Photon's SIGMOD 2013 abstract — verified verbatim — is entirely
about joining click against query streams; the deck's problem statement is 'Join click with query...
Cannot put query inside the click'. Uber (2021-09-23) runs a separate Attribution job that 'ingests
order data from a Kafka topic... and queries for matching ad events'. Zalando's entire 2026-07-24
post is the join stage: a 15-minute two-way bid/interaction match, ~70 million entries held
permanently in the expiration queue, 15-30% of CPU lost to RocksDB seeks. That in-flight state is
what sizes a real cluster, and this model cannot see it.  MONEY-OF-RECORD ON ONE POSTGRES PRIMARY AT
42% (confirmed). Mesa (VLDB 2014) exists because of a requirement this model cannot express: 'It
must not be possible to query the system in a state where only some of the updates have been
applied.' Mesa is multi-versioned, geo-replicated, Colossus + BigTable, with a stateless committer
that assigns each update batch a version number and commits 'every few minutes'. Uber uses Pinot
upsert + Hive UUID dedup. The high-stakes:payments flag is honest, but the engine reports a
comfortable 0.4206 on a component whose actual requirement is a correctness property, not a rate.
Related: replay_reconcile is a 0.1% live request flow through the dashboard API, not a scheduled
batch recompute — so the one path that protects the money is never sized.  LATENCY MAGNITUDE
(confirmed). Summed base_latency_ms is tens of ms; the real figures are <10s average end-to-end
(Photon SIGMOD abstract, verbatim), 1-min tumbling windows + 2-min checkpoints (Uber), a 15-min join
window with 3-min incremental RocksDB checkpoints (Zalando), 'within minutes' (Mesa). The
assumptions flag the mechanism but not the three-to-five-order magnitude.  WHAT IS RIGHT AND MUST
NOT BE 'FIXED': the 98/1.9/0.1 mix is correct and is in fact CONSERVATIVE. Mesa's abstract: 'handles
petabytes of data, processes millions of row updates per second, and serves billions of queries.'
The Photon deck's closing slide gives the AdWords storage engine as '32M rows updated per sec'
against '200K read queries/sec with latency of 90ms' — a 160:1 write:read ratio. The blueprint's
98:1.9 is 51:1, i.e. it over-represents reads relative to both published systems, which is the safe
direction. The three batching visit_probs (0.02 / 0.05 / 0.001) are the right modelling device, are
stated explicitly, and are the honest reason a 500k/s firehose lands on one database. Redis at
100k/node is conservative against redis.io's measured 'SET: 180180.17 requests per second' (though
note that was a 3-byte payload over loopback with no pipelining). Kafka at 30k/broker is ~7x below
Confluent's 605 MB/s across 3 i3en.2xlarge at 1KB/RF=3 (~200k/broker, 2020-08-21) but sits at 0.6806
and is not load-bearing here.

**Fix**

1. Report the tie. Collector 0.7424 and aggregator 0.7299 are separated by 1.25 points of unsourced
input. Until both carry a citation, the verdict line should name both and say the bottleneck is not
determined. This is the single highest-value change. 2. Add the join/dedup stage as a first-class
stateful component between q and agg, visit_prob 1.0 on the ingest flow, with a GAP recording that
its in-flight state — not its request rate — is what sizes it (Zalando: ~70M entries held
permanently for a 15-minute window). Cite Photon, Uber's Attribution job, and the Zalando post. 3.
Do NOT simply invert 6,000/12,000 on the researcher's reasoning — their evidence is about joins, and
this aggregator is memoryless counting. Either cite both numbers or equalise them and report a tie.
4. Relabel the rollup store 'versioned aggregate store (Mesa / Pinot / ClickHouse class)' and attach
a GAP quoting Mesa's atomic-update requirement: a single SQL primary is not how any published ad
billing system holds money-of-record. 5. Model replay_reconcile as a scheduled batch job with a
stated period and partition count, not as 0.1% of live request traffic. 6. Add a latency GAP giving
the real magnitudes (<10s Photon, 1-min window + 2-min checkpoint Uber, 15-min window Zalando,
'within minutes' Mesa) so the summed base_latency_ms is never read as end-to-end freshness. 7. Leave
the 98/1.9/0.1 mix and the three batching visit_probs alone. They are verified correct and
conservative.

**Verified sources**

- https://research.google/pubs/photon-fault-tolerant-and-scalable-joining-of-continuous-data-streams/ — SIGMOD 2013. Abstract verbatim: 'Our production deployment processes millions of events per minute at peak with an average end-to-end latency of less than 10 seconds.'
- https://cloud.berkeley.edu/data/photon.pdf — Google-internal slide deck (marked 'Google Confidential and Proprietary'), NOT the SIGMOD paper; extracted locally with pdftotext. Verified: 'Join click with query', 'Millions of joins per minute', 'Latency: O(seconds)', 'O(700)-way sharded PaxosDB', '5 PaxosDB replicas spread across East Coast, West Coast, Mid-West', '2 Photon pipelines running in East Coast, West Coast', 'Dispatcher retry ensures at-least-once'. Closing slide: '32M rows updated per sec, 140T total rows' and '200K read queries/sec with latency of 90ms'.
- http://www.vldb.org/pvldb/vol7/p1259-gupta.pdf — Mesa, VLDB 2014 (Gupta et al., Google); extracted locally with pdftotext. Abstract verbatim: 'Mesa handles petabytes of data, processes millions of row updates per second, and serves billions of queries that fetch trillions of rows per day.' Requirements section: 'It must not be possible to query the system in a state where only some of the updates have been applied.' Architecture: Colossus + BigTable; 'The committer assigns each update batch a new version number'; commits 'typically once every few minutes'. Section 6 Figure 7 (single data source, 7 days) axis runs 3-6 million row updates/second; Figure 8 shows ~400-650 million queries/day; Figure 10 shows query throughput reaching ~5,000-6,000 queries/second at 128 query servers. NOTE: the 3.5-5.5M and ~500M/day figures are chart reads, not prose quotes — the quotable prose is 'millions of row updates per second' and 'billions of queries'.
- https://www.uber.com/us/en/blog/real-time-exactly-once-ad-event-processing/ — published 2021-09-23. Verified: Kafka + Flink + Pinot + Hive; 'a Tumbling window of one minute in length'; checkpoint interval set to 2 minutes (default 10 min judged too long); Pinot 'leverage[s] the upsert feature to ensure that we never duplicate records with the same identifier'; Hive dedup by generated record UUID; a separate 'Attribution job... ingests order data from a Kafka topic... and queries for matching ad events'; 'Active-Active' across two regions with no cross-region replication.
- https://engineering.zalando.com/posts/2026/07/migrating-ad-event-processing-to-flink.html — published 2026-07-24. Verified verbatim: 'We limit it to 15 minutes'; 'up to 200MB/s'; '~70 million entries permanently'; 'about 15-30% of CPU just on seek operations'; 'Event enrichment success rate: Flink output matched the status quo at 99.9% on average'; '~0.2% by event ID in the output stream'; 'reduced average pod count from a constant 20 to 5 on average'; 'CPU reduced from 30 to ~20 cores'; 'We added a RocksDB state backend with incremental 3-minute checkpoints'; migration from Interval Join to a custom KeyedCoProcessFunction.
- https://www.confluent.io/blog/kafka-fastest-messaging-system/ — published 2020-08-21. Verified: peak stable throughput 605 MB/s on 3 brokers, i3en.2xlarge (8 vCore / 64 GB / 2x2500 GB NVMe), 1 KB messages, replication factor 3 — i.e. roughly 200k msg/s per broker.
- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/ — verified verbatim: 'SET: 180180.17 requests per second, p50=0.143 msec' (3-byte payload, 50 clients, no pipelining, loopback). With -P 16: 'SET: 1536098.25 requests per second' / 'GET: 1811594.25'. Also: 'processing 10 bytes, 100 bytes, or 1000 bytes queries almost result in the same throughput.'
- https://kafka.apache.org/powered-by/ — verified verbatim: Criteo 'tens of Kafka clusters deployed over multiple data centres across three continents processing up to 30 million messages/sec.'

### agent_observability

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

I reproduced every engine figure independently: proc 79.71%, api 78.40%, store 75.00%, judge 59.70%,
blob 38.56%, lb 14.70%, q 7.44%. Margin 1.31pts. Exact match to the researcher's reproduction.  THE
VERDICT IS CORRECT AND MORE ROBUST THAN THE MARGIN SUGGESTS — confirmed. Both near-tied contenders
dissolve under correct figures: • api at 5,880 rps is a unit error. The OTel Collector batch
processor README confirms verbatim "send_batch_size (default = 8192)" and "timeout (default =
200ms)". At a 200ms flush, 5,460 spans/s is a handful of HTTP requests/s, not 5,460. For scale
reference I verified the collector's own testbed: the OTLP trace load tests run at 10,000 spans/s
with "ExpectedMaxCPU: 20, ExpectedMaxRAM: 100" for OTLP-gRPC and OTLP-HTTP. • store at 4,000
writes/s/node is heavily pessimistic. ClickHouse's own benchmark confirms 65.33B rows on a single
59-core/236GB server at ~4M rows/s. Langfuse notes "individual rows can carry multiple megabytes of
text and maps", so a large derate is warranted — but not to 4,000. Remove both and proc stands
alone, matching the blueprint's own assumption and Langfuse's operational guidance to scale workers
on queue depth and CPU.  THE MISS THE ENGINE MAKES — confirmed, and I verified the quota table
against the primary source rather than memory. The judge is modelled purely as a request-rate quota
(3 pools × 4,000 RPM ≈ 201 calls/s) and reports a comfortable 59.7%. But the published limits are
enforced on three axes simultaneously: the rate-limits doc states "If you exceed any of the rate
limits you will get a 429 error describing which rate limit was exceeded." At the highest standard
tier (Scale) for Claude Opus 5 / Sonnet 5 / Haiku 4.5 the ceilings are 10,000 RPM, 10,000,000 ITPM,
2,000,000 OTPM; Build tier is 5,000 / 5,000,000 / 1,000,000. At 120 calls/s × 2,500 input tokens the
workload needs 18,000,000 ITPM against a 10M ceiling — 1.8x over — while output at 1,440,000 OTPM
sits under the 2M ceiling and requests at 7,200 RPM sit comfortably under 10,000. Modelling only RPM
therefore produces a false green on the one axis that binds. This is the single most misleading line
in the output, and the engine does not see it.  One correction in the blueprint's favour that
strengthens the fix: the doc confirms cache reads are exempt — "cache_read_input_tokens (tokens read
from cache) ✗ Do NOT count toward ITPM for most models." Caching the rubric is therefore a
documented, first-class lever against exactly this ceiling, not a hopeful one.  COST: I re-derived
it against the published per-token rates. 18M input + 1.44M output per minute at the cheapest
current tier (Haiku 4.5, $1.00/$5.00 per MTok) is $18.00 + $7.20 = $25.20/min, ≈$1.09M/month at
sustained peak. The order of magnitude holds. The caveat "sustained peak 24/7" is doing work and
should be stated.  SHAPE — reasonable_simplification, and I am holding this rather than escalating.
LB → OTLP API → Kafka → enrichment workers → columnar store with a blob store is a real production
spine: Langfuse v3 (Dec 2024, still current per their March 2026 write-up) is this modulo Redis-for-
Kafka, and Honeycomb (Nov 30 2021) is shepherd ingest workers → Kafka → retriever columnar store,
with Kafka called the "beating heart" and RF=3 at 30% peak CPU on single-digit brokers.  The blob
ordering IS genuinely inverted — Langfuse writes every raw event to S3 BEFORE enqueuing a reference
("By introducing S3 as persistent storage for events, we could retain only references in Redis";
"Ingestion spikes therefore translate into queue depth, not database pressure, and because every
event is persisted in blob storage before processing, events can be replayed if downstream
processing fails"). At the correct ordering blob carries 5,460 PUT/s against a 3,500 PUT/s per-
prefix ceiling. But the blueprint explicitly defines instances as PREFIXES, and AWS states there are
no limits to the number of prefixes — so this is a config knob with unlimited headroom, not an
architectural bottleneck. It would cost a reader one line of config, not a wrong optimisation
target. That is why shape stays a reasonable simplification while the durability inversion still
deserves a fix.  PROPORTION — misleading, confirmed. 7% trace queries = 420 UI queries/s against
5,460 spans/s: one human-initiated read per 13 spans written. No LLM-observability vendor publishes
a read:write ratio and I will not invent one. But every adjacent published ratio is far more write-
skewed (Grafana GEM 500M: ~167 q/s; Monarch: ~95% machine-driven standing queries). This is not a
cosmetic inflation — it is precisely what lifts api into contention at 78.40%, one point behind the
winner. Drop trace_query to 0.005 and api falls to ~73%, clearing the photo finish. A traffic mix
that manufactures a false #2 contender is misleading whatever the disclaimer says. Conversely, the
2% judge sampling rate is defensible: Langfuse's docs confirm "Observation-level evaluators are the
recommended target for live production data", so sampling per span rather than per trace matches
documented guidance.  My own finding the researcher missed: flow shares are fractions of system_rps,
not of the ingest flow, so eval_sample at 0.02 is 120/s while the assumption says "2% of spans" — 2%
of 5,460 spans is 109/s. A small internal inconsistency between the assumption prose and the model.
Also worth noting that a sampled span is counted at proc twice (once in span_ingest, once in
eval_sample); that is defensible as separate eval work, but it should be stated since it is what
carries proc over the api.  The engine caveat in the assumptions — that ingest burstiness is
inexpressible and the Kafka buffer's value is therefore invisible — is exactly right and is the most
useful sentence in the file. It is why q shows 7.4%, and a reader must not read that as over-
provisioned.  NUMBERS — plausible, confirmed. proc's 700 spans/s per 2-vCPU is the one figure with
real corroboration, though weaker than the researcher claimed: Langfuse's scaling page confirms "A
load above 50% for a 2 CPU container is an indicator that the instance is saturated" and minimums of
2 CPU/4GiB web and worker, 2 CPU/8GiB ClickHouse, 1 CPU/1.5GiB Redis, and confirms
LANGFUSE_S3_CONCURRENT_WRITES default 50 — but I could not confirm a documented default for
LANGFUSE_INGESTION_QUEUE_PROCESSING_CONCURRENCY, so the "concurrency 20 per worker" half of that
corroboration is dropped. The remaining CPU-saturation guidance still puts 700 spans/s in a
defensible band at a few tens of ms of work per event.

**Fix**

1. Model the judge quota in tokens, not requests. Add ITPM/OTPM ceilings beside the RPM figure: 120
calls/s × 2,500 input tokens = 18M ITPM against a 10M published ceiling at the highest standard
tier. Raise the provisioned quota, drop the eval sample to ~1.1%, or — best — model prompt caching
of the rubric, since the docs confirm cache_read_input_tokens do NOT count toward ITPM. Whichever
you pick, the report must say the judge tier is token-bound, not request-bound. That is the single
most misleading line in the current output. 2. Move blob to the front of span_ingest: lb → api →
blob(x1.0) → q → proc → store. This matches Langfuse's documented S3-first design and makes the
replay/durability property visible. Note in the assumption that at that ordering 5,460 PUT/s exceeds
the 3,500 PUT/s per-prefix ceiling so prefixes must be ≥2 — but say plainly it is a prefix-count
knob with unlimited headroom, not a wall. 3. Separate read and write ceilings on blob. The component
becomes write-dominated; 5,500 is AWS's GET/HEAD figure and 3,500 is the PUT figure. Using the read
number for a write workload overstates headroom by 57%. 4. Re-proportion the flows — suggested
span_ingest 0.975, eval_sample 0.02, trace_query 0.005 (~30 UI queries/s). This is the change that
dissolves the false photo finish with api. If you want a larger read share, relabel it as machine-
driven (scheduled dashboards, alerting over trace data) and say so; 420 humans per second is not
defensible. 5. Raise store to a sourced figure or state the basis. ClickHouse's published single-
node measurement is ~4M rows/s on 59 cores; even a heavy derate for multi-megabyte agent-trace rows
sits far above 4,000/s. An unsourced, ~1,000x-pessimistic figure currently occupies third place on
the contenders list and flatters the ranking's tightness. 6. Fix the api unit or state the batching
factor — OTLP's default send_batch_size is 8,192 with a 200ms timeout. Sizing an HTTP receiver at
one request per span is the same category error that inflates the metrics blueprint's load balancer.
7. Reconcile the eval_sample share with its prose: 0.02 of system_rps is 120/s, but "2% of spans" is
109/s. Also state that a sampled span visits proc twice, since that second visit is what carries
proc over api. 8. Add one line to the LB assumption: trace-ID-affinity routing is required if any
tail sampling runs downstream — the tail sampling processor states "All spans for a given trace MUST
be received by the same collector instance", default decision_wait 30s. A round-robin LB silently
breaks trace-complete sampling decisions. 9. Keep the verdict but strengthen the wording. Enrichment
worker is right for a structural reason — per-span CPU work does not batch away, unlike transport
and columnar inserts — not as a 1.31-point photo finish. Add the judge's token quota as a named
second finding, because that is the constraint that actually pages someone.

**Verified sources**

- https://langfuse.com/blog/2024-12-langfuse-v3-infrastructure-evolution — Dec 2024. S3-first then reference-in-Redis confirmed; Postgres-era ceiling (50s ingestion API response times, p95 prompt retrieval 7s, tens of thousands of events/min) confirmed.
- https://langfuse.com/resources/engineering/clickhouse-at-agent-scale — the queue-depth/replay sentence confirmed verbatim; ~60% of observations via the OpenTelemetry endpoint as of March 2026; 90% of updates within 10s; "individual rows can carry multiple megabytes of text and maps". Page carries no explicit publication date.
- https://langfuse.com/self-hosting/configuration/scaling — minimums 2 CPU/4GiB web and worker, 2 CPU/8GiB ClickHouse, 1 CPU/1.5GiB Redis; "A load above 50% for a 2 CPU container is an indicator that the instance is saturated"; autoscale on langfuse.queue.ingestion.depth type:waiting; LANGFUSE_S3_CONCURRENT_WRITES default 50.
- https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge — "Observation-level evaluators are the recommended target for live production data"; cost managed by "using sampling to evaluate a percentage of traces"; "Asynchronous architecture processes thousands of evaluations per minute."
- https://www.honeycomb.io/blog/scaling-kafka-observability-pipelines — Nov 30 2021 (dated; a 5-year-old architecture). Confirms shepherd ingest workers → Kafka → retriever columnar storage engine, Beagle for SLOs, Kafka as the "beating heart", RF=3, 30% peak CPU on im4gn.4xlarge, tiered storage to S3, 2-4h local NVMe retention, and the 16× c5.xlarge → 6× i3en.2xlarge → im4gn.4xlarge progression (6 brokers in production).
- https://github.com/open-telemetry/opentelemetry-collector/blob/main/processor/batchprocessor/README.md — "send_batch_size (default = 8192)", "timeout (default = 200ms)".
- https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/tailsamplingprocessor/README.md — "All spans for a given trace MUST be received by the same collector instance for effective sampling decisions"; decision_wait default 30s.
- https://opentelemetry.io/docs/collector/deploy/gateway/ — "The gateway Collector deployment pattern consists of applications or other Collectors sending telemetry signals to a single OTLP endpoint."
- https://opentelemetry.io/docs/collector/deploy/other/agent-to-gateway/ — agent→gateway confirmed as a recommended pattern for centralized processing, network isolation and tail-based sampling, with an explicit note that it adds operational complexity and is not universally recommended.
- https://raw.githubusercontent.com/open-telemetry/opentelemetry-collector-contrib/main/testbed/tests/trace_test.go — OTLP trace load tests at 10,000 spans/s; OTLP-gRPC and OTLP-HTTP ExpectedMaxCPU 20, ExpectedMaxRAM 100.
- https://clickhouse.com/docs/best-practices/selecting-an-insert-strategy — batches of at least 1,000 rows, ideally 10,000–100,000; ~one insert query per second; async_insert flush at 100MiB / 200ms (1000ms on Cloud) / 450 accumulated queries.
- https://clickhouse.com/blog/supercharge-your-clickhouse-data-loads-part2 — 65.33B rows (~14TiB uncompressed) at ~4M rows/s on a single 59-core / 236GB server.
- https://platform.claude.com/docs/en/api/rate-limits — three simultaneous axes (RPM/ITPM/OTPM), 429 names which was exceeded. Scale tier Claude Opus 5 / Sonnet 5 / Haiku 4.5: 10,000 RPM / 10,000,000 ITPM / 2,000,000 OTPM. Build tier: 5,000 / 5,000,000 / 1,000,000. Confirms cache_read_input_tokens do NOT count toward ITPM.
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html — 3,500 PUT/COPY/POST/DELETE and 5,500 GET/HEAD per partitioned prefix; no limit on prefix count.

### api_gateway

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

CONFIRMED as the strongest of the three files, and I am upholding the lenient verdicts. The engine's
named bottleneck — the upstream service tier at 23,250/32,000 = 72.66% (engine 0.7266) — is correct
and is where a real gateway deployment binds. Two soft spots, neither of which changes the named
bottleneck. (a) The `auth` tier is a phantom near-contender at 3,987.5/6,000 = 66.46%, only 6.2 pts
behind (engine margin 6.2 confirmed). Its 1,500 rps/instance rating is defensible only under the
file's own gloss of 'signature verification plus introspection', but that combination is redundant —
a JWT is self-contained — and real gateways verify in-proxy: Envoy's jwt_authn doc states 'It will
verify its signature, audiences and issuer' against local_jwks or a remote_jwks cached
(cache_duration: 300s in the doc's own example), with no per-request external call, and Kong's
official benchmark runs key-auth + rate limiting INSIDE one 16-vCPU c5.4xlarge at 96,259.7 RPS (p99
9.75ms, HTTPS, five 15-min runs, Kong 3.15). Pure verification measures 6,566.2/s (ECDSA P-256) to
22,220.4/s (RSA-2048) on one core (OpenSSL Cookbook, OpenSSL 1.1.1f, 2020). So the tier is modelled
4-15x slow without saying it is a variant. Crucially this errs in the SAFE direction: correcting it
moves auth DOWN to 6.65% and WIDENS the winning margin from 6.2 to 10.16 pts, so it does not
misdirect a reader — hence reasonable_simplification, not misleading. (b) The genuinely harmful
claim is the limiter assumption stating as fact that 'a stale counter is a quota bypass' and
therefore 'Redis availability is a hard dependency of the whole API, not an optimisation.' Both
primaries contradict this as a design choice: Kong's docs say on Redis disconnect 'Kong Gateway
keeps the local counters for rate limiting and syncs with Redis once the connection is re-
established', accepting that 'users will be able to perform more requests than the limit, but there
will still be a limit per node'; Stripe (2017-03-30) states the goal 'Make sure that if there were
bugs in the rate limiting code (or if Redis were to go down), requests wouldn't be affected.'
Telling a learner a correct limiter must take the whole API down with Redis is the single claim here
most likely to produce a worse system — but it is an availability-design error, not a bottleneck-
location error, which is why the shape verdict stays at reasonable_simplification. The 5% steady-
state 429 rate has no public support (Stripe's only published counts are 'millions of requests this
month' for the request limiter and '12,000 requests this month' for the concurrent limiter — orders
of magnitude less), but it too errs safe: a lower 429 rate pushes MORE traffic to the app tier the
engine already names.

**Fix**

1) Split `auth`. Model in-proxy JWT verification as part of the gateway's service time, or as a tier
at 10,000-20,000 rps/instance derived from the openssl verify rates, and keep a separate
introspection path at low visit probability for opaque tokens only. At 15,000 rps/instance auth
falls to 6.65%, the runner-up becomes `gw` at 62.50%, and the margin widens to 10.16 pts — a verdict
you can rely on. If you keep the external hop, say plainly it is Envoy's ext_authz pattern and that
Envoy/Kong verify in-proxy by default. 2) Rewrite the limiter assumption: document fail-open-to-
local-counters as the shipped default (Kong), with fail-closed as an explicit, costly opt-in, and
note Envoy's documented two-stage pattern — 'a local token bucket rate limit can absorb very large
bursts in load that might otherwise overwhelm a global rate limit service. Thus, the rate limit is
applied in two stages.' 3) Relabel the 5% 429 share as a stress scenario, not the baseline. 4) Add
AWS API Gateway's default account-level throttle — 10,000 RPS with a 5,000-request burst bucket, and
2,500/1,250 in 13 named regions — as a hard constraint on the managed-gateway option; it sharpens
the file's existing, honest $0-compute GAP into a limit this 25k-rps design would hit. 5) Optional,
for honesty not for the verdict: `limiter` at 100,000 rps/instance is optimistic for an atomic Lua
token bucket over a real network against a large keyspace — Redis's own docs show 180,180 SET/s on
loopback but 72,144.87/s against a 100k random keyspace and 69,881.20/s for a script load, and warn
'In many real world scenarios, Redis throughput is limited by the network well before being limited
by the CPU.' At 12.25% utilisation it changes nothing. 6) Minor: the flow runs `limiter` before
`keycache`/`auth`, i.e. rate-limits before identifying the caller; Kong's own benchmark names the
realistic order 'Key Auth + Rate Limiting'. Path order does not change utilisation in this engine,
so fix it for teaching value only. 7) Leave the metering-bus assumption alone — one event per
request including 429s is correct and well argued — and leave `gw` at 5,000 rps/instance, which sits
inside Kong's own published sizing envelope ('Medium: Throughput requirements: < 10000 RPS', latency
< 10 ms, Kong 3.4.x+).

**Verified sources**

- https://developer.konghq.com/gateway/performance/benchmarks/
- https://developer.konghq.com/gateway/resource-sizing-guidelines/
- https://developer.konghq.com/gateway/rate-limiting/strategies/
- https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/jwt_authn_filter
- https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/other_features/global_rate_limiting
- https://www.envoyproxy.io/docs/envoy/latest/faq/performance/how_fast_is_envoy
- https://github.com/envoyproxy/ratelimit
- https://github.com/envoyproxy/envoy/issues/28318
- https://stripe.com/blog/rate-limiters
- https://www.feistyduck.com/library/openssl-cookbook/online/openssl-command-line/performance.html
- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/
- https://docs.aws.amazon.com/apigateway/latest/developerguide/limits.html

### blog_platform

- **shape:** matches · **numbers:** plausible

**What a reader would get wrong**

The named bottleneck is RIGHT and robust, and I re-derived the engine's arithmetic myself: app load
2,160 rps / 2,700 cap = 80.00%, next-highest tier lb at 7.20%, so the 72.8-pt margin is honest. I
stress-tested it against the real write mix and it holds: at 0.5% writes app = 69.8%, at the
measured en.wikipedia ratio (0.075% writes) app = 68.8%. Still the bottleneck by ~60 points. SHAPE
IS OBSERVED, NOT JUST REASONED. I re-ran the live check myself on 2026-09-12:
blog.cloudflare.com/casb-policies/ returned `cf-cache-status: HIT, age: 3011` and the index `HIT,
age: 137` — real article HTML edge-cached with a long age, index pages revalidating far more often,
which is directionally the blueprint's 80%-articles / 50%-feeds split. Wikitech documents the same
two-layer structure the blueprint draws: Varnish frontend in-memory 'capped to 1 day with a 7-day
keep' (Jun 2022) over an ATS on-disk backend 'capped to 24 hours' (Apr 2020, T249627), application
max-age for page views '14 days' (Jul 2016, T124954), and a separate parser cache at '30 days' (Dec
2023, T280604) — that parser cache is precisely the blueprint's 'rendered-page cache' behind the
edge. THE ONE GENUINELY MISSING FACT is primary and load-bearing: Cloudflare documents that 'The
Cloudflare CDN does not cache HTML or JSON by default', and HTML caching requires an explicit Cache
Rule (default Edge TTL 120m). The blueprint's `app` assumption already discloses the cold-CDN spike
honestly ('the origin as a whole goes from 2,160 to 8,000 req/s, ~3.7x its design load. This tier is
the first thing to fall over' — I confirmed 8,000/2,700 = 296%), so the researcher's charge that it
frames this as a tail risk overstates. What it does NOT say is that with Cloudflare's shipped
defaults the cold case is the day-one state, not an incident. And the 0.20 article visit probability
is the most load-bearing input in the file: I recomputed app util across it at 0.05 / 0.10 / 0.20 /
0.50 / 1.00 = 42.2% / 54.8% / 80.0% / 155.6% / 281.5%. One assumption moves the verdict further than
every other input combined, and it is reported as a bare point estimate. SECONDARY: the 5% write
share is arithmetically extreme — 320 comments/s plus 80 publishes/s is ~6.9M posts published per
day against 8,000 reads/s, a 19:1 read:write ratio where the measured comparator (en.wikipedia, July
2026: 6,749,320,082 user pageviews vs 5,064,322 edits) is 1,333:1, ~70x heavier on writes. I
verified this inflates the app tier by 400 of 2,160 rps (18.5%) but does NOT move the bottleneck, so
I am grading it as a proportion error to fix rather than a bottleneck error.

**Fix**

1) Add an assumption citing Cloudflare's default-cache-behavior doc that HTML is NOT edge-cached by
default, and reframe the 0.20 article visit probability as a CONFIGURED outcome (an explicit Cache
Rule), not a property of 'having a CDN'. 2) Add a cache-hit-rate sensitivity row to the report — app
util at article visit probability 0.05 / 0.20 / 1.00 = 42% / 80% / 282% (fully cold across both read
flows = 296%) — and drive the confidence band off that input, since it dominates every other. 3) Cut
the write share to ~0.5% or lower, or state plainly that 400 writes/s is a deliberately stress-
loaded write path rather than a realistic one, citing the en.wikipedia measurement (6,749,320,082
pageviews vs 5,064,322 edits, July 2026 = 1,333:1). 4) Refine the egress line: 150,000 GB against
CloudFront's published North America tiers (1 TB free + 9 TB @ $0.085 + 40 TB @ $0.080 + remainder @
$0.060) is ~$9,990/mo, so the flat $0.09/GB figure of $13,500 sits ~35% above list BEFORE any
negotiation. The blueprint already calls this line 'a ceiling', which is honest — this just makes
the ceiling quantified. 5) Add the publish -> purge/invalidation edge; Wikimedia documents exactly
this coupling, and without it publish_post reads as a harmless 80 rps write rather than the
mechanism that touches the whole read path. KEEP AS IS AND PROMOTE: the CDN per-request cost gap
note is exactly right and is effectively GROUNDED, not an ASSUMPTION — I recomputed it: 7,600 edge
rps at the stated 30% average-to-peak over a month is 5.91B requests, which at CloudFront's
published $0.75/M (HTTP) to $1.00/M (HTTPS) North America rates is $4,432-$5,910, squarely inside
the blueprint's stated '$4,000-6,000/month'. Relabel and cite it.

**Verified sources**

- https://developers.cloudflare.com/cache/concepts/default-cache-behavior/
- https://developers.cloudflare.com/cache/performance-review/cache-performance/
- https://wikitech.wikimedia.org/wiki/CDN
- https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate/en.wikipedia.org/all-access/user/monthly/2026070100/2026073100
- https://wikimedia.org/api/rest_v1/metrics/edits/aggregate/en.wikipedia.org/all-editor-types/all-page-types/monthly/2026070100/2026080100
- https://aws.amazon.com/cloudfront/pricing/pay-as-you-go/
- https://blog.cloudflare.com/casb-policies/

### cdn_design

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

I DOWNGRADE THE RESEARCHER'S "misleading" TO "reasonable_simplification" ON PROPORTION. Their lead
finding is refuted by the page they cited for it, and the two findings that survive do not move the
bottleneck. What remains is one genuine arithmetic contradiction — in the COST line, not the
bottleneck.  The engine's headline is right and I reproduce it exactly: app 18,000x0.85 =
15,300/22,000 = 69.55%; edge 120,000/180,000 = 66.67%; margin 2.88 pts; shield 22,740/45,000 =
50.53% (matching the blueprint's own stated 22,740 req/s); store 1,416 (also matching); dns
2,280/10,000 = 22.8%; lb 30.6%; db 19.1%; cache 19.1%. The blueprint's prose lesson — the CDN
absorbs 86%, what survives is the expensive dynamic remainder, so origin capacity is what you size —
is correct and well stated. The two-tier edge+shield topology is exactly what the vendors document:
Fastly, "Designating a shield POP ensures requests to your origin will come from a single POP,
thereby increasing the chances of an end user request resulting in a cache HIT"; CloudFront Origin
Shield, "an additional layer in the CloudFront caching infrastructure," consolidating requests
"resulting in as few as one request going to your origin."  WHAT SURVIVES:  (1) THE VIDEO SHARE AND
THE BANDWIDTH LINE ARE ARITHMETICALLY INCOMPATIBLE — confirmed by my own calculation, and this is
the strongest finding in the file. The blueprint derives 9,331,200 GB/month from "120k rps x 30 KB
average response"; I verify that (3.6 GB/s x 2,592,000 s = 9,331,200 GB). But 4% of 120,000 rps is
4,800 video-segment requests/second. At 500 KB/segment video alone is 6,220,800 GB/month — 67% of
the stated total, forcing the other 115,200 rps to average 10.4 KB. At 2 MB/segment (an ordinary
6-second HLS segment at ~3 Mbps is ~2.25 MB) video alone is 24,883,200 GB/month, 2.67x the stated
total for the entire system. The blueprint stakes its headline on this line — it "dominates every
other cost in this design by two orders of magnitude, which is the true shape of CDN economics" — so
the one number it asks the reader to take seriously is inconsistent with its own traffic mix. This
misleads about COST, not about the bottleneck.  (2) THE 2.88-PT MARGIN IS ASSUMPTION-DRIVEN, AND THE
CONTENDERS LIST CONTRADICTS THE BLUEPRINT'S OWN PROSE. I verified the sensitivity: drop the L1
static hit ratio from 94% to 85% and shield = 96,000x0.15 + 15,300 + 480 + 1,200 = 31,380/45,000 =
69.73%, overtaking app at 69.55% by 0.19 pts. So the verdict is robust only because both near-
contenders are vendor-managed tiers. The blueprint says exactly this in prose ("Edge PoP count is
the CDN vendor's problem, not a dial you turn") while the engine's `contenders` list names "Managed
CDN edge PoPs" alongside the origin tier — inviting the reader to tune a dial owned by CloudFront.
That internal contradiction is real and worth fixing, though it does not change the answer a reader
acts on.  (3) MINOR, VERIFIED: "GeoDNS / GSLB resolver tier (anycast steering)" names two mutually
exclusive mechanisms. CloudFront steers by DNS — "DNS routes the request to the CloudFront POP (edge
location) that can best serve the request, typically the nearest CloudFront POP in terms of
latency." Cloudflare steers by BGP anycast — "With Anycast, multiple machines can share the same IP
address... the network itself will direct traffic to the nearest CloudFlare data center" (21 Oct
2011), and such a CDN has no DNS steering tier on the request path at all. Cosmetic here: the dns
tier runs at 22.8% and never contends.  (4) SCALE NUMBERS ARE PLACEHOLDERS, HONESTLY SO.
Cloudflare's Radar 2025 Year in Review confirms "a presence in 330 cities in over 125
countries/regions" handling "over 81 million HTTP requests per second on average, with more than 129
million HTTP requests per second at peak" — roughly 245k rps per city, about 12x the modelled 20,000
rps/PoP. The blueprint's own `engine` assumption already concedes the single-region limitation, so
this is disclosed rather than hidden.  A note on what I also verified and the researcher did not
mention: Fastly documents a reporting trap this blueprint is silent on — "Local MISS/Shield HIT gets
reported as a miss and a hit in the statistics, even though there is no call to the backend." Worth
a line if the blueprint teaches shielding.

**Fix**

1. Reconcile video with the bandwidth line — this is the one change that fixes a number a reader
would quote. Give video segments their own average object size and recompute GB/month, or drop the
video flow and state the design is static+dynamic only. As written the headline cost figure and the
4% video share disagree by roughly 3x at realistic segment sizes. 2. Make the engine's `contenders`
list agree with the blueprint's prose: mark `edge` and `shield` as vendor-managed and either exclude
them from the bottleneck contest or have the report print "top contender is a vendor-managed tier,
not a dial you control." 3. Publish the hit-ratio sensitivity you already have the machinery for: at
85% L1 the shield overtakes the origin app tier by 0.19 pts, so the reader knows the 2.88-pt margin
is an artefact of the 94%/80% assumptions. 4. Split the routing component and name one mechanism:
"GeoDNS/GSLB steering (CloudFront/Akamai model)" with the DNS tier on the path, or "BGP anycast
(Cloudflare/Fastly model)" with no DNS tier at all. Do not label one component with both. 5. Say
which mid-tier `shield` represents — CloudFront regional edge caches, CloudFront Origin Shield, or a
Fastly shield POP — because they differ precisely on whether dynamic pass-through traverses them
(see dropped_claims). Cite the AWS Origin Shield cost section, which settles it. 6. Add Fastly's
shielding caveat that a local-miss/shield-hit is double-counted in reported CHR, since the blueprint
teaches shielding and quotes hit ratios.

**Verified sources**

- https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/HowCloudFrontWorks.html
- https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/origin-shield.html
- https://www.fastly.com/documentation/guides/getting-started/hosts/shielding/
- https://www.fastly.com/blog/truth-about-cache-hit-ratios
- https://blog.cloudflare.com/a-brief-anycast-primer/
- https://blog.cloudflare.com/radar-2025-year-in-review/
- https://www.cs.cornell.edu/~qhuang/papers/sosp_fbanalysis.pdf
- https://engineering.fb.com/2014/02/27/web/an-analysis-of-facebook-photo-caching-2/

### ci_cd

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

NOT the bottleneck. I reproduced the engine arithmetic exactly (runner util 0.75789, margin 75.65
pts over the DB at 0.136%) and the 'capacity is set by fleet size x job duration, not request rate'
thesis is corroborated by two primary operator docs I opened: Buildkite's cluster queue metrics page
exposes connected/idle/in-use agents, 'Scheduled (needs agent)' jobs and p50/p95/p99 dispatch wait-
time, and contains NO request-rate metric at all; GitHub's actions-runner-controller documents 'a
1:1 scaling of runners to queued jobs' plus a PercentageRunnersBusy alternative, with a 1m default
--sync-period and an explicit warning that it consumes GitHub API rate budget (which independently
justifies the status_poll flow). I also verified the author's own Erlang-C caveat arithmetically and
it is correct: at 144 erlangs on 190 servers, Erlang-C P(wait) = 0.00015156 and mean wait is 0.99
ms, while the engine's M/M/1 form returns a 1239.1 s sojourn. That is an unusually honest self-
disclosure.  The real trap is FLEET SIZE, via the 1-webhook-equals-1-job fan-out. push_build hits
runner(x1.0), so 0.48 webhooks/s becomes 0.48 jobs/s and the file needs only 190 runners. I can
ground the fan-out objection on a primary source rather than the researcher's uncited Buildkite
quote (which I dropped): the CircleCI 2025 State of Software Delivery report defines its unit
verbatim as 'the time from when an individual workflow is triggered until all of its jobs and steps
are complete' - the industry's measured unit is a WORKFLOW CONTAINING MANY JOBS - and GitHub's
limits page caps CONCURRENT JOBS per plan (20/40/60 Free/Pro/Team, 500 Enterprise, 1,000 larger
runners), a cap that only bites if one push yields many jobs. At 5x fan-out this design needs ~950
runners, at 20x ~3,800, at 50x ~9,500, against the 190 modelled. The assumption list never mentions
fan-out. This does NOT move where the bottleneck is (it makes the runner fleet even more dominant),
so it is not a wrong-component error - but it is a 5-50x quantitative trap on the one number a
reader will copy.  Second: the object store reads as free at 0.0135% because the engine models it as
a request-rate device only, with no bytes/bandwidth dimension. Cache restore and artifact upload -
which dominate wall clock on short jobs, and which GitHub bounds at 10 GB of cache per repository -
are invisible. 'Store is at 0.013%' is true and useless.  Third, a defect in the file's evidence
that the researcher missed: the 300 s average job is NOT corroborated by the CircleCI percentiles,
because those measure workflows, not jobs. A workflow's duration is at least its longest job and at
most the sum, so real per-job means sit at or below p50 2m43s / p75 8m7s. The minutes-scale order of
magnitude holds, so 300 s stays plausible - but it is an assumption, not a measured match, and I
downgraded the numbers verdict from 'matches' accordingly.  Minor: the 30-day retention assumption
is below GitHub's documented 90-day default for logs and artifacts, so the 40 TB store estimate is
low for a GitHub-shaped deployment.

**Fix**

(a) Add an explicit fan-out on the build flow - runner(xN) where N is jobs-per-pipeline - and state
N and its source in the assumptions, citing the CircleCI report's own definition (a workflow spans
all its jobs and steps) as the reason the unit matters. Without this the runner count is the one
number in the file a reader will copy and get 5-50x wrong. (b) Either add a bytes dimension to the
object store or add one line saying store utilisation is request-count-only and says nothing about
cache-restore time, noting GitHub's 10 GB per-repository cache cap. (c) Re-label the job-duration
assumption honestly: 300 s is an assumption in the right order of magnitude, and the published
CircleCI percentiles measure workflows rather than jobs, so they bound it from above rather than
confirm it. (d) Raise the retention assumption to GitHub's documented 90-day default, or state
explicitly that 30 days is a deliberate non-GitHub choice, and re-derive the 40 TB. (e) If the file
cites GitHub queue cancellation, qualify it: the 24h queue timeout is documented for SELF-HOSTED
runners, not hosted ones. (f) Change nothing else. The M/M/1-vs-Erlang-C admission, peak-vs-average,
no-autoscaling/spot, the single-writer DB rationale and 'treat 76% as headroom not a promise about
wait time' are the most honest block in the corpus, and I verified the Erlang-C claim
arithmetically.

**Verified sources**

- https://buildkite.com/docs/pipelines/cluster-queue-metrics - opened; confirms verbatim the queue metrics: 'Connected' / 'In use' / 'Idle' / 'Paused' / 'Draining' agents, 'Scheduled (needs agent)' jobs, and 'p50, p95, and p99 dispatch wait-time percentiles'. No request-rate metric on the page.
- https://github.com/actions/actions-runner-controller/blob/master/docs/automatically-scaling-runners.md - opened; confirms verbatim 'a 1:1 scaling of runners to queued jobs', the separate PercentageRunnersBusy metric, 'the controller defaults to a sync period of 1m', and the warning 'Relatively large amounts of API requests are required to maintain this metric, you may run into API rate limit issues'.
- https://docs.github.com/en/actions/reference/limits - opened; confirms concurrent job caps 20 (Free) / 40 (Pro) / 60 (Team) / 500 (Enterprise) and 1000 for larger runners, the 6-hour hosted-runner job cap, and that the 24-hour queue cancellation applies to SELF-HOSTED jobs (a qualifier the researcher omitted).
- https://circleci.com/landing-pages/assets/2025-state-of-software-delivery-report.pdf - WebFetch could not parse the PDF, so I extracted the text myself with pypdf. Confirms verbatim 'DURATION 38s 2m 43s 8m 7s 11m 2s 10m' under headers P25 P50 P75 AVG BENCHMARK; methodology '14,146,319 workflows', 'Every day between September 1, 2024 and September 28, 2024', 'Only GitHub projects'. CRITICAL: the metric is defined as 'Duration measures the time from when an individual workflow is triggered until all of its jobs and steps are complete' - these are WORKFLOW durations, not job durations.
- https://bazel.build/remote/rbe - opened; confirms 'Remote execution of a Bazel build allows you to distribute build and test actions across multiple machines, such as a datacenter' and the benefit 'Reuse of build outputs across a development team'.
- https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts - opened; confirms 'By default, GitHub stores build logs and artifacts for 90 days, and this retention period can be customized'. It does NOT mention any cache limit, contrary to the researcher's attribution.
- https://docs.github.com/en/actions/reference/dependency-caching-reference - opened by me to rescue the mis-attributed cache claim; confirms 'By default, the limit is 10 GB per repository' plus the 7-day unused-entry eviction policy.
- Own computation (scratchpad erl.py), not a web source: reproduced runner util 0.7578947, DB util 0.00136, margin 75.653 pts, store util 0.0135%, gw util 0.015%, M/M/1 sojourn 1239.13 s, Erlang-B 3.6696e-05, Erlang-C P(wait) 0.00015156, mean wait 0.000988 s, implied price $0.06777 per instance-hour, and fan-out fleet sizes of 950 / 3,800 / 9,500 runners at 5x / 20x / 50x.

### distributed_consensus

- **shape:** reasonable_simplification · **numbers:** implausible

**What a reader would get wrong**

I reproduced the engine arithmetic exactly and CONFIRM the tie is real: wal = 2250/3000 = 0.750 and
store = 12000/(2x8000) = 0.750, which is why margin_pts is 0.0. Naming 'the WAL is your bottleneck'
off a zero-point margin between two hand-chosen ASSUMPTION constants is an artefact, not a finding.
This is the strongest defect and it is a defect in the reported VERDICT, which is what we were asked
to judge.  THE HEADLINE CLAIM IS FALSE AS STATED (verified). The wal assumption says ~3,000
committed entries/s 'is the real ceiling of a Raft cluster and it does NOT improve by adding
members.' The second half is CORRECT and well-supported: I read Spanner Table III directly — write
throughput 4.2 / 1.8 / 1.2 Kops/sec at 1 / 3 / 5 replicas on 4-core 4GB spanservers — and Ongaro
p.144 says verbatim 'performance degrades when using larger clusters, since the leader has to send
each entry to a larger number of followers.' The first half is FALSE. etcd's own benchmark on ONE
fixed 3-member cluster (8 vCPU / 16 GB / 50 GB SSD, etcd 3.2.0) spans 583 write QPS at 1 conn/1
client to 44,341 at 100 conn/1000 clients — a 76x span on identical hardware. Mechanism confirmed in
Ongaro §10.2.2, which I extracted verbatim: 'it is much faster to send two entries over the network
in one packet than in two separate packets, or to write two entries to disk at once', LogCabin
leaders send 'up to one megabyte in size' per AppendEntries, and 'the follower then writes all the
new entries from a single AppendEntries request to its disk at once.' LogCabin itself sustains
~19,500 kilobyte-sized writes/s on three servers at 100 threads (p.144) — 6.5x the blueprint's
figure. The value 3,000 is defensible as a conservative LOW-CONCURRENCY single-group figure; the
claim hung on it is not.  THE LATENCY PARAMETER DESCRIBES A SICK DISK (verified, and this is the
clearest hard error). wal base_latency_ms 8.0 is offered for an 'NVMe-backed node'. Ongaro p.146:
writing one kilobyte durably to disk 'we measured in a microbenchmark to be about 0.25 ms'; end-to-
end LogCabin 1 KB write latency is ~0.7 ms on one server and ~1.0 ms on two-to-five servers. etcd's
performance page states fdatasync is ~10 ms for a SPINNING disk and 'often lower than 1ms' for SSDs.
So 8.0 ms is 8-32x too slow for the stated hardware and is essentially etcd's spinning-disk/alert
regime. A learner calibrates 'normal' against a number that signals disk trouble.  SCALE CONTEXT
OMITTED. etcd's own hardware tiering (verified): Large = 'fewer than 10,000 of requests per second',
xLarge = 'more than 1,500 clients, more than 10,000 of requests per second'. The blueprint runs a
SINGLE Raft group at 15,000 ops/s, past etcd's own xLarge line, and never says so. Every production
system shards instead: TiKV verbatim — 'Raft group is divided into multiple Raft groups in terms of
partitions, namely, Region'; Spanner's test database 'was created with 50 Paxos groups'. Multi-Raft
is the single most important architectural move in real consensus systems and appears nowhere, so
the blueprint frames a single-leader ceiling as an immovable fact rather than the moment you shard.
THE ROUTER'S REASON FOR EXISTING CARRIES NO TRAFFIC. The component is named 'watch coalescing' and
etcd's gRPC proxy docs confirm that is its purpose — 'coalesces multiple client watchers
(c-watchers) on the same key or range into a single watcher (s-watcher)' and 'reduces the stream
load on the etcd server from N to 1'. There is no watch flow in the file. This one MATTERS for the
verdict: store is already tied at 0.750, so any watch load would push store past wal and change the
named bottleneck.  SNAPSHOT FREQUENCY IS 100x OFF (verified but immaterial). snap is visited at
x0.001; etcd's --snapshot-count default is confirmed at 100000 committed transactions, i.e.
x0.00001. At 2.25 req/s this cannot move any utilisation — a teaching nit, not a bottleneck risk,
and the file's own GAP note already flags this component's cost line as a floor.  WHAT THE BLUEPRINT
GETS RIGHT AND MUST KEEP. The linearizable_read flow never touches the WAL — Ongaro §6.4 confirms
ReadIndex 'avoids synchronous disk writes', and I verified all five steps including 'issues a new
round of heartbeats and waits for their acknowledgments from a majority of the cluster.' Routing the
final serve to followers is endorsed by §6.4 (followers ask the leader for a readIndex, then execute
steps 4-5 locally). The wal/store split is exactly Consul's documented shape: 'Servers are generally
I/O bound for writes because the underlying Raft log store performs a sync to disk every time an
entry is appended. Servers are generally CPU bound for reads since reads work from a fully in-memory
data store.' The instances=1 leader with its 'that is not an availability bug' note, the honest
peers fan-out-vs-pool limitation with 2x headroom, the quorum-max() caveat, and the admission that
the lease cache is a type-system workaround are all good. store at 8,000 rps/member and
base_latency_ms 3.0 are DEFENSIBLE, not defects — etcd measures serialisable reads from 2,909 QPS at
1 client (0.3 ms) to 185,758 at 1000 clients (2.2 ms), so 8,000/member sits inside the measured span
and 3.0 ms is close to the measured high-concurrency latency.

**Fix**

1. KILL THE FIXED-CEILING CLAIM, KEEP THE NUMBER. Rewrite the wal assumption to name the operating
point: '~3,000 committed entries/s at LOW client concurrency with small batches.' Cite the span that
proves it is not a constant (etcd 3-member SSD: 583 writes/s at 1 conn/1 client vs 44,341 at 100
conn/1000 clients) and the mechanism (Ongaro §10.2.2: up to 1 MB per AppendEntries, follower writes
the whole batch in one disk write). Keep 3,000 as the conservative single-group figure — Spanner
Table III's 1.8 Kops/s at 3 replicas supports it — but attach the concurrency assumption to it. KEEP
the 'more members makes writes slower' half unchanged; it is correct and doubly sourced. 2. FIX
base_latency_ms ON wal: 8.0 -> ~0.5-1.0 ms for NVMe (Ongaro: 0.25 ms for a durable 1 KB write; etcd:
SSD fdatasync under 1 ms). Add a note that ~10 ms is etcd's SPINNING-disk figure, so a reader
recognises 8 ms as a failure signal rather than a baseline. This is the single clearest factual
error in the file. 3. REPORT THE TIE HONESTLY. At margin_pts 0.0 the report must say 'wal and store
are indistinguishable at these inputs' rather than naming a winner. This is a Keystone engine/report
change, not just a blueprint change, and it generalises to every zero-margin verdict. 4. ADD A WATCH
FLOW. The router's entire justification is watch coalescing (etcd gRPC proxy: c-watchers collapsed
to one s-watcher, N->1). This is the one omission that would change the named bottleneck, so it is
worth more than the cosmetic fixes. 5. NOTE THE SINGLE-GROUP LIMIT AND SHIP A SHARDED VARIANT. Say
against etcd's own tiering that 15,000 ops/s is already past the xLarge line (over 10,000 req/s) for
one group, and add a second variant sharded into N Raft groups, citing TiKV Regions and Spanner's 50
Paxos groups. Without it the blueprint teaches a dead end. 6. CHANGE THE SNAPSHOT VISIT RATIO to
x0.00001 to match etcd's --snapshot-count default of 100,000, or justify snapshotting 100x more
often. Immaterial to utilisation; fix it for the operational intuition. 7. OPTIONAL, LATENCY ONLY:
note (citing Ongaro §10.2.1 / Figure 10.2(b)) that the leader's disk write runs in PARALLEL with
follower replication and 'the leader may even commit an entry before it has been written to its own
disk, if a majority of followers have written it to their disks', so the modelled serial path is
Figure 10.2(a), the unoptimised pipeline. Do NOT expect this to change any utilisation — see
dropped_claims. 8. LEAVE store ALONE. Its rps and its 3.0 ms latency are both inside etcd's measured
range; changing them to break the tie would be fitting the inputs to a desired verdict.

**Verified sources**

- https://web.stanford.edu/~ouster/cgi-bin/papers/OngaroPhD.pdf — Ongaro PhD thesis, Stanford, 2014. I downloaded and extracted the PDF text myself. Verified verbatim: §6.4 ReadIndex steps 1-5 and 'since it avoids synchronous disk writes'; §6.4 followers offloading reads via a leader-supplied readIndex; §6.4.1 'we do not recommend' clock/lease reads; §10.2.2 batching ('write two entries to disk at once', LogCabin 'up to one megabyte', follower 'writes all the new entries from a single AppendEntries request to its disk at once'); §10.2.1 leader writes disk in parallel, 'may even commit an entry before it has been written to its own disk'; p.144 '19,500 kilobyte-sized writes per second' on three servers at 100 threads and 'performance degrades when using larger clusters'; p.146 durable 1 KB write 'about 0.25 ms', latency ~0.7 ms single-server / ~1.0 ms two-to-five servers; §5.1.2 'Snapshotting still creates a burst of CPU and disk bandwidth usage'.
- https://etcd.io/docs/v3.5/op-guide/performance/ — verified: 3-member cluster, 8 vCPU/16 GB/50 GB SSD each, etcd 3.2.0. Writes to leader 583 QPS at 1 conn/1 client, 44,341 at 100 conn/1000 clients. Serialisable reads 2,909 QPS / 0.3 ms and 185,758 / 2.2 ms. Linearizable 1,353 / 0.7 ms and 141,578 / 5.5 ms. fdatasync ~10 ms spinning disk, 'often lower than 1ms' for SSD.
- https://etcd.io/docs/v3.5/op-guide/hardware/ — verified tiering: Large 'fewer than 1,500 clients, fewer than 10,000 of requests per second'; xLarge 'more than 1,500 clients, more than 10,000 of requests per second'.
- https://etcd.io/docs/v3.5/op-guide/grpc_proxy/ — verified verbatim: c-watchers coalesced into a single s-watcher; lease stream load reduced 'from N to 1'; range responses cached.
- https://etcd.io/docs/v3.5/op-guide/configuration/ — verified: --snapshot-count default '100000', 'Number of committed transactions to trigger a snapshot to disk.'
- https://developer.hashicorp.com/consul/docs/reference/architecture/server — verified verbatim: 'Servers are generally I/O bound for writes because the underlying Raft log store performs a sync to disk every time an entry is appended. Servers are generally CPU bound for reads since reads work from a fully in-memory data store that is optimized for concurrent access.' Production specs 8-16 cores, 32-64 GB, 7500+ IOPS, 250+ MB/s.
- https://tikv.org/deep-dive/scalability/multi-raft/ — verified: 'Raft group is divided into multiple Raft groups in terms of partitions, namely, Region.'
- https://www.cs.cornell.edu/courses/cs5414/2017fa/papers/Spanner.pdf — Corbett et al., ACM TOCS 31(3), Article 8, August 2013. I extracted the PDF myself. Table III verified: write throughput 4.2 / 1.8 / 1.2 Kops/sec at 1 / 3 / 5 replicas, spanservers at 4 GB RAM and 4 cores. Commit wait ~4 ms, Paxos latency ~10 ms. Test DB 'created with 50 Paxos groups'.
- https://github.com/kubernetes/enhancements/blob/master/keps/sig-api-machinery/2340-Consistent-reads-from-cache/README.md — verified: 'More than 80% of LISTs served by apiserver are consistent reads from cache.'

### distributed_txn

- **shape:** reasonable_simplification · **numbers:** implausible

**What a reader would get wrong**

PROPORTION IS THE HEADLINE DEFECT AND IT IS AN INTERNAL INCONSISTENCY, NOT A SIMPLIFICATION. (The
schema gives me no proportion field, so I record it here: shape is a fair simplification, proportion
is WRONG.) The file models db(x1.0) and coord(x1.0) as though a saga costs one saga-log write and
one orchestrator invocation. A saga is a SEQUENCE. I verified microservices.io's own orchestration
example: the Create Order saga takes SIX steps across Order Service and Customer Service — one
remote participant. This blueprint has THREE participants, so per saga the orchestrator handles a
start plus three replies (~4 invocations) and the saga log takes a durable write per state
transition (~5). Temporal, the reference production orchestrator, names this unit outright: a State
Transition is 'a unit of progress by a Workflow Execution', and its server docs state 'the number of
History Shards represents the number of concurrent database operations that can occur for a Temporal
Service' — real orchestrators are sized in per-step DB operations, not in workflows.  THE FILE
ALREADY DIAGNOSED THIS AND FIXED IT FOR EXACTLY ONE COMPONENT. I read the `q` assumption in the
file: 'One saga costs roughly 7 broker messages (1 start + 3 commands + 3 replies)... The engine's
visit_prob is a probability in [0,1] and cannot express a >1 visit ratio, so the fan-out lives in
the capacity input instead of the flow.' That reasoning is correct — and it is not applied to db or
coord in the same file. That is an error the author had already identified, not a teaching
simplification.  THE ARITHMETIC, WHICH I REPRODUCED EXACTLY. As shipped: db 2880/4000 = 0.720, inv
2850/4000 = 0.7125, coord 3000/4500 = 0.6667, q 2850/8400 = 0.339, cache 3000/200000 = 0.015.
Applying the visit counts the file's own Kafka reasoning implies: db ~14,400 writes/s vs 4,000
capacity = ~3.6x over; coord ~11,400 invocations/s vs 4,500 = ~2.5x over; inv genuinely ~1 visit, so
~0.71 unchanged. The engine therefore names db — the RIGHT component — at 72% with '28% headroom'
when it is roughly 4x over, and its contender list is wrong: inv is comfortable, coord is the real
number two. A reader plans capacity for a system already far past its durability anchor.  THE
VERDICT IS DECIDED BY 0.75 PERCENTAGE POINTS. db 72.00% vs inv 71.25%, both ASSUMPTION constants,
where db's capacity rests on a mechanism claim that is itself wrong. Any honest error bar flips it.
'EACH WRITE IS SYNCHRONOUS' DOES NOT MEAN ONE fsync PER WRITE. The db assumption reasons from 'every
state transition is an fsync'd write' to a fixed ~4,000 rps. Postgres group commit defeats that,
verified verbatim: commit_delay 'can improve group commit throughput by allowing a larger number of
transactions to commit via a single WAL flush', and 'Beginning in PostgreSQL 9.3, the first process
that becomes ready to flush waits for the configured interval, while subsequent processes wait only
until the leader completes the flush operation.' Same mechanism error as the consensus blueprint's
WAL. 4,000 is a fine order of magnitude for one unsharded writer; it is not a physical ceiling, and
the load-bearing verdict treats it as one.  KAFKA IS 10-20x TOO SLOW AND IS MADE TO LOOK LIKE A
CONTENDER. 2,800 tx/s per broker = ~20,000 msg/s per broker. LinkedIn's own benchmark (27 Apr 2014,
six-core Xeon, six 7200 RPM SATA drives, 1 GbE, 100-byte messages) sustained 421,823 records/s at 3x
SYNCHRONOUS replication. Confluent (21 Aug 2020, three i3en.2xlarge NVMe brokers, 1 KB records, 100
partitions) peaked at 605 MB/s, roughly 200k records/s per broker. Kafka sits at 0.339 utilisation
and fourth place here; in reality it is not in the conversation, and the under-count invites a
reader to tune a broker fleet with 10-20x the headroom they think.  THE ACTUAL BOTTLENECK IS NOT IN
THE MODEL AT ALL. The design authorises 0.9 x 3,000 + compensations = 2,850 payment operations/s.
Stripe's published live-mode global limit is 100 requests per second per account, with individual
endpoints at 25 requests per second — verified on Stripe's own rate-limits page, which also names
this exact scenario: 'A sudden increase in charge volume, such as a flash sale, might result in rate
limiting.' That is ~28x the global quota and ~114x the per-endpoint quota. Stripe additionally
documents concurrency limits that 'restrict the number of simultaneously active requests, separate
from rate limits', and 429 lock_timeout errors on concurrent access to the same object. The `pay`
assumption DOES flag the missing PSP hop but frames it purely as LATENCY ('typically 100-300 ms').
It is primarily a CAPACITY omission and it dominates every other finding in the file. The engine
says 'shard your Postgres saga log'; the real answer is 'you cannot run this at all until you
negotiate a PSP quota increase, and then you need ~570 concurrent in-flight authorisations to cover
a 200 ms round trip.'  MISSING COMPONENTS. (a) No message relay, though the outbox pattern requires
one — microservices.io verified: 'A separate process then sends the messages to the message broker',
via transaction log tailing or a polling publisher, and 'The Message relay might publish a message
more than once.' The db assumption even says 'the outbox is polled by the relay', yet that relay is
neither a component nor a load, and its poll read load would land on the very component named as the
bottleneck. (b) No durable timer store, despite coord being named 'state machine, timeouts, retries'
— Temporal makes exactly this a sharded first-class persistence concern. (c) No dead-letter / stuck-
saga path.  SCALE CONTEXT THE READER IS NOT GIVEN. 3,000 multi-participant business transactions/s
is Black-Friday-tier. Percolator (Peng & Dabek, OSDI 2010, read directly): a single-cell write
'incurs roughly a factor of four overhead' over raw Bigtable (a read to check locks, a write to add
the lock, a write to remove it — with batching optimisations disabled for that measurement); its
TPC-E-like workload 'performs 11,200 tps using 15,000 cores' against '3,183 tpsE using a single
large shared-memory machine', and the authors 'estimate that Percolator uses roughly 30 times more
CPU per transaction than the benchmark system', at 2-5 second average latency. Spanner Table IV, 2PC
within one region across 3 zones of 25 spanservers: 1 participant 14.6 ms mean / 26.6 ms p99; 2
participants 20.7 / 32.0; 5 participants 23.9 / 46.4; 50 participants 33.8 / 62.4; 'latencies start
to rise noticeably at 100 participants.' Distributed transactions are expensive and the blueprint's
per-instance numbers convey none of that.  WHAT IS GENUINELY GOOD. Orchestration over choreography
with state in the log and a stateless coordinator; the compensate flow correctly bypassing the
gateway; the outbox co-located with the saga log in one transaction; at-least-once plus idempotency
keys; the explicit 'Sagas are NOT serialisable — intermediate states are visible to other readers',
which matches microservices.io's own named drawback, 'Lack of isolation (the I in ACID)'; and the
excellent engine caveat that an open queueing network has no notion of ordering or in-flight saga
lifetime. The Redis sizing is the one set of numbers that MATCHES reality: 100,000 rps/instance at
0.4 ms against redis-benchmark's measured 'SET: 180180.17 requests per second, p50=0.143 msec' un-
pipelined and 72,144 rps against a 100k random keyspace. It is also the one place the missing visit
count is harmless — idempotency is really touched ~3-6 times per saga, moving utilisation from 1.5%
to ~9%, still nothing.

**Fix**

1. APPLY THE FILE'S OWN KAFKA CORRECTION TO db AND coord. This is the change that matters most.
Either bake the per-saga visit count into their capacities exactly as `q` already does and say so in
the same words, or add a visits_per_txn field so the engine can express a >1 visit ratio instead of
smuggling it into capacity. State the derivation: 3 participants -> ~4 orchestrator invocations and
~5 saga-log writes per saga, citing microservices.io's 6-step one-remote-participant example and
Temporal's State Transition as the unit of load. After this, db lands ~3.6x over and coord ~2.5x
over, the margin becomes decisive, and the contender list correctly reads db then coord — not db
then inv. 2. ADD THE EXTERNAL PAYMENT RAIL AS A RATE-LIMITED DEPENDENCY WITH A CITED QUOTA. Stripe
live mode: 100 requests/second global per account, 25 requests/second per endpoint. It becomes the
binding constraint immediately at 2,850 authorisations/s, and that is the single most useful thing
this blueprint could teach. Pair it with the concurrency figure — 2,850 rps x ~0.2 s PSP round trip
is ~570 concurrent in-flight calls — and note Stripe's separately documented concurrency limits and
429 lock_timeout behaviour. Rewrite the `pay` assumption so the omission reads as capacity first,
latency second. 3. RAISE `q` TO A SOURCED PER-BROKER FIGURE — at minimum ~100k msg/s per broker with
3x synchronous replication, citing LinkedIn's 421,823 records/s at 3x sync (2014, 100-byte records,
SATA) or Confluent's 605 MB/s across three NVMe brokers (2020, 1 KB records). Keep the honest
'capacity stated in transactions/s, one saga is about 7 messages' framing; just fix the underlying
msg/s. Kafka should visibly drop out of contention. 4. RESTATE db's CAPACITY AS CONCURRENCY-
DEPENDENT. Replace 'the log is append-mostly but each write is synchronous' with a note that
Postgres group commit lets many transactions share one WAL flush (commit_delay / commit_siblings;
post-9.3 leader-flush behaviour), so 4,000 rps is one operating point rather than a ceiling. Keep
the excellent existing advice — 'the first thing to shard by saga id' — and point at Temporal's
History Shards as the production precedent, since the shard count there literally IS the count of
concurrent DB operations. 5. ADD THE MISSING COMPONENTS: a message relay (transaction log tailing or
polling publisher) with its poll load landing on db, and a durable timer/timeout store behind coord.
Both are required by patterns the file already names, and the relay's load lands on the named
bottleneck. 6. REFUSE THE 0.75-POINT VERDICT AS SHIPPED. At margin_pts 0.75 between two ASSUMPTION
constants the report must say 'db and inv are indistinguishable at these inputs' rather than naming
a bottleneck. Fixes 1 and 4 make the real margin decisive, at which point naming db is earned rather
than lucky. 7. GIVE THE READER THE COST OF THE ALTERNATIVE. Add one line on what choosing a saga
bought them versus 2PC, with measured figures: Percolator's client-coordinated 2PC at ~4x write
overhead and ~30x CPU per transaction with 2-5 s average latency, and Spanner's 2PC at 20.7 ms mean
/ 32.0 ms p99 for 2 participants with ~4 ms commit wait — throughput and availability, paid for with
the loss of isolation the file already honestly discloses. Note the title alone reads as XA/2PC,
though the summary field already says 'Orchestrated saga coordinator', so this is a one-line
addition, not a rewrite. 8. STATE THAT THE Redis UNDER-COUNT IS HARMLESS. Idempotency keys are
really touched ~3-6 times per saga, not once, but at 100,000 rps/instance that moves utilisation
from 1.5% to ~9%. Saying so proves the visit-count correction was applied everywhere deliberately,
rather than only where it changed the answer.

**Verified sources**

- https://microservices.io/patterns/data/saga.html — verified: 'an orchestrator (object) tells the participants what local transactions to execute'; the drawback 'Lack of isolation (the I in ACID)'; the Create Order orchestration example runs SIX steps across Order Service and Customer Service (one remote participant).
- https://microservices.io/patterns/data/transactional-outbox.html — verified: the message is stored 'in the database as part of the transaction that updates the business entities'; 'A separate process then sends the messages to the message broker' via transaction log tailing or polling publisher; 'The Message relay might publish a message more than once.'
- https://docs.stripe.com/rate-limits — verified: Global API rate limit live mode 100 requests per second (sandbox 25); individual API endpoints 25 requests per second; Files API 20 read / 20 write per second; Search API 20 read per second. Concurrency limits 'restrict the number of simultaneously active requests, separate from rate limits.' 429 lock_timeout object-lock behaviour documented. Verbatim: 'A sudden increase in charge volume, such as a flash sale, might result in rate limiting.'
- https://engineering.linkedin.com/kafka/benchmarking-apache-kafka-2-million-writes-second-three-cheap-machines — verified, dated 27 April 2014, six-core Intel Xeon 2.5 GHz, six 7200 RPM SATA drives, 32 GB RAM, 1 GbE, 100-byte messages: single producer no replication 821,557 rec/s (78.3 MB/s); 3x async 786,980 (75.1 MB/s); 3x sync 421,823 (40.2 MB/s); single consumer 940,521 (89.7 MB/s).
- https://www.confluent.io/blog/kafka-fastest-messaging-system/ — verified, dated 21 August 2020: three i3en.2xlarge brokers (8 vCore, 2 x 2,500 GB NVMe), 1 KB records, 100 partitions; Kafka peak 605 MB/s.
- https://www.postgresql.org/docs/current/runtime-config-wal.html — verified verbatim: commit_delay 'can improve group commit throughput by allowing a larger number of transactions to commit via a single WAL flush'; and 'Beginning in PostgreSQL 9.3, the first process that becomes ready to flush waits for the configured interval, while subsequent processes wait only until the leader completes the flush operation.'
- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/ — verified: 'SET: 180180.17 requests per second, p50=0.143 msec' and 'LPUSH: 188323.91 requests per second, p50=0.135 msec' at 50 clients without pipelining; 72,144 rps SET against a 100k random keyspace; 'SET: 1536098.25 requests per second' and 'GET: 1811594.25' with -P 16 on a MacBook Air; 'Redis is, mostly, a single-threaded server from the POV of commands execution'.
- http://notes.stephenholiday.com/Percolator.pdf — Peng & Dabek, 'Large-scale Incremental Processing Using Distributed Transactions and Notifications' (OSDI 2010). I downloaded and extracted the PDF; author/affiliation block confirms identity. Verified: commit 'is coordinated by the client'; a single-cell write 'incurs roughly a factor of four overhead on this benchmark' from 'a read to check for locks, a write to add the lock, and a second write to remove the lock record' (measured with batching optimisations disabled); '11,200 tps using 15,000 cores' vs '3,183 tpsE using a single large shared-memory machine'; 'roughly 30 times more CPU per transaction'; 'average transaction latency is 2 to 5 seconds'; oracle 'serves around 2 million timestamps' per second.
- https://www.cs.cornell.edu/courses/cs5414/2017fa/papers/Spanner.pdf — Corbett et al., ACM TOCS 31(3), Article 8, August 2013. PDF extracted directly. Table IV verified: 1 participant 14.6 ms mean / 26.550 ms p99; 2 -> 20.7 / 31.958; 5 -> 23.9 / 46.428; 50 -> 33.8 / 62.420; 100 -> 55.9 / 88.859. Text verified: 'latencies start to rise noticeably at 100 participants'; 3 zones each with 25 spanservers; commit wait ~4 ms, Paxos latency ~10 ms.
- https://docs.temporal.io/glossary — verified: State Transition is 'a unit of progress by a Workflow Execution'; 'An Action is the fundamental pricing unit in Temporal Cloud'.
- https://docs.temporal.io/temporal-service/temporal-server — verified verbatim: 'the number of History Shards represents the number of concurrent database operations that can occur for a Temporal Service'; range 1 to 128K; the count must be chosen before integrating a database and cannot be changed afterwards.

### iot_platform

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

This is the strongest of the three and its assumptions block is the best honesty in the set — it
names the socket-memory ceiling the engine cannot model, names the batching factor as 'the single
most important number in this design', and names rebalance storms as invisible. Those are real GAPs
declared before anyone had to find them. Three problems remain, all confirmed.  (1) THE NAMED
BOTTLENECK IS FALSE PRECISION (confirmed). Engine says ingest bridge 0.7833, margin 0.54 points —
reproduced exactly. But the top four rows are 0.7833 / 0.7779 / 0.7600 / 0.7500, a 3.3-point band,
and every one of the four is sized by an unsourced ASSUMPTION rate. A 0.54-point margin cannot
survive that. Two of the four are also demonstrably conservative against published figures, so
correcting them reshuffles the band: Kafka at 30,000 msg/s per broker is ~7x below Confluent's
~200k/broker (1 KB, RF=3, 2020), and the gateway at 40,000 msg/s per node is 2.5-5x below EMQX's
measured 100k/node at QoS 1 or 200k/node at QoS 0. CORRECTION TO THE RESEARCHER'S ARITHMETIC: they
wrote that fixing these drops the gateway to '~0.15' while citing the QoS 1 figure. At QoS 1
(100k/node x 4 = 400,000 against 120,000 load) the gateway lands at 0.30, not 0.15; 0.15 is the QoS
0 result. Either way it leaves the contender band. Kafka drops to 0.114. What remains is ingest
0.7833 against proc 0.7779 — still a 0.54-point coin flip between 4,000 and 5,000 msg/s per
instance, two numbers with no source at all. The honest output is a four-way tie, resolvable only by
measurement.  (2) 'DEVICE SHADOW' IS THE WRONG NAME AND IT IMPORTS WRONG ECONOMICS (confirmed, and
the ratio is exact). The component is a self-hosted Redis last-known-state cache written on every
telemetry message. For a self-hosted platform that is a legitimate design, so this is not a shape
error — but the name invites a reader to map it onto AWS IoT Device Shadow or Azure device twin,
where both semantics and economics differ completely. AWS's Well-Architected IoT Lens describes
Shadow verbatim as a way 'to implement command and control over MQTT', with 'a clientToken, to track
the origin of a request, version numbers for managing conflict resolution, and the ability to store
commands in the cloud in the event that a device is offline' — a control-plane object, not a
telemetry sink. And the quotas price it accordingly: AWS allows 20,000 inbound publishes/sec/account
but only 4,000 Device Shadow API requests/sec/account and 20/sec per thing. Azure S3 is harsher and
the researcher's 24:1 figure is exactly right — 6,000 device-to-cloud sends/sec/unit against 250
twin updates/sec/unit, with twin reads at 500/sec/unit. A reader who ports this design to a managed
platform hits a wall 24x sooner than the model predicts, on the very component the blueprint itself
calls 'the design's real availability risk'. That risk statement is correct for the Redis design as
drawn and wrong for anything called a shadow.  (3) THE TIME-SERIES SINK IS TIGHTER THAN 0.7056 LOOKS
(confirmed verbatim). 1,128 write ops/s x 100 readings = 112,800 rows/s landing on ONE modelled
instance. Timescale's own guidance, quoted exactly, is that 'you should aim for ingesting 50-100k
rows per second per ingest process' — so this is at or above the top of the vendor's own per-process
ceiling and implies a parallel writer pool the single-instance model cannot express. The stated
batch of 100 rows is also below the same page's recommendation to 'try to write hundreds (or
thousands) of rows per INSERT'. The number is not wrong; the 70% reading is comfortable in a way the
underlying constraint is not.  WHAT IS RIGHT AND SHOULD BE LEFT ALONE: the 94/5/1 mix is well-
defended and independently corroborated — 1M devices at one reading per 8s = 125k/s against the
stated 120k, and Azure's own 24:1 telemetry-to-twin-write quota ratio confirms that control and
human traffic are a small minority of telemetry. The gateway -> bridge -> bus -> processor -> TSDB +
state cache + query/command API skeleton is the real shape, matching both managed platforms. Redis
at 100k/node is conservative against redis.io's measured 180,180 unpipelined SET. And the
connection-ceiling GAP is precisely the right call, better supported than the blueprint itself
claims: EMQX needed 5 nodes at 32 cores/64 GB and roughly 28-36 GB of RAM per node purely to hold 2M
sockets each, and AWS IoT Core's default concurrent-connection quota is 500,000 per account against
this design's assumed 1,000,000 devices — so the thing the engine cannot see is genuinely the thing
that bites first.

**Fix**

1. Report a tie, not a winner. When the top N components sit within a few points and all carry
ASSUMPTION provenance, the verdict line should read 'four components within 3.3 points — bottleneck
not determined' and list them. A 0.54-point margin over unsourced inputs is false precision, and
this is the single change that most improves the file's honesty. It is the same report-layer fix all
three blueprints need. 2. Raise Kafka to ~200k msg/s per broker (Confluent 2020) and the gateway to
~100k msg/s per node at QoS 1 (EMQX 2021), both cited. This removes two rows from the contender band
(q to 0.114, gw to 0.30 — note 0.30, not the 0.15 the researcher wrote, which is the QoS 0 figure)
and forces the real question — 4,000 vs 5,000 msg/s per instance for the bridge and processor — into
the open. 3. Rename 'Device shadow / last-known state (Redis)' to 'Last-known-state cache (Redis)'
and add a GAP: on managed platforms the equivalent object is metered 5-24x more scarcely than
telemetry (AWS: 4,000 shadow req/s/account and 20/s per thing against 20,000 inbound publishes/s;
Azure S3: 250 twin updates/s/unit against 6,000 D2C sends/s/unit), so a per-message write does not
port. Cite the AWS quota table and the Azure throttle table. 4. Add a GAP on the tsdb row: 112,800
rows/s is at or above Timescale's published per-ingest-process guidance of 50-100k rows/s, so the
single 'instance' implies a parallel writer pool; and the 100-row batch is below the recommended
hundreds-to-thousands. 5. Keep the gateway socket-ceiling assumption exactly as written and
strengthen it with the two concrete numbers: EMQX needed ~28-36 GB RAM per node to hold 2M
connections, and AWS IoT Core's default concurrent-connection quota is 500,000 per account against
this design's 1M devices. Azure's docs also make the point that matters — new-connection RATE is
throttled separately from concurrent connection COUNT ('The device connections throttle doesn't
relate to the maximum number of simultaneously connected devices'), which is a second dimension the
engine cannot express.

**Verified sources**

- https://docs.aws.amazon.com/general/latest/gr/iot-core.html — verified: 100 publish requests/sec per connection (NOT adjustable); 20,000 inbound publish requests/sec per account (adjustable); 500,000 maximum concurrent client connections per account (adjustable); 3,000 connect requests/sec per account (adjustable); 128 KB maximum MQTT payload (NOT adjustable); 20,000 rule evaluations/sec per account. Device Shadow: 4,000 API requests/sec per account; 'The Device Shadow service supports up to 20 requests per second per shadow'; 'Each individual shadow document must be 8KB or less in size.'
- https://docs.aws.amazon.com/wellarchitected/latest/iot-lens/aws-iot-device-shadow-service.html — verified verbatim: Shadow is a feature 'to implement command and control over MQTT', with benefits including 'a clientToken, to track the origin of a request, version numbers for managing conflict resolution, and the ability to store commands in the cloud in the event that a device is offline and unable to receive the command when it is issued.'
- https://learn.microsoft.com/en-us/azure/iot-hub/iot-hub-devguide-quotas-throttling — page updated 2026-05-06. Verified from the throttle tables: S3 device-to-cloud sends 6,000 send operations/sec/unit; S3 twin reads 500/sec/unit; S3 twin updates 250/sec/unit (so the 24:1 telemetry-to-twin-update ratio is exact). 'The total number of devices plus modules that can be registered to a single IoT hub is capped at 1,000,000.' On connections: 'The device connections throttle doesn't relate to the maximum number of simultaneously connected devices.'
- https://www.emqx.com/en/resources/emqx-v-4-3-0-ten-million-connections-performance-test-report — published 2021-11-05. Verified: 5 nodes at 32 cores and 64 GB each; 10 million concurrent MQTT connections (2M per node); 1 million msg/s aggregate at QoS 0 (200k/node); 500,000 msg/s at QoS 1 (100k/node); approximately 28-36 GB RAM per node during messaging.
- https://www.tigerdata.com/blog/timescale-cloud-tips-how-to-optimize-your-ingest-rate — published 2022-08-17, updated 2025-12-09. Verified verbatim: 'you should aim for ingesting 50-100k rows per second per ingest process' and 'try to write hundreds (or thousands) of rows per INSERT'.
- https://www.confluent.io/blog/kafka-fastest-messaging-system/ — published 2020-08-21. 605 MB/s across 3 i3en.2xlarge brokers, 1 KB messages, RF=3 => ~200k msg/s per broker, against this blueprint's 30,000.
- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/ — verified 'SET: 180180.17 requests per second' unpipelined (3-byte payload, 50 clients, loopback), so 100k/node is conservative. Also relevant to a 1M-device design: 'Redis has already been benchmarked at more than 60000 connections, and was still able to sustain 50000 q/s in these conditions. As a rule of thumb, an instance with 30000 connections can only process half the throughput achievable with 100 connections.'
- https://kafka.apache.org/powered-by/ — verified: TBMQ entry states it can 'support over 100 million concurrent connections while maintaining horizontal scalability and multi-million message-per-second throughput.'

### leaderboard

- **shape:** matches · **numbers:** plausible

**What a reader would get wrong**

The parts list is not the problem — I am upgrading shape to `matches`. Redis's own leaderboard use-
case page documents this design almost element for element: the board "is stored as a Redis sorted
set — one key per board" with "a companion hash per entity" for metadata; ZADD, ZRANGE and ZREVRANK
"all running in O(log N) regardless of set size"; EXPIRE on per-window keys for daily/weekly/monthly
boards and ZUNIONSTORE to aggregate them. ZADD's command reference confirms "O(log(N)) for each item
added". Adding a durable score log ahead of the sorted set is a standard and well-justified
addition. The components and their connections are right.  The misleading parts are flow proportion
and capacity crediting, and they are verdict-changing.  (1) The named bottleneck is an artifact of a
consumer that cannot keep up. submit_score puts 30,000 x 0.10 = 3,000 events/s into the score log;
materialise drains it at 30,000 x 0.05 = 1,500/s. Because each flow's rate is an independent share
of system_rps, the consumer rate is decoupled from the producer rate, so the queue grows 1,500
events/s forever while the model reports it healthy at 18.75%. Charge the materialiser the rate that
actually arrives and it is 3,000 / (4 x 500) = 150% — a blowout, and the correct headline. The API's
79.17% is visible only because the worker was quietly given half its real work. I confirmed 8
instances are needed to hold it at or under 80%.  (2) Redis is shown at 15.83% because 2 nodes are
credited as 2x capacity, but the premise of the design is that the live ranking is ONE sorted-set
key. The Redis Cluster spec states "When the cluster is stable, a single hash slot will be served by
a single node", with keys mapped by HASH_SLOT = CRC16(key) mod 16384; replica reads require
READONLY, which "tells a Redis Cluster replica node that the client is ok reading possibly stale
data" — for a live ranking that is a product decision, not free capacity. Charged to one node the
28,500 ops/s is 31.67%; against Redis's own conservative rule of thumb of "25Gb or 25K Ops/Second"
per shard it is 114% of the vendor's recommended operating point — on the one key you cannot shard
your way out of, because splitting the ZSET destroys the global ranking that is the product. Redis
rates hot keys a HIGH-severity anti-pattern and describes this exact shape: "if you have a cluster
of 99 nodes and you have a single key that gets a million requests in a second, all million of those
requests will be going to a single node, not spread across the other 98 nodes." The blueprint's
cache_ha assumption is admirably honest that 2x over-credits the WRITE path but concludes "the
distortion does not change the verdict here" — it does, because the distortion is on the READ path
too: 24,000 of the 28,500 ops/s are reads of the same hot key.  (3) No byte model. Redis's benchmark
page warns "In many real world scenarios, Redis throughput is limited by the network well before
being limited by the CPU" and works the example that 4 KB values at 100,000 q/s consume 3.2 Gbit/s.
I verified the arithmetic: 21,000 top-100 reads/s at ~40-byte members is 84 MB/s (0.67 Gbit/s) off a
single node, and 1.01 Gbit/s at 60-byte members — enough to saturate a 1 GbE link while the model
still reports the cache at 16%.  Net: a reader takes away "add API instances". The real first wall
is the materialiser, and the second is the single Redis key's throughput and egress bytes.  On
numbers, `plausible` stands but is unevenly earned. The Redis figure (90,000 ops/s per node) is
checkable and sits in the right band — redis-benchmark publishes non-pipelined SET at 180,180.17
req/s and 72,144.87 req/s over a 100k keyspace, and sorted sets are among the types benchmarked on
the bare-metal Xeon Gold 6230 series. The API (4,000) and worker (500) figures have no public
referent at all: no game or consumer company has published a production leaderboard architecture
with numbers. Riot confirms only that a discrete leaderboard service exists among its meta-game
services and gives fleet-wide counts (>14,500 containers, 25 Feb 2020) — no design, no scale
figures. All three numbers currently carry the same undifferentiated ASSUMPTION label.

**Fix**

1) Derive the materialise flow from the submit flow rather than from system_rps. Either charge it
the true 3,000 events/s — and then report the worker at 150% and size it to 8 instances — or state
an explicit batching factor in the worker assumption ("one materialise step per N score events") so
the 2:1 gap is a declared design choice rather than a silent leak. As written the blueprint models
an unbounded queue and reports it as healthy.  2) Model the ranking set as 1 effective instance, not
2. Cite the Redis Cluster spec line that a single hash slot is served by a single node, and note
that replica reads require READONLY and return possibly-stale data. Add Redis's own 25K ops/s per-
shard threshold to the cache assumption so the reader sees that 28,500 ops/s on one key is already
past the vendor's recommended operating point, on the one key that cannot be sharded without
destroying the product.  3) Add one line of response-byte arithmetic to the cache assumption (21,000
top-N reads/s x N members x ~40-60 B = 0.67-1.0 Gbit/s off a single node), citing Redis's "limited
by the network well before the CPU" guidance. The engine has no byte model; saying so with a number
is far more useful than saying so in prose.  4) Differentiate the provenance labels. State plainly
that no production leaderboard architecture with numbers has been published, so the API (4,000) and
worker (500) per_instance_rps figures are modelling choices with no public referent, while the Redis
figure (90,000/node) is checkable against published redis-benchmark results.

**Verified sources**

- https://redis.io/docs/latest/develop/use-cases/leaderboard/
- https://redis.io/docs/latest/commands/zadd/
- https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/
- https://redis.io/tutorials/redis-anti-patterns-every-developer-should-avoid/
- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/
- https://www.riotgames.com/en/news/running-online-services-riot-part-vi

### mcp_rag_assistant

- **shape:** reasonable_simplification · **numbers:** implausible

**What a reader would get wrong**

PROPORTION: wrong (confirmed). This is the one that would actively send a reader the wrong way. I
re-derived the engine block and it is internally correct: api = 200 against 5x60 = 0.6667; llm =
172x0.7 + 6 = 126.4 against 3x67 = 0.6289; margin 3.78 pts. Both figures are ASSUMPTIONs, the margin
is inside the noise of either, and three independent corrections all push the gateway past the API
tier. (a) The ask flow visits the model gateway 0.7 times. A retrieval-augmented answer cannot work
that way -- the query must be EMBEDDED before the ANN search and an answer GENERATED after it. This
is not a simplification but a flow that cannot physically run as drawn, and it is internally
inconsistent with the blueprint's own token assumption, which says the 5,800/650 figure is 'blended
across answer generation and embedding calls' -- so embeddings do route through this node; the path
simply never visits it for them. At a corrected x1.4 the gateway takes 246.8 calls/s against 201 --
util 1.23 vs the modelled 0.63. That alone inverts the verdict, and repeated llm visits are already
expressible (multi_agent_supervisor's run path visits llm three times), so this is an omission, not
an engine limitation. (b) The quota is modelled in the wrong DIMENSION. At the blueprint's own 126.4
calls/s x 5,800 input tokens the design needs 44.0M ITPM against Anthropic's published Scale ceiling
of 10,000,000 -- 4.4x over -- and 4.93M OTPM against 2,000,000 -- 2.5x over. RPM at 7,584 against
10,000 is the ONLY limiter with headroom, and RPM is the only one the model represents. I confirmed
the Scale tier numbers exactly. (c) The 60 rps/instance figure derives from the blueprint's own
'~2.4 s model round-trip' (60 x 2.4 = 144 concurrent held requests/instance -- an unstated thread-
per-request assumption). But 650 output tokens at Artificial Analysis's measured 74 output tok/s for
Claude Sonnet 5 is 8.8 s of GENERATION ALONE, already 3.7x the modelled 2,400 ms before any time-to-
first-token. CORRECTION TO THE RESEARCHER: I could not confirm their cited TTFT of 1.33-2.02 s --
the page reports Sonnet 5 (max) TTFT at 176.14 s (reasoning-inclusive) and Haiku 4.5 non-reasoning
at 0.74 s. The finding survives without it, on the confirmed output-speed figure alone. Net effect:
a reader is taught 'add API runtime instances' when the actual wall is a contractual token-per-
minute quota that adding your own instances cannot relieve -- and the one lever that WOULD move it
is filed purely as a cost caveat. NUMBERS: implausible, confirmed on three independent measurements.
900 ANN searches/s on 2 vCPU / 16 GiB over 'a few million' 1,536-dim chunks does not survive
contact: AWS's own test on that exact instance (db.r5.large, 2 vCPU / 16 GiB) used only 58,634
documents at 364 MB and disclaimed benchmarking intent; Jonathan Katz measured a 1M x 1536-dim HNSW
index at 7,734 MB; 1M such vectors is ~6.1 GB of heap plus that index = ~13.9 GB, so 'a few million'
is ~42 GB on a 16 GiB box and the index cannot be resident. Supabase needed an 8-core/32 GB instance
to benchmark 1M x 1536 at all. It is also internally incoherent: 900 rps x 25 ms is 22.5 Postgres
backends in flight on 2 vCPU for a CPU-bound SIMD workload, where both published harnesses run one
query at a time.

**Fix**

1) Add the embedding call to the ask path: `lb, api, cache(x1.0), llm(x0.7) [embed query],
vec(x0.7), docs(x0.35), llm(x0.7) [generate]`. 2) Express the provider quota in the limiter that
binds -- give the gateway an ITPM/OTPM ceiling, or state the RPM ceiling alongside the implied ITPM
and say which binds first. Replace the unattributed '4,000 requests/minute' with Anthropic's
published Scale tier (10,000 RPM / 10M ITPM / 2M OTPM for Sonnet 5 / Opus 5 / Haiku 4.5), and add
the caveat the docs force: limits are per-organization and per-model, and pools cannot be assembled
from workspaces within one org -- 'Organization-wide limits always apply, even if Workspace limits
add up to more.' They must be distinct models, providers, or accounts. 3) Promote prompt caching
from a cost footnote to a CAPACITY lever, citing that cache_read_input_tokens do not count toward
ITPM on most models -- Anthropic's own worked example is 'With a 2,000,000 ITPM limit and an 80%
cache hit rate, you could effectively process 10,000,000 total input tokens per minute.' This is the
difference between infeasible and feasible for this design. 4) Restate the vector store honestly:
either shrink the corpus to what fits in RAM (then ~1.5 ms/query and 25 ms is far too pessimistic)
or raise the instance and lower the rps. 5) State a recall/ef_search target. Alibaba's official ANN-
Benchmarks run on 16 cores over 290K x 256-dim moves 1,423.985 QPS at recall 0.630 to 297.267 at
0.918 to 84.268 at 0.969 -- a pgvector rps with no recall target is not a capacity number, and
teaching that is arguably worth more than the number. 6) Set llm base_latency to a full-response
figure (~9-11 s for ~650 output tokens at measured frontier speeds) or rename the field and say it
is TTFT -- 2,400 ms is a TTFT-shaped number in a full-response slot, exactly what the blueprint's
own caveat says v1 cannot compute. 7) Keep the docs tier: 5,500 GET/s per prefix matches AWS
verbatim and the 'instances mean PREFIXES, not servers' disclosure is exactly right -- the one
properly grounded number in the file. (Minor: the ingest flow writes, where AWS documents 3,500/s.)

**Verified sources**

- https://platform.claude.com/docs/en/api/rate-limits
- https://developers.openai.com/api/docs/guides/rate-limits.md
- https://aws.amazon.com/blogs/database/optimize-generative-ai-applications-with-pgvector-indexing-a-deep-dive-into-ivfflat-and-hnsw-techniques/
- https://www.alibabacloud.com/help/en/rds/apsaradb-rds-for-postgresql/pgvector-performance-test-based-on-hnsw-indexes
- https://jkatz05.com/post/postgres/pgvector-hnsw-performance/
- https://supabase.com/blog/increase-performance-pgvector-hnsw
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html
- https://artificialanalysis.ai/providers/anthropic

### mcp_starter

- **shape:** reasonable_simplification · **numbers:** no_public_figure

**What a reader would get wrong**

PROPORTION: misleading (confirmed, on corrected reasoning). I re-derived the engine block: mcp =
60+390+150 = 600 rps against 2x400 = 0.7500; worker = 150 against 5x40 = 0.7500. The exact tie and
margin_pts 0.0 are real. But the researcher's framing -- that the verdict is 'a coin flip' carrying
'no information' -- is OVERSTATED, and I am correcting it: the correction they propose RESOLVES the
tie in favour of the component the engine already named. The real defect is the headroom, not the
identity. The 25% async flow is modelled submit-and-forget (lb->mcp->q->worker->db, '~2 KB async
acknowledgement') with no result-retrieval traffic, and under the 2026-07-28 spec neither branch is
free. Via the official tasks extension, retrieval is polling: the changelog verbatim says it
'replaces the blocking tasks/result method with polling via tasks/get'. At a ~2 s tool call and 500
ms poll interval that is ~4 extra requests per async call: 150 x 4 = +600 rps, taking mcp from 600
to ~1,200 against capacity 800 -- util 1.5, while worker stays at 0.75. So mcp is confirmed as the
bottleneck and the tie breaks the engine's way, but the 25% headroom is illusory and the tier is
loaded 2x what is shown. On the core protocol there is no ack to send at all: the spec says the
server answers each POST with 'a Server-Sent Events (SSE) stream scoped to that request' and
'Closing the SSE response stream MUST be treated by the server as cancellation of that request', so
the tier is bounded by ~300 concurrently held streams (150/instance at 2 s), not 400 rps of CPU. A
reader sizes for 600 rps of short request/response calls and gets a fleet that falls over at roughly
half the intended load. The blueprint's engine caveat gestures at exactly this risk but pins it on
'Streamable-HTTP/SSE sessions' -- and SEP-2567 removed protocol-level sessions and the Mcp-Session-
Id header entirely, so the caveat is right about the risk for a reason that is now wrong, which
makes it easy to dismiss. NUMBERS: no_public_figure is correct and I confirmed it independently --
neither IBM ContextForge nor Docker's MCP Gateway publishes any throughput benchmark, and no vendor
publishes MCP server capacity. 400 rps/instance and 40 tasks/s/instance are ungrounded, and the tie
is an artifact of the modeller's instance counts.

**Fix**

1) Add the missing return traffic: either a fourth flow `tool_result_poll` (share = async_calls x
polls_per_call, path lb -> mcp -> cache) citing the tasks extension's tasks/get polling, or model
the async path as a held stream and state the concurrency ceiling (150 open streams/instance at 2 s)
as the MCP tier's real capacity unit. 2) Rename the Redis component: drop 'Session' -- there is no
protocol session as of 2026-07-28 -- and call it 'Tool-result + policy cache' (tool-result caching
is now spec-blessed via ttlMs/cacheScope). 3) Replace the stale `engine` assumption: streams are
request-scoped and NON-RESUMABLE -- the changelog says verbatim 'A broken response stream loses the
in-flight request; clients MUST re-issue it as a new request with a new request ID' -- so retry
traffic is real and unmodelled. 4) Break the 0.75/0.75 tie deliberately: an exact tie with
margin_pts 0.0 should be suppressed by the engine or justified in the text rather than presented as
a finding. 5) Soften the architecture assumption's absolutism: 'there is no model provider, no token
spend' is right for a pure tool server, but the same revision DEPRECATED Sampling with the migration
advice 'integrate directly with LLM provider APIs instead', pushing a growing class of MCP servers
into owning a provider quota. 6) CORRECTED from the researcher: credit the TWO components the spec
actually mandates on servers -- 'Validate all tool inputs' and 'Rate limit tool invocations' are
server MUSTs. 'Log tool usage for audit purposes' is a CLIENT SHOULD, not a server MUST; do not
label the audit log GROUNDED on that basis.

**Verified sources**

- https://modelcontextprotocol.io/specification/2026-07-28/changelog
- https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
- https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://blog.cloudflare.com/remote-model-context-protocol-servers-mcp/

### mcp_tool_gateway

- **shape:** matches · **numbers:** no_public_figure

**What a reader would get wrong**

PROPORTION: DOWNGRADED from the researcher's 'misleading' to reasonable_simplification. I am
applying the grading rule the researcher's own prose already concedes: none of the defects they
found relocates the bottleneck. They wrote 'very little', 'this is the honest one of the four',
'second-order', and 'it does not move the bottleneck here' -- then labelled it misleading anyway.
The label was harsher than the analysis. I verified the engine block exactly: upstream = 840 against
7x150 = 0.8000; gw = 840+216+108 = 1,164 against 2x900 = 0.6467; 80.00 - 64.67 = 15.33 pts, matching
margin_pts to the digit. This is the only verdict in the set that carries real information: one
named component, a margin wide enough that plausible perturbations do not flip it. The attached
lesson -- 'The gateway is cheap; the fleet behind it is what you pay for and what saturates first'
-- is correct, matches how both real open-source gateways are built, and matches the spec's design
intent in letting a gateway route on headers without parsing bodies. The residual defects are real
but confined: (i) oauth_token at 9% is 108 token mints/s against 840 tool calls/s -- one new token
per 7.8 calls -- where OAuth 2.1 access tokens are cached client-side and presented on every request
('Note that authorization MUST be included in every HTTP request from client to server'), so minting
happens at authorization and refresh, not per call; this is two to three orders of magnitude high in
steady state and would mislead anyone sizing an authorization server, but removing it entirely only
moves gw from 64.67% to 58.7% and widens the margin. (ii) The archive is double-counted: tool_call
ends in archive(x0.15) AND audit_flush writes to it, while the assumption says flushes are batched
25:1. Audit events are 840+108 = 948/s, which at 25:1 is ~38/s and matches the 36/s flush flow well
-- but the x0.15 path adds another 126/s unbatched. x0.15 is 1-in-6.7, not 1-in-25. Archive sits at
162/5,500 = 2.9%, so it is immaterial to the verdict, but it is a defect that contradicts a stated
assumption. (iii) list_tools at 18% is defensible rather than wrong: 216 discovery calls/s with the
spec's 5-minute ttlMs implies ~64,800 clients each making one tool call every ~77 s, which is a
coherent if very large fleet -- it needs stating, not lowering. NUMBERS: no_public_figure confirmed.
I checked both real gateways myself: IBM ContextForge publishes 7,000+ tests but no throughput
metrics, and Docker's MCP Gateway documentation publishes none either. The entire verdict rests on
an unsourced 150 executions/s per upstream instance, so a reader should treat 'the tool fleet
saturates first' as a structural claim, not a measured one. There is also a live tension the
blueprint does not name: it has the gateway performing 'JSON-Schema validation of every tool
argument', which requires parsing the body -- the exact cost SEP-2243's mirrored headers were
introduced to let a gateway avoid. That is defensible as defence-in-depth, but it is the single
design choice the 900 rps encodes and the thing that would close the 15-point margin if heavier than
assumed.

**Fix**

1) Cut oauth_token drastically or restate it -- drop the share to ~0.1-0.5%, or relabel the flow as
per-request token VALIDATION (which the cache visit already covers). Also state explicitly that the
authorization server is assumed co-hosted with the gateway: the spec says it 'may be hosted with the
resource server or a separate entity', so this is a real choice being made silently. 2) Fix the
double-counted archive writes: the x0.15 tool_call tail and the batched audit_flush count the same
writes twice, and x0.15 contradicts the stated 25:1 batching. 3) Price the archive at S3's
documented PUT rate (3,500/s), not the GET rate (5,500/s) -- this tier carries an append-only write
workload. 4) Justify list_tools at 18% by stating the client population it implies (~65,000 clients
at the spec's 5-minute ttlMs), or lower it; note that a gateway is the single best place in the
topology to cache a merged manifest, and that servers SHOULD now return tools in deterministic order
precisely to enable that caching. 5) Add one sentence naming the gateway's real cost driver: body-
parsing JSON-Schema validation (now with $ref-resolution requirements per SEP-2106), and note that
SEP-2243's Mcp-Method/Mcp-Name headers let a gateway route and meter without it. That is the
decision the 900 rps actually encodes. 6) CORRECTED from the researcher: TWO components, not three,
are spec MUSTs -- servers MUST 'Validate all tool inputs' and 'Rate limit tool invocations'. 'Log
tool usage for audit purposes' is a CLIENT SHOULD. Promote the first two from ASSUMPTION to
GROUNDED; leave the audit log as a SHOULD-backed choice. The rest of the component set does map
closely onto ContextForge's published architecture (federation, Redis caching, PostgreSQL for
production, OpenTelemetry, admin UI) and Docker's -- say so.

**Verified sources**

- https://github.com/IBM/mcp-context-forge
- https://docs.docker.com/ai/mcp-gateway/
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
- https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html

### microservices

- **shape:** reasonable_simplification · **numbers:** implausible

**What a reader would get wrong**

THE BOTTLENECK ITSELF - a genuine wrong-component defect, not a simplification. The shape (gateway
-> independent services -> database-per-service -> Kafka, with a shared cache-aside Redis) is
standard and needs no defence. But the engine names the catalog service at 74.4% on a 7.73-point
margin, and that verdict is an artifact of ONE unjustified input: orderdb is given per_instance_rps
= 8,000, which is 2.7x the 3,000 given to the two READ-ONLY Postgres instances in the same file.
That is backwards - the write database is the slow one. It lets 1,824 rps against a single un-
sharded Postgres primary (1,440 order-creating transactions plus 384 status reads) read as 22.8%
utilised.  I verified the ceiling against the primary paper directly, extracting the PDF myself.
Verbitski et al., 'Amazon Aurora', SIGMOD 2017, Table 5 (Percona TPC-C variant, r3.8xlarge, 32 vCPU
/ 244 GB, EBS 30K provisioned IOPS), 500 connections / 10GB / 100 warehouses: MySQL 5.7 = 25,289
tpmC = 421 tx/s; Aurora = 73,955 tpmC = 1,233 tx/s. Table 2 (SysBench write-only, explicitly
labelled writes/sec, i.e. statements not transactions) gives MySQL 8,400/s at 1 GB falling to
1,500/s at 100 GB. So 1,824 rps is 4.3x a 32-vCPU single-node MySQL 5.7 and above even Aurora's
distributed-storage result; allowing a generous 3x for 2017->2026 hardware (~1,263/s) it is still at
or past the ceiling, not at a quarter of it. The paper's section 6.1.5 singles out hot-row
contention - exactly an inventory decrement on a popular SKU - as where single-node engines
collapse. Substitute a TPC-C-class 1,200 tps and the order database goes to 152% and becomes the
bottleneck by 77.6 points, with catalog a distant second. I reproduced every one of these figures.
Second: the 7.73-point margin is thinner than the uncertainty in any per_instance_rps in the file,
and `contenders` names only catalog when auth and orders are BOTH at exactly 66.67% - a tie the
engine should disclose.  Third, the mesh assumption worries about the wrong thing and the published
data inverts its emphasis. Istio's own 1.21 performance page measures the client+server proxy pair
adding 0.182 ms at p90 and 0.248 ms at p99 (1000 rps, 1 kB, mTLS on). Against this blueprint's 29.5
ms place-order base latency, a 5-6 hop mesh adds ~1.5 ms at p99, about 5% - immaterial. The 2019
Istio 1.2 figures everyone still quotes (+3 ms p50, +10 ms p99 at 16 connections, Mixer in the data
path, published 9 Jul 2019) are superseded and ~40x worse than current. The CPU tax is what could
actually move the verdict: Istio 1.21 documents ~0.5 vCPU per 1000 rps per sidecar plus ~50 MB;
Istio 1.24 documents ~0.20 vCPU and 60 MB (ztunnel 0.06 vCPU / 12 MB). NOTE - correcting the
researcher - the claim that this costs '-20% of app-tier capacity', taking catalog from 74.4% to
93.0%, is an ILLUSTRATIVE sensitivity, not a documented figure: the blueprint never states vCPU per
instance, so vCPU-per-1000-rps cannot be converted to a percentage without assuming instance size.
The direction is documented; the magnitude is not.  Fourth, PROPORTION. 12% of requests placing an
order fails two hard primary checks. Shopify Engineering, 21 Dec 2018: BFCM peak of 'nearly 11,000
orders created per minute and around 100,000 requests per second' - orders are 0.183% of requests.
Shopify Engineering, 20 Nov 2025: 2024 peak was 284M edge requests/min and 80M app-server
requests/min, and the 2025 scale test 'hit 146 million requests per minute and 80,000+ checkouts per
minute' - 0.055%. The file is 65x the 2018 ratio and 219x the 2025 one. Allowing definitional slack
between edge and app-server requests, the direction is unambiguous: sub-1%, not 12%. Correcting to
~1% happens to leave catalog unchanged at 74.4% (catalog sits on both browse and place-order at
x1.0, so the shares merely trade places) but drops auth to 52% and orders to 30% - the engine's
named verdict gets MORE robust while revealing the order tier is built for roughly 65x the real
order rate. Two large errors in opposite directions partially cancel and the reader is told neither.
Fifth: the gateway's 20,000 rps/instance is an assumption wearing a number's clothes. Envoy's own
benchmarking FAQ states 'There is no single QPS, latency or throughput overhead that can
characterize a network proxy such as Envoy' and 'never measure latency at max load'. Not load-
bearing here (gateway sits at 30%), but it should be labelled.

**Fix**

(1) Drop orderdb per_instance_rps from 8,000 to a write-realistic figure - 1,200-1,500 at most for a
single primary - citing Verbitski et al. SIGMOD 2017 Table 5, or model orders as sharded/partitioned
and say so. This is the one change that alters the answer, and it is the file's only real defect.
(2) Cut place-order share from 0.12 to ~0.01 and move the remainder to browse-catalog, citing
Shopify BFCM 2018 and 2025; then re-size the order tier, currently provisioned for ~65x the real
order rate. (3) Make the engine emit tied contenders whenever the margin is under ~10 points - auth
and orders at exactly 66.67% belong in the published `contenders` list, and a 7.73-point margin
should read 'catalog, auth and orders are within noise' rather than a single winner. (4) Rewrite the
mesh assumption around the published figures: the sidecar pair costs ~0.25 ms at p99 (immaterial on
a 29.5 ms path) but 0.20-0.5 vCPU per 1000 rps per proxy (material) - subtract it from per-instance
capacity rather than caveating latency, and state the instance vCPU size so the subtraction is
derivable rather than illustrative. Do not rely on the 2019 Istio 1.2 numbers; they are superseded
by ~40x. (5) Label the gateway's 20,000 rps/instance as unverifiable and cite Envoy's own FAQ
refusing to publish such a number.

**Verified sources**

- https://istio.io/v1.21/docs/ops/deployment/performance-and-scalability/ - opened; confirms verbatim 'two proxies add about 0.182 ms and 0.248 ms to the 90th and 99th percentile latency, respectively' at 1000 rps, 1 kB payload, HTTP/1.1, mutual TLS enabled, 2 proxy workers; and 'about 0.5 vCPU per 1000 requests per second' plus 'approximately 50 MB of memory'.
- https://istio.io/latest/docs/ops/deployment/performance-and-scalability/ - opened; this is Istio 1.24 and confirms verbatim 'a single sidecar proxy with 2 worker threads consumes about 0.20 vCPU and 60 MB of memory' at 1000 rps / 1 KB, waypoint 'about 0.25 vCPU and 60 MB', ztunnel 'about 0.06 vCPU and 12 MB'. Latency on this page is presented graphically, so the 0.182/0.248 ms figures correctly come from the v1.21 page instead.
- https://istio.io/latest/blog/2019/performance-best-practices/ - opened; published 9 Jul 2019 for Istio 1.2, confirms 'Istio adds 3 milliseconds per request in the 50th percentile' and '10 milliseconds in the 99th percentile' at 1000 RPS / 16 concurrent connections with Mixer enabled. Establishes that the widely-quoted figures are superseded and ~40x worse than current.
- https://www.envoyproxy.io/docs/envoy/latest/faq/performance/how_to_benchmark_envoy - opened; confirms verbatim 'There is no single QPS, latency or throughput overhead that can characterize a network proxy such as Envoy' and 'never measure latency at max load, this is not generally meaningful or reflecting of real system performance; aim to measure below the knee of the QPS-latency curve'.
- https://shopify.engineering/preparing-shopify-for-black-friday-cyber-monday - opened; published 21 Dec 2018, confirms verbatim 'nearly 11,000 orders created per minute and around 100,000 requests per second being served for extended periods during the weekend' (= 0.183% order-to-request ratio).
- https://shopify.engineering/bfcm-readiness-2025 - opened; published 20 Nov 2025, confirms '284 million requests per minute on edge' and '80 million on app servers' for the 2024 peak, and 'by the fourth test, we hit 146 million requests per minute and 80,000+ checkouts per minute' for the 2025 scale test (= 0.055%).
- https://web.stanford.edu/class/cs245/readings/aurora.pdf - WebFetch could not parse the PDF, so I extracted the text myself with pypdf. Confirms verbatim 'Table 5: Percona TPC-C Variant (tpmC) ... 500/10GB/100  73,955  6,093  25,289' (Aurora / MySQL 5.6 / MySQL 5.7); the instance spec 'r3.8xlarge EC2 instances with 32 vCPUs and 244GB of memory' on 'an EBS volume with 30K provisioned IOPS'; 'Table 2: SysBench Write-Only (writes/sec)' giving MySQL 8,400 at 1 GB and 1,500 at 100 GB (statements per second, not transactions); and section 6.1.5 'Throughput with hot row contention'.
- Own computation (scratchpad erl.py), not a web source: reproduced catalog 7,440 rps = 0.744, auth 6,000 rps = 0.66667, orders 2,400 rps = 0.66667, margin 7.733 pts, orderdb 1,824 rps = 0.228 at cap 8,000 and 1.52 at cap 1,200, gateway 0.30; corrected-mix (place-order 0.01, browse 0.61) leaves catalog at 0.744 while auth falls to 0.52 and orders to 0.30; the illustrative -20% capacity haircut yields catalog 0.930 and auth 0.8333; place-order base latency sums to 29.5 ms and 6 sidecar-pair hops at 0.248 ms = 1.49 ms = 5.0%.

### ml_pipeline

- **shape:** reasonable_simplification · **numbers:** implausible

**What a reader would get wrong**

ONE VERIFIED, DECISIVE DEFECT — and it is enough on its own. The engine names Kafka at 0.7760 with
margin_pts 0.0. I reproduced the tie exactly: q and stream both carry 11,640 rps against identical
15,000 capacities. The engine broke a dead heat, and it broke it toward the most wrong number in the
file. The Kafka row is 3 brokers x 5,000 msg/s. Confluent measured 605 MB/s across 3 i3en.2xlarge
brokers at 1 KB with RF=3 (~200k/broker, 2020). LinkedIn measured '2,024,032 records/sec' across 3
machines with 3x async replication at 100-byte messages (~675k/broker, 2014). 5,000 msg/s per broker
is 40x to 135x below both. That is not conservatism, it is wrong by two orders. Correct it to the
Confluent figure and Kafka's capacity becomes 600,000, dropping it to 0.0194 — about 2% utilisation.
The bottleneck then becomes the streaming transformer alone at 0.7760, with a real 2.6-point margin
over batch at 0.75. A user is currently told to buy brokers for a cluster that is 98% idle. This is
a confirmed bottleneck-relocating defect and it is why the numbers verdict stands at implausible.
TWO OF THE RESEARCHER'S THREE SHAPE CHARGES DID NOT SURVIVE — I am downgrading their 'misleading'
verdict to reasonable_simplification.  (a) The db(x0.08) fallback edge. The researcher claimed
Feast's docs are 'explicit' that an unmaterialised lookup 'returns null rather than falling
through'. I fetched the online-store page and searched it: the words null, miss, fallback and
offline do not appear on it at all. That sub-claim is unsupported and I dropped it. What the docs DO
say, verbatim, is that the offline store is used for 'Building training datasets from time-series
features' and 'Materializing (loading) features into an online store to serve those features at low-
latency', and that in the online store 'for each entity key, only the latest feature values are
stored. No historical values are stored.' That is architectural intent, not a prohibition — real
deployments do sometimes read through. More importantly, applying the reviewer's own test: with the
edge, db sits at 0.4875; without it, db = 60/8000 = 0.0075. Either way db never enters the contender
band. The edge does not move where a reader thinks their bottleneck is, so under L0 teaching-
reference rules it is a simplification worth a GAP, not a shape error.  (b) The Redis fan-out
charge. The researcher claimed true Redis load is 'plausibly 1-2.5M ops/s against a 100k capacity,
i.e. 10-25x over', citing Hopsworks' 50-250 features-per-request sweep. They missed that the
blueprint already addresses this explicitly: its cache assumption reads 'Feature vectors are large
values, so a node is modelled at 50k ops/s rather than the 100k a counter workload would give.' The
component is named 'Redis online feature store (hot vectors)' — one serialized vector per entity
key, which is how feature stores actually store them, giving a fan-out of 1, not 50. And redis.io
states directly that 'processing 10 bytes, 100 bytes, or 1000 bytes queries almost result in the
same throughput', which supports rather than undermines the 2x derate. The Hopsworks sweep is a
P99-LATENCY benchmark and does not establish one Redis operation per feature. This is an unresolved
storage-layout question deserving a GAP, not a verified 10-25x error, and I dropped the quantified
claim.  WHAT IS GENUINELY RIGHT: the component inventory matches published platforms. Chronon's
README confirms 'Managed pipelines for batch and realtime feature computation and updates to the
serving backend'. Uber's SIGMOD 2021 paper confirms the same Kafka -> Flink -> serving-store/HDFS
split at 'trillions of messages and petabytes of data per day', and names their 'Kappa+' approach.
The stream assumption is the most honest disclosure in the whole set — it says outright that
'training/serving skew and point-in-time correctness are CORRECTNESS properties this engine does not
model at all; it sizes the pipeline, it does not validate the features.' Chronon's existence proves
that point: its distinguishing feature is measuring exactly that skew, by passing logged online
fetch keys 'to a Join backfill... It then compares the backfilled values to actual fetched values to
measure consistency.' The batch assumption correctly flags that a real backfill is bursty and the
smoothed average is an artefact.  Secondary and unresolved: an 80:19.4 read:write split is write-
heavy for a feature store, but I found no primary source establishing the true ratio, so I am not
grading it. Once Kafka is fixed, 2,500 msg/s per transformer instance becomes the load-bearing
number and it too has no citation.

**Fix**

1. Raise the Kafka broker rate to a cited figure — ~200k msg/s per broker (Confluent 2020, 1 KB,
RF=3) or ~675k/broker (LinkedIn 2014, 100-byte, 3x async) — and re-run. This is the one change that
must happen. Expect the bottleneck to move to the streaming transformer at 0.7760 with a 2.6-point
margin over batch. 2. Then immediately check 2,500 msg/s per transformer instance, because it
becomes the load-bearing number and currently has no source. 3. Print the tie. q and stream match to
4 decimal places and margin_pts is 0.0 — that is the engine correctly saying it cannot distinguish.
The report should say 'TIE — two components at 0.776' rather than silently naming one. This bug is
shared with the other two files and should be fixed once in the report layer. 4. Keep the db(x0.08)
edge but attach a GAP, not a deletion: quote Feast's documented purposes for the offline store
(training-set construction and materialization into the online store) and note that the real failure
mode of an online-store miss is a degraded or null feature vector — a correctness incident — not
extra database load. Do not assert 'Feast returns null'; the cited page does not say that. 5. Add a
GAP on the Redis row stating the open question rather than a number: whether one lookup is one
operation on a serialized vector (fan-out 1, as modelled) or one operation per feature (fan-out
50-250, per the Hopsworks sweep) depends on storage layout, and the 50k/node derate only covers the
former.

**Verified sources**

- https://www.confluent.io/blog/kafka-fastest-messaging-system/ — published 2020-08-21. 605 MB/s peak stable throughput, 3 brokers (i3en.2xlarge), 1 KB messages, replication factor 3 => ~200k msg/s per broker.
- https://engineering.linkedin.com/kafka/benchmarking-apache-kafka-2-million-writes-second-three-cheap-machines — published 2014-04-27. Verified: '2,024,032 records/sec' (193.0 MB/sec), three machines, 100-byte messages, 3x asynchronous replication => ~675k msg/s per broker. Note: async replication and 100-byte messages make this the more favourable of the two benchmarks.
- https://docs.feast.dev/getting-started/components/offline-store — verified verbatim, the two documented purposes: 'Building training datasets from time-series features' and 'Materializing (loading) features into an online store to serve those features at low-latency in a production setting.' The page does NOT state that the offline store must not serve online.
- https://docs.feast.dev/getting-started/components/online-store — verified verbatim: 'for each entity key, only the latest feature values are stored. No historical values are stored'; populated by the materialize command and by push sources ('Features can also be written directly to the online store via push sources'). Searched explicitly: the words null, miss, fallback and offline do not appear on this page.
- https://github.com/airbnb/chronon — verified verbatim: 'Managed pipelines for batch and realtime feature computation and updates to the serving backend', and on consistency measurement: 'Chronon then passes the keys and timestamps to a Join backfill as the left side, asking the compute engine to backfill the feature values. It then compares the backfilled values to actual fetched values to measure consistency.' Stripe appears in the adopters list only.
- https://ar5iv.labs.arxiv.org/html/2104.00087 — Uber, 'Real-time Data Infrastructure at Uber', SIGMOD 2021. Verified verbatim: 'As of October 2020, trillions of messages and petabytes of such data were generated per day across all regions'; and on architecture choice: 'The Kappa+ architecture is able to reuse the stream processing logic just like Kappa architecture but it can directly read archived data from offline datasets such as Hive.'
- https://www.hopsworks.ai/post/feature-store-benchmark-comparison-hopsworks-and-feast — published 2023-12-22. VENDOR BENCHMARK (Hopsworks measuring itself against Feast) — declared as such, and cited only for its test parameters, not its win/loss claims. Verified verbatim: 'gradually increased the number of features in the vector from 50 to 250' and 'increased the batch size of feature vectors to read from 1 to 100'. Primary metric is P99 latency at a constant 10 RPS — it does not establish Redis operations per feature.
- https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/ — verified verbatim: 'processing 10 bytes, 100 bytes, or 1000 bytes queries almost result in the same throughput', which supports the blueprint's large-value derate rather than contradicting it. Measured 'SET: 180180.17 requests per second' unpipelined (3-byte payload, loopback).

### multi_agent_supervisor

- **shape:** matches · **numbers:** implausible

**What a reader would get wrong**

PROPORTION: misleading (confirmed). The engine names the right component and gives the best single
sentence in the set -- 'a PROVIDER QUOTA is not a fleet you own. Its concurrency is a contractual
number you buy, it can be changed by the provider, and it cannot be relieved by adding your own
instances.' The shape it sits on matches Anthropic's published orchestrator-worker architecture
closely, and I confirmed every structural element verbatim (lead agent coordinating specialized
subagents in parallel; the plan saved to Memory because 'if the context window exceeds 200,000
tokens it will be truncated'). I re-derived the engine block: llm = 66x3 + 9.6 = 207.6 against 4x67
= 0.7746; worker = 141.6 against 200 = 0.708; margin 6.66 pts. All exact. What misleads is the
MARGIN, not the identity. A reader sees 77.46% and concludes there is 23% headroom. On published
limits there is none, in three compounding ways. (a) Wrong limiter dimension: at 207.6 calls/s x
7,000 input tokens the design needs 87.2M ITPM against the published Scale ceiling of 10,000,000 --
8.7x over -- and 9.96M OTPM against 2,000,000 -- 5.0x over. Even RPM at 12,456 exceeds the 10,000
Scale ceiling, so the modelled '4 pools x 4,000 rpm' already requires a Custom-tier contract or
multiple accounts, and cannot be built from workspaces. (b) Understated fan-out: the blueprint
dispatches 2 subtasks and makes 3 model calls per run, against Anthropic's published 'the lead agent
spins up 3-5 subagents in parallel rather than serially', each of which is itself an agent loop
using '3+ tools in parallel'. CORRECTION TO THE RESEARCHER: their 'plausibly 10-30 calls' is their
own inference, not a published figure -- the citable anchors are the 3-5 subagents, the 3+ parallel
tools, and 'multi-agent systems use about 15x more tokens than chats'. The direction is solidly
grounded; the specific range is not. At even 3x the call volume the gateway passes 2.0 utilisation.
(c) A hidden second wall: status_poll is 35% of requests, 42 polls/s against 66 runs/s -- 0.64 polls
per run -- for runs Anthropic describes as taking minutes ('more work in minutes instead of hours').
A UI polling a 2-minute run every 2 s issues ~60 polls per run; with 66 runs/s starting and 120 s
runs, ~7,920 runs are in flight and polling runs at ~3,960 rps, ~94x the modelled figure, which by
itself puts the supervisor tier (capacity 300/s) at ~13x over. So the design has a second saturation
point the model never surfaces, and that one DOES relocate the bottleneck -- this is the finding
that makes the verdict misleading rather than merely optimistic. Separately, base_latency is badly
understated: 2,800 ms for 800 output tokens implies ~286 output tok/s, where Artificial Analysis
measures Claude Sonnet 5 at 74 tok/s -- 800/74 = 10.8 s of generation alone, 3.9x too small before
any TTFT, and the path takes three such calls. (I could not confirm the researcher's cited 1.33-2.02
s TTFT, so I restate this on generation time alone, which is sufficient.) The blueprint correctly
notes its serial sum is an upper bound for parallel fan-out, but that upper bound is computed on a
term ~4x too small, so the caveat does not rescue it. NUMBERS: implausible, confirmed.

**Fix**

1) Express the provider quota in ITPM/OTPM rather than RPM, citing Anthropic's published Scale tier
(10,000 RPM / 10,000,000 ITPM / 2,000,000 OTPM, per model, per organization). Then state the
consequence plainly: at 7,000 input tokens per call this design needs a Custom-tier contract, or
roughly an 89% prompt-cache hit rate -- and note that cache_read_input_tokens do not count toward
ITPM on most models, so caching is a CAPACITY lever here, not only a cost one. The existing cost
caveat has this exactly half-right. 2) Add the unstated constraint that 'pools' cannot be assembled
from workspaces inside one organization ('Organization-wide limits always apply, even if Workspace
limits add up to more'); they must be distinct models, providers, or accounts -- noting the spec
does allow the first, since 'Rate limits are applied separately for each model'. 3) Raise fan-out
toward Anthropic's published 3-5 subagents and give each subtask more than a single model call --
or, if minimal fan-out is deliberate for teaching, say so and quantify the multiple rather than
leaving 'real model-call volume is higher than shown' unquantified. The '15x more tokens than chats'
figure is the citable anchor. 4) Fix status_poll: either raise its share to match a minutes-long run
with a stated poll interval -- which will expose the supervisor tier as a second bottleneck, a
genuinely useful finding -- or change the design to push/SSE and say polling was rejected for
exactly this reason. 0.64 polls per multi-minute run is not a simplification, it is an inconsistency
with the blueprint's own description of the workload. 5) Add the supervisor's final synthesis model
call: the run path ends worker -> llm -> sup -> state, so the supervisor aggregates without ever
calling the model, whereas in the published architecture the lead agent synthesizes subagent
results. 6) Set llm base_latency to a measured full-response figure (~11-13 s for 800 output tokens
at 74 tok/s) or relabel it as TTFT and say so. 7) Keep what is right and label it GROUNDED against
the Anthropic engineering post (dated June 13 2025 -- the only published primary source for this
shape, and now ~15 months old): the orchestrator-worker shape, the durable resumable run state, the
shared scratchpad memory, modelling resume as a first-class flow, and the 7,000 input / 800 output
token split, which matches Anthropic's account of why agent prompts cost ~4x chat and is the most
defensible number in the file.

**Verified sources**

- https://www.anthropic.com/engineering/multi-agent-research-system
- https://platform.claude.com/docs/en/api/rate-limits
- https://developers.openai.com/api/docs/guides/rate-limits.md
- https://artificialanalysis.ai/providers/anthropic

### object_storage

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

WHERE THE BOTTLENECK IS — confirmed, on two independent grounds, each of which I recomputed myself.
I reproduce the engine exactly: api arrivals 49,000 (31,000 GET + 9,000 PUT + 7,500 HEAD/LIST +
1,500 DELETE) against 18x4,000 = 72,000 capacity = 68.06%; lb second at 49,000/80,000 = 61.25%;
margin 6.81 pts. Every other tier: data 41,000/72,000 = 56.9%, meta 11,500/24,000 = 47.9%, q 47.9%,
metarep 6,900/16,000 = 43.1%, gc 33.3%, metacache 23.8%.  (1) ERASURE-CODING WRITE FAN-OUT IS ABSENT
AND DOMINANT. The blueprint's own `data` assumption states it: "one client PUT becomes 11 fragment
writes across failure domains. The engine counts the client operation once, so internal write
amplification on the data plane is NOT reflected here." Warfield (allthingsdistributed, 27 Jul 2023
— note the post is dated the 27th, not the 24th) confirms the mechanism verbatim: "we use an
algorithm, such as Reed-Solomon, and split our object into a set of k 'identity' shards. Then we
generate an additional set of m parity shards." f4 (OSDI'14) confirms the asymmetry that stops it
cancelling out: "Normal-case reads are redirected to the appropriate storage node (R2) that then
reads the BLOB directly from its enclosing data block (R3). Failure-case reads use the Data API to
read companion and parity blocks" — so the modelled get_object -> data(x1.0) is RIGHT and only the
write side fans out.  I recomputed the counterfactual rather than taking the researcher's figure.
put_object -> data(x11) gives data = 31,000 + 99,000 + 1,000 = 131,000/72,000 = 181.9%, not the
195.8% reported (see dropped_claims). A mild 4+2 code gives 86,000/72,000 = 119.4%, which I
reproduce exactly. So under every variant the data plane is OVER CAPACITY and clears the API tier by
51 to 114 points. The engine's verdict survives only because the largest term in the system is
missing from the model. This is the defect: a reader sizes API front-end instances while the data
plane sits at ~1.8x capacity.  (2) LIST IS BUNDLED WITH HEAD BEHIND A CACHE THAT CANNOT SERVE IT.
Vogels (Apr 2021) confirms the metadata subsystem "is on the data path for GET, PUT, and DELETE
requests, and is responsible for handling LIST and HEAD requests" — but an object-keyed cache
serving a 70% hit rate on a paginated range scan is a modelling error, not a simplification. Routing
head_or_list to metarep at x1.0 gives 4,650 + 7,500 = 12,150/16,000 = 75.9%, above the API tier at
68.06%. I verified this arithmetic. (The reasoning that a point-lookup cache cannot serve a range
scan is sound engineering inference, not a sourced claim — no primary source describes S3's metadata
cache internals at that granularity.)  (3) THE BLUEPRINT OVERCLAIMS ON EVEN SHARDING. It says the
divide-arrivals-across-instances model "is the correct shape for once." AWS publishes the real wall
verbatim: "at least 3,500 PUT/COPY/POST/DELETE or 5,500 GET/HEAD requests per second per partitioned
Amazon S3 prefix" and "While Amazon S3 is scaling to your new higher request rate, you may see some
503 (Slow Down) errors." That ceiling is per-prefix on the index and is invisible to an even-split
model. The aggregate-capacity shape is fine; the claim of correctness is what overreaches.  (4)
SMALLER, VERIFIED: 2 metadata read replicas cannot cover 3 independent shards — an internal
inconsistency in the blueprint's own numbers.  (5) LATENCY, HONESTLY LABELLED NOT MISLEADING:
modelled GET is ~31 ms (lb 1 + api 4 + metacache 0.4 + metarep 0.15x5 + data 25). AWS publishes
"consistent small object latencies (and first-byte-out latencies for larger objects) of roughly
100–200 milliseconds." In-datacenter 31 ms is defensible for a self-built store; the risk is only
that a reader quotes it as an S3 figure.  Shape confirmed as a reasonable simplification: api ->
metacache -> meta/metarep -> data genuinely mirrors Vogels' "persistence tier that stores metadata"
plus "a caching technology" plus the witness read barrier. Numbers confirmed plausible: no public
per-node S3 figure exists, and 6,000 ops/s per data node is consistent with Warfield's ~120
IOPS/disk and f4's 80 IOPS per 4TB disk once a node is understood as tens of disks. The 62/18/15/3
mix cannot be graded — no source publishes an aggregate S3 request mix, and saying so is the right
answer.

**Fix**

1. Put the fan-out you already disclose into the model: put_object -> data(xK), K = k+m. At 8+3 the
data plane reaches ~182% and the instance count must rise several-fold; at 4+2, ~119%. Keep the
prose note, but a verdict computed without the dominant term is computed on a fiction. 2. Split
head_or_list into `head` (point lookup, metacache-servable) and `list` (range scan, metacache x0,
metarep x1.0), and state the pagination assumption (keys per call). 3. Raise metarep to >= 3 (one
per shard) or state that the replicas are pooled across shards — 2 cannot cover 3. 4. Replace "the
correct shape for once" with the same skew caveat the kv_store blueprint already carries, and cite
AWS's published per-prefix ceiling (3,500 write / 5,500 read, 503 Slow Down) as the figure an even-
split model structurally cannot reproduce. 5. Add one line comparing the modelled ~31 ms GET with
AWS's published 100–200 ms for S3 Standard, so the number is not quoted as an S3 figure. 6.
Optional: drop or requalify the "read replicas" name — S3's metadata path has been strongly
consistent since Dec 2020 via the witness read barrier — but this is a naming preference, not a
defect (see dropped_claims).

**Verified sources**

- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html
- https://www.allthingsdistributed.com/2021/04/s3-strong-consistency.html
- https://www.allthingsdistributed.com/2023/07/building-and-operating-a-pretty-big-storage-system.html
- https://www.usenix.org/system/files/conference/osdi14/osdi14-paper-muralidhar.pdf
- https://aws.amazon.com/blogs/aws/amazon-s3s-15th-birthday-it-is-still-day-1-after-5475-days-100-trillion-objects/
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/directory-bucket-high-performance.html

### paste_bin

- **shape:** reasonable_simplification · **numbers:** plausible

**What a reader would get wrong**

I recomputed the engine and it is correct for the model as drawn: app 1,200 / 1,600 = 75.00%, db
8.60%, store 5.13%, cache 2.70%, lb 4.00% — margin 66.4 pts, and the ranking is robust to any
plausible read:write mix because every flow passes lb -> app at x1.0, so the app sees all 1,200 rps
regardless. I am DOWNGRADING the researcher's 'misleading' on shape. The missing edge tier is a real
omission, but adding one would only lower the app's utilisation — nothing else overtakes it — so a
reader is not mis-diagnosing which component binds; they are over-provisioning a component that
genuinely binds. That is an efficiency error at L0, not a bottleneck error. The omission is still
worth naming and is not trivial: a write-once-read-many public snippet host with immutable, public
bodies is the most CDN-cacheable workload in this corpus, and I verified myself (2026-09-12) that
the real pastebin.com returns `server: cloudflare` with `cf-cache-status: DYNAMIC`. What makes the
silence uncomfortable rather than merely simplifying is the asymmetry: the blueprint's assumptions
go out of their way to argue AGAINST a DB replica ('a replica would be cost without benefit') while
never mentioning the one component the real system actually has — and the sibling blog_platform.json
in the same corpus DOES model a CDN, so this is not a corpus-wide convention. TWO CONCRETE DEFECTS I
CONFIRMED IN THE FILE: (a) raw_download is routed lb -> app -> store at x1.0 with NO cache hop at
all, so the most cacheable object in the system — an immutable raw body — is modelled as always
missing, while rendered HTML views get an 85% hit rate. That is backwards. (b) the object store's
base_latency_ms of 20 sits 5-10x below AWS's only published figure: 'consistent small object
latencies ... of roughly 100-200 milliseconds'. It is defensible as a warm in-region connection but
it is currently bare, and it is exactly the number that would otherwise push a reader toward a
higher hit rate or an edge tier. PROPORTION: correctly 'no public figure' — no pastebin operator
publishes a read:write ratio, request rate, or cache hit rate. But raw_download at 2% is very likely
low: Pastebin's own scraping documentation gates automated access behind PRO membership plus IP
whitelisting, warns 'Your IP will most likely get blocked to prevent unnecessary load on our
servers', advises 'not making more than 1 request per second', and states 'Do not scrape /raw/*
pages, as you will get blocked'. You do not build that much machinery around 2% of your traffic.

**Fix**

1) Either add an edge/CDN tier in front, or — if it is deliberately excluded to teach origin sizing
— say so in an explicit assumption and state what it would remove, citing that the real pastebin.com
serves from Cloudflare (`server: cloudflare`, verified 2026-09-12). Right now the absence is silent,
and silence is what turns a simplification into a wrong lesson. 2) Route raw_download through the
cache rather than straight to the store, and raise its share, citing Pastebin's own scraping
documentation as operator evidence that automated /raw/* traffic is material enough to rate-limit to
1 req/s, gate behind PRO + IP whitelisting, and block outright. 3) Do not leave base_latency_ms 20.0
on the object store bare: either raise it toward AWS's published 100-200 ms for small objects, or
add an assumption stating that 20 ms models a warm in-region connection and sits BELOW the only
published figure. 4) Qualify the app's 800 rps/instance with the runtime it assumes — on 2 vCPU that
is comfortable for a compiled handler and optimistic for an interpreted one, and the blueprint's own
justification ('little more than a cache lookup and a template') only holds for the former. KEEP AS
IS: the object store's 5,500 rps is EXACTLY AWS's published 'at least 3,500 PUT/COPY/POST/DELETE or
5,500 GET/HEAD requests per second per partitioned Amazon S3 prefix' — relabel it GROUNDED with that
citation instead of ASSUMPTION. The metadata-in-Postgres / bodies-in-object-storage split is
genuinely sound against the documented primitives, and the reasoning for skipping the replica
(primary at ~260 rps, ~9%, which I confirmed at 8.6%) is correct and well argued.

**Verified sources**

- https://pastebin.com/doc_scraping_api
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html
- https://pastebin.com/

### serverless_api

- **shape:** matches · **numbers:** implausible

**What a reader would get wrong**

THIS IS THE ONLY REAL DEFECT IN THE THREE, AND IT FLIPS THE BOTTLENECK. I confirmed it two
independent ways. FIRST, INTERNALLY, WITHOUT ANY SOURCE: the function tier declares base_latency_ms
25.0 AND per_instance_rps 500 in the same component. One execution environment at 25 ms serves
1/0.025 = 40 rps, not 500; per_instance_rps 500 implies a 2 ms function. The file contradicts
itself. SECOND, AGAINST AWS'S OWN PUBLISHED ARITHMETIC: Lambda documents the formula outright —
'Concurrency = (average requests per second) * (average request duration in seconds)' — so 1,500 rps
at 25 ms needs 1,500 x 0.025 = 37.5 concurrent execution environments, not the 4 modelled. The
blueprint is 9.4x under its own latency figure. It also inverts the quota in the other direction:
AWS states 'At both the account level and the function level, Lambda also enforces a requests per
second limit of equal to 10 times the corresponding concurrency quota', so a function pinned to 4
units of reserved concurrency is capped at 40 rps — making the blueprint's '4 units x ~500 req/s' a
50x overstatement. This backwards claim is stated as the file's central modelling insight ('the
CONCURRENCY CEILING ... is the shape that actually constrains a Lambda-style API'), which is the
worst possible place for it. I RECOMPUTED THE RANKING WITH AWS'S REAL NUMBERS AND IT REVERSES. The
engine currently reports fn at 1,500/2,000 = 75.00% and apigw at 1,500/10,000 = 15.00%, margin 60.0
pts. Corrected: the function tier needs ~37.5 of a default 1,000 per-Region account concurrency =
3.75% utilised, against a service AWS scales at 'a rate of 1,000 concurrent executions every 10
seconds' per function (a documented 12x increase announced 2023-12-06). The API Gateway sits at 15%
of a HARD, ACCOUNT-WIDE, CROSS-API quota — AWS's table reads '10,000 requests per second (RPS) ...
per account, per Region across HTTP APIs, REST APIs, WebSocket APIs, and WebSocket callback APIs'.
So the tier the blueprint reports as comfortable headroom is the one with a real non-elastic
ceiling, and the tier it names as the bottleneck is the one AWS elastically scales for you. A
learner shards functions and tunes memory when the actual ticket is a Service Quotas increase.
REGION-SPECIFIC AND DIRECTLY RELEVANT TO AN AFRICA-BASED DEPLOYMENT: I confirmed the footnote
verbatim — 'For the following Regions, the default throttle quota is 2500 RPS and the default burst
quota is 1250 RPS: Africa (Cape Town), Europe (Milan), Asia Pacific (Jakarta), Middle East (UAE),
Asia Pacific (Hyderabad), Asia Pacific (Melbourne), Europe (Spain), Europe (Zurich), Israel (Tel
Aviv), Canada West (Calgary), Asia Pacific (Malaysia), Asia Pacific (Thailand), and Mexico
(Central).' In af-south-1, 1,500 rps peak is 60% of a hard quota shared with every other API in the
account. That is a pre-launch blocker the blueprint does not mention at all. PRICING: the $3.00/M
gateway rate matches NEITHER published price. I recomputed 777.6M requests at AWS's published rates:
REST at $3.50/M = $2,722/mo; HTTP API at the tiering shown in AWS's own worked example ($1.00/M then
$0.90/M) = $730/mo. The blueprint's $3.00/M gives $2,333. CREDIT WHERE DUE: the qualitative
conclusion — gateway dominates compute — SURVIVES either choice, because published Lambda on-demand
for this workload (777.6M invocations, 25 ms, 512 MB) is $155.52 requests + $162.00 duration =
~$318/mo. Only the magnitude is a pricing-tier choice the blueprint never names. The cold-start
disclosure is honest and good practice, but it does not cover this defect: the failure is in the
modelled warm-path capacity itself, not in the unmodelled tail.

**Fix**

1) Re-derive the function tier from AWS's own formula instead of asserting a concurrency ceiling: at
1,500 rps and 25 ms set instances: 38 and per_instance_rps: 40 (= 1/0.025 s), and state the real
ceiling as the documented account limit of 1,000 concurrency / 10,000 rps with a per-function
scaling rate of 1,000 execution environments every 10 seconds. The tier then reads ~4% utilised,
which is the truth, and the assumption text stops teaching the inverse of AWS's arithmetic. 2) Model
the constraint that actually binds: carry the API Gateway account throttle explicitly (10,000 rps
default; 2,500 rps in Africa (Cape Town) and the twelve other listed Regions) and make the headline
region-dependent. For any Africa-region deployment this is a launch gate, not a footnote. 3) Fix the
rate and name the API type: $3.50/M (REST) or $1.00/M then $0.90/M (HTTP API), not $3.00/M — the
gateway line is $2,722/mo or $730/mo depending on that single choice, and a 2026 serverless REST API
would very likely pick HTTP APIs. 4) Replace the hand-wave 'treat the compute line as an upper
bound' with the computable published figure: Lambda on-demand for this workload is ~$318/mo ($0.20
per 1M requests + $0.0000166667 per GB-s, x86). State whether that is above or below the provisioned
catalogue rather than asserting a direction. 5) Keep the cold-start disclosure but attach AWS's own
numbers — 'Cold starts typically occur in under 1% of invocations. The duration of a cold start
varies from under 100 ms to over 1 second.' — so the reader sees it is a tail-latency story, not a
capacity one, and that 25 ms is a warm-path figure. 6) For the item store, cite the limit that
actually bites: DynamoDB documents that 'throttling will occur if a single partition receives more
than 3000 read operation or more than 1000 write operations', with adaptive capacity lifting a hot
key only to 'the partition maximum of 3,000 RCUs and 1,000 WCUs' and burst retaining 'up to five
minutes (300 seconds) of unused read and write capacity'. A flat 5,000 rps hides that DynamoDB
throttles on key distribution, not table-wide rps; this design's write path is safe only if keys
spread. KEEP AS IS: the gateway's 10,000 per_instance_rps is EXACTLY AWS's published default account
quota and the object store's 5,500 is exactly AWS's published S3 per-prefix GET/HEAD figure —
relabel both GROUNDED; and the explicit honesty about the engine lacking serverless and key-value
component kinds is exemplary and should stay.

**Verified sources**

- https://docs.aws.amazon.com/apigateway/latest/developerguide/limits.html
- https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html
- https://docs.aws.amazon.com/lambda/latest/dg/scaling-behavior.html
- https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html
- https://aws.amazon.com/lambda/pricing/
- https://aws.amazon.com/api-gateway/pricing/
- https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/burst-adaptive-capacity.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html
- https://aws.amazon.com/about-aws/whats-new/2023/12/aws-lambda-functions-scale-up/
