import os
import re
import sys
import json
import time
import math
import random
import asyncio
import hashlib
import networkx as nx
from typing import Dict, Any, List, Optional, Set
from pathlib import Path

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field

SERVER_DIR = Path(__file__).resolve().parent
WASP_LAB_DIR = SERVER_DIR.parent
WEB_DIR = WASP_LAB_DIR / "web"
ROOT_DIR = WASP_LAB_DIR.parent

# anti-GAN content authenticity detector lives in gan_lab/, a sibling of
# wasp_lab/ -- not an installed package, so it needs its directory on the
# path. Import is optional: the engine falls back gracefully (scan endpoint
# returns a clear error) if the detector was never trained.
sys.path.insert(0, str(ROOT_DIR / "gan_lab"))
try:
    import anti_gan_infer
    ANTI_GAN_AVAILABLE = anti_gan_infer.is_available()
except ImportError:
    anti_gan_infer = None
    ANTI_GAN_AVAILABLE = False

# Real content catalog: drop folders like `server/content/cats/`,
# `server/content/dogs/` next to this file and a producer whose category
# matches a folder name serves those actual filenames as content names
# (e.g. "/cats/cat_image17.jpg") instead of a synthetic placeholder.
# Ported from the NetworkCaching-backend lab (KavyaN025/NetworkCaching-backend).
CONTENT_ROOT = os.environ.get("WASP_CONTENT_ROOT", str(SERVER_DIR / "content"))
CONTENT_ITEMS_PER_CATEGORY = 15  # fallback item count when a category has no real folder
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_IGNORED_DIR_NAMES = {"__pycache__", "venv", ".venv", "env", "node_modules", ".git"}


def discover_content_folders(root=CONTENT_ROOT):
    """Scan `root` for subdirectories containing image files and return
    {folder_name: [sorted file names]}, e.g. {"cats": [...], "dogs": [...]}."""
    found = {}
    if not os.path.isdir(root):
        return found
    for entry in sorted(os.listdir(root)):
        full_path = os.path.join(root, entry)
        if not os.path.isdir(full_path):
            continue
        if entry.startswith(".") or entry in _IGNORED_DIR_NAMES:
            continue
        files = sorted(
            f for f in os.listdir(full_path)
            if os.path.isfile(os.path.join(full_path, f))
            and os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
        )
        if files:
            found[entry] = files
    return found


def build_content_pool(categories, real_folders=None):
    """One content list per publisher category. A category matching a real
    folder (e.g. "cats" -> content/cats/*.jpg) gets the actual filenames
    (e.g. "/cats/fluffy.jpg"); otherwise it falls back to synthetic names
    (e.g. "/publisher-3/item7.dat")."""
    real_folders = real_folders or {}
    pool = {}
    for cat in categories:
        files = real_folders.get(cat)
        if files:
            pool[cat] = [f"/{cat}/{fname}" for fname in files]
        else:
            pool[cat] = [f"/{cat}/item{i + 1}.dat" for i in range(CONTENT_ITEMS_PER_CATEGORY)]
    return pool



class ScenarioConfig(BaseModel):
    scenario: str = "FULL_WASP"
    seed: int = 42
    real_time_factor: float = 0.2
    duration: float = 60.0

class NetworkInit(BaseModel):
    num_routers: int = 3
    num_consumers: int = 3
    num_producers: int = 2  # default to 2 so both real content folders (cats/dogs) are used
    pattern: str = "linear" # "linear" or "mesh"
    link_latency_ms: float = 10.0
    cs_capacity: int = 100
    scenario: str = "FULL_WASP"

# The four schemes compared in the paper (Lal & Malani, Fig. 3-4):
# A=NORMAL (no adversary), C=ATTACK (unshielded), B=STATIC_CRYPTO (fixed-key,
# non-adaptive), D=WASP (full adaptive Shield+Crypto pipeline).
SCHEMES = ["NORMAL", "ATTACK", "STATIC_CRYPTO", "WASP"]

class SchemeConfig(BaseModel):
    scheme: str = "WASP"

class InjectConfig(BaseModel):
    consumer_id: str = "s0"
    name: str = "/cats/cat_image1.jpg"

class AttackerTarget(BaseModel):
    target: str

class PoisonConfig(BaseModel):
    router_id: str
    category: Optional[str] = None       # used to auto-pick targets when target_names is omitted
    target_names: Optional[List[str]] = None  # explicit real content names to substitute fake content under
    count: int = 3                       # how many names to auto-pick if target_names is omitted
    source_dir: Optional[str] = None     # defaults to gan_lab/server/content/fake_<GAN_SOURCE_MODEL>

class ScanConfig(BaseModel):
    router_id: str
    mitigate: Optional[bool] = None      # None = use engine-wide default

class MitigationConfig(BaseModel):
    enabled: bool

class WaspParams(BaseModel):
    router_id: Optional[str] = "all"
    alpha: float = 0.40
    beta: float = 0.20
    gamma: float = 0.20
    delta: float = 0.20
    kappa: float = 8.0
    tau: float = 0.50
    tau_1: float = 0.50
    tau_2: float = 0.65
    eta_1: float = 0.40
    eta_2: float = 0.70
    delta_min_ms: float = 5.0
    delta_max_ms: float = 50.0
    K_min: int = 128
    K_max: int = 256
    T_b: float = 0.05
    rho: float = 1.5

class AblationConfig(BaseModel):
    name_obfuscation: bool = True
    timing_decorrelation: bool = True
    routing_diversity: bool = True

class ReseedConfig(BaseModel):
    traffic_seed: int = 42
    wasp_seed: int = 1337

class TrafficConfig(BaseModel):
    zipf_alpha: float = 1.2
    catalog_size: int = 1000
    mean_inter_arrival_ms: float = 50.0
    watchlist_size: int = 20
    obs_router: Optional[str] = "r1"
    confidence_prior: Optional[float] = 0.10


