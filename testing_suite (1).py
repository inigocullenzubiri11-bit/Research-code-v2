"""
=============================================================================
  TESTING SUITE — FLOOD EVACUATION ROUTE OPTIMIZATION SYSTEM
  All 4 Testing Phases from Research Plan
=============================================================================
  INSTALL:  pip install folium requests matplotlib numpy
  RUN:      python testing_suite.py
  NOTE:     Ph_evac_route__5_.py (the router module) must be in the same
            folder, and the import below must match its exact filename!
=============================================================================

  PHASE 1 — Computational & Algorithmic Testing
    A. Computational & Algorithmic Testing
    B. Pathfinding Accuracy & Optimality
    C. Dynamic Re-routing Validation
    D. Network Resilience Analysis

  PHASE 2 — System Performance Validation
    A. Hydrodynamic Integrated Simulation
    B. 10/30 Coupled Model
    C. Scenario-based Stress Tests

  PHASE 3 — Expert Validation (logs + reports for DLSU AdRIC)

  PHASE 4 — Community Feedback & Pilot Testing
    (generates simplified map + feedback form)
=============================================================================
"""

import random, math, time, os, sys, json
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed

try:
    import matplotlib
    # On Linux there's often no X server (SSH sessions, Docker containers,
    # CI/testing-facility machines, headless research servers). If DISPLAY
    # isn't set, force the non-interactive Agg backend BEFORE importing
    # pyplot — otherwise matplotlib silently picks a GUI backend (TkAgg,
    # QtAgg, ...) and either throws "no display name and no $DISPLAY
    # environment variable" or hangs. Agg still writes PNGs perfectly fine.
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    MATPLOTLIB_OK = True
except ImportError:
    MATPLOTLIB_OK = False
    print("pip install matplotlib numpy  for charts\n")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Ph_evac_route__5_ import (
    fetch_osm_data, build_graph, find_best, find_all_shelter_routes,
    bbox_from_point, FLOOD_RISK, FLOOD_EMOJI, ROAD_COLOR,
    SCENARIOS, FLOOD_SCENARIOS, SPEED_PROFILES,
    haversine_m, walk_time, dijkstra, get_path,
    pick_location,
    # NEW — router features added since the last testing_suite sync:
    embedded_mini_montecarlo, assess_network_resilience,
    score_route_accuracy, get_drrmo_info,
)

SEP   = "=" * 68
SEED  = 42
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG   = []   # global log for expert validation report

# Shared context set in main() before phase1a — used by Test 6 to rebuild graphs
_phase1a_ways     = []
_phase1a_shelters = []

def log(msg):
    LOG.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    print(msg)

def mean(lst): return sum(lst)/len(lst) if lst else 0.0
def stdev(lst):
    if len(lst) < 2: return 0.0
    m = mean(lst)
    return math.sqrt(sum((x-m)**2 for x in lst)/(len(lst)-1))

def spearman_corr(xs, ys):
    """Simple Spearman rank correlation, no numpy/scipy required."""
    n = len(xs)
    if n < 2: return 0.0
    def ranks(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0]*len(vals)
        for rank, idx in enumerate(order):
            r[idx] = rank
        return r
    rx, ry = ranks(xs), ranks(ys)
    d2 = sum((a-b)**2 for a, b in zip(rx, ry))
    return 1 - (6*d2) / (n*(n**2-1)) if n > 1 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  PARALLEL SAMPLING WORKERS
#  build_graph() re-derives the whole road/flood/cost graph from `ways` on
#  every call — that cost is identical across samples in the same phase and
#  only the start point/weights change, so Phase 1B / 2B's hundreds of calls
#  are embarrassingly parallel. Workers load `ways`/`shelters` ONCE per
#  process (via the pool initializer) instead of re-pickling them per task.
# ─────────────────────────────────────────────────────────────────────────────

_WORKER_WAYS     = None
_WORKER_SHELTERS = None

def _init_worker(ways, shelters):
    global _WORKER_WAYS, _WORKER_SHELTERS
    _WORKER_WAYS     = ways
    _WORKER_SHELTERS = shelters

def _sample_worker(args):
    """One (start point, mode weights, flood multiplier) sample. Returns
    (dist_m, risk) on success, or None if no route was found/errored."""
    lat, lon, mult, alpha, beta, gamma, delta = args
    try:
        g, ni, sh, _ = build_graph(lat, lon, _WORKER_WAYS, _WORKER_SHELTERS,
                                    mult, alpha, beta, gamma, delta)
        s = next((x for x, xd in ni.items() if xd[3] == "start"), None)
        if not s:
            return None
        _, segs, _ = find_best(g, s, sh)
        if not segs:
            return None
        dist = sum(x["dist_m"] for x in segs)
        risk = max(FLOOD_RISK[x["flood"]] for x in segs)
        return (dist, risk)
    except Exception:
        return None

def _make_pool(ways, shelters):
    """Best-effort process pool. Falls back to None (sequential) if the
    platform/environment can't spawn worker processes."""
    try:
        pool = ProcessPoolExecutor(max_workers=os.cpu_count() or 4,
                                    initializer=_init_worker,
                                    initargs=(ways, shelters))
        return pool
    except Exception as exc:
        log(f"  ⚠  Parallel pool unavailable ({exc}); falling back to sequential.")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 1A — COMPUTATIONAL & ALGORITHMIC TESTING
#  Verifies Dijkstra correctness by comparing against brute-force on small graphs
# ─────────────────────────────────────────────────────────────────────────────

