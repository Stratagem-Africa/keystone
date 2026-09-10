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