# Simulation Engine
class SimulationEngine:
    def __init__(self):
        # Configuration
        self.config = {
            "topology": {
                "n_subscribers": 3,
                "n_routers": 3,
                "n_producers": 2,
                "pattern": "linear",
                "link_latency_ms": 10.0,
                "cs_capacity": 100
            },
            "traffic": {
                "catalog_size": 1000,
                "zipf_alpha": 1.2,
                "mean_inter_arrival_ms": 50.0,
                "watchlist_size": 20,
                "duration_s": 60.0
            },
            "wasp": {
                "W": 50,
                "tau_1": 0.50,
                "tau_2": 0.65,
                "eta_1": 0.40,
                "eta_2": 0.70,
                "kappa": 8.0,
                "tau": 0.50,
                "weights": {"alpha": 0.40, "beta": 0.20, "gamma": 0.20, "delta": 0.20},
                "K_min": 128,
                "K_max": 256,
                "T_b": 0.05,
                "delta_min_ms": 5.0,
                "delta_max_ms": 50.0,
                "rho": 1.5,
                "omega": [0.5, 0.3, 0.2]
            },
            "attacker": {
                "observation_routers": ["r1"],
                "confidence_prior": 0.10
            },
            "seeds": {
                "traffic": 42,
                "wasp": 1337
            },
            "ablation": {
                "name_obfuscation": True,
                "timing_decorrelation": True,
                "routing_diversity": True
            },
            "static_crypto": {
                "key_size": 256,
                "suppression": 0.5
            },
            "anti_gan": {
                "mitigation_enabled": False,
                "threshold": 0.5
            }
        }

        # Simulation state
        self.status = "STOPPED"
        self.sim_time = 0.0
        self.scheme = "WASP"  # "NORMAL", "ATTACK", "STATIC_CRYPTO", "WASP"
        self.packet_counter = 0

        # PRNGs
        self.rng_traffic = np.random.default_rng(42)

        # Topology and Nodes (also builds self.content_pool and self.watchlist
        # from the real/synthetic content catalog -- must run before the
        # watchlist-dependent posteriors are initialized below)
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, str]] = []
        self.watchlist: Set[str] = set()
        self.init_topology()

        # Attacker Bayesian Posteriors per scheme: scheme -> name -> [alpha, beta]
        self.posteriors: Dict[str, Dict[str, List[float]]] = {}
        self.reset_posteriors()

        # Sliding window history for Traffic Monitoring
        self.window_history: List[Dict[str, Any]] = []

        # In-flight packets
        self.active_packets: List[Dict[str, Any]] = []

        # Trace log (bounded)
        self.trace_log: List[Dict[str, Any]] = []

        # Content Poisoning Attack event log (see poison_cache())
        self.poison_log: List[Dict[str, Any]] = []

        # Anti-GAN authenticity scan event log (see scan_router_cache())
        self.scan_log: List[Dict[str, Any]] = []

        # Historical metrics for time-series charts
        self.metrics_history: List[Dict[str, Any]] = []

        # Paper reference constants for UI display
        self.paper_reference = {
            "attacker_confidence_unshielded": 0.85,
            "attacker_confidence_wasp": 0.18,
            "pdr_wasp": 0.94,
            "pdr_static_crypto": 0.87,
            "chr": 0.35,
            "latency_hit_ms": 5.0,
            "latency_miss_ms": 28.0,
            "shielding_overhead": 0.12,
            "crypto_overhead": 0.08
        }

    def reset_posteriors(self):
        prior = self.config["attacker"]["confidence_prior"]
        self.posteriors = {scheme: {} for scheme in SCHEMES}
        for scheme in SCHEMES:
            for name in self.watchlist:
                self.posteriors[scheme][name] = [prior * 10.0, (1.0 - prior) * 10.0]

    def init_topology(self):
        """Builds the router interconnect, subscriber/publisher attachment,
        per-category FIB, and content catalog. Topology generator, FIB, and
        content discovery ported from NetworkCaching-backend
        (KavyaN025/NetworkCaching-backend): a random connected mesh of
        routers via networkx, one publisher per content category, and a
        BFS shortest-path-tree FIB per category -- instead of WASP's
        original single-producer, name-agnostic chain."""
        # Seed the global random module from the traffic seed so identical
        # topology configs (same counts/pattern + same seed) reproduce the
        # same mesh/attachments -- otherwise /network/init and /reseed with
        # the same seed would silently give a different topology each call.
        random.seed(self.config["seeds"]["traffic"])

        top_cfg = self.config["topology"]
        n_subs = top_cfg["n_subscribers"]
        n_routers = max(1, top_cfg["n_routers"])
        n_prods = max(1, top_cfg["n_producers"])
        pattern = top_cfg.get("pattern", "linear")

        self.nodes = {}
        self.edges = []
        router_ids = [f"r{i}" for i in range(n_routers)]

        # Router interconnect: random connected mesh, or a simple chain.
        graph = nx.Graph()
        graph.add_nodes_from(router_ids)
        if pattern == "mesh" and n_routers >= 2:
            for i in range(1, n_routers):
                j = random.randint(0, i - 1)
                graph.add_edge(router_ids[j], router_ids[i])
            extra_target = max(0, round(n_routers * 0.45))
            added, attempts = 0, 0
            while added < extra_target and attempts < extra_target * 12 and n_routers > 2:
                attempts += 1
                a, b = random.sample(router_ids, 2)
                if not graph.has_edge(a, b):
                    graph.add_edge(a, b)
                    added += 1
        else:  # linear chain
            for i in range(n_routers - 1):
                graph.add_edge(router_ids[i], router_ids[i + 1])
        self.graph = graph

        # Router nodes
        obs_routers = self.config["attacker"]["observation_routers"]
        for rid in router_ids:
            self.nodes[rid] = {
                "id": rid,
                "type": "router",
                "status": "ONLINE",
                "wasp_enabled": self.scheme in ("STATIC_CRYPTO", "WASP"),
                "is_compromised": rid in obs_routers,
                "pit": [],
                "cs": [],
                "fib": [],
                "cache_hits": 0,
                "cache_misses": 0,
                "neighbors": []
            }

        # Subscribers: attached to a router. A mesh spreads them across
        # random routers; a linear chain keeps the simple "all start at r0"
        # picture.
        self.subscribers = []
        for i in range(n_subs):
            sid = f"s{i}"
            attach = random.choice(router_ids) if pattern == "mesh" else router_ids[0]
            self.nodes[sid] = {"id": sid, "type": "subscriber", "status": "ONLINE", "router": attach, "neighbors": []}
            self.subscribers.append(sid)

        # Publishers: one real content folder (server/content/cats,
        # server/content/dogs, ...) per publisher where available, else a
        # synthetic category -- always works, real folders or not.
        real_folders = discover_content_folders()
        real_names = sorted(real_folders.keys())
        categories = [real_names[i] if i < len(real_names) else f"publisher-{i + 1}" for i in range(n_prods)]

        self.publishers = []
        self.category_publisher = {}
        for i, cat in enumerate(categories):
            pid = f"p{i}"
            attach = random.choice(router_ids) if pattern == "mesh" else router_ids[-1]
            label = f"Publisher · {cat}" if cat in real_folders else f"Publisher {i + 1}"
            self.nodes[pid] = {
                "id": pid,
                "type": "producer",
                "status": "ONLINE",
                "category": cat,
                "label": label,
                "router": attach,
                "neighbors": []
            }
            self.publishers.append(pid)
            self.category_publisher[cat] = pid

        self.content_pool = build_content_pool(categories, real_folders)

        # Links: router interconnect + subscriber/publisher access links
        def add_link(u, v):
            self.edges.append({"src": u, "dst": v})
            if v not in self.nodes[u]["neighbors"]:
                self.nodes[u]["neighbors"].append(v)
            if u not in self.nodes[v]["neighbors"]:
                self.nodes[v]["neighbors"].append(u)

        for a, b in graph.edges():
            add_link(a, b)
        for sid in self.subscribers:
            add_link(sid, self.nodes[sid]["router"])
        for pid in self.publishers:
            add_link(pid, self.nodes[pid]["router"])

        # Per-category FIB: BFS shortest-path tree rooted at each publisher's
        # router. Every other router's entry for that category is simply its
        # parent in the tree -- the neighbor to forward toward.
        self.fib = {rid: {} for rid in router_ids}
        for pid in self.publishers:
            pub = self.nodes[pid]
            root, cat = pub["router"], pub["category"]
            paths = nx.single_source_shortest_path(graph, root)
            for rid in router_ids:
                if rid == root:
                    self.fib[rid][cat] = "local"
                else:
                    path = paths.get(rid)
                    self.fib[rid][cat] = path[-2] if path and len(path) > 1 else None

        for rid in router_ids:
            self.nodes[rid]["fib"] = [
                {"prefix": f"/{cat}/*", "face": nxt, "cost": 1.0}
                for cat, nxt in self.fib[rid].items() if nxt and nxt != "local"
            ]

        self.rebuild_watchlist()

    def rebuild_watchlist(self):
        """(Re)builds self.watchlist from the current content_pool using the
        configured watchlist_size, split evenly across categories -- a
        sensitive SUBSET of the catalog, matching the paper's
        watchlist-attack premise. Callable on its own (e.g. after a traffic
        config change) without regenerating the rest of the topology."""
        watchlist_size = self.config["traffic"].get("watchlist_size", 20)
        categories = list(self.content_pool.keys())
        per_category = max(1, watchlist_size // max(1, len(categories)))
        self.watchlist = set()
        for cat in categories:
            pool = self.content_pool[cat]
            self.watchlist.update(pool[:min(per_category, len(pool))])

    def route(self, start_router, category):
        """FIB-driven path from start_router to the category's publisher's
        router, one hop at a time. Ported from NetworkCaching-backend's
        Network.route()."""
        path = [start_router]
        current = start_router
        seen = {current}
        while self.fib.get(current, {}).get(category) not in (None, "local"):
            nxt = self.fib[current][category]
            if nxt is None or nxt in seen:
                break
            path.append(nxt)
            seen.add(nxt)
            current = nxt
        return path

    def reseed(self, seed_traffic: int, seed_wasp: int):
        self.config["seeds"]["traffic"] = seed_traffic
        self.config["seeds"]["wasp"] = seed_wasp
        self.rng_traffic = np.random.default_rng(seed_traffic)
        self.reset_posteriors()

    def apply_scheme(self, scheme: str):
        scheme = scheme.upper()
        if scheme not in SCHEMES:
            return
        self.scheme = scheme
        wasp_enabled = scheme in ("STATIC_CRYPTO", "WASP")
        for node in self.nodes.values():
            if node["type"] == "router":
                node["wasp_enabled"] = wasp_enabled

    def reset_simulation(self):
        """Full reset for STOP (distinct from PAUSE, which halts the clock
        but preserves everything): sim time, packet counter, trace/metric
        history, poisoning/scan logs, and router cache state all return to
        a fresh starting point, so the next START begins a genuinely new
        run instead of resuming where the last one left off. Topology is
        rebuilt (not just cache-cleared) since that's the simplest way to
        guarantee every nested mutable field poisoning/scanning touched is
        truly reset -- safe because topology generation is seeded, so the
        same config always reproduces the same mesh."""
        self.status = "STOPPED"
        self.sim_time = 0.0
        self.packet_counter = 0
        self.window_history = []
        self.active_packets = []
        self.trace_log = []
        self.metrics_history = []
        self.poison_log = []
        self.scan_log = []
        self.init_topology()
        self.reset_posteriors()

    def poison_cache(self, router_id: str, target_names: List[str], image_filenames: List[str]):
        """Content Poisoning Attack simulation: substitutes GAN-generated
        fake images into a router's Content Store UNDER THE NAME OF
        EXISTING REAL CONTENT (e.g. overwriting the cache entry for
        '/cats/cat_image5.jpg') -- exactly how a real CPA works. The
        attacker doesn't invent a new name; they corrupt an existing
        (often popular/watchlisted) one, so every subsequent legitimate
        request for that name organically gets served the fake object
        instead of the real one, through the exact same cache-hit path
        process_interest() already uses -- no special-casing needed.
        WASP's routing/caching/privacy math can't tell the difference,
        since it's a name-based lookup; that's precisely the gap this
        GAN/anti-GAN track exists to close. Returns the list of
        {name, source_image} substitutions actually made."""
        if router_id not in self.nodes or self.nodes[router_id]["type"] != "router":
            raise ValueError(f"Unknown router: {router_id}")
        cs = self.nodes[router_id]["cs"]
        poisoned = []
        for content_name, fname in zip(target_names, image_filenames):
            cs[:] = [e for e in cs if e["prefix"] != content_name]
            if len(cs) >= self.config["topology"]["cs_capacity"]:
                cs.pop(0)
            cs.append({
                "prefix": content_name,
                "cached_time": self.sim_time,
                "hit_count": 0,
                "fresh": True,
                "is_synthetic": True,
                "source_image": fname
            })
            poisoned.append({"name": content_name, "source_image": fname})

        self.poison_log.append({
            "time": round(self.sim_time, 2),
            "router_id": router_id,
            "items": poisoned
        })
        if len(self.poison_log) > 100:
            self.poison_log.pop(0)
        return poisoned

    def scan_router_cache(self, router_id: str, mitigate: Optional[bool] = None):
        """Anti-GAN authenticity scan: runs the trained content-authenticity
        detector (gan_lab/anti_gan_infer.py) over everything currently
        cached at a router. Deliberately NOT run automatically on every
        cache insert -- inference is too slow (tens of ms) to do on every
        packet in the 10Hz simulation loop, and a triggered scan matches
        the real "attack happens, dwell time passes, detection catches up"
        security narrative better than continuous scanning anyway.

        If mitigation is enabled (explicit param, else the engine-wide
        config default), any entry the detector flags SUSPECT gets evicted
        and replaced with a freshly re-verified copy of the real content --
        the "detect AND correct" policy, closing the loop WASP's privacy
        pipeline alone never could. Returns the per-entry scan results."""
        if router_id not in self.nodes or self.nodes[router_id]["type"] != "router":
            raise ValueError(f"Unknown router: {router_id}")
        if anti_gan_infer is None or not ANTI_GAN_AVAILABLE:
            raise RuntimeError("Anti-GAN detector not available -- run gan_lab/anti_gan_train.py first.")

        if mitigate is None:
            mitigate = self.config["anti_gan"]["mitigation_enabled"]
        threshold = self.config["anti_gan"]["threshold"]

        cs = self.nodes[router_id]["cs"]
        results = []
        for entry in list(cs):
            content_name = entry["prefix"]
            if entry.get("is_synthetic"):
                img_path = FAKE_CONTENT_DIR / entry.get("source_image", "")
            else:
                img_path = CONTENT_DIR / content_name.lstrip("/")

            try:
                score = anti_gan_infer.score_image_cached(str(img_path))
            except Exception:
                score = None

            label, corrected = None, False
            if score is not None:
                label = "VERIFIED" if score >= threshold else "SUSPECT"
                entry["authenticity_score"] = round(score, 4)
                entry["authenticity_label"] = label

                if label == "SUSPECT" and mitigate:
                    cs.remove(entry)
                    real_path = CONTENT_DIR / content_name.lstrip("/")
                    if real_path.exists():
                        real_score = anti_gan_infer.score_image_cached(str(real_path))
                        cs.append({
                            "prefix": content_name,
                            "cached_time": self.sim_time,
                            "hit_count": 0,
                            "fresh": True,
                            "is_synthetic": False,
                            "authenticity_score": round(real_score, 4),
                            "authenticity_label": "VERIFIED (restored)"
                        })
                        corrected = True

            results.append({
                "name": content_name,
                "ground_truth_synthetic": entry.get("is_synthetic", False),
                "score": round(score, 4) if score is not None else None,
                "label": label,
                "corrected": corrected
            })

        self.scan_log.append({
            "time": round(self.sim_time, 2),
            "router_id": router_id,
            "mitigated": mitigate,
            "results": results
        })
        if len(self.scan_log) > 50:
            self.scan_log.pop(0)
        return results

    # Algorithm 1 Pipeline & Calculations
    def process_interest(self, content_name: str, subscriber_id: str = "s0", synthetic: bool = False) -> Dict[str, Any]:
        self.packet_counter += 1
        pkt_id = f"pkt-{self.packet_counter:04d}"
        t = self.sim_time
        top_cfg = self.config["topology"]
        wasp_cfg = self.config["wasp"]
        ablation = self.config["ablation"]
        n_routers = top_cfg["n_routers"]
        W = wasp_cfg["W"]

        # Record this Interest in window history
        self.window_history.append({"name": content_name, "time": t, "pkt_id": pkt_id})
        if len(self.window_history) > 500:
            self.window_history.pop(0)

        # ---------------------------------------------------------------------
        # Stage 1: Traffic Monitoring (TM)
        # ---------------------------------------------------------------------
        window_interests = self.window_history[-W:] if len(self.window_history) > W else self.window_history
        F_c = sum(1 for item in window_interests if item["name"] == content_name)
        
        # Inter-arrival interval T_c
        same_name_times = [item["time"] for item in window_interests if item["name"] == content_name]
        if len(same_name_times) >= 2:
            T_c = (same_name_times[-1] - same_name_times[0]) / (len(same_name_times) - 1)
        else:
            T_c = wasp_cfg["delta_max_ms"] / 1000.0

        # Cache hit ratio C_c
        total_requests = len(self.window_history)
        total_hits = sum(self.nodes[f"r{i}"]["cache_hits"] for i in range(n_routers))
        C_c = (total_hits / max(1, total_requests))

        # Resolve which category/publisher this content belongs to, and the
        # FIB-driven router path from the requesting subscriber to it (ported
        # from NetworkCaching-backend's Network.route()).
        name_parts = content_name.strip("/").split("/")
        category = name_parts[0] if name_parts and name_parts[0] in self.category_publisher else next(iter(self.category_publisher), "")
        start_router = self.nodes.get(subscriber_id, {}).get("router") or next(iter(self.fib), "r0")
        router_path = self.route(start_router, category)

        # Hop count H_c (real path length, not a constant)
        H_c = float(len(router_path))

        # ---------------------------------------------------------------------
        # Stage 2: Privacy Exposure Estimation (PE)
        # ---------------------------------------------------------------------
        # Normalization
        F_norm = min(1.0, F_c / 15.0)
        C_norm = min(1.0, C_c)
        T_norm = min(1.0, max(0.0, 1.0 - (T_c / 2.0)))
        H_norm = min(1.0, H_c / max(1.0, float(n_routers + 1)))

        weights = wasp_cfg["weights"]
        alpha = weights["alpha"]
        beta = weights["beta"]
        gamma = weights["gamma"]
        delta = weights["delta"]

        PES = alpha * F_norm + beta * C_norm + gamma * T_norm + delta * H_norm
        P_i = float(np.clip(PES, 0.0, 1.0))

        tau_1 = wasp_cfg["tau_1"]
        tau_2 = wasp_cfg["tau_2"]
        if P_i < tau_1:
            risk_level = "Low"
        elif P_i < tau_2:
            risk_level = "Medium"
        else:
            risk_level = "High"

        # ---------------------------------------------------------------------
        # Stage 3: Adaptive Shielding Control (ASC)
        # ---------------------------------------------------------------------
        kappa = wasp_cfg["kappa"]
        tau = wasp_cfg["tau"]
        S_i = float(1.0 / (1.0 + np.exp(-kappa * (P_i - tau))))

        eta_1 = wasp_cfg["eta_1"]
        eta_2 = wasp_cfg["eta_2"]
        if S_i < eta_1:
            adaptive_mode = "Normal"
        elif S_i < eta_2:
            adaptive_mode = "Protected"
        else:
            adaptive_mode = "Shielded"

        adaptive_decision = 1 if adaptive_mode in ["Protected", "Shielded"] else 0

        # Scheme override: each of the paper's four schemes follows a different
        # protection policy, not just a display filter over the same pipeline.
        scheme = self.scheme
        if scheme == "NORMAL":
            decision, mode = 0, "Normal"
        elif scheme == "ATTACK":
            decision, mode = 0, "Unshielded"
        elif scheme == "STATIC_CRYPTO":
            decision, mode = 1, "StaticCrypto"
        else:  # WASP
            decision, mode = adaptive_decision, adaptive_mode

        # ---------------------------------------------------------------------
        # Stage 4: Dynamic Cryptographic Protection (DCP)
        # ---------------------------------------------------------------------
        K_min = wasp_cfg["K_min"]
        K_max = wasp_cfg["K_max"]
        T_b = wasp_cfg["T_b"]
        static_cfg = self.config["static_crypto"]

        if scheme == "STATIC_CRYPTO":
            # Conventional cryptography: fixed key size for every packet,
            # no sigmoid-driven adaptivity (paper Fig. 3b, scheme B).
            K_i = static_cfg["key_size"]
            T_enc = T_b * (K_i / 128.0)
            O_c = T_enc * (K_i / 256.0)
        elif decision == 1:
            K_i = int(K_min + S_i * (K_max - K_min))
            T_enc = T_b * (K_i / 128.0)
            O_c = T_enc * (K_i / 256.0)
        else:
            K_i = 0
            T_enc = 0.0
            O_c = 0.0

        # ---------------------------------------------------------------------
        # Stage 5: Secure Forwarding (SF)
        # ---------------------------------------------------------------------
        delta_min = wasp_cfg["delta_min_ms"]
        delta_max = wasp_cfg["delta_max_ms"]
        rho = wasp_cfg["rho"]

        if scheme == "WASP" and decision == 1 and ablation["timing_decorrelation"]:
            adaptive_delay_ms = delta_min + (delta_max - delta_min) * S_i
        else:
            adaptive_delay_ms = 0.0

        if scheme == "WASP" and decision == 1 and ablation["routing_diversity"]:
            routing_diversity = 1.0 + rho * S_i
        else:
            routing_diversity = 1.0

        # Route determination: walk the FIB-resolved path computed in Stage 1,
        # checking each router's cache along the way.
        route_nodes = [subscriber_id] + router_path
        cache_hit_node = None

        served_synthetic = False
        for rid in router_path:
            r_node = self.nodes[rid]
            cs_entries = [entry["prefix"] for entry in r_node["cs"]]
            if content_name in cs_entries:
                cache_hit_node = rid
                r_node["cache_hits"] += 1
                for entry in r_node["cs"]:
                    if entry["prefix"] == content_name:
                        entry["hit_count"] += 1
                        served_synthetic = entry.get("is_synthetic", False)
                break
            else:
                r_node["cache_misses"] += 1

        if not cache_hit_node:
            pub_id = self.category_publisher.get(category)
            if pub_id:
                route_nodes.append(pub_id)
            # Cache at every router actually on the path (only those the
            # Interest/Data genuinely traversed, not every router network-wide)
            for rid in router_path:
                cs = self.nodes[rid]["cs"]
                if not any(entry["prefix"] == content_name for entry in cs):
                    if len(cs) >= top_cfg["cs_capacity"]:
                        cs.pop(0)
                    cs.append({
                        "prefix": content_name,
                        "cached_time": t,
                        "hit_count": 0,
                        "fresh": True,
                        "is_synthetic": False
                    })

        # Calculate latency
        link_lat = top_cfg["link_latency_ms"]
        num_hops = len(route_nodes) - 1
        base_latency = num_hops * link_lat * 2 # RTT
        total_latency_ms = base_latency + T_enc + adaptive_delay_ms

        # ---------------------------------------------------------------------
        # Attacker Observation & Bayesian Update
        # ---------------------------------------------------------------------
        is_watchlisted = content_name in self.watchlist
        obs_routers = self.config["attacker"]["observation_routers"]
        observed_by_attacker = any(r in route_nodes for r in obs_routers)

        # NORMAL has no watchlist adversary present at all (paper's unattacked baseline)
        observed_name = content_name
        if observed_by_attacker and is_watchlisted and scheme != "NORMAL":
            bank = self.posteriors[scheme]
            a, b = bank[content_name]
            if scheme == "WASP" and decision == 1 and ablation["name_obfuscation"]:
                # A-SHLD-1: Name Obfuscation into Opaque Token; confidence decays via Eq. 48
                token_hash = hashlib.sha256(content_name.encode()).hexdigest()[:8]
                observed_name = f"OPAQUE_{token_hash}"
                suppression = max(0.0, 1.0 - S_i)
                bank[content_name] = [a * suppression, b + (1.0 - suppression)]
            elif scheme == "STATIC_CRYPTO":
                # Conventional crypto hides the name behind a fixed-strength token, but
                # without adaptive timing/routing cover it still leaks via side channels
                token_hash = hashlib.sha256(content_name.encode()).hexdigest()[:8]
                observed_name = f"ENC_{token_hash}"
                suppression = static_cfg["suppression"]
                bank[content_name] = [a * suppression, b + (1.0 - suppression)]
            else:
                # ATTACK (and WASP when the adaptive decision is 0): plaintext observation
                bank[content_name][0] += 1.0

        # Posterior confidence for this content under every scheme (for comparison charts)
        if is_watchlisted:
            conf_by_scheme = {
                s: self.posteriors[s][content_name][0] / max(1e-6, sum(self.posteriors[s][content_name]))
                for s in SCHEMES
            }
        else:
            conf_by_scheme = {s: 0.0 for s in SCHEMES}

        # Add to active packets in transit for animation (capped at 16 to maintain high-fps rendering)
        if len(self.active_packets) < 16:
            self.active_packets.append({
                "id": pkt_id,
                "name": content_name,
                "type": "Interest",
                "src": route_nodes[0],
                "dst": route_nodes[1] if len(route_nodes) > 1 else route_nodes[0],
                "path": route_nodes,
                "path_idx": 0,
                "progress": 0.0,
                "mode": mode,
                "decision": decision,
                "is_watchlisted": is_watchlisted,
                "is_shielded": decision == 1,
                "served_synthetic": served_synthetic,
                "start_time": t,
                "total_latency": total_latency_ms
            })

        # Generate full mathematical formulas breakdown object
        breakdown = {
            "stage1_tm": {
                "F_c": {
                    "eq": "F_c(t) = \\sum_{i=1}^W \\delta(I_i, c)",
                    "sub": f"count('{content_name}' in last {W}) = {F_c}",
                    "val": F_c
                },
                "T_c": {
                    "eq": "T_c = \\frac{T_N - T_1}{N - 1}",
                    "sub": f"arrival interval over {len(same_name_times)} requests",
                    "val": f"{T_c:.3f} s"
                },
                "C_c": {
                    "eq": "C_c = \\frac{Hits}{Requests}",
                    "sub": f"{total_hits} hits / {max(1, total_requests)} requests",
                    "val": f"{C_c:.3f}"
                },
                "H_c": {
                    "eq": "H_c = \\frac{1}{N} \\sum h_i",
                    "sub": f"{n_routers} hops along shortest path",
                    "val": f"{H_c:.1f}"
                }
            },
            "stage2_pe": {
                "X_norm": {
                    "eq": "X'_i = \\frac{X_i - X_{min}}{X_{max} - X_{min}}",
                    "sub": f"[F': {F_norm:.2f}, C': {C_norm:.2f}, T': {T_norm:.2f}, H': {H_norm:.2f}]",
                    "val": [round(F_norm, 3), round(C_norm, 3), round(T_norm, 3), round(H_norm, 3)]
                },
                "PES": {
                    "eq": "PES_i = \\alpha F' + \\beta C' + \\gamma T' + \\delta H'",
                    "sub": f"{alpha:.2f}({F_norm:.2f}) + {beta:.2f}({C_norm:.2f}) + {gamma:.2f}({T_norm:.2f}) + {delta:.2f}({H_norm:.2f})",
                    "val": round(PES, 3)
                },
                "P_i": {
                    "eq": "P_i = \\text{norm}(PES_i)",
                    "sub": f"clip({PES:.3f}, 0, 1)",
                    "val": round(P_i, 3)
                },
                "risk_level": {
                    "eq": "P_i \\ge \\tau_2 \\to High, P_i \\ge \\tau_1 \\to Med, else Low",
                    "sub": f"{P_i:.3f} (tau_1={tau_1}, tau_2={tau_2})",
                    "val": risk_level
                }
            },
            "stage3_asc": {
                "S_i": {
                    "eq": "S_i = \\frac{1}{1 + e^{-\\kappa(P_i - \\tau)}}",
                    "sub": f"1 / (1 + exp(-{kappa} * ({P_i:.3f} - {tau})))",
                    "val": round(S_i, 3)
                },
                "mode": {
                    "eq": "S_i < \\eta_1 \\to Normal, S_i < \\eta_2 \\to Protected, else Shielded",
                    "sub": f"{S_i:.3f} (eta_1={eta_1}, eta_2={eta_2})",
                    "val": mode
                },
                "decision": {
                    "eq": "D_i = 1 \\text{ if } mode \\in \\{Protected, Shielded\\} \\text{ else } 0",
                    "sub": f"mode is {mode}",
                    "val": decision
                }
            },
            "stage4_dcp": {
                "K_i": {
                    "eq": "K_i = K_{min} + S_i(K_{max} - K_{min})",
                    "sub": f"{K_min} + {S_i:.3f} * ({K_max} - {K_min})",
                    "val": f"{K_i} bits"
                },
                "T_enc": {
                    "eq": "T_{enc} = T_b \\times (K_i / 128)",
                    "sub": f"{T_b} * ({K_i} / 128)",
                    "val": f"{T_enc:.3f} ms"
                },
                "O_c": {
                    "eq": "O_c = T_{enc} \\times (K_i / 256)",
                    "sub": f"{T_enc:.3f} * ({K_i} / 256)",
                    "val": round(O_c, 3)
                }
            },
            "stage5_sf": {
                "Delta_i": {
                    "eq": "\\Delta_i = \\Delta_{min} + (\\Delta_{max} - \\Delta_{min})S_i",
                    "sub": f"{delta_min} + ({delta_max} - {delta_min}) * {S_i:.3f}",
                    "val": f"{adaptive_delay_ms:.2f} ms"
                },
                "R_i": {
                    "eq": "R_i = 1 + \\rho S_i",
                    "sub": f"1 + {rho} * {S_i:.3f}",
                    "val": round(routing_diversity, 3)
                },
                "route": {
                    "eq": "R^* = \\arg\\min C_f",
                    "sub": " -> ".join(route_nodes),
                    "val": " -> ".join(route_nodes)
                }
            },
            "attacker_posterior": {
                "observation": {
                    "eq": "O(t) = \\text{Inspect}(c)",
                    "sub": f"At {obs_routers}: observed as '{observed_name}' (active scheme={scheme})",
                    "val": observed_name
                },
                "confidence_normal": {
                    "eq": "P_L(c) = \\frac{\\alpha}{\\alpha + \\beta}",
                    "sub": f"Posterior on '{content_name}' under Normal (no attacker)",
                    "val": round(conf_by_scheme["NORMAL"], 3)
                },
                "confidence_attack": {
                    "eq": "P_L(c) = \\frac{\\alpha}{\\alpha + \\beta}",
                    "sub": f"Posterior on '{content_name}' under unprotected Watchlist Attack",
                    "val": round(conf_by_scheme["ATTACK"], 3)
                },
                "confidence_static_crypto": {
                    "eq": "P_L(c) = \\frac{\\alpha}{\\alpha + \\beta}",
                    "sub": f"Posterior on '{content_name}' under Static/Conventional Crypto",
                    "val": round(conf_by_scheme["STATIC_CRYPTO"], 3)
                },
                "confidence_wasp": {
                    "eq": "P_L(c) = \\frac{\\alpha}{\\alpha + \\beta}",
                    "sub": f"Posterior on '{content_name}' under Full WASP defense",
                    "val": round(conf_by_scheme["WASP"], 3)
                }
            }
        }

        trace_entry = {
            "id": pkt_id,
            "name": content_name,
            "synthetic": synthetic,
            "time": round(t, 2),
            "src": subscriber_id,
            "dst": self.category_publisher.get(category, "p0"),
            "category": category,
            "path": route_nodes,
            "cache_hit": cache_hit_node is not None,
            "cache_node": cache_hit_node,
            "served_synthetic": served_synthetic,
            "is_watchlisted": is_watchlisted,
            "observed_by_attacker": observed_by_attacker,
            "observed_as": observed_name,
            "scheme": scheme,
            "pes": round(PES, 3),
            "risk": round(P_i, 3),
            "risk_level": risk_level,
            "shielding_intensity": round(S_i, 3),
            "mode": mode,
            "decision": decision,
            "key_size": K_i,
            "encryption_time_ms": round(T_enc, 3),
            "adaptive_delay_ms": round(adaptive_delay_ms, 2),
            "routing_diversity": round(routing_diversity, 2),
            "latency_ms": round(total_latency_ms, 2),
            "conf_normal": round(conf_by_scheme["NORMAL"], 3),
            "conf_attack": round(conf_by_scheme["ATTACK"], 3),
            "conf_static_crypto": round(conf_by_scheme["STATIC_CRYPTO"], 3),
            "conf_wasp": round(conf_by_scheme["WASP"], 3),
            "breakdown": breakdown
        }

        self.trace_log.append(trace_entry)
        if len(self.trace_log) > 300:
            self.trace_log.pop(0)

        return trace_entry

    def step(self, dt: float = 0.05):
        if self.status != "RUNNING":
            return

        self.sim_time += dt

        # Update in-flight active packets progress
        finished_indices = []
        for idx, pkt in enumerate(self.active_packets):
            pkt["progress"] += 0.08 # smooth animation increment
            if pkt["progress"] >= 1.0:
                pkt["path_idx"] += 1
                if pkt["path_idx"] < len(pkt["path"]) - 1:
                    pkt["src"] = pkt["path"][pkt["path_idx"]]
                    pkt["dst"] = pkt["path"][pkt["path_idx"] + 1]
                    pkt["progress"] = 0.0
                else:
                    # Switch to reverse Data packet if not already
                    if pkt["type"] == "Interest":
                        pkt["type"] = "Data"
                        pkt["path"] = list(reversed(pkt["path"]))
                        pkt["path_idx"] = 0
                        pkt["src"] = pkt["path"][0]
                        pkt["dst"] = pkt["path"][1] if len(pkt["path"]) > 1 else pkt["path"][0]
                        pkt["progress"] = 0.0
                    else:
                        finished_indices.append(idx)

        for idx in reversed(finished_indices):
            self.active_packets.pop(idx)

        # Stochastic traffic arrival: pick a random category, then a
        # Zipf-ranked item within that category's real content pool (keeps
        # the popularity skew that drives F_c / the privacy-exposure math,
        # now over real filenames instead of a flat synthetic /c/N catalog).
        mean_ia = self.config["traffic"]["mean_inter_arrival_ms"] / 1000.0
        prob_arrival = dt / max(1e-4, mean_ia)
        if self.rng_traffic.random() < prob_arrival and self.content_pool:
            alpha = self.config["traffic"]["zipf_alpha"]
            categories = list(self.content_pool.keys())
            category = categories[int(self.rng_traffic.integers(0, len(categories)))]
            pool = self.content_pool[category]
            rank = int(self.rng_traffic.zipf(alpha))
            idx = min(rank - 1, len(pool) - 1)
            content_name = pool[idx]
            sub_id = f"s{self.rng_traffic.integers(0, self.config['topology']['n_subscribers'])}"
            self.process_interest(content_name, sub_id)

        # Periodically record time-series metric snapshot (every ~0.5s)
        if int(self.sim_time * 10) % 5 == 0:
            self.record_metric_sample()

    def record_metric_sample(self):
        # Mean attacker confidence over watchlist, per scheme bank
        mean_conf = {}
        for s in SCHEMES:
            bank = self.posteriors[s]
            mean_conf[s] = float(np.mean([a / max(1e-6, a + b) for a, b in bank.values()])) if bank else 0.1

        # Latency hit vs miss (from the currently active scheme's traces)
        recent_traces = self.trace_log[-20:] if self.trace_log else []
        hits = [t["latency_ms"] for t in recent_traces if t["cache_hit"]]
        misses = [t["latency_ms"] for t in recent_traces if not t["cache_hit"]]
        lat_hit = float(np.mean(hits)) if hits else 5.0
        lat_miss = float(np.mean(misses)) if misses else 25.0

        # PDR per scheme (paper-reported reference values, Fig. 3b) and CHR
        pdr_reference = {"NORMAL": 0.98, "ATTACK": 0.65, "STATIC_CRYPTO": 0.87, "WASP": 0.94}
        pdr_active = pdr_reference[self.scheme] if self.status == "RUNNING" else 0.0
        total_hits = sum(self.nodes[f"r{i}"]["cache_hits"] for i in range(self.config["topology"]["n_routers"]))
        total_misses = sum(self.nodes[f"r{i}"]["cache_misses"] for i in range(self.config["topology"]["n_routers"]))
        chr = float(total_hits / max(1, total_hits + total_misses))

        # Overheads
        recent_s = [t["shielding_intensity"] for t in recent_traces]
        E_s = float(np.mean(recent_s)) if recent_s else 0.0
        O_s = E_s * 0.2
        recent_oc = [t["breakdown"]["stage4_dcp"]["O_c"]["val"] for t in recent_traces]
        O_c = float(np.mean(recent_oc)) if recent_oc else 0.0
        E_f = float(np.mean([t["routing_diversity"] for t in recent_traces])) if recent_traces else 1.0

        sample = {
            "time": round(self.sim_time, 2),
            "scheme": self.scheme,
            "conf_normal": round(mean_conf["NORMAL"], 3),
            "conf_attack": round(mean_conf["ATTACK"], 3),
            "conf_static_crypto": round(mean_conf["STATIC_CRYPTO"], 3),
            "conf_wasp": round(mean_conf["WASP"], 3),
            "lat_hit": round(lat_hit, 2),
            "lat_miss": round(lat_miss, 2),
            "pdr_active": round(pdr_active, 3),
            "chr": round(chr, 3),
            "isr": round(mean_conf["ATTACK"] - mean_conf["WASP"], 3),
            "E_s": round(E_s, 3),
            "O_s": round(O_s, 3),
            "O_c": round(O_c, 3),
            "E_f": round(E_f, 3),
            "paper": self.paper_reference
        }

        self.metrics_history.append(sample)
        if len(self.metrics_history) > 100:
            self.metrics_history.pop(0)

    def get_full_state(self) -> Dict[str, Any]:
        # Calculate watchlist confidences for UI with safe numeric sorting
        watchlist_stats = []
        def safe_sort(name):
            # Pulls the last run of digits out of the name for ordering --
            # works for both old-style "/c/17" and real filenames like
            # "/cats/cat_image17.jpg" (int(name.split("/")[-1]) only ever
            # worked for the former and silently collapsed every real
            # filename to the same fallback key).
            match = re.search(r"(\d+)(?:\.\w+)?$", name)
            return int(match.group(1)) if match else 9999

        for name in sorted(list(self.watchlist), key=safe_sort):
            item = {"name": name}
            for s in SCHEMES:
                a, b = self.posteriors[s].get(name, [1.0, 9.0])
                item[f"conf_{s.lower()}"] = round(float(a / max(1e-6, a + b)), 3)
            watchlist_stats.append(item)

        # A few non-watchlisted items per category, for UI quick-select
        # controls that want to offer a "normal" (unmonitored) content item
        # alongside the sensitive watchlisted ones.
        content_sample = []
        for cat, pool in self.content_pool.items():
            normal_items = [c for c in pool if c not in self.watchlist]
            content_sample.extend(normal_items[:3])

        # Summary router metrics
        router_states = {}
        for nid, node in self.nodes.items():
            if node["type"] == "router":
                router_states[nid] = {
                    "id": nid,
                    "status": node["status"],
                    "wasp_enabled": node["wasp_enabled"],
                    "is_compromised": node["is_compromised"],
                    "cache_hits": node["cache_hits"],
                    "cache_misses": node["cache_misses"],
                    "pit_size": len(node["pit"]),
                    "cs_size": len(node["cs"]),
                    "fib_size": len(node["fib"]),
                    "pit": node["pit"][-10:],
                    "cs": node["cs"][-10:],
                    "fib": node["fib"],
                    "poisoned_count": sum(1 for e in node["cs"] if e.get("is_synthetic"))
                }

        # Lightweight traces: strip heavy nested breakdown trees except latest 3 to keep websocket payloads tiny and fast
        recent_subset = self.trace_log[-12:]
        light_traces = []
        for i, t in enumerate(recent_subset):
            entry = {
                "id": t["id"],
                "name": t["name"],
                "category": t.get("category"),
                "dst": t["dst"],
                "time": t["time"],
                "src": t["src"],
                "path": t["path"],
                "cache_hit": t["cache_hit"],
                "cache_node": t["cache_node"],
                "served_synthetic": t["served_synthetic"],
                "is_watchlisted": t["is_watchlisted"],
                "observed_by_attacker": t["observed_by_attacker"],
                "observed_as": t["observed_as"],
                "scheme": t["scheme"],
                "pes": t["pes"],
                "risk": t["risk"],
                "risk_level": t["risk_level"],
                "shielding_intensity": t["shielding_intensity"],
                "mode": t["mode"],
                "decision": t["decision"],
                "key_size": t["key_size"],
                "latency_ms": t["latency_ms"],
                "conf_normal": t["conf_normal"],
                "conf_attack": t["conf_attack"],
                "conf_static_crypto": t["conf_static_crypto"],
                "conf_wasp": t["conf_wasp"]
            }
            if i >= len(recent_subset) - 3:
                entry["breakdown"] = t.get("breakdown")
            light_traces.append(entry)

        # Latest trace (retains full mathematical breakdown for formulas panel)
        latest_trace = self.trace_log[-1] if self.trace_log else None

        return {
            "status": self.status,
            "sim_time": round(self.sim_time, 2),
            "packet_count": self.packet_counter,
            "scheme": self.scheme,
            "config": self.config,
            "topology": {
                "nodes": [
                    {
                        "id": nid,
                        "type": n["type"],
                        "is_compromised": n.get("is_compromised", False),
                        "category": n.get("category"),
                        "label": n.get("label")
                    }
                    for nid, n in self.nodes.items()
                ],
                "edges": self.edges,
                "pattern": self.config["topology"].get("pattern", "linear")
            },
            "routers": router_states,
            "active_packets": self.active_packets,
            "recent_traces": light_traces,
            "latest_trace": latest_trace,
            "watchlist": watchlist_stats,
            "content_sample": content_sample,
            "poison_log": self.poison_log[-20:],
            "scan_log": self.scan_log[-20:],
            "gan_source_model": GAN_SOURCE_MODEL,
            "anti_gan": {
                "available": ANTI_GAN_AVAILABLE,
                "mitigation_enabled": self.config["anti_gan"]["mitigation_enabled"],
                "threshold": self.config["anti_gan"]["threshold"]
            },
            "metrics": self.metrics_history[-25:],
            "paper_reference": self.paper_reference
        }


# Global engine instance
engine = SimulationEngine()


# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: Dict[str, Any]):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                disconnected.append(connection)
        for dead in disconnected:
            self.disconnect(dead)

manager = ConnectionManager()


# Background Simulation Task
simulation_task: Optional[asyncio.Task] = None

async def simulation_loop():
    step_count = 0
    while True:
        try:
            if engine.status == "RUNNING":
                engine.step(dt=0.05)
                step_count += 1
                # Broadcast state update at clean 10 Hz (every 2 physics steps = 100ms)
                if step_count % 2 == 0 and manager.active_connections:
                    await manager.broadcast({
                        "type": "state_update",
                        "data": engine.get_full_state()
                    })
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Simulation Loop Exception] {e}", file=sys.stderr)
            await asyncio.sleep(0.1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global simulation_task
    simulation_task = asyncio.create_task(simulation_loop())
    yield
    if simulation_task and not simulation_task.done():
        simulation_task.cancel()

# Create FastAPI app with lifespan
app = FastAPI(title="WASP Network Lab Controller", version="0.1.0", lifespan=lifespan)

# Mount static web directory
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

CONTENT_DIR = SERVER_DIR / "content"
if CONTENT_DIR.exists():
    app.mount("/content", StaticFiles(directory=str(CONTENT_DIR)), name="content")



# WebSocket Endpoint (/ws)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    # Immediately send full current state
    await websocket.send_json({
        "type": "initial_state",
        "data": engine.get_full_state()
    })
    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                msg = json.loads(raw_data)
                action = msg.get("action", "")

                if action == "start":
                    engine.status = "RUNNING"
                elif action == "pause":
                    engine.status = "PAUSED"
                elif action == "resume":
                    engine.status = "RUNNING"
                elif action == "stop":
                    engine.reset_simulation()
                elif action == "step":
                    prev = engine.status
                    engine.status = "RUNNING"
                    engine.step(dt=0.1)
                    engine.status = prev if prev != "RUNNING" else "PAUSED"
                elif action == "reseed":
                    t_seed = msg.get("traffic_seed", 42)
                    w_seed = msg.get("wasp_seed", 1337)
                    engine.reseed(t_seed, w_seed)
                elif action == "set_scheme":
                    engine.apply_scheme(msg.get("scheme", "WASP"))
                elif action == "set_ablation":
                    mech = msg.get("mechanism")
                    val = bool(msg.get("enabled", True))
                    if mech in engine.config["ablation"]:
                        engine.config["ablation"][mech] = val
                elif action == "inject":
                    name = msg.get("name", "/cats/cat_image1.jpg")
                    cid = msg.get("consumer_id", "s0")
                    engine.process_interest(name, cid, synthetic=True)

                # Send updated state immediately
                await manager.broadcast({
                    "type": "state_update",
                    "data": engine.get_full_state()
                })
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# Browsers can silently serve a stale cached copy of these on a plain
# refresh since FileResponse sets no cache headers by default -- during
# active iteration on the dashboard that reads as "refresh does nothing."
NO_CACHE_HEADERS = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}