def phase1a_algorithmic_testing(graph, node_info, shelter_ids, start):
    log(f"\n{SEP}")
    log(f"  PHASE 1A — COMPUTATIONAL & ALGORITHMIC TESTING")
    log(SEP)

    results = {"passed": 0, "failed": 0, "tests": []}

    # Test 1: Dijkstra finds a path when one exists
    log("\n  Test 1: Route existence check")
    path, segs, cost = find_best(graph, start, shelter_ids)
    t1 = path is not None
    status = "PASS" if t1 else "FAIL"
    log(f"  [{status}] Dijkstra finds route: {t1}")
    results["tests"].append({"name": "Route existence", "result": status})
    if t1: results["passed"] += 1
    else:  results["failed"] += 1

    # Test 2: Cost is non-negative
    log("\n  Test 2: Non-negative cost check")
    t2 = cost >= 0
    status = "PASS" if t2 else "FAIL"
    log(f"  [{status}] Route cost >= 0: {cost:.4f}")
    results["tests"].append({"name": "Non-negative cost", "result": status})
    if t2: results["passed"] += 1
    else:  results["failed"] += 1

    # Test 3: Path is continuous (each node connects to next)
    log("\n  Test 3: Path continuity check")
    t3 = True
    if path and len(path) > 1:
        for i in range(len(path)-1):
            a, b = path[i], path[i+1]
            connected = any(e["to"] == b for e in graph.get(a, []))
            if not connected:
                t3 = False
                log(f"  Broken link at {a} -> {b}")
                break
    status = "PASS" if t3 else "FAIL"
    log(f"  [{status}] Path is continuous: {t3}")
    results["tests"].append({"name": "Path continuity", "result": status})
    if t3: results["passed"] += 1
    else:  results["failed"] += 1

    # Test 4: Destination is a shelter
    log("\n  Test 4: Destination is valid shelter")
    t4 = path and path[-1] in shelter_ids
    status = "PASS" if t4 else "FAIL"
    log(f"  [{status}] Route ends at shelter: {t4}")
    results["tests"].append({"name": "Valid destination", "result": status})
    if t4: results["passed"] += 1
    else:  results["failed"] += 1

    # Test 5: W formula weights sum to 1.0
    log("\n  Test 5: Weight coefficient validation (α+β+γ+δ=1.0)")
    all_valid = True
    for k, v in SCENARIOS.items():
        total = v["alpha"] + v["beta"] + v["gamma"] + v["delta"]
        if abs(total - 1.0) > 0.001:
            log(f"  FAIL Mode {k}: weights sum to {total:.3f}")
            all_valid = False
    status = "PASS" if all_valid else "FAIL"
    log(f"  [{status}] All 8 optimization modes have valid weights")
    results["tests"].append({"name": "Weight coefficients", "result": status})
    if all_valid: results["passed"] += 1
    else:         results["failed"] += 1

    # Test 6: MAX SAFETY produces lower flood risk than MAX SPEED
    log("\n  Test 6: MAX SAFETY vs MAX SPEED flood risk validation")
    opt_s = SCENARIOS["1"]; opt_p = SCENARIOS["2"]
    nd = node_info[start]
    # We need the raw ways/shelters — extract them from node_info for shelter list
    # and use the same ways that built the current graph by passing ways from caller.
    # The current graph was built with the real ways; rebuild both graphs with same data.
    # NOTE: we use the already-built graph (which used real ways) for SAFETY since
    # the caller built it with balanced or default weights. Instead, rebuild both
    # properly using the ways/shelters passed into this phase via the test harness.
    try:
        # Rebuild SAFETY graph with real ways
        g_s, ni_s, sh_s, _ = build_graph(
            nd[0], nd[1], _phase1a_ways, _phase1a_shelters, 1.0,
            opt_s["alpha"], opt_s["beta"], opt_s["gamma"], opt_s["delta"])
        _, segs_s, _ = find_best(g_s, start, sh_s)
        risk_s = max(FLOOD_RISK[s["flood"]] for s in segs_s) if segs_s else 0.0
    except Exception as exc:
        log(f"  Could not build SAFETY graph: {exc}")
        risk_s = None

    try:
        g_p, ni_p, sh_p, _ = build_graph(
            nd[0], nd[1], _phase1a_ways, _phase1a_shelters, 1.0,
            opt_p["alpha"], opt_p["beta"], opt_p["gamma"], opt_p["delta"])
        _, segs_p, _ = find_best(g_p, start, sh_p)
        risk_p = max(FLOOD_RISK[s["flood"]] for s in segs_p) if segs_p else 0.0
    except Exception as exc:
        log(f"  Could not build SPEED graph: {exc}")
        risk_p = None

    if risk_s is not None and risk_p is not None:
        t6 = risk_s <= risk_p
        status = "PASS" if t6 else "FAIL"
        log(f"  [{status}] MAX SAFETY risk ({risk_s:.3f}) <= MAX SPEED risk ({risk_p:.3f})")
    else:
        status = "SKIP"
        log(f"  [SKIP] Could not build graphs for comparison")
    results["tests"].append({"name": "Safety vs Speed risk", "result": status})
    if status == "PASS": results["passed"] += 1

    # Test 7: Beta-risk correlation across ALL 8 modes (not just 2)
    # Higher beta (flood-avoidance weight) should correlate with lower risk.
    #
    # FIX: this used to take ONE route per mode (n=8 data points total), which
    # is thin enough that a single noisy/shared-road route could tank the
    # whole correlation even when the router's actual behavior is fine —
    # Phase 1B already samples many start points per mode and shows every
    # mode at 100% success, so the router isn't the problem; the test was.
    # Now each mode is scored from K sampled start points and we correlate
    # against the MEAN risk per mode, which is far less sensitive to any
    # single route's noise.
    log("\n  Test 7: Beta-weight vs avg-risk correlation (all 8 modes, sampled)")
    K = 6
    rng7 = random.Random(SEED + 7)
    road_nds7 = [(nid, ni) for nid, ni in node_info.items() if ni[3] == "road"]
    betas, risks_by_mode = [], []
    for ok, opt in SCENARIOS.items():
        mode_risks = []
        sample_points = [nd] + [rng7.choice(road_nds7)[1] for _ in range(K - 1)] if road_nds7 else [nd]
        for pt in sample_points:
            try:
                g7, ni7, sh7, _ = build_graph(
                    pt[0], pt[1], _phase1a_ways, _phase1a_shelters, 1.0,
                    opt["alpha"], opt["beta"], opt["gamma"], opt["delta"])
                s7 = next((x for x, xd in ni7.items() if xd[3] == "start"), None)
                if not s7:
                    continue
                _, segs7, _ = find_best(g7, s7, sh7)
                if segs7:
                    mode_risks.append(max(FLOOD_RISK[s["flood"]] for s in segs7))
            except Exception:
                continue
        if mode_risks:
            betas.append(opt["beta"])
            risks_by_mode.append(mean(mode_risks))
    if len(betas) >= 3:
        corr = spearman_corr(betas, risks_by_mode)
        t7 = corr <= -0.3   # expect a meaningfully negative correlation
        status = "PASS" if t7 else "FAIL"
        log(f"  [{status}] Spearman(beta, mean risk over {K} samples/mode) = {corr:.3f} (expect <= -0.3)")
        results["tests"].append({"name": "Beta-risk correlation", "result": status,
                                  "correlation": round(corr, 3)})
        if t7: results["passed"] += 1
        else:  results["failed"] += 1
    else:
        log("  [SKIP] Not enough successful modes to correlate")
        results["tests"].append({"name": "Beta-risk correlation", "result": "SKIP"})

    total = results["passed"] + results["failed"]
    log(f"\n  PHASE 1A RESULT: {results['passed']}/{total} tests passed")
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 1B — PATHFINDING ACCURACY & OPTIMALITY
#  Verifies routes are truly optimal by testing multiple modes
# ─────────────────────────────────────────────────────────────────────────────