# HTML View Page Routes
@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file, headers=NO_CACHE_HEADERS)
    return HTMLResponse("<h1>WASP Lab Dashboard</h1><p>index.html not found</p>")

@app.get("/network", response_class=HTMLResponse)
async def get_network():
    network_file = WEB_DIR / "network.html"
    if network_file.exists():
        return FileResponse(network_file, headers=NO_CACHE_HEADERS)
    return HTMLResponse("<h1>WASP Lab Network Mode</h1><p>network.html not found</p>")

@app.get("/router", response_class=HTMLResponse)
@app.get("/router/{router_id}", response_class=HTMLResponse)
async def get_router(router_id: str = "r0"):
    router_file = WEB_DIR / "router.html"
    if router_file.exists():
        return FileResponse(router_file, headers=NO_CACHE_HEADERS)
    return HTMLResponse("<h1>WASP Lab Router Mode</h1><p>router.html not found</p>")

@app.get("/gan-comparison", response_class=HTMLResponse)
async def get_gan_comparison():
    gan_file = WEB_DIR / "gan_comparison.html"
    if gan_file.exists():
        return FileResponse(gan_file, headers=NO_CACHE_HEADERS)
    return HTMLResponse("<h1>GAN Comparison</h1><p>gan_comparison.html not found</p>")