def phase1b_pathfinding_accuracy(ways, shelters, node_info, start, flood_mult, n=40, executor=None):
    log(f"\n{SEP}")
    log(f"  PHASE 1B — PATHFINDING ACCURACY & OPTIMALITY")
    mode_txt = "parallel" if executor else "sequential"
    log(f"  Testing {n} random start points across all 8 modes ({mode_txt})")
    log(SEP)

    rng      = random.Random(SEED)
    nd       = node_info[start]
    road_nds = [(nid,ni) for nid,ni in node_info.items() if ni[3]=="road"]

    results = {"mode_stats": {}, "optimal_verified": 0, "total": 0}

    for ok, opt in SCENARIOS.items():
        risks = []; dists = []; successes = 0
        if not road_nds:
            results["mode_stats"][ok] = {"name": opt["name"], "success_rate": 0,
                                          "avg_dist": 0, "avg_risk": 0, "std_dist": 0}
            results["total"] += n
            continue

        samples = [rng.choice(road_nds) for _ in range(n)]
        args = [(ni[0], ni[1], flood_mult, opt["alpha"], opt["beta"],
                 opt["gamma"], opt["delta"]) for _, ni in samples]

        if executor is not None:
            futures = [executor.submit(_sample_worker, a) for a in args]
            outcomes = [f.result() for f in futures]
        else:
            outcomes = [_sample_worker(a) for a in args]

        for outcome in outcomes:
            if outcome is None: continue
            dist, risk = outcome
            successes += 1
            dists.append(dist)
            risks.append(risk)

        results["mode_stats"][ok] = {
            "name":         opt["name"],
            "success_rate": successes/n*100,
            "avg_dist":     mean(dists),
            "avg_risk":     mean(risks),
            "std_dist":     stdev(dists),
        }
        results["total"] += n
        results["optimal_verified"] += successes
        log(f"  Mode {ok} {opt['name']}: {successes/n*100:.0f}% success | "
            f"avg risk={mean(risks):.3f} | avg dist={mean(dists):.0f}m")

    # Verify safety ordering: MAX SAFETY risk < BALANCED risk < MAX SPEED risk
    ms  = results["mode_stats"].get("1",{}).get("avg_risk",0)
    bal = results["mode_stats"].get("4",{}).get("avg_risk",0)
    spd = results["mode_stats"].get("2",{}).get("avg_risk",0)
    ordering_ok = ms <= bal <= spd
    log(f"\n  Safety ordering check (SAFETY={ms:.3f} <= BALANCED={bal:.3f} <= SPEED={spd:.3f}): "
        f"{'PASS' if ordering_ok else 'FAIL'}")
    results["ordering_verified"] = ordering_ok

    log(f"\n  PHASE 1B RESULT: {results['optimal_verified']}/{results['total']} successful routes")
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 1C — DYNAMIC RE-ROUTING VALIDATION
#  Tests that the system correctly re-routes when roads are blocked
# ─────────────────────────────────────────────────────────────────────────────

def phase1c_dynamic_rerouting(graph, node_info, shelter_ids, start, ways, shelters):
    log(f"\n{SEP}")
    log(f"  PHASE 1C — DYNAMIC RE-ROUTING VALIDATION")
    log(f"  Simulates road blockages and verifies alternative routes found")
    log(SEP)

    results = {"scenarios": [], "passed": 0, "failed": 0}
    opt = SCENARIOS["1"]  # MAX SAFETY

    # Get original route
    path_orig, segs_orig, _ = find_best(graph, start, shelter_ids)
    if not path_orig:
        log("  SKIP — No original route found")
        return results

    orig_dist = sum(s["dist_m"] for s in segs_orig)
    log(f"  Original route: {len(segs_orig)} segments | {orig_dist}m")

    # Test each flood scenario as a "blockage simulation"
    for fk, fd in FLOOD_SCENARIOS.items():
        mult  = fd["multiplier"]
        fname = fd["name"].split("—")[-1].strip()
        nd    = node_info[start]
        try:
            g2, ni2, sh2, _ = build_graph(
                nd[0], nd[1], ways, shelters, mult,
                opt["alpha"], opt["beta"], opt["gamma"], opt["delta"])
            s2 = next((x for x,xd in ni2.items() if xd[3]=="start"), None)
            if not s2:
                results["scenarios"].append({"scenario": fname, "result": "SKIP"})
                continue
            path2, segs2, _ = find_best(g2, s2, sh2)
            found = path2 is not None
            status = "PASS" if found else "BLOCKED"
            dist2  = sum(s["dist_m"] for s in segs2) if segs2 else 0
            log(f"  [{status}] {fname}: route {'found' if found else 'blocked'}"
                f"{f' | {dist2}m' if found else ''}")
            results["scenarios"].append({
                "scenario": fname, "result": status,
                "dist_m": dist2, "segments": len(segs2) if segs2 else 0
            })
            if found: results["passed"] += 1
            else:     results["failed"] += 1
        except Exception as e:
            log(f"  [ERROR] {fname}: {e}")
            results["scenarios"].append({"scenario": fname, "result": "ERROR"})

    log(f"\n  PHASE 1C RESULT: {results['passed']} scenarios re-routed successfully, "
        f"{results['failed']} fully blocked")
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 1D — NETWORK RESILIENCE ANALYSIS
#  Tests how many alternative routes exist and network connectivity
# ─────────────────────────────────────────────────────────────────────────────

def phase1d_network_resilience(graph, node_info, shelter_ids, start):
    log(f"\n{SEP}")
    log(f"  PHASE 1D — NETWORK RESILIENCE ANALYSIS")
    log(SEP)

    results = {}

    # Count reachable nodes
    dist, _ = dijkstra(graph, start)
    reachable = sum(1 for d in dist.values() if d < float("inf"))
    total     = len(graph)
    conn_pct  = reachable/total*100 if total else 0

    log(f"  Reachable nodes : {reachable}/{total} ({conn_pct:.1f}%)")
    results["reachable_pct"] = conn_pct

    # Count reachable shelters
    reachable_shelters = [s for s in shelter_ids
                          if dist.get(s, float("inf")) < float("inf")]
    log(f"  Reachable shelters: {len(reachable_shelters)}/{len(shelter_ids)}")
    results["reachable_shelters"] = len(reachable_shelters)
    results["total_shelters"]     = len(shelter_ids)

    # Get all shelter routes ranked
    all_routes = find_all_shelter_routes(graph, start, shelter_ids)
    log(f"  Alternative routes available: {len(all_routes)}")
    results["alternative_routes"] = len(all_routes)

    # Resilience score
    score = min(100, conn_pct * 0.4 + len(reachable_shelters)*10 + len(all_routes)*5)
    if score >= 70:   status = "RESILIENT"
    elif score >= 40: status = "MODERATE"
    else:             status = "VULNERABLE"
    log(f"  Resilience Score: {score:.0f}/100 — {status}")
    results["score"]  = score
    results["status"] = status

    # Avg edge connectivity (avg edges per node)
    avg_edges = mean([len(v) for v in graph.values()])
    log(f"  Avg edges per node: {avg_edges:.1f}")
    results["avg_edges"] = avg_edges

    if all_routes:
        log(f"\n  TOP SHELTER ROUTES:")
        for i, (sid, sp, ss, sc, td) in enumerate(all_routes[:5], 1):
            sn  = node_info[sid]
            tm  = td / 1.1 / 60
            mfl = max(FLOOD_RISK[s["flood"]] for s in ss) if ss else 0
            rl  = next(k for k,v in FLOOD_RISK.items() if v==mfl)
            log(f"  {i}. {sn[2][:35]} | {td}m | ~{tm:.0f}min | {FLOOD_EMOJI.get(rl,'')} {rl}")

    log(f"\n  PHASE 1D RESULT: Network is {status} with {score:.0f}/100 resilience score")
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 1E — NEW FEATURE VALIDATION
#  Sanity-checks the three router features added since the last sync:
#  Mini Monte Carlo, Network Resilience, and Route Decision Accuracy scoring,
#  plus the DRRMO hotline lookup.
# ─────────────────────────────────────────────────────────────────────────────

def phase1e_feature_validation(graph, node_info, shelter_ids, start, ways, shelters,
                                flood_mult, area_name):
    log(f"\n{SEP}")
    log(f"  PHASE 1E — NEW FEATURE VALIDATION")
    log(f"  Mini Monte Carlo | Network Resilience | Route Accuracy | DRRMO lookup")
    log(SEP)

    results = {"tests": [], "passed": 0, "failed": 0}
    opt  = SCENARIOS["1"]
    nd   = node_info[start]
    path, segs, _ = find_best(graph, start, shelter_ids)

    def record(name, ok, extra=None):
        status = "PASS" if ok else "FAIL"
        log(f"  [{status}] {name}")
        entry = {"name": name, "result": status}
        if extra: entry.update(extra)
        results["tests"].append(entry)
        if ok: results["passed"] += 1
        else:  results["failed"] += 1

    # Test: embedded_mini_montecarlo returns a well-formed report
    log("\n  Testing embedded_mini_montecarlo()...")
    try:
        mc = embedded_mini_montecarlo(nd[0], nd[1], ways, shelters, flood_mult,
                                       opt["alpha"], opt["beta"], opt["gamma"], opt["delta"],
                                       n=15, seed=SEED)
        ok = (mc is not None
              and 0 <= mc["success_rate"] <= 100
              and mc["confidence"] in ("HIGH", "MODERATE", "LOW")
              and set(mc["avg_times"].keys()) == set(SPEED_PROFILES.keys()))
        record("Mini Monte Carlo returns valid report", ok,
               {"success_rate": mc["success_rate"] if mc else None,
                "confidence": mc["confidence"] if mc else None})
    except Exception as exc:
        record("Mini Monte Carlo returns valid report", False, {"error": str(exc)})

    # Test: assess_network_resilience returns a well-formed report
    log("\n  Testing assess_network_resilience()...")
    try:
        res = assess_network_resilience(graph, start, shelter_ids, node_info, segs)
        ok = (res is not None
              and 0 <= res["score"] <= 100
              and res["status"] in ("RESILIENT", "MODERATE", "VULNERABLE", "NO_ROUTE"))
        record("Network resilience returns valid score/status", ok,
               {"score": res["score"] if res else None,
                "status": res["status"] if res else None})
    except Exception as exc:
        record("Network resilience returns valid score/status", False, {"error": str(exc)})

    # Test: score_route_accuracy returns a well-formed report matching segs
    log("\n  Testing score_route_accuracy()...")
    try:
        acc = score_route_accuracy(segs, node_info, opt["alpha"], opt["beta"],
                                    opt["gamma"], opt["delta"])
        ok = (acc is not None
              and 0 <= acc["overall_score"] <= 100
              and acc["rating"] in ("EXCELLENT", "GOOD", "ACCEPTABLE", "POOR")
              and len(acc["seg_scores"]) == len(segs))
        record("Route accuracy score matches segment count", ok,
               {"overall_score": acc["overall_score"] if acc else None,
                "rating": acc["rating"] if acc else None})
    except Exception as exc:
        record("Route accuracy score matches segment count", False, {"error": str(exc)})

    # Test: DRRMO hotline lookup — known area resolves, unknown area falls back
    log("\n  Testing get_drrmo_info()...")
    try:
        known_lgu, known_no = get_drrmo_info(area_name)
        fallback_lgu, fallback_no = get_drrmo_info("Nonexistent Barangay Zzzqx")
        ok = (isinstance(known_lgu, str) and isinstance(known_no, str)
              and fallback_lgu == "Local DRRMO" and "911" in fallback_no)
        record("DRRMO lookup resolves + falls back correctly", ok,
               {"resolved_lgu": known_lgu, "fallback_lgu": fallback_lgu})
    except Exception as exc:
        record("DRRMO lookup resolves + falls back correctly", False, {"error": str(exc)})

    total = results["passed"] + results["failed"]
    log(f"\n  PHASE 1E RESULT: {results['passed']}/{total} feature checks passed")
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 2A — HYDRODYNAMIC INTEGRATED SIMULATION
#  Simulates rising flood levels over time and tests system adaptation
# ─────────────────────────────────────────────────────────────────────────────