@app.get("/mesh-poisoning", response_class=HTMLResponse)
async def get_mesh_poisoning():
    poison_file = WEB_DIR / "mesh_poisoning.html"
    if poison_file.exists():
        return FileResponse(poison_file, headers=NO_CACHE_HEADERS)
    return HTMLResponse("<h1>Mesh Poisoning</h1><p>mesh_poisoning.html not found</p>")


# Fallback direct routes for CSS and JS
@app.get("/styles.css")
async def get_styles():
    f = WEB_DIR / "styles.css"
    if f.exists():
        return FileResponse(f, media_type="text/css", headers=NO_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="styles.css not found")

@app.get("/app.js")
async def get_app_js():
    f = WEB_DIR / "app.js"
    if f.exists():
        return FileResponse(f, media_type="application/javascript", headers=NO_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="app.js not found")


# REST API Endpoints (WaspClient & Frontend Compatible)
@app.get("/status")
def get_status():
    return {
        "status": engine.status,
        "scenario": "FULL_WASP",
        "scheme": engine.scheme,
        "time": round(engine.sim_time, 2)
    }

@app.post("/start")
def start_simulation(config: Optional[ScenarioConfig] = None):
    engine.status = "RUNNING"
    return {"status": "started", "scenario": config.scenario if config else "FULL_WASP"}