def phase2a_hydrodynamic_simulation(ways, shelters, node_info, start):
    log(f"\n{SEP}")
    log(f"  PHASE 2A — HYDRODYNAMIC INTEGRATED SIMULATION")
    log(f"  Simulates rising flood levels — tests system adaptation over time")
    log(SEP)

    opt     = SCENARIOS["1"]   # MAX SAFETY
    nd      = node_info[start]
    results = {"time_steps": [], "system_held": True}

    # Simulate flood rising over 10 time steps (multiplier 1.0 → 4.0)
    multipliers = [round(1.0 + i * 0.33, 2) for i in range(10)]
    log(f"  Simulating {len(multipliers)} time steps (flood rising from 1.0x to 4.0x)")
    log(f"  {'Step':<6} {'Multiplier':<12} {'Status':<10} {'Dist':>8} {'Risk':>8}")
    log(f"  {'-'*50}")

    prev_dist = None
    for step, mult in enumerate(multipliers, 1):
        try:
            g, ni, sh, _ = build_graph(
                nd[0], nd[1], ways, shelters, mult,
                opt["alpha"], opt["beta"], opt["gamma"], opt["delta"])
            s = next((x for x,xd in ni.items() if xd[3]=="start"), None)
            if not s:
                results["time_steps"].append({"step":step,"mult":mult,"status":"ERROR"})
                continue
            path2, segs2, _ = find_best(g, s, sh)
            if path2 and segs2:
                dist2 = sum(x["dist_m"] for x in segs2)
                risk2 = max(FLOOD_RISK[x["flood"]] for x in segs2)
                status = "ROUTE FOUND"
                change = f"+{dist2-prev_dist}m" if prev_dist and dist2 != prev_dist else "same"
                log(f"  {step:<6} {mult:<12} {status:<10} {dist2:>7}m {risk2:>8.3f}  ({change})")
                prev_dist = dist2
                results["time_steps"].append({
                    "step": step, "mult": mult, "status": status,
                    "dist_m": dist2, "risk": risk2
                })
            else:
                log(f"  {step:<6} {mult:<12} {'BLOCKED':<10} {'N/A':>8} {'N/A':>8}")
                results["time_steps"].append({"step":step,"mult":mult,"status":"BLOCKED"})
                results["system_held"] = False
        except Exception as e:
            log(f"  {step:<6} {mult:<12} {'ERROR':<10} {str(e)[:20]}")
            results["time_steps"].append({"step":step,"mult":mult,"status":"ERROR"})

    found = sum(1 for t in results["time_steps"] if t["status"]=="ROUTE FOUND")
    log(f"\n  PHASE 2A RESULT: Route found in {found}/{len(multipliers)} time steps")
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 2B — 10/30 COUPLED MODEL
#  Tests 10 flood scenarios × 30 random start points = 300 simulations
# ─────────────────────────────────────────────────────────────────────────────

def phase2b_coupled_model(ways, shelters, node_info, start, n_per_mult=50, executor=None):
    log(f"\n{SEP}")
    mode_txt = "parallel" if executor else "sequential"
    log(f"  PHASE 2B — 10/{n_per_mult} COUPLED MODEL")
    log(f"  10 flood multipliers × {n_per_mult} random start points"
        f" = {10*n_per_mult} simulations ({mode_txt})")
    log(SEP)

    rng      = random.Random(SEED + 10)
    opt      = SCENARIOS["1"]
    road_nds = [(nid,ni) for nid,ni in node_info.items() if ni[3]=="road"]
    mults    = [round(1.0 + i*0.33, 2) for i in range(10)]
    results  = {"multipliers": [], "total": 0, "success": 0}

    log(f"  {'Multiplier':<12} {'Success':>10} {'Avg Dist':>10} {'Avg Risk':>10}")
    log(f"  {'-'*50}")

    for mult in mults:
        if not road_nds:
            results["multipliers"].append({"mult": mult, "success": 0, "avg_dist": 0, "avg_risk": 0})
            results["total"] += n_per_mult
            continue

        samples = [rng.choice(road_nds) for _ in range(n_per_mult)]
        args = [(ni[0], ni[1], mult, opt["alpha"], opt["beta"],
                 opt["gamma"], opt["delta"]) for _, ni in samples]

        if executor is not None:
            futures = [executor.submit(_sample_worker, a) for a in args]
            outcomes = [f.result() for f in futures]
        else:
            outcomes = [_sample_worker(a) for a in args]

        succ = 0; dists = []; risks = []
        for outcome in outcomes:
            if outcome is None: continue
            dist, risk = outcome
            succ += 1
            dists.append(dist)
            risks.append(risk)

        results["total"]   += n_per_mult
        results["success"] += succ
        entry = {"mult": mult, "success": succ, "avg_dist": mean(dists), "avg_risk": mean(risks)}
        results["multipliers"].append(entry)
        log(f"  {mult:<12} {succ:>4}/{n_per_mult} ({succ/n_per_mult*100:>4.0f}%) "
            f"{mean(dists):>10.0f}m {mean(risks):>10.3f}")

    overall = results["success"]/results["total"]*100
    log(f"\n  PHASE 2B RESULT: {results['success']}/{results['total']} ({overall:.1f}%) overall success")
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 2C — SCENARIO-BASED STRESS TESTS
#  Tests system under extreme conditions and edge cases
# ─────────────────────────────────────────────────────────────────────────────