@app.post("/stop")
def stop_simulation():
    engine.reset_simulation()
    return {"status": "stopped"}

@app.post("/pause")
def pause_simulation():
    engine.status = "PAUSED"
    return {"status": "paused"}

@app.post("/resume")
def resume_simulation():
    engine.status = "RUNNING"
    return {"status": "resumed"}

@app.post("/step")
def step_simulation():
    prev = engine.status
    engine.status = "RUNNING"
    engine.step(dt=0.1)
    engine.status = prev if prev != "RUNNING" else "PAUSED"
    return {"status": "stepped", "sim_time": round(engine.sim_time, 2)}

@app.post("/reseed")
def reseed_simulation(cfg: ReseedConfig):
    engine.reseed(cfg.traffic_seed, cfg.wasp_seed)
    return {"status": "reseeded", "seeds": engine.config["seeds"]}

@app.post("/network/init")
def init_network(config: NetworkInit):
    engine.config["topology"]["n_routers"] = config.num_routers
    engine.config["topology"]["n_subscribers"] = config.num_consumers
    engine.config["topology"]["n_producers"] = config.num_producers
    engine.config["topology"]["pattern"] = config.pattern
    engine.config["topology"]["link_latency_ms"] = config.link_latency_ms
    engine.config["topology"]["cs_capacity"] = config.cs_capacity
    engine.init_topology()
    engine.reset_posteriors()  # watchlist/content pool changed, rebuild posterior banks to match
    return {"status": "initialized", "topology": engine.config["topology"]}