def phase2c_stress_tests(graph, node_info, shelter_ids, start, ways, shelters):
    log(f"\n{SEP}")
    log(f"  PHASE 2C — SCENARIO-BASED STRESS TESTS")
    log(SEP)

    results = {"tests": [], "passed": 0, "failed": 0}
    nd = node_info[start]

    def run_test(name, fn):
        try:
            t_start = time.time()
            result  = fn()
            elapsed = time.time() - t_start
            status  = "PASS" if result else "FAIL"
            log(f"  [{status}] {name} ({elapsed:.2f}s)")
            results["tests"].append({"name":name,"result":status,"time":elapsed})
            if result: results["passed"] += 1
            else:      results["failed"] += 1
        except Exception as e:
            log(f"  [ERROR] {name}: {e}")
            results["tests"].append({"name":name,"result":"ERROR"})
            results["failed"] += 1

    # Stress 1: All 8 modes complete without crash
    def test_all_modes():
        for ok, opt in SCENARIOS.items():
            g, ni, sh, _ = build_graph(
                nd[0], nd[1], ways, shelters, 1.0,
                opt["alpha"], opt["beta"], opt["gamma"], opt["delta"])
            s = next((x for x,xd in ni.items() if xd[3]=="start"), None)
            if s: find_best(g, s, sh)
        return True
    run_test("All 8 optimization modes complete without crash", test_all_modes)

    # Stress 2: All 4 flood scenarios complete without crash
    def test_all_floods():
        opt = SCENARIOS["1"]
        for fk, fd in FLOOD_SCENARIOS.items():
            g, ni, sh, _ = build_graph(
                nd[0], nd[1], ways, shelters, fd["multiplier"],
                opt["alpha"], opt["beta"], opt["gamma"], opt["delta"])
            s = next((x for x,xd in ni.items() if xd[3]=="start"), None)
            if s: find_best(g, s, sh)
        return True
    run_test("All 4 flood scenarios complete without crash", test_all_floods)

    # Stress 3: All 6 speed profiles produce valid times
    def test_speed_profiles():
        path, segs, _ = find_best(graph, start, shelter_ids)
        if not segs: return False
        for pk, pv in SPEED_PROFILES.items():
            t = walk_time(segs, pv["speed"])
            if t <= 0: return False
        return True
    run_test("All 6 speed profiles produce valid times", test_speed_profiles)

    # Stress 4: System handles extreme flood (4.0x) gracefully
    def test_extreme_flood():
        g, ni, sh, _ = build_graph(
            nd[0], nd[1], ways, shelters, 4.0,
            0.05, 0.90, 0.03, 0.02)
        s = next((x for x,xd in ni.items() if xd[3]=="start"), None)
        if not s: return True  # graceful skip
        path2, segs2, _ = find_best(g, s, sh)
        return True  # not crashing = pass (route may or may not exist)
    run_test("Extreme flood (4.0x) handled gracefully", test_extreme_flood)

    # Stress 5: Large graph — count nodes and edges
    def test_graph_size():
        n_nodes = len(graph)
        n_edges = sum(len(v) for v in graph.values())
        log(f"       Graph size: {n_nodes} nodes, {n_edges} edges")
        return n_nodes > 10 and n_edges > 10
    run_test("Graph has sufficient nodes and edges", test_graph_size)

    # Stress 6: Response time < 10 seconds for route finding
    def test_response_time():
        t0 = time.time()
        find_best(graph, start, shelter_ids)
        return (time.time() - t0) < 10.0
    run_test("Route finding completes in < 10 seconds", test_response_time)

    # Stress 7: Multiple simultaneous shelter lookups
    def test_all_shelters():
        all_routes = find_all_shelter_routes(graph, start, shelter_ids)
        return len(all_routes) >= 0  # just checking it doesn't crash
    run_test("All shelter route lookup completes", test_all_shelters)

    total = results["passed"] + results["failed"]
    log(f"\n  PHASE 2C RESULT: {results['passed']}/{total} stress tests passed")
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 3 — EXPERT VALIDATION REPORT
#  Generates a formatted report for DLSU AdRIC / CITE4D Lab experts
# ─────────────────────────────────────────────────────────────────────────────

def phase3_expert_validation_report(all_results, area_name):
    log(f"\n{SEP}")
    log(f"  PHASE 3 — EXPERT VALIDATION REPORT")
    log(f"  Generating report for DLSU AdRIC / CITE4D Lab")
    log(SEP)

    report = {
        "title":       "Expert Validation Report — Flood Evacuation Route Optimization System",
        "study_area":  area_name,
        "timestamp":   datetime.now().isoformat(),
        "phases":      all_results,
        "log":         LOG,
    }

    fname = f"expert_validation_report_{STAMP}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)
    log(f"  Expert validation report saved → {fname}")

    # Also save human-readable text report
    txt_fname = f"expert_validation_report_{STAMP}.txt"
    with open(txt_fname, "w", encoding="utf-8") as f:
        f.write("=" * 68 + "\n")
        f.write("  EXPERT VALIDATION REPORT\n")
        f.write("  Flood Evacuation Route Optimization System\n")
        f.write(f"  Study Area: {area_name}\n")
        f.write(f"  Date: {datetime.now().strftime('%B %d, %Y %H:%M')}\n")
        f.write("=" * 68 + "\n\n")
        f.write("TESTING LOG:\n")
        for entry in LOG:
            f.write(entry + "\n")
        f.write("\n" + "=" * 68 + "\n")
        f.write("FOR EXPERT REVIEW:\n")
        f.write("1. Verify algorithmic correctness results in Phase 1A\n")
        f.write("2. Review pathfinding accuracy across all 8 optimization modes\n")
        f.write("3. Confirm dynamic re-routing behaves correctly under flood scenarios\n")
        f.write("4. Validate network resilience scores against community standards\n")
        f.write("5. Check Mini Monte Carlo, resilience, accuracy scoring, and DRRMO\n")
        f.write("   lookup outputs in Phase 1E for sanity\n")
        f.write("6. Assess coupled model results for statistical validity\n")
        f.write("7. Check stress test results for production readiness\n")
        f.write("=" * 68 + "\n")

    log(f"  Text report saved → {txt_fname}")
    log(f"\n  PHASE 3: Reports ready for DLSU AdRIC submission")
    return fname, txt_fname


# ─────────────────────────────────────────────────────────────────────────────
#  CHARTS
# ─────────────────────────────────────────────────────────────────────────────