@app.post("/traffic/config")
def update_traffic_config(cfg: TrafficConfig):
    engine.config["traffic"]["zipf_alpha"] = max(1.01, cfg.zipf_alpha)
    engine.config["traffic"]["catalog_size"] = max(10, cfg.catalog_size)
    engine.config["traffic"]["mean_inter_arrival_ms"] = max(5.0, cfg.mean_inter_arrival_ms)
    if max(1, cfg.watchlist_size) != engine.config["traffic"]["watchlist_size"]:
        engine.config["traffic"]["watchlist_size"] = max(1, cfg.watchlist_size)
        engine.rebuild_watchlist()
        engine.reset_posteriors()
    if cfg.obs_router and cfg.obs_router in engine.nodes:
        engine.config["attacker"]["observation_routers"] = [cfg.obs_router]
        for nid, node in engine.nodes.items():
            if node["type"] == "router":
                node["is_compromised"] = (nid == cfg.obs_router)
    if cfg.confidence_prior:
        engine.config["attacker"]["confidence_prior"] = cfg.confidence_prior
        engine.reset_posteriors()
    return {"status": "updated", "traffic": engine.config["traffic"], "attacker": engine.config["attacker"]}

@app.post("/scheme/set")
def set_scheme(cfg: SchemeConfig):
    engine.apply_scheme(cfg.scheme)
    return {"status": "set", "scheme": engine.scheme}

@app.get("/network/state")
def get_network_state():
    recent = engine.trace_log[-5:] if engine.trace_log else []
    active_links = list(set([t["path"][1] for t in recent if len(t["path"]) > 1]))
    wasp_enabled = engine.scheme in ("STATIC_CRYPTO", "WASP")
    return {
        "num_routers": engine.config["topology"]["n_routers"],
        "num_consumers": engine.config["topology"]["n_subscribers"],
        "wasp_enabled": wasp_enabled,
        "scheme": engine.scheme,
        "total_packets": engine.packet_counter,
        "threat_level": "HIGH" if any(t["risk_level"] == "High" for t in recent) else "LOW",
        "active_links": active_links
    }

@app.get("/network/topology")
def get_topology():
    nodes = [{"id": n, "type": data["type"], "is_compromised": data.get("is_compromised", False)} for n, data in engine.nodes.items()]
    return {"nodes": nodes, "edges": engine.edges}

@app.get("/network/visualizer_state")
def get_visualizer_state():
    conf_map = {}
    for name, (a, b) in engine.posteriors[engine.scheme].items():
        conf_map[name] = round(a / max(1e-6, a + b), 3)

    routers = {}
    for nid, node in engine.nodes.items():
        if node["type"] == "router":
            routers[nid] = {
                "wasp_enabled": node["wasp_enabled"],
                "pes": 0.0,
                "mode": "NORMAL"
            }

    # Grab recent events to update router pes
    for t in engine.trace_log[-20:]:
        for hop in t["path"]:
            if hop in routers:
                routers[hop]["pes"] = t["pes"]
                routers[hop]["mode"] = t["mode"]

    return {
        "time": round(engine.sim_time, 2),
        "packets": engine.active_packets,
        "attacker_confidence": conf_map,
        "routers": routers
    }

@app.get("/node/{node_id}")
def get_node_state(node_id: str):
    if node_id == "ATTACKER":
        active_bank = engine.posteriors[engine.scheme]
        mean_leakage = np.mean([
            a / max(1e-6, a + b) for a, b in active_bank.values()
        ]) if active_bank else 0.1
        conf_map = {k: round(a / max(1e-6, a + b), 3) for k, (a, b) in active_bank.items()}
        return {
            "type": "attacker",
            "scheme": engine.scheme,
            "observations": sum(int(a) for a, b in active_bank.values()),
            "leakage": round(float(mean_leakage), 3),
            "watchlist": sorted(list(engine.watchlist)),
            "inferred": conf_map
        }

    if node_id not in engine.nodes:
        return {"error": f"Node {node_id} not found"}

    node = engine.nodes[node_id]
    state = {
        "id": node_id,
        "type": node["type"],
        "status": node["status"],
        "neighbors": node["neighbors"]
    }

    if node["type"] == "router":
        state["wasp_enabled"] = node["wasp_enabled"]
        state["is_compromised"] = node["is_compromised"]
        state["cache_hits"] = node["cache_hits"]
        state["cache_misses"] = node["cache_misses"]
        state["pit"] = node["pit"]
        state["cs"] = node["cs"]
        state["fib"] = node["fib"]

        # Latest metrics for this router
        recent_router = [t for t in engine.trace_log if node_id in t["path"]]
        if recent_router:
            last = recent_router[-1]
            state["pes"] = last["pes"]
            state["shielding"] = last["shielding_intensity"]
            state["mode"] = last["mode"]
        else:
            state["pes"] = 0.0
            state["shielding"] = 0.0
            state["mode"] = "Normal"

    return state