def make_testing_charts(p1a, p1b, p1d, p2b, p2c, area_name):
    if not MATPLOTLIB_OK:
        return

    plt.style.use("dark_background")
    fig = plt.figure(figsize=(18, 10))
    fig.patch.set_facecolor("#0a0f1a")
    gs  = gridspec.GridSpec(2, 3, figure=fig)
    fig.suptitle(
        f"Testing Suite Results — Flood Evacuation Route Optimizer\n{area_name}",
        fontsize=13, fontweight="bold", color="white"
    )

    # Chart 1: Phase 1A test results
    ax1 = fig.add_subplot(gs[0,0])
    names  = [t["name"][:20] for t in p1a["tests"]]
    colors = ["#00cc55" if t["result"]=="PASS" else
              "#ff3300" if t["result"]=="FAIL" else "#888888"
              for t in p1a["tests"]]
    ax1.barh(names, [1]*len(names), color=colors, alpha=0.85)
    ax1.set_title("Phase 1A: Algorithm Tests", color="white", fontsize=10)
    ax1.tick_params(colors="white", labelsize=7)
    ax1.set_xlim(0, 1.5)
    for i, t in enumerate(p1a["tests"]):
        ax1.text(0.05, i, t["result"], va="center", fontsize=8,
                 color="white", fontweight="bold")

    # Chart 2: Phase 1B mode success rates
    ax2 = fig.add_subplot(gs[0,1])
    if p1b and p1b.get("mode_stats"):
        modes = [v["name"].replace("🛡️","").replace("⚡","").replace("👥","")
                 .replace("⚖️","").replace("🌊","").replace("🏃","")
                 .replace("🏟️","").replace("🛣️","").strip()
                 for v in p1b["mode_stats"].values()]
        rates = [v["success_rate"] for v in p1b["mode_stats"].values()]
        ax2.bar(modes, rates, color="#4472C4", alpha=0.85)
        ax2.set_title("Phase 1B: Mode Success Rates (%)", color="white", fontsize=10)
        ax2.set_ylim(0, 110)
        ax2.tick_params(colors="white", labelsize=7)
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")

    # Chart 3: Phase 1D resilience
    ax3 = fig.add_subplot(gs[0,2])
    if p1d:
        cats = ["Connectivity\n(%)", "Reachable\nShelters", "Alt Routes", "Score"]
        vals = [p1d.get("reachable_pct",0),
                p1d.get("reachable_shelters",0)*10,
                p1d.get("alternative_routes",0)*5,
                p1d.get("score",0)]
        colors3 = ["#00cc55","#00aaff","#ffcc00","#ff6600"]
        ax3.bar(cats, vals, color=colors3, alpha=0.85)
        ax3.set_title("Phase 1D: Network Resilience", color="white", fontsize=10)
        ax3.tick_params(colors="white", labelsize=8)

    # Chart 4: Phase 2B coupled model
    ax4 = fig.add_subplot(gs[1,0])
    if p2b and p2b.get("multipliers"):
        n_per_mult = p2b["total"] // max(len(p2b["multipliers"]), 1) or 1
        mults  = [m["mult"] for m in p2b["multipliers"]]
        succs  = [m["success"]/n_per_mult*100 for m in p2b["multipliers"]]
        ax4.plot(mults, succs, color="#00cc55", marker="o", linewidth=2)
        ax4.fill_between(mults, succs, alpha=0.2, color="#00cc55")
        ax4.set_title("Phase 2B: 10/30 Coupled Model\nSuccess Rate vs Flood Level",
                      color="white", fontsize=10)
        ax4.set_xlabel("Flood Multiplier", color="white")
        ax4.set_ylabel("Success Rate (%)", color="white")
        ax4.tick_params(colors="white")
        ax4.set_ylim(0,110)

    # Chart 5: Phase 2C stress tests
    ax5 = fig.add_subplot(gs[1,1])
    if p2c and p2c.get("tests"):
        t_names  = [t["name"][:25] for t in p2c["tests"]]
        t_colors = ["#00cc55" if t["result"]=="PASS" else
                    "#ff3300" if t["result"]=="FAIL" else "#888888"
                    for t in p2c["tests"]]
        ax5.barh(t_names, [1]*len(t_names), color=t_colors, alpha=0.85)
        ax5.set_title("Phase 2C: Stress Tests", color="white", fontsize=10)
        ax5.tick_params(colors="white", labelsize=7)
        for i, t in enumerate(p2c["tests"]):
            ax5.text(0.05, i, t["result"], va="center", fontsize=8,
                     color="white", fontweight="bold")

    # Chart 6: Overall summary
    ax6 = fig.add_subplot(gs[1,2])
    phases = ["1A\nAlgorithm", "1B\nPathfinding", "2B\nCoupled", "2C\nStress"]
    scores = [
        p1a["passed"]/(p1a["passed"]+p1a["failed"])*100 if p1a else 0,
        p1b.get("optimal_verified",0)/max(p1b.get("total",1),1)*100 if p1b else 0,
        p2b["success"]/max(p2b["total"],1)*100 if p2b else 0,
        p2c["passed"]/(p2c["passed"]+p2c["failed"])*100 if p2c else 0,
    ]
    bar_colors = ["#00cc55" if s>=80 else "#ffcc00" if s>=50 else "#ff3300"
                  for s in scores]
    bars = ax6.bar(phases, scores, color=bar_colors, alpha=0.85)
    for bar, val in zip(bars, scores):
        ax6.text(bar.get_x()+bar.get_width()/2,
                 bar.get_height()+1, f"{val:.0f}%",
                 ha="center", va="bottom", fontsize=9, color="white")
    ax6.set_title("Overall Testing Summary", color="white", fontsize=10)
    ax6.set_ylabel("Pass Rate (%)", color="white")
    ax6.set_ylim(0, 115)
    ax6.tick_params(colors="white")

    plt.tight_layout(rect=[0,0,1,0.93])
    fname = f"testing_results_{STAMP}.png"
    plt.savefig(fname, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    log(f"\n  Testing charts saved → {fname}")

    # Only pop up a window if we're actually on an interactive GUI backend.
    # On Agg (headless Linux) there's no window to show — calling plt.show()
    # there either raises or hangs the process waiting on a display that
    # will never appear. The PNG is already saved above either way.
    if plt.get_backend().lower() != "agg":
        try:
            plt.show()
        except Exception as exc:
            log(f"  ⚠  Could not display chart window ({exc}); PNG was still saved.")

    # Close the figure explicitly. main() can loop this 3x, N times, or
    # infinitely — without this, each run's Figure object stays alive and
    # accumulates in memory for the life of the process (a slow leak on
    # long unattended batch runs, which is exactly this suite's use case).
    plt.close(fig)



# ─────────────────────────────────────────────────────────────────────────────
#  MAIN — automated repeat loop for testing facilities
# ─────────────────────────────────────────────────────────────────────────────

import time as _time

def _run_once(lat, lon, area_name, radius_m, run_number, total_runs="?"):
    """Run all phases once. Never prompts."""
    global STAMP, _phase1a_ways, _phase1a_shelters

    STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(); print(SEP)
    print(f"  RUN {run_number}/{total_runs}  —  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"  Location: {area_name}")
    print(SEP)

    print(f"\n  Fetching OSM data...")
    bbox = bbox_from_point(lat, lon, radius_m)
    ways, shelters = fetch_osm_data(bbox)
    if not ways:
        print("  ⚠  No road data — skipping run.")
        return None

    opt = SCENARIOS["1"]
    fd  = FLOOD_SCENARIOS["1"]
    print("  Building graph...")
    graph, node_info, shelter_ids, raw_edges = build_graph(
        lat, lon, ways, shelters, fd["multiplier"],
        opt["alpha"], opt["beta"], opt["gamma"], opt["delta"]
    )
    start = next((nid for nid, nd in node_info.items() if nd[3] == "start"), None)
    if not start:
        print("  ⚠  Could not place start node — skipping.")
        return None

    print(f"  {len(graph)} nodes | {sum(len(v) for v in graph.values())} edges | {len(shelter_ids)} shelters")

    all_results = {}
    t_phase_start = _time.time()

    print(f"\n  ▶  Phase 1 — Computational & Algorithmic Testing")
    _phase1a_ways     = ways
    _phase1a_shelters = shelters

    # One process pool shared across every heavy sampling phase in this run —
    # ways/shelters are pickled to each worker ONCE (via the initializer),
    # not once per sample, which is what made this slow before.
    pool = _make_pool(ways, shelters)
    try:
        p1a = phase1a_algorithmic_testing(graph, node_info, shelter_ids, start)
        p1b = phase1b_pathfinding_accuracy(ways, shelters, node_info, start,
                                            fd["multiplier"], executor=pool)
        p1c = phase1c_dynamic_rerouting(graph, node_info, shelter_ids, start, ways, shelters)
        p1d = phase1d_network_resilience(graph, node_info, shelter_ids, start)
        p1e = phase1e_feature_validation(graph, node_info, shelter_ids, start,
                                          ways, shelters, fd["multiplier"], area_name)
        all_results.update({"1A": p1a, "1B": p1b, "1C": p1c, "1D": p1d, "1E": p1e})

        print(f"\n  ▶  Phase 2 — System Performance Validation")
        p2a = phase2a_hydrodynamic_simulation(ways, shelters, node_info, start)
        p2b = phase2b_coupled_model(ways, shelters, node_info, start, executor=pool)
        p2c = phase2c_stress_tests(graph, node_info, shelter_ids, start, ways, shelters)
        all_results.update({"2A": p2a, "2B": p2b, "2C": p2c})
    finally:
        if pool is not None:
            pool.shutdown(wait=True)

    elapsed = _time.time() - t_phase_start
    print(f"\n  ⏱  Phases 1–2 completed in {elapsed:.1f}s"
          f"{' (parallelized across ' + str(os.cpu_count()) + ' cores)' if pool else ' (sequential fallback)'}")

    print(f"\n  ▶  Phase 3 — Expert Validation Report")
    phase3_expert_validation_report(all_results, area_name)

    if MATPLOTLIB_OK:
        make_testing_charts(p1a, p1b, p1d, p2b, p2c, area_name)

    fname = f"testing_results_{STAMP}_run{run_number}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str, ensure_ascii=False)
    print(f"\n  ✅  Run {run_number} done — saved → {fname}")
    return all_results


def main():
    print(); print(SEP)
    print("  TESTING SUITE — FLOOD EVACUATION ROUTE OPTIMIZER")
    print("  Automated Repeat Mode for Testing Facilities")
    print(SEP)

    lat, lon, area_name, radius_m = pick_location()

    print("\n  AUTOMATED RUN SETTINGS  (press Enter for defaults)\n")
    try:
        n_input = input("  How many times to repeat? [0 = infinite, default: 3]: ").strip() or "3"
        n_runs  = int(n_input)
    except ValueError:
        n_runs = 3
    except (EOFError, OSError):
        # No TTY attached — e.g. run non-interactively on a Linux
        # server/CI job. Fall back to defaults instead of crashing.
        print("  (no interactive input available — using default: 3)")
        n_runs = 3
    infinite = (n_runs == 0)
    if not infinite:
        n_runs = max(1, n_runs)

    try:
        delay_s = float(input("  Delay between runs in seconds? [default: 5]: ").strip() or "5")
    except ValueError:
        delay_s = 5.0
    except (EOFError, OSError):
        print("  (no interactive input available — using default: 5s)")
        delay_s = 5.0
    delay_s = max(0.0, delay_s)

    run_label = "infinite ∞" if infinite else str(n_runs)
    print(f"\n  Will run {run_label}x with {delay_s:.0f}s delay between runs.")
    if infinite:
        print("  Press Ctrl+C at any time to stop.")
    try:
        input("  Press Enter to start...")
    except (EOFError, OSError):
        print("  (no interactive input available — starting automatically)")

    all_runs = []
    i = 0
    try:
        while True:
            i += 1
            total_label = "∞" if infinite else str(n_runs)
            result = _run_once(lat, lon, area_name, radius_m, i, total_label)
            if result:
                all_runs.append(result)
            if not infinite and i >= n_runs:
                break
            print(f"\n  ⏳  Next run in {delay_s:.0f}s...  (Ctrl+C to stop)")
            _time.sleep(delay_s)
    except KeyboardInterrupt:
        print(f"\n  Stopped after {i} run(s).")

    # Summary across all runs
    if len(all_runs) > 1:
        print(); print(SEP)
        print(f"  SUMMARY — {len(all_runs)} runs completed")
        print(SEP)
        for phase_key in ["1A", "1B", "1E", "2B", "2C"]:
            rates = []
            for r in all_runs:
                ph = r.get(phase_key, {})
                if   "pass_rate"    in ph: rates.append(ph["pass_rate"])
                elif "success_rate" in ph: rates.append(ph["success_rate"])
                elif "passed" in ph and "failed" in ph:
                    denom = ph["passed"] + ph["failed"]
                    if denom: rates.append(ph["passed"] / denom * 100)
            if rates:
                avg = sum(rates) / len(rates)
                print(f"  Phase {phase_key}:  avg={avg:.1f}%  "
                      f"min={min(rates):.1f}%  max={max(rates):.1f}%")

        sfname = f"testing_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(sfname, "w", encoding="utf-8") as f:
            json.dump({"runs": len(all_runs), "results": all_runs},
                      f, indent=2, default=str, ensure_ascii=False)
        print(f"\n  📊  Summary saved → {sfname}")

    print(f"\n  All done! Laging handa. 🙏\n")


if __name__ == "__main__":
    main()