@app.get("/events")
def get_events(limit: int = 20):
    traces = engine.trace_log[-limit:]
    events = []
    for t in traces:
        events.append({
            "interest_id": t["id"],
            "interest": t["name"],
            "router_id": t["path"][1] if len(t["path"]) > 1 else "r0",
            "decision": {
                "risk": t["pes"],
                "shielding_decision": t["shielding_intensity"],
                "mode": t["mode"],
                "key_size": t["key_size"],
                "delay": t["adaptive_delay_ms"]
            }
        })
    return {"events": events, "total": len(engine.trace_log)}

@app.post("/inject")
def inject_traffic(config: InjectConfig):
    trace = engine.process_interest(config.name, config.consumer_id, synthetic=True)
    return {"status": "injected", "trace": trace}

@app.post("/attacker/watchlist")
def add_watchlist(target: AttackerTarget):
    engine.watchlist.add(target.target)
    prior = engine.config["attacker"]["confidence_prior"]
    for s in SCHEMES:
        if target.target not in engine.posteriors[s]:
            engine.posteriors[s][target.target] = [prior * 10.0, (1.0 - prior) * 10.0]
    return {"status": "added", "watchlist": sorted(list(engine.watchlist))}

# Default source of GAN-generated fake images for cache poisoning: WGAN-GP
# was selected as the deployed generator (tied-best FID with DCGAN, but the
# stronger theoretical guarantee against mode collapse -- see gan-comparison
# page). Images pre-generated via gan_lab/generate.py --model wgan_gp.
GAN_SOURCE_MODEL = "wgan_gp"
FAKE_CONTENT_DIR = SERVER_DIR / "content" / f"fake_{GAN_SOURCE_MODEL}"

@app.post("/attack/poison_cache")
def poison_cache_endpoint(cfg: PoisonConfig):
    source_dir = Path(cfg.source_dir) if cfg.source_dir else FAKE_CONTENT_DIR
    if not source_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"No generated images found at {source_dir}. Run gan_lab/generate.py first."
        )
    image_files = sorted(
        f.name for f in source_dir.iterdir()
        if f.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )
    if not image_files:
        raise HTTPException(status_code=404, detail=f"{source_dir} has no generated images.")

    if cfg.target_names:
        target_names = cfg.target_names
    else:
        # Default to poisoning watchlisted content specifically -- the same
        # content WASP's privacy pipeline is trying to protect, now shown
        # vulnerable on the authenticity axis instead.
        candidates = [n for n in engine.watchlist if not cfg.category or n.startswith(f"/{cfg.category}/")]
        if not candidates and cfg.category:
            candidates = engine.content_pool.get(cfg.category, [])
        if not candidates:
            raise HTTPException(
                status_code=400,
                detail="No target content names available -- pass target_names explicitly or a valid category."
            )
        target_names = candidates[:max(1, cfg.count)]

    chosen_images = [image_files[i % len(image_files)] for i in range(len(target_names))]
    poisoned = engine.poison_cache(cfg.router_id, target_names, chosen_images)
    return {"status": "poisoned", "router_id": cfg.router_id, "poisoned": poisoned}

@app.get("/attack/poison_log")
def get_poison_log():
    return {"log": engine.poison_log[-30:]}

@app.post("/attack/scan_router")
def scan_router(cfg: ScanConfig):
    if not ANTI_GAN_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Anti-GAN detector not trained yet -- run gan_lab/anti_gan_train.py first."
        )
    try:
        results = engine.scan_router_cache(cfg.router_id, cfg.mitigate)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "scanned", "router_id": cfg.router_id, "results": results}

@app.get("/attack/scan_log")
def get_scan_log():
    return {"log": engine.scan_log[-30:]}

@app.post("/attack/set_mitigation")
def set_mitigation(cfg: MitigationConfig):
    engine.config["anti_gan"]["mitigation_enabled"] = cfg.enabled
    return {"status": "updated", "mitigation_enabled": cfg.enabled}

@app.get("/attack/anti_gan_status")
def get_anti_gan_status():
    return {
        "available": ANTI_GAN_AVAILABLE,
        "mitigation_enabled": engine.config["anti_gan"]["mitigation_enabled"],
        "threshold": engine.config["anti_gan"]["threshold"]
    }

@app.post("/wasp/params")
def update_params(params: WaspParams):
    w = engine.config["wasp"]
    w["weights"]["alpha"] = params.alpha
    w["weights"]["beta"] = params.beta
    w["weights"]["gamma"] = params.gamma
    w["weights"]["delta"] = params.delta
    w["kappa"] = params.kappa
    w["tau"] = params.tau
    w["tau_1"] = params.tau_1
    w["tau_2"] = params.tau_2
    w["eta_1"] = params.eta_1
    w["eta_2"] = params.eta_2
    w["delta_min_ms"] = params.delta_min_ms
    w["delta_max_ms"] = params.delta_max_ms
    w["K_min"] = params.K_min
    w["K_max"] = params.K_max
    w["T_b"] = params.T_b
    w["rho"] = params.rho
    return {"status": "updated", "wasp": w}

@app.post("/network/ablation")
def set_ablation(cfg: AblationConfig):
    engine.config["ablation"]["name_obfuscation"] = cfg.name_obfuscation
    engine.config["ablation"]["timing_decorrelation"] = cfg.timing_decorrelation
    engine.config["ablation"]["routing_diversity"] = cfg.routing_diversity
    return {"status": "updated", "ablation": engine.config["ablation"]}

@app.get("/trace/{interest_id}")
def get_trace(interest_id: str):
    matches = [t for t in engine.trace_log if t["id"] == interest_id or t["name"] == interest_id]
    if matches:
        return {"trace": matches[-1]}
    return {"error": f"Interest ID {interest_id} not found", "trace": []}

@app.get("/api/state")
def get_api_state():
    return engine.get_full_state()

@app.get("/api/report")
def get_report():
    mean_conf = {}
    for s in SCHEMES:
        bank = engine.posteriors[s]
        mean_conf[s] = float(np.mean([a / max(1e-6, a + b) for a, b in bank.values()])) if bank else 0.1

    pdr_reference = {"NORMAL": 0.98, "ATTACK": 0.65, "STATIC_CRYPTO": 0.87, "WASP": 0.94}

    report_content = f"""# WASP Network Security Simulation Report

## Run Metadata
- Run Time: {engine.sim_time:.2f} s
- Total Packets Processed: {engine.packet_counter}
- Active Scheme: {engine.scheme}
- Seeds: Traffic={engine.config['seeds']['traffic']}, WASP={engine.config['seeds']['wasp']}

## Evaluation Metrics vs Paper References (Lal & Malani, Fig. 3-4)

| Metric | Normal (A) | Attack / Unshielded (C) | Static Crypto (B) | Full WASP (D) |
|---|---|---|---|---|
| Attacker Mean Confidence | {mean_conf['NORMAL']:.3f} | {mean_conf['ATTACK']:.3f} | {mean_conf['STATIC_CRYPTO']:.3f} | {mean_conf['WASP']:.3f} |
| Packet Delivery Ratio (PDR, paper ref.) | {pdr_reference['NORMAL']:.3f} | {pdr_reference['ATTACK']:.3f} | {pdr_reference['STATIC_CRYPTO']:.3f} | {pdr_reference['WASP']:.3f} |

Currently running scheme: **{engine.scheme}**. Switch schemes via POST /scheme/set to accumulate comparable confidence data for the other three.

## Active Shielding Mechanisms (apply only while scheme = WASP)
- A-SHLD-1 Name Obfuscation: {"ENABLED" if engine.config['ablation']['name_obfuscation'] else "DISABLED"}
- A-SHLD-2 Timing Decorrelation: {"ENABLED" if engine.config['ablation']['timing_decorrelation'] else "DISABLED"}
- A-SHLD-3 Routing Diversity: {"ENABLED" if engine.config['ablation']['routing_diversity'] else "DISABLED"}

## Scheme Definitions
- **Normal (A)**: no watchlist adversary present; unshielded baseline ICN.
- **Attack / Unshielded (C)**: watchlist adversary active, zero defense, plaintext names.
- **Static Crypto (B)**: adversary active, every Interest encrypted at a fixed key size ({engine.config['static_crypto']['key_size']} bits), no adaptive timing/routing cover.
- **Full WASP (D)**: adversary active, adaptive Traffic Monitoring -> Privacy Exposure -> Shielding Control -> Dynamic Crypto -> Secure Forwarding pipeline (Algorithm 1, Eqs. 1-48).
"""
    return Response(content=report_content, media_type="text/markdown")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8001, reload=False)

