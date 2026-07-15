"""
=============================================================================
  FLOOD EVACUATION ROUTE OPTIMIZATION SYSTEM — PHILIPPINES EDITION
  W = αD + βR + γC + δP  |  Dijkstra's Algorithm
=============================================================================
  INSTALL:  pip install folium requests geopandas
  RUN:      python ph_evac_router.py
=============================================================================

  NEW FEATURES:
  1. Embedded Mini Monte Carlo — auto-validates route after each search
  2. Network Resilience — when best route is blocked, auto-finds alternatives
  3. Route Decision Accuracy — segment scoring with confidence rating
  4. Improved Web Interface — enhanced HTML map with resilience indicators
  - OSM geometry: exact road curves, no snapping, no straight-line guesses
=============================================================================
"""

import heapq, math, webbrowser, os, time
import folium
import requests

try:
    import geopandas as gpd
    from shapely.geometry import Point
    GEOPANDAS_OK = True
except ImportError:
    GEOPANDAS_OK = False

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
# Multiple Overpass mirrors — tried in order on timeout/error
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REV = "https://nominatim.openstreetmap.org/reverse"
HEADERS       = {"User-Agent": "PhEvacRouter/3.0"}

# ── DRRMO / LGU Emergency Hotlines (major PH cities & municipalities) ─────
# Format: lowercase keywords -> (LGU name, hotline)
DRRMO_HOTLINES = {
    # NCR
    "manila":          ("Manila DRRMO",           "8-527-9657"),
    "quezon":          ("Quezon City DRRMO",       "8-925-0000"),
    "makati":          ("Makati DRRMO",            "8-870-0261"),
    "pasig":           ("Pasig DRRMO",             "8-643-0109"),
    "taguig":          ("Taguig DRRMO",            "8-838-2672"),
    "marikina":        ("Marikina DRRMO",          "8-646-2536"),
    "pasay":           ("Pasay DRRMO",             "8-551-1516"),
    "caloocan":        ("Caloocan DRRMO",          "8-288-8817"),
    "malabon":         ("Malabon DRRMO",           "8-281-6701"),
    "mandaluyong":     ("Mandaluyong DRRMO",       "8-532-3751"),
    "muntinlupa":      ("Muntinlupa DRRMO",        "8-862-2911"),
    "paranaque":       ("Parañaque DRRMO",         "8-826-0633"),
    "las pinas":       ("Las Piñas DRRMO",         "8-871-0442"),
    "valenzuela":      ("Valenzuela DRRMO",        "8-293-8891"),
    "navotas":         ("Navotas DRRMO",           "8-281-0203"),
    "san juan":        ("San Juan DRRMO",          "8-725-5710"),
    "pateros":         ("Pateros DRRMO",           "8-641-1975"),
    # Bulacan
    "san jose del monte": ("SJDM DRRMO",          "(044) 760-3091"),
    "sjdm":            ("SJDM DRRMO",              "(044) 760-3091"),
    "gumaoc":          ("SJDM DRRMO",              "(044) 760-3091"),
    "malolos":         ("Malolos CDRRMO",          "(044) 796-1000"),
    "meycauayan":      ("Meycauayan CDRRMO",       "(044) 840-1892"),
    "marilao":         ("Marilao MDRRMO",          "(044) 711-1290"),
    "bocaue":          ("Bocaue MDRRMO",           "(044) 694-2016"),
    "baliwag":         ("Baliwag MDRRMO",          "(044) 766-2765"),
    "santa maria":     ("Sta. Maria MDRRMO",       "(044) 641-0047"),
    "bulakan":         ("Bulakan MDRRMO",          "(044) 762-3143"),
    "calumpit":        ("Calumpit MDRRMO",         "(044) 675-2524"),
    "hagonoy":         ("Hagonoy MDRRMO",          "(044) 791-1284"),
    "plaridel":        ("Plaridel MDRRMO",         "(044) 794-3131"),
    # Cavite
    "bacoor":          ("Bacoor CDRRMO",           "(046) 417-5100"),
    "imus":            ("Imus CDRRMO",             "(046) 471-4444"),
    "dasmarinas":      ("Dasmariñas CDRRMO",       "(046) 424-0901"),
    "general trias":   ("Gen. Trias CDRRMO",       "(046) 509-0000"),
    "kawit":           ("Kawit MDRRMO",            "(046) 412-3218"),
    # Laguna
    "san pablo":       ("San Pablo CDRRMO",        "(049) 562-5730"),
    "calamba":         ("Calamba CDRRMO",          "(049) 545-1234"),
    "santa rosa":      ("Sta. Rosa CDRRMO",        "(049) 534-2245"),
    "binan":           ("Biñan CDRRMO",            "(049) 511-4010"),
    "cabuyao":         ("Cabuyao CDRRMO",          "(049) 531-0000"),
    # Rizal
    "antipolo":        ("Antipolo CDRRMO",         "(02) 8697-5000"),
    "cainta":          ("Cainta MDRRMO",           "(02) 8682-3009"),
    "taytay":          ("Taytay MDRRMO",           "(02) 8660-1246"),
    "angono":          ("Angono MDRRMO",           "(02) 8651-0306"),
    # Cebu
    "cebu":            ("Cebu City DRRMO",         "(032) 255-3450"),
    "mandaue":         ("Mandaue CDRRMO",          "(032) 344-5785"),
    "lapu-lapu":       ("Lapu-Lapu CDRRMO",        "(032) 340-5237"),
    # Davao
    "davao":           ("Davao City DRRMO",        "(082) 241-1000"),
    # Pampanga
    "angeles":         ("Angeles CDRRMO",          "(045) 888-0101"),
    "san fernando":    ("San Fernando CDRRMO",     "(045) 961-2665"),
    "mabalacat":       ("Mabalacat CDRRMO",        "(045) 893-1001"),
    # Iloilo
    "iloilo":          ("Iloilo City DRRMO",       "(033) 337-5765"),
    # Bacolod
    "bacolod":         ("Bacolod CDRRMO",          "(034) 434-0904"),
    # Cagayan de Oro
    "cagayan de oro":  ("CDO DRRMO",               "(088) 857-5268"),
    # Zamboanga
    "zamboanga":       ("Zamboanga CDRRMO",        "(062) 991-0001"),
}

def get_drrmo_info(area_name):
    """
    Return (lgu_name, hotline) for the given area name string.
    Falls back to generic NDRRMC if no match found.
    """
    area_lower = area_name.lower()
    for keyword, info in DRRMO_HOTLINES.items():
        if keyword in area_lower:
            return info
    return ("Local DRRMO", "8-911 (NDRRMC)")

SPEED_MS  = 1.1   # default walking speed m/s

# ── Speed profiles (like Google Maps transport modes) ─────────────────────────
SPEED_PROFILES = {
    "1": {"name": "🏃  Running",          "speed": 2.5, "desc": "Healthy adult running"},
    "2": {"name": "🚶  Walking (default)", "speed": 1.1, "desc": "Normal adult walking"},
    "3": {"name": "👨‍👩‍👧  With children",    "speed": 0.8, "desc": "Adults with young children"},
    "4": {"name": "👴  Elderly",           "speed": 0.6, "desc": "Senior citizens / older adults"},
    "5": {"name": "♿  PWD / Disabled",    "speed": 0.4, "desc": "Wheelchair / limited mobility"},
    "6": {"name": "👥  Group / Crowd",     "speed": 0.7, "desc": "Mass evacuation crowd movement"},
}
K_NEAREST = 4
SEP       = "=" * 68

HIGHWAY_FLOOD_RISK = {
    "trunk":         0.05, "trunk_link":      0.05,
    "primary":       0.10, "primary_link":    0.10,
    "secondary":     0.15, "secondary_link":  0.15,
    "tertiary":      0.20, "tertiary_link":   0.20,
    "residential":   0.30,
    "unclassified":  0.35,
    "service":       0.40,
    "living_street": 0.35,
    "footway":       0.45,
    "path":          0.50,
    "track":         0.55,
}

ROAD_COLOR  = {"DRY":"#00ff88","LOW":"#44dd77","MODERATE":"#ff9900",
               "HIGH":"#ff3300","CRITICAL":"#880000"}
FLOOD_EMOJI = {"DRY":"✅","LOW":"🟢","MODERATE":"🟠","HIGH":"🔴","CRITICAL":"⛔"}

# Distinct icon per shelter type, so a school doesn't look like a church
# doesn't look like a hospital on the map.
SHELTER_ICONS = {
    "school":            "🏫",
    "university":        "🎓",
    "medical":           "🏥",
    "government":        "🏛️",
    "church":            "⛪",
    "evacuation_center": "🚩",
    "sports":            "🏟️",
    "community":         "🏢",
    "fallback":          "📍",
}

def _gradient_color(t):
    """t=0 -> vivid green (closest shelter), t=1 -> grey (farthest shown)."""
    t = max(0.0, min(1.0, t))
    g0 = (0, 200, 70)     # vivid green
    g1 = (150, 150, 150)  # grey
    r = round(g0[0] + (g1[0]-g0[0])*t)
    g = round(g0[1] + (g1[1]-g0[1])*t)
    b = round(g0[2] + (g1[2]-g0[2])*t)
    return f"#{r:02x}{g:02x}{b:02x}"
FLOOD_RISK  = {"DRY":0.0,"LOW":0.2,"MODERATE":0.4,"HIGH":0.7,"CRITICAL":1.0}

# ─────────────────────────────────────────────────────────────────────────────
#  NOAH FLOOD DATA — optional shapefile integration
# ─────────────────────────────────────────────────────────────────────────────

FLOOD_GDF = None

def load_flood_shapefile(path):
    global FLOOD_GDF
    if not GEOPANDAS_OK:
        print("  warning  geopandas not installed. Using road-type estimation.")
        return False
    try:
        print(f"  loading flood shapefile: {path}")
        gdf = gpd.read_file(path)
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        if "dmflr" not in gdf.columns:
            print("  warning  dmflr column not found. Using road-type estimation.")
            return False
        FLOOD_GDF = gdf[gdf["dmflr"] > 0].copy()
        mn = FLOOD_GDF["dmflr"].min()
        mx = FLOOD_GDF["dmflr"].max()
        print(f"  loaded {len(FLOOD_GDF)} flood zones. Depth: {mn:.3f}m to {mx:.3f}m")
        return True
    except Exception as exc:
        print(f"  warning  could not load shapefile: {exc}")
        return False


def get_flood_depth_at(lat, lon):
    if FLOOD_GDF is None or not GEOPANDAS_OK:
        return None
    try:
        pt  = Point(lon, lat)
        hit = FLOOD_GDF[FLOOD_GDF.geometry.contains(pt)]
        if hit.empty:
            return None
        return float(hit.iloc[0]["dmflr"])
    except Exception:
        return None


def depth_to_flood_level(depth_m, multiplier=1.0):
    s = depth_m * multiplier
    if s >= 0.50: return "CRITICAL"
    if s >= 0.30: return "HIGH"
    if s >= 0.10: return "MODERATE"
    if s >= 0.01: return "LOW"
    return "DRY"


# ─────────────────────────────────────────────────────────────────────────────
#  OPTIMIZATION MODES
# ─────────────────────────────────────────────────────────────────────────────
SCENARIOS = {
    "1": {"name":"🛡️  MAX SAFETY",   "alpha":0.05,"beta":0.90,"gamma":0.03,"delta":0.02,
          "desc":"Avoids flooded roads at all cost."},
    "2": {"name":"⚡  MAX SPEED",     "alpha":0.70,"beta":0.10,"gamma":0.15,"delta":0.05,
          "desc":"Shortest route. Accepts some flood risk."},
    "3": {"name":"👥  MAX CAPACITY",  "alpha":0.10,"beta":0.30,"gamma":0.10,"delta":0.50,
          "desc":"Routes toward largest-capacity shelters."},
    "4": {"name":"⚖️  BALANCED",      "alpha":0.25,"beta":0.25,"gamma":0.25,"delta":0.25,
          "desc":"Equal weight to all four factors."},
    "5": {"name":"🌊  FLOOD-AWARE",   "alpha":0.30,"beta":0.65,"gamma":0.03,"delta":0.02,
          "desc":"Strong flood avoidance + reasonable speed."},
    "6": {"name":"🏃  FAST & SAFE",   "alpha":0.42,"beta":0.42,"gamma":0.08,"delta":0.08,
          "desc":"Equal split between speed and safety."},
    "7": {"name":"🏟️  CAPACITY+SAFE", "alpha":0.08,"beta":0.45,"gamma":0.07,"delta":0.40,
          "desc":"Large shelters + flood avoidance."},
    "8": {"name":"🛣️  ROAD QUALITY",  "alpha":0.20,"beta":0.30,"gamma":0.45,"delta":0.05,
          "desc":"Prefers wide multi-lane roads."},
}

FLOOD_SCENARIOS = {
    "1": {"name":"☀️  No Flood — Baseline",  "multiplier":1.0},
    "2": {"name":"🌦️  Partial Flooding",      "multiplier":1.5},
    "3": {"name":"🌊  Severe Inundation",     "multiplier":2.5},
    "4": {"name":"⛈️  Extreme — Near Total",  "multiplier":4.0},
}


# ─────────────────────────────────────────────────────────────────────────────
#  GEO HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    p = math.pi / 180
    a = (math.sin((lat2-lat1)*p/2)**2
         + math.cos(lat1*p)*math.cos(lat2*p)*math.sin((lon2-lon1)*p/2)**2)
    return 2*R*math.asin(math.sqrt(a))


def bbox_from_point(lat, lon, radius_m):
    dlat = radius_m / 111_320
    dlon = radius_m / (111_320 * math.cos(math.radians(lat)))
    return (lat-dlat, lon-dlon, lat+dlat, lon+dlon)


# ─────────────────────────────────────────────────────────────────────────────
#  GEOCODING
# ─────────────────────────────────────────────────────────────────────────────

def geocode_address(query_str):
    params = {"q": query_str + ", Philippines",
              "format":"json","limit":5,"countrycodes":"ph"}
    try:
        resp    = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=15)
        results = resp.json()
        if not results: return None
        print("\n  📍  Geocoding results:")
        for i, r in enumerate(results[:5], 1):
            print(f"  {i}. {r['display_name'][:80]}")
            print(f"     ({float(r['lat']):.5f}, {float(r['lon']):.5f})")
        while True:
            try:
                ch = int(input(f"\n  Pick (1–{min(5,len(results))}) or 0 to re-search: "))
                if ch == 0: return None
                if 1 <= ch <= min(5, len(results)):
                    r = results[ch-1]
                    return float(r["lat"]), float(r["lon"]), r["display_name"]
            except ValueError:
                pass
            print("  ⚠  Invalid choice.")
    except Exception as exc:
        print(f"  ⚠  Geocoding failed: {exc}")
        return None


def reverse_geocode(lat, lon):
    try:
        r = requests.get(NOMINATIM_REV,
            params={"lat":lat,"lon":lon,"format":"json"},
            headers=HEADERS, timeout=10)
        return r.json().get("display_name", f"{lat:.5f}, {lon:.5f}")
    except Exception:
        return f"{lat:.5f}, {lon:.5f}"


# ─────────────────────────────────────────────────────────────────────────────
#  OSM FETCH  — uses [out geom] so way elements carry full inline geometry
# ─────────────────────────────────────────────────────────────────────────────

import hashlib as _hashlib

# ── Simple bbox cache so the same area is never fetched twice ──────────────────
_OSM_CACHE: dict = {}
_OSM_CACHE_MAX = 8   # keep last 8 unique bboxes

def _cache_key(bbox):
    s = ",".join(f"{x:.4f}" for x in bbox)
    return _hashlib.md5(s.encode()).hexdigest()[:12]

def _overpass_query(query, timeout=30):
    """
    Try each Overpass mirror with a short timeout — first response wins.
    Falls back to next mirror on any failure.
    """
    last_exc = None
    for mirror in OVERPASS_MIRRORS:
        try:
            resp = requests.post(mirror, data={"data": query},
                                 timeout=timeout, headers=HEADERS)
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception as exc:
            last_exc = str(exc)
            continue
    raise RuntimeError(f"All Overpass mirrors failed. Last: {last_exc}")


def _is_shelter(tags):
    amenity  = tags.get("amenity","")
    building = tags.get("building","")
    emergency= tags.get("emergency","")
    leisure  = tags.get("leisure","")
    office   = tags.get("office","")
    return (
        amenity in ("school","university","community_centre","community_center",
                    "townhall","hospital","clinic","social_facility",
                    "place_of_worship","gym","gymnasium","public_building",
                    "barangay_hall","civic_centre") or
        building in ("civic","government","school","university","church","chapel",
                     "barangay_hall","gymnasium","sports_hall","public") or
        emergency in ("evacuation_centre","assembly_point","evacuation_center") or
        leisure in ("sports_centre","stadium","sports_hall","fitness_centre") or
        office in ("government","administrative")
    )

def _shelter_name(tags, lat, lon):
    for k in ("name","name:en","official_name","short_name","alt_name"):
        if k in tags:
            # Strip surrogate characters from OSM names
            raw = tags[k]
            return raw.encode('utf-8', 'replace').decode('utf-8')
    a = tags.get("amenity","")
    b = tags.get("building","")
    if a == "school" or b == "school":         return f"School ({lat:.4f},{lon:.4f})"
    if a in ("townhall","barangay_hall") or b == "barangay_hall": return f"Barangay Hall ({lat:.4f},{lon:.4f})"
    if a in ("hospital","clinic"):             return f"Health Facility ({lat:.4f},{lon:.4f})"
    if a == "place_of_worship" or b in ("church","chapel"): return f"Church/Chapel ({lat:.4f},{lon:.4f})"
    if a in ("gym","gymnasium") or b in ("gymnasium","sports_hall"): return f"Gymnasium ({lat:.4f},{lon:.4f})"
    if a in ("community_centre","community_center"): return f"Community Center ({lat:.4f},{lon:.4f})"
    if tags.get("office","") in ("government","administrative"): return f"Gov't Office ({lat:.4f},{lon:.4f})"
    if tags.get("leisure","") in ("sports_centre","stadium"): return f"Sports Complex ({lat:.4f},{lon:.4f})"
    return f"Evacuation Center ({lat:.4f},{lon:.4f})"

def _shelter_capacity(tags):
    for k in ("capacity","capacity:persons"):
        try: return int(tags[k])
        except: pass
    a = tags.get("amenity","")
    b = tags.get("building","")
    l = tags.get("leisure","")
    if a == "school":                               return 800
    if a == "university":                           return 3000
    if a in ("hospital","clinic"):                  return 500
    if a in ("townhall","barangay_hall","civic_centre"): return 300
    if a in ("community_centre","community_center"): return 400
    if a == "place_of_worship":                     return 350
    if a in ("gym","gymnasium"):                    return 250
    if b in ("church","chapel"):                    return 350
    if b in ("gymnasium","sports_hall"):            return 500
    if b in ("civic","government","public"):        return 300
    if b in ("school","university"):                return 800
    if b == "barangay_hall":                        return 300
    if l in ("sports_centre","stadium"):            return 2000
    if l == "sports_hall":                          return 600
    return 200

def _shelter_type(tags):
    a = tags.get("amenity","")
    b = tags.get("building","")
    if a == "school":       return "school"
    if a == "university":   return "university"
    if a in ("hospital","clinic"): return "medical"
    if a == "townhall":     return "government"
    if a == "place_of_worship" or b in ("church","chapel") or tags.get("religion",""):
        return "church"
    if tags.get("emergency",""): return "evacuation_center"
    if tags.get("leisure","") in ("sports_centre","stadium"): return "sports"
    return "community"

def _dedup_shelters(shelters, min_dist_m=30):
    kept = []
    for s in shelters:
        if not any(haversine_m(s["lat"],s["lon"],k["lat"],k["lon"]) < min_dist_m
                   for k in kept):
            kept.append(s)
    return kept



def fetch_osm_data(bbox):
    """
    Returns (ways, shelters). Single reliable Overpass query with
    automatic mirror failover. Results cached by bbox.
    """
    ck = _cache_key(bbox)
    if ck in _OSM_CACHE:
        print("  ⚡  Using cached OSM data.")
        return _OSM_CACHE[ck]

    S, W, N, E = bbox
    hw = ("trunk|trunk_link|primary|primary_link|secondary|secondary_link|"
          "tertiary|tertiary_link|residential|unclassified|service|"
          "living_street|footway|path|track")

    query = f"""
[out:json][timeout:55];
(
  way["highway"~"^({hw})$"]({S},{W},{N},{E});
  node["amenity"~"school|university|community_centre|community_center|townhall|hospital|clinic|place_of_worship|gym|gymnasium|barangay_hall|civic_centre"]({S},{W},{N},{E});
  way["amenity"~"school|university|community_centre|community_center|townhall|hospital|clinic|place_of_worship|gym|gymnasium|barangay_hall|civic_centre"]({S},{W},{N},{E});
  node["building"~"school|university|church|chapel|barangay_hall|gymnasium|sports_hall|civic|government|public"]({S},{W},{N},{E});
  way["building"~"school|university|church|chapel|barangay_hall|gymnasium|sports_hall|civic|government|public"]({S},{W},{N},{E});
  node["emergency"~"evacuation_centre|assembly_point|evacuation_center"]({S},{W},{N},{E});
  node["leisure"~"sports_centre|stadium|sports_hall"]({S},{W},{N},{E});
  node["office"~"government|administrative"]({S},{W},{N},{E});
);
out geom;
"""
    print(f"\n  🌐  Fetching OSM data ({S:.4f},{W:.4f})–({N:.4f},{E:.4f})...")
    try:
        elements = _overpass_query(query, timeout=58)
    except RuntimeError as exc:
        print(f"  ❌  {exc}")
        return [], []

    ways     = []
    shelters = []

    for el in elements:
        etype = el.get("type")
        tags  = el.get("tags", {})

        # ── Road ways ─────────────────────────────────────────────────────────
        if etype == "way" and "highway" in tags and "geometry" in el:
            coords = [(pt["lat"], pt["lon"]) for pt in el["geometry"]]
            if len(coords) >= 2:
                ways.append({"id": el["id"], "tags": tags, "geom": coords})

        # ── Shelter nodes ──────────────────────────────────────────────────────
        elif etype == "node" and _is_shelter(tags):
            lat = el.get("lat"); lon = el.get("lon")
            if lat is not None and lon is not None:
                shelters.append({
                    "lat": lat, "lon": lon,
                    "name": _shelter_name(tags, lat, lon),
                    "capacity": _shelter_capacity(tags),
                    "stype": _shelter_type(tags),
                })

        # ── Shelter ways (centroid) ────────────────────────────────────────────
        elif etype == "way" and _is_shelter(tags) and "highway" not in tags:
            if "center" in el:
                lat = el["center"]["lat"]; lon = el["center"]["lon"]
                shelters.append({
                    "lat": lat, "lon": lon,
                    "name": _shelter_name(tags, lat, lon),
                    "capacity": _shelter_capacity(tags),
                    "stype": _shelter_type(tags),
                })
            elif "geometry" in el:
                coords = [(pt["lat"], pt["lon"]) for pt in el["geometry"]]
                if coords:
                    lat = sum(c[0] for c in coords) / len(coords)
                    lon = sum(c[1] for c in coords) / len(coords)
                    shelters.append({
                        "lat": lat, "lon": lon,
                        "name": _shelter_name(tags, lat, lon),
                        "capacity": _shelter_capacity(tags),
                        "stype": _shelter_type(tags),
                    })

    shelters = _dedup_shelters(shelters)

    if not shelters:
        clat = (S + N) / 2; clon = (W + E) / 2
        print("  ⚠  No tagged shelters found — adding bbox centre as fallback.")
        shelters = [{"lat": clat, "lon": clon,
                     "name": "⚠ Nearest Open Area (Unverified)",
                     "capacity": 100, "stype": "fallback"}]

    print(f"  ✅  {len(ways)} road ways | {len(shelters)} shelters")

    if ways:
        if len(_OSM_CACHE) >= _OSM_CACHE_MAX:
            del _OSM_CACHE[next(iter(_OSM_CACHE))]
        _OSM_CACHE[ck] = (ways, shelters)

    return ways, shelters

# ─────────────────────────────────────────────────────────────────────────────
#  FLOOD LEVEL FROM TAGS
# ─────────────────────────────────────────────────────────────────────────────

def road_flood_level(tags, flood_multiplier, lat=None, lon=None):
    if lat is not None and lon is not None:
        depth = get_flood_depth_at(lat, lon)
        if depth is not None:
            return depth_to_flood_level(depth, flood_multiplier)
    hw   = tags.get("highway","unclassified")
    surf = tags.get("surface","")
    base = HIGHWAY_FLOOD_RISK.get(hw, 0.4)
    if surf in ("unpaved","dirt","mud","grass","ground","gravel","compacted"):
        base = min(base + 0.2, 0.9)
    elif surf in ("paved","asphalt","concrete","paving_stones"):
        base = max(base - 0.05, 0.0)
    raw = min(base * flood_multiplier, 1.0)
    if raw >= 0.95: return "CRITICAL"
    if raw >= 0.65: return "HIGH"
    if raw >= 0.38: return "MODERATE"
    if raw >= 0.15: return "LOW"
    return "DRY"


# ─────────────────────────────────────────────────────────────────────────────
#  GRAPH BUILDER
#
#  Node IDs are (lat_rounded6, lon_rounded6) tuples — one per unique
#  coordinate point in the OSM geometry.  Consecutive points on the same
#  way share a node if they round to the same key (i.e. they're the same
#  OSM node), allowing the graph to properly represent road junctions.
#
#  Each edge stores EXACTLY the two real OSM lat/lon points as its
#  waypoints — so the map line follows the road precisely.
# ─────────────────────────────────────────────────────────────────────────────

def build_graph(start_lat, start_lon, ways, shelters,
                flood_multiplier, alpha, beta, gamma, delta):
    """
    Returns (graph, node_info, shelter_ids, raw_edges).
    """
    node_info = {}   # node_key -> (lat, lon, label, ntype, capacity, stype)

    def reg(lat, lon, label="", ntype="road", cap=0, stype=""):
        key = (round(lat,6), round(lon,6))
        if key not in node_info:
            node_info[key] = (lat, lon, label, ntype, cap, stype)
        return key

    # Register start
    start_id = reg(start_lat, start_lon, "📍 Your location", "start", 0)

    # Register shelters
    shelter_ids = set()
    for sh in shelters:
        sid = reg(sh["lat"], sh["lon"], sh["name"], "shelter", sh["capacity"], sh.get("stype",""))
        shelter_ids.add(sid)

    # Pre-register all OSM geometry points as road nodes
    for way in ways:
        for lat, lon in way["geom"]:
            reg(lat, lon)

    # Distance normalisation pass
    all_dists = []
    for way in ways:
        g = way["geom"]
        for i in range(len(g)-1):
            d = haversine_m(g[i][0],g[i][1], g[i+1][0],g[i+1][1])
            if d > 0.1:
                all_dists.append(d)

    mn  = min(all_dists, default=1.0)
    mx  = max(all_dists, default=1.0)
    rng = mx - mn + 1e-9
    max_cap = max((sh["capacity"] for sh in shelters), default=1) or 1

    # Build graph
    graph     = {nid: [] for nid in node_info}
    raw_edges = []   # for map drawing

    for way in ways:
        tags   = way["tags"]
        geom   = way["geom"]
        mid_idx = len(geom) // 2
        mid_lat, mid_lon = geom[mid_idx]
        flood  = road_flood_level(tags, flood_multiplier, mid_lat, mid_lon)
        R      = FLOOD_RISK[flood]
        oneway = tags.get("oneway","no")
        name   = tags.get("name", tags.get("ref", tags.get("highway","road")))
        try:
            lanes = max(int(tags.get("lanes", 1)), 1)
        except (ValueError, TypeError):
            lanes = 1

        for i in range(len(geom)-1):
            lat_a, lon_a = geom[i]
            lat_b, lon_b = geom[i+1]
            a = (round(lat_a,6), round(lon_a,6))
            b = (round(lat_b,6), round(lon_b,6))
            if a == b: continue

            # Ensure nodes exist (may have been added by different way)
            if a not in node_info: node_info[a] = (lat_a, lon_a,"","road",0,""); graph[a]=[]
            if b not in node_info: node_info[b] = (lat_b, lon_b,"","road",0,""); graph[b]=[]

            # EXACT geometry for this edge = the two real OSM coordinate points
            wpts_ab = [(lat_a, lon_a), (lat_b, lon_b)]
            wpts_ba = [(lat_b, lon_b), (lat_a, lon_a)]

            dist = haversine_m(lat_a, lon_a, lat_b, lon_b)
            if dist < 0.1: continue
            dist_m = int(dist)

            raw_edges.append((a, b, dist_m, lanes, name, flood, wpts_ab))

            if R >= 1.0:
                continue   # blocked — in raw_edges for display but not graph

            Dn = (dist - mn) / rng
            C  = min(1.0 / lanes, 1.0)

            nd_b = node_info[b]
            P_b  = (1.0 - nd_b[4]/max_cap) if nd_b[3]=="shelter" else 0.5
            base_ab = alpha*Dn + beta*R + gamma*C + delta*P_b

            nd_a = node_info[a]
            P_a  = (1.0 - nd_a[4]/max_cap) if nd_a[3]=="shelter" else 0.5
            base_ba = alpha*Dn + beta*R + gamma*C + delta*P_a

            # Flood avoidance — two-part penalty:
            # 1) Multiplier on base cost (scales with route length)
            # 2) Flat additive surcharge (makes even short flooded roads expensive)
            # Both scale with beta so MAX SAFETY (0.90) hits hard,
            # MAX SPEED (0.10) barely notices.
            MULT = {"DRY":1.0,"LOW":1.1,"MODERATE":3.5,"HIGH":25.0,"CRITICAL":1.0}
            FLAT = {"DRY":0.0,"LOW":0.0,"MODERATE":0.05,"HIGH":0.5,"CRITICAL":0.0}
            pm   = 1.0 + (MULT.get(flood, 1.0) - 1.0) * beta
            flat = FLAT.get(flood, 0.0) * beta
            W_ab = base_ab * pm + flat
            W_ba = base_ba * pm + flat

            graph[a].append({"to":b,"W":W_ab,"R":R,"flood":flood,
                             "road":name,"dist_m":dist_m,"waypoints":wpts_ab})
            if oneway not in ("yes","true","1","-1"):
                graph[b].append({"to":a,"W":W_ba,"R":R,"flood":flood,
                                 "road":name,"dist_m":dist_m,"waypoints":wpts_ba})

    # Connect start & shelters to K nearest road nodes.
    # Tiered max distance — never leaves a node stranded:
    #   tier 1:  500 m  |  tier 2: 1500 m  |  tier 3: 5000 m
    road_nodes = [nid for nid,nd in node_info.items() if nd[3]=="road"]

    def connect_to_graph(src_id):
        src = node_info[src_id]
        nbrs = sorted(road_nodes,
                      key=lambda n: haversine_m(src[0],src[1],
                                                node_info[n][0],node_info[n][1]))
        done = 0
        for max_d in (500, 1500, 5000):
          for nid in nbrs:
            if done >= K_NEAREST: break
            nd  = node_info[nid]
            d   = haversine_m(src[0],src[1], nd[0],nd[1])
            if d < 0.1: continue
            if d > max_d: break
            dm  = int(d)
            Dn2 = (d - mn) / rng
            W2  = alpha*Dn2 + beta*0.0 + gamma*0.5 + delta*0.5
            wf  = [(src[0],src[1]), (nd[0],nd[1])]
            wr  = [(nd[0],nd[1]),   (src[0],src[1])]
            if nid not in graph: graph[nid] = []
            graph[src_id].append({"to":nid,"W":W2,"R":0.0,"flood":"DRY",
                                  "road":"Walking path","dist_m":dm,"waypoints":wf})
            graph[nid].append({"to":src_id,"W":W2,"R":0.0,"flood":"DRY",
                                "road":"Walking path","dist_m":dm,"waypoints":wr})
            raw_edges.append((src_id, nid, dm, 1, "Walking path", "DRY", wf))
            done += 1
          if done > 0: break  # got connections — no need to widen

    if start_id not in graph: graph[start_id] = []
    connect_to_graph(start_id)
    for sid in shelter_ids:
        if sid not in graph: graph[sid] = []
        connect_to_graph(sid)

    return graph, node_info, shelter_ids, raw_edges


# ─────────────────────────────────────────────────────────────────────────────
#  DIJKSTRA
# ─────────────────────────────────────────────────────────────────────────────

def dijkstra(graph, start):
    dist = {n: float("inf") for n in graph}
    prev = {n: None for n in graph}
    dist[start] = 0.0
    pq = [(0.0, start)]
    while pq:
        cost, u = heapq.heappop(pq)
        if cost > dist[u]: continue
        for e in graph[u]:
            alt = dist[u] + e["W"]
            if alt < dist[e["to"]]:
                dist[e["to"]] = alt
                prev[e["to"]] = {"from":u, **e}
                heapq.heappush(pq, (alt, e["to"]))
    return dist, prev


def get_path(prev, start, end):
    path, segs = [], []
    node = end
    while node != start:
        entry = prev.get(node)
        if not entry: return None, []
        path.append(node); segs.append(entry); node = entry["from"]
    path.append(start); path.reverse(); segs.reverse()
    return path, segs


def find_best(graph, start, shelters):
    dist, prev = dijkstra(graph, start)
    best, bc   = None, float("inf")
    for s in shelters:
        if s in dist and dist[s] < bc and s != start:
            bc = dist[s]; best = s
    if not best: return None, [], float("inf")
    p, sg = get_path(prev, start, best)
    return p, sg, bc


def find_all_shelter_routes(graph, start, shelters):
    dist, prev = dijkstra(graph, start)
    results = []
    for s in shelters:
        if s in dist and dist[s] < float("inf") and s != start:
            p, sg = get_path(prev, start, s)
            td = sum(x["dist_m"] for x in sg)
            results.append((s, p, sg, dist[s], td))
    results.sort(key=lambda x: x[3])
    return results


def walk_time(segs, speed_ms=None):
    spd = speed_ms if speed_ms else SPEED_MS
    return sum(s["dist_m"] for s in segs) / spd / 60


# ─────────────────────────────────────────────────────────────────────────────
#  BUILDINGS  — fetch OSM building footprints for 3D rendering
# ─────────────────────────────────────────────────────────────────────────────

def fetch_buildings(bbox):
    """
    Returns list of building footprints:
      {"coords": [(lat,lon),...], "levels": int, "type": str}
    Returns [] silently on failure so the map still works.
    """
    S, W, N, E = bbox
    query = f"""
[out:json][timeout:30];
way["building"]({S},{W},{N},{E});
out geom;
"""
    try:
        elements = _overpass_query(query, "buildings")
    except Exception:
        return []
    buildings = []
    for el in elements:
        if el.get("type") != "way" or "geometry" not in el:
            continue
        coords = [(nd["lat"], nd["lon"]) for nd in el["geometry"]]
        if len(coords) < 3:
            continue
        tags   = el.get("tags", {})
        levels = int(tags.get("building:levels", tags.get("levels", 1)) or 1)
        levels = max(1, min(levels, 20))
        btype  = tags.get("building", "yes")
        buildings.append({"coords": coords, "levels": levels, "type": btype})
    return buildings


# ─────────────────────────────────────────────────────────────────────────────
#  MAP  — route lines follow exact OSM geometry
# ─────────────────────────────────────────────────────────────────────────────

def draw_map(start, path, segs, node_info, raw_edges,
             flood_name, opt_name, alpha, beta, gamma, delta, area_name,
             buildings=None, drrmo_info=None):
    import json

    def _s(v):
        """Strip surrogate unicode chars that break UTF-8 serialisation."""
        if isinstance(v, str):
            return v.encode('utf-8', 'replace').decode('utf-8')
        return v

    if drrmo_info is None:
        drrmo_info = ("Local DRRMO", "8-911 (NDRRMC)")
    drrmo_lgu, drrmo_number = _s(drrmo_info[0]), _s(drrmo_info[1])
    area_name  = _s(area_name)
    flood_name = _s(flood_name)
    opt_name   = _s(opt_name)

    snd = node_info[start]
    m   = folium.Map(location=[snd[0], snd[1]], zoom_start=16,
                     tiles="OpenStreetMap", prefer_canvas=True)
    map_var = m.get_name()  # e.g. "map_a1b2c3d4" — injected into JS directly

    # ── No background road coloring — only show the route itself ─────────────
    # The base OpenStreetMap tile already shows all roads clearly.
    # We only draw the recommended route so the map stays clean like Google Maps.

    # ── Route is drawn entirely by JavaScript after the person marker is placed ──
    # No static Python-rendered route lines or step badges are added here.
    # The JS below triggers an initial Dijkstra from the start coords and draws
    # the route, so badges and lines only appear when/where the marker actually is.

    # ── Shelter markers (nearest 10 + best destination) ────────────────────────
    shelter_nids = [(nid, nd) for nid, nd in node_info.items() if nd[3]=="shelter"]
    shelter_nids.sort(key=lambda x: haversine_m(snd[0], snd[1], x[1][0], x[1][1]))
    show_shelters = set(nid for nid,_ in shelter_nids[:10])
    if path: show_shelters.add(path[-1])

    # Rank among the shown shelters (0 = closest), used to fade from green to
    # grey. Anything beyond the nearest-10 cap doesn't get a rank here — it
    # can only show up via is_best, which gets its own dedicated color anyway.
    rank_of  = {nid: i for i, (nid, _) in enumerate(shelter_nids[:10])}
    n_ranked = max(len(shelter_nids[:10]) - 1, 1)

    for nid, nd in node_info.items():
        if nd[3] != "shelter" or nid not in show_shelters: continue
        is_best = path and nid == path[-1]
        emoji   = SHELTER_ICONS.get(nd[5], SHELTER_ICONS["community"])
        if is_best:
            bg_color = "#00cc44"
        else:
            bg_color = _gradient_color(rank_of.get(nid, n_ranked) / n_ranked)
        icon_html = (
            f'<div data-sid="{nid}" class="sh-mk" style="background:{bg_color};'
            f'border:{"3px solid #fff" if is_best else "2px solid #ccc"};'
            f'border-radius:50%;width:{"34px" if is_best else "24px"};'
            f'height:{"34px" if is_best else "24px"};display:flex;'
            f'align-items:center;justify-content:center;font-size:{"18px" if is_best else "13px"};'
            f'box-shadow:{"0 0 10px #00ff88" if is_best else "none"};">{emoji}</div>'
        )
        folium.Marker([nd[0], nd[1]],
            tooltip=f"{'⭐ BEST: ' if is_best else ''}{nd[2]} | Cap: {nd[4]}",
            popup=folium.Popup(f"<b>{nd[2]}</b><br>Capacity: {nd[4]}", max_width=220),
            icon=folium.DivIcon(html=icon_html,
                icon_size=(34 if is_best else 24, 34 if is_best else 24),
                icon_anchor=(17 if is_best else 12, 17 if is_best else 12))
        ).add_to(m)

    # ── Other shelters beyond the nearest 10 (toggleable, OFF by default) ──────
    # Same per-type icon as the main badges above, just dimmer — so you can
    # still tell "recommended nearest 10" apart from "everything else nearby"
    # while still seeing what TYPE each one is.
    other_shelters = [(nid, nd) for nid, nd in shelter_nids if nid not in show_shelters]
    other_layer = folium.FeatureGroup(name=f"Other shelters ({len(other_shelters)})", show=False)
    for nid, nd in other_shelters:
        emoji = SHELTER_ICONS.get(nd[5], SHELTER_ICONS["community"])
        icon_html = (
            f'<div data-sid="{nid}" class="sh-mk" style="background:#999999;'
            f'border:2px solid #ccc;border-radius:50%;width:22px;height:22px;'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:12px;opacity:0.85;">{emoji}</div>'
        )
        folium.Marker([nd[0], nd[1]],
            tooltip=f"{nd[2]} | Cap: {nd[4]}",
            popup=folium.Popup(f"<b>{nd[2]}</b><br>Capacity: {nd[4]}", max_width=220),
            icon=folium.DivIcon(html=icon_html, icon_size=(22,22), icon_anchor=(11,11))
        ).add_to(other_layer)
    other_layer.add_to(m)

    # ── Road nodes (debug layer, OFF by default) ────────────────────────────────
    # Every intersection/road point currently in the graph, as small dots you
    # can toggle on via the layer control (top-right). Built with CircleMarker,
    # NOT Marker: CircleMarker is a vector layer, so with prefer_canvas=True
    # (already set on the map above) it all draws into one canvas — cheap even
    # with thousands of nodes, unlike a separate DOM Marker per node.
    n_road_nodes = sum(1 for nd in node_info.values() if nd[3] == "road")
    road_layer = folium.FeatureGroup(name=f"Road nodes ({n_road_nodes})", show=False)
    for nid, nd in node_info.items():
        if nd[3] != "road":
            continue
        folium.CircleMarker(
            [nd[0], nd[1]], radius=3, color="#00aaff", weight=1,
            fill=True, fill_color="#00aaff", fill_opacity=0.6,
            tooltip=f"node {nid} ({nd[0]:.5f}, {nd[1]:.5f})"
        ).add_to(road_layer)
    road_layer.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)

    # ── Info panel HTML (updated by JS on drag) ────────────────────────────────
    if path:
        dstn = node_info[path[-1]]
        td   = sum(s["dist_m"] for s in segs)
        tm   = walk_time(segs)
        mfl  = max(FLOOD_RISK[s["flood"]] for s in segs)
        rl   = next(k for k,v in FLOOD_RISK.items() if v==mfl)
        steps_html = "".join(
            f'<div class="step-row">'
            f'<span class="step-num">{i+1}</span>'
            f'<span class="step-info"><b>{s["road"]}</b>'
            f'<span class="flood-badge" style="background:{ROAD_COLOR[s["flood"]]}22;'
            f'color:{ROAD_COLOR[s["flood"]]};border:1px solid {ROAD_COLOR[s["flood"]]}55;">'
            f'{FLOOD_EMOJI[s["flood"]]} {s["flood"]}</span>'
            f'<span class="step-dist">{s["dist_m"]}m</span></span></div>'
            for i,s in enumerate(segs))
        risk_bar_pct = int(mfl * 100)
        risk_color   = ROAD_COLOR[rl]
        init_html = f"""
          <div class="panel-header">
            <span class="panel-badge">⭐ BEST ROUTE</span>
            <span class="risk-pill" style="background:{risk_color}22;color:{risk_color};border:1px solid {risk_color}55;">
              {FLOOD_EMOJI[rl]} {rl}
            </span>
          </div>
          <div class="panel-section">
            <div class="info-row">📍 <span class="info-val">{snd[2][:45]}</span></div>
            <div class="info-row">🏥 <span class="info-val">{dstn[2][:45]}</span></div>
          </div>
          <div class="stats-grid">
            <div class="stat-box"><div class="stat-val" id="panel-dist">{td}</div><div class="stat-label">meters</div></div>
            <div class="stat-box"><div class="stat-val" id="panel-time">{tm:.0f}</div><div class="stat-label">min walk</div></div>
            <div class="stat-box"><div class="stat-val" id="panel-cap">{dstn[4]}</div><div class="stat-label">capacity</div></div>
          </div>
          <div class="risk-bar-wrap">
            <div class="risk-bar-label">Flood Risk Level</div>
            <div class="risk-bar-track"><div class="risk-bar-fill" style="width:{risk_bar_pct}%;background:{risk_color};"></div></div>
          </div>
          <div class="steps-header">Turn-by-turn</div>
          <div id="panel-steps" class="steps-list">{steps_html}</div>
          <div class="drag-hint">🚶 Drag the orange pin to re-route!</div>"""
        panel_border = "#00cc55"
    else:
        init_html = """
          <div class="panel-header">
            <span class="panel-badge" style="background:#ff330022;color:#ff3300;border-color:#ff330055;">⛔ NO SAFE ROUTE</span>
          </div>
          <div class="panel-section" style="color:#ffaa88;">
            All paths to shelters are flooded or blocked.<br><br>
            Move to nearest high ground immediately.
          </div>
          <div class="emergency-box">
            <div style="font-weight:bold;color:#ff4422;">CALL FOR HELP</div>
            <div>NDRRMC: <b>8-911</b></div>
          </div>
          <div class="drag-hint">🚶 Drag the orange pin to try another spot!</div>"""
        panel_border = "#ff3300"

    m.get_root().html.add_child(folium.Element(f"""
    <style>
      .evac-person {{ background:transparent !important; border:none !important; }}
      .evac-person img {{ display:none !important; }}
      #route-panel {{
        position:fixed; bottom:20px; left:20px; z-index:9999;
        background:rgba(10,16,28,0.97);
        border:1.5px solid {panel_border};
        border-radius:14px; padding:0;
        font-family:'Segoe UI',system-ui,sans-serif;
        color:#e8f0fe; width:300px; font-size:12px; line-height:1.5;
        max-height:75vh; overflow-y:auto;
        box-shadow:0 8px 32px rgba(0,0,0,0.5),0 0 0 1px rgba(255,255,255,0.04);
        scrollbar-width:thin; scrollbar-color:#1e3a5c transparent;
      }}
      #route-panel::-webkit-scrollbar {{ width:4px; }}
      #route-panel::-webkit-scrollbar-thumb {{ background:#1e3a5c; border-radius:4px; }}
      .panel-header {{ display:flex; align-items:center; justify-content:space-between; padding:12px 14px 8px; border-bottom:1px solid rgba(255,255,255,0.06); }}
      .panel-badge {{ background:#00cc5522; color:#00cc55; border:1px solid #00cc5555; border-radius:20px; padding:3px 10px; font-size:11px; font-weight:700; }}
      .risk-pill {{ border-radius:20px; padding:3px 9px; font-size:10px; font-weight:600; }}
      .panel-section {{ padding:8px 14px; border-bottom:1px solid rgba(255,255,255,0.06); font-size:11.5px; color:#a0b4cc; }}
      .info-row {{ margin:2px 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
      .info-val {{ color:#e8f0fe; font-weight:500; }}
      .stats-grid {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:1px; background:rgba(255,255,255,0.05); border-bottom:1px solid rgba(255,255,255,0.06); }}
      .stat-box {{ background:rgba(10,16,28,0.97); padding:8px 6px; text-align:center; }}
      .stat-val {{ font-size:18px; font-weight:700; color:#00d4ff; }}
      .stat-label {{ font-size:9px; color:#556677; text-transform:uppercase; letter-spacing:0.5px; }}
      .risk-bar-wrap {{ padding:8px 14px 6px; border-bottom:1px solid rgba(255,255,255,0.06); }}
      .risk-bar-label {{ font-size:9px; color:#556677; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px; }}
      .risk-bar-track {{ background:rgba(255,255,255,0.08); border-radius:4px; height:6px; overflow:hidden; }}
      .risk-bar-fill {{ height:100%; border-radius:4px; }}
      .steps-header {{ padding:6px 14px 2px; font-size:9px; color:#556677; text-transform:uppercase; letter-spacing:0.5px; }}
      .steps-list {{ padding:0 14px 8px; }}
      .step-row {{ display:flex; align-items:flex-start; gap:8px; padding:5px 0; border-bottom:1px solid rgba(255,255,255,0.04); }}
      .step-row:last-child {{ border-bottom:none; }}
      .step-num {{ min-width:20px; height:20px; line-height:20px; text-align:center; background:rgba(0,180,255,0.12); color:#00b4ff; border-radius:50%; font-size:10px; font-weight:700; margin-top:1px; }}
      .step-info {{ flex:1; display:flex; flex-direction:column; gap:2px; }}
      .step-info b {{ color:#e8f0fe; font-size:11.5px; }}
      .flood-badge {{ display:inline-block; border-radius:4px; padding:1px 6px; font-size:10px; font-weight:600; width:fit-content; }}
      .step-dist {{ font-size:10px; color:#556677; }}
      .emergency-box {{ margin:8px 14px; background:rgba(255,50,0,0.1); border:1px solid rgba(255,50,0,0.3); border-radius:8px; padding:8px 10px; font-size:11.5px; }}
      .drag-hint {{ padding:8px 14px 10px; font-size:10.5px; color:#ff9900; border-top:1px solid rgba(255,255,255,0.06); text-align:center; }}
      .action-btn {{ flex:1; background:rgba(0,100,200,0.15); border:1px solid rgba(0,150,255,0.3); color:#88ccff; padding:5px 8px; border-radius:8px; font-size:10.5px; cursor:pointer; font-family:inherit; white-space:nowrap; }}
      .action-btn:hover {{ background:rgba(0,100,200,0.3); }}
      /* Flood legend */
      #flood-legend {{ position:fixed; bottom:165px; right:18px; z-index:9999; background:rgba(10,16,28,0.95); border:1.5px solid #1e3a5c; border-radius:12px; padding:10px 14px; font-family:'Segoe UI',system-ui,sans-serif; color:#e8f0fe; min-width:170px; box-shadow:0 4px 20px rgba(0,0,0,0.4); }}
      .legend-row {{ display:flex; align-items:center; gap:8px; margin:4px 0; }}
      .legend-dot {{ width:12px; height:12px; border-radius:50%; flex-shrink:0; }}
      .legend-label {{ font-size:11px; color:#a0b4cc; }}
      .legend-title {{ font-size:9px; color:#556677; text-transform:uppercase; letter-spacing:0.6px; margin-bottom:8px; font-weight:700; }}
    </style>
    <div id="route-panel">{init_html}</div>
    <div id="flood-legend">
      <div class="legend-title">🌊 Flood Risk</div>
      <div class="legend-row"><span class="legend-dot" style="background:#00ff88;box-shadow:0 0 5px #00ff8877;"></span><span class="legend-label">DRY — Safe</span></div>
      <div class="legend-row"><span class="legend-dot" style="background:#44dd77;box-shadow:0 0 5px #44dd7755;"></span><span class="legend-label">LOW — Passable</span></div>
      <div class="legend-row"><span class="legend-dot" style="background:#ff9900;box-shadow:0 0 5px #ff990055;"></span><span class="legend-label">MODERATE — Caution</span></div>
      <div class="legend-row"><span class="legend-dot" style="background:#ff3300;box-shadow:0 0 5px #ff330055;"></span><span class="legend-label">HIGH — Dangerous</span></div>
      <div class="legend-row"><span class="legend-dot" style="background:#880000;box-shadow:0 0 5px #88000055;"></span><span class="legend-label">CRITICAL — Blocked</span></div>
      <div class="legend-row" style="margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.08);">
        <span style="font-size:15px;line-height:1;">🏥</span><span class="legend-label">Evacuation Shelter</span>
      </div>
      <div class="legend-row"><span style="font-size:15px;line-height:1;">📍</span><span class="legend-label">Your Position</span></div>
    </div>
    """))

    m.get_root().html.add_child(folium.Element(f"""
    <div style="position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:9999;
        background:rgba(8,15,26,0.92);border:1px solid #1e3a5c;border-radius:8px;
        padding:7px 20px;font-family:monospace;color:white;text-align:center;pointer-events:none;">
      <b style="color:#00d4ff;">🌊 Philippines Flood Evacuation Router</b><br>
      <span style="color:#88aacc;font-size:11px;">
        {area_name[:50]} &nbsp;|&nbsp; {flood_name.strip()} &nbsp;|&nbsp; {opt_name.strip()}
      </span>
    </div>"""))

    # ── Build compact graph JSON for in-browser Dijkstra ──────────────────────
    nodes_js = {}
    for nid, nd in node_info.items():
        safe_name = nd[2][:40].encode('utf-8', 'replace').decode('utf-8')
        nodes_js[str(nid)] = [round(nd[0],6), round(nd[1],6), safe_name, nd[3], nd[4]]

    mn_d  = min((e[2] for e in raw_edges), default=1.0)
    mx_d  = max((e[2] for e in raw_edges), default=1.0)
    rng_d = mx_d - mn_d + 1e-9
    max_c = max((nd[4] for nd in node_info.values() if nd[3]=="shelter"), default=1) or 1

    edges_js = []
    for (a, b, dist_m, lanes, name, flood, wpts) in raw_edges:
        R  = FLOOD_RISK.get(flood, 0.0)
        if R >= 1.0: continue
        Dn = (dist_m - mn_d) / rng_d
        C  = min(1.0 / max(int(lanes), 1), 1.0)
        nd_b = node_info.get(b)
        P_b  = (1.0 - nd_b[4]/max_c) if nd_b and nd_b[3]=="shelter" else 0.5
        W    = alpha*Dn + beta*R + gamma*C + delta*P_b
        edges_js.append([
            str(a), str(b), round(W,5), flood, dist_m, name,
            [round(wpts[0][0],6), round(wpts[0][1],6)],
            [round(wpts[1][0],6), round(wpts[1][1],6)]
        ])

    shelter_ids_js = [str(nid) for nid,nd in node_info.items() if nd[3]=="shelter"]
    graph_json = json.dumps({
        "nodes":    nodes_js,
        "edges":    edges_js,
        "shelters": shelter_ids_js,
        "flood_colors": ROAD_COLOR,
        "flood_risk":   {k: v for k,v in FLOOD_RISK.items()},
        "drrmo_lgu":    drrmo_lgu,
        "drrmo_number": drrmo_number,
        "forced_shelter": str(path[-1]) if path else "",
    }, ensure_ascii=True, separators=(',',':'))

    # ── All-in-one drag JS: person marker + Dijkstra + live re-route ──────────
    drag_js = """
<script>
(function() {
  var GD = """ + graph_json + """;
  var _MAPVAR = """ + json.dumps(map_var) + """;
  var isFirstRoute = true;  // use forced_shelter only on initial load

  // ── Mini priority queue ────────────────────────────────────────────────────
  function PQ() { this.h = []; }
  PQ.prototype.push = function(cost, id) {
    this.h.push([cost, id]);
    this.h.sort(function(a,b){return a[0]-b[0];});
  };
  PQ.prototype.pop = function() { return this.h.shift(); };
  PQ.prototype.empty = function() { return this.h.length === 0; };

  // ── Build adjacency list once ──────────────────────────────────────────────
  var adj = {};
  Object.keys(GD.nodes).forEach(function(n){ adj[n] = []; });
  GD.edges.forEach(function(e) {
    var a=e[0],b=e[1],W=e[2],flood=e[3],dist_m=e[4],road=e[5],wA=e[6],wB=e[7];
    if (!adj[a]) adj[a]=[];
    if (!adj[b]) adj[b]=[];
    adj[a].push({to:b,W:W,flood:flood,dist_m:dist_m,road:road,wpts:[wA,wB]});
    adj[b].push({to:a,W:W,flood:flood,dist_m:dist_m,road:road,wpts:[wB,wA]});
  });

  // ── Dijkstra ───────────────────────────────────────────────────────────────
  function dijkstra(startId) {
    if (!adj[startId]) return null;
    var dist={}, prev={};
    Object.keys(GD.nodes).forEach(function(n){dist[n]=Infinity;prev[n]=null;});
    dist[startId] = 0;
    var pq = new PQ();
    pq.push(0, startId);
    while (!pq.empty()) {
      var top = pq.pop();
      var cost=top[0], u=top[1];
      if (cost > dist[u]) continue;
      var nbrs = adj[u] || [];
      for (var i=0; i<nbrs.length; i++) {
        var e = nbrs[i];
        var alt = dist[u] + e.W;
        if (alt < dist[e.to]) {
          dist[e.to] = alt;
          prev[e.to] = {from:u, flood:e.flood, dist_m:e.dist_m,
                        road:e.road, wpts:e.wpts};
          pq.push(alt, e.to);
        }
      }
    }
    // Find best reachable shelter — use Flask-computed shelter on first load
    var best=null, bc=Infinity;
    var forced = GD.forced_shelter || null;
    if (forced && isFirstRoute && dist[forced] !== undefined && dist[forced] < Infinity && forced !== startId) {
      best = forced;
    } else {
      for (var si=0; si<GD.shelters.length; si++) {
        var s = GD.shelters[si];
        if (dist[s] < bc && s !== startId) { bc=dist[s]; best=s; }
      }
    }
    if (!best) return null;
    // Trace path back
    var segs=[], node=best;
    while (node !== startId) {
      var p=prev[node];
      if (!p) break;
      segs.unshift(p);
      node = p.from;
    }
    return {shelter:best, segs:segs, cost:bc};
  }

  // ── Nearest node ──────────────────────────────────────────────────────────
  // MAX_SNAP_DEG ≈ 150 m in lat/lon degrees (avoids snapping to distant roads)
  var MAX_SNAP_DEG = 0.0015;
  function nearest(lat, lon) {
    var bestId=null, bestD=Infinity;
    var entries = Object.entries(GD.nodes);
    for (var i=0; i<entries.length; i++) {
      var nid=entries[i][0], nd=entries[i][1];
      var d = Math.hypot(lat-nd[0], lon-nd[1]);
      if (d < bestD) { bestD=d; bestId=nid; }
    }
    // If the closest node is too far, there's no road network nearby — return null
    if (bestD > MAX_SNAP_DEG) return null;
    return bestId;
  }

  // ── Route drawing ─────────────────────────────────────────────────────────
  var routeLayers = [];
  var routeTimers = [];   // track all setInterval/setTimeout for route animation
  function clearRoutes(map) {
    // Cancel all pending animations first so old lines don't bleed through
    routeTimers.forEach(function(t){ clearInterval(t); clearTimeout(t); });
    routeTimers = [];
    routeLayers.forEach(function(l){ try{ map.removeLayer(l); }catch(e){} });
    routeLayers = [];
  }
  function drawRoutes(map, segs) {
    if (!segs || segs.length===0) return;
    // Build one continuous list of points across all segments
    var allPts = [];
    for (var si=0; si<segs.length; si++) {
      allPts.push(segs[si].wpts[0]);
    }
    allPts.push(segs[segs.length-1].wpts[1]);

    // White glow underneath entire route as a single continuous line
    routeLayers.push(L.polyline(allPts,{color:'#ffffff',weight:14,opacity:0.15}).addTo(map));
    // Animate route reveal segment by segment — slime effect
    function drawSeg(idx) {
      if (idx >= segs.length) return;
      var seg   = segs[idx];
      var color = GD.flood_colors[seg.flood] || '#00ff88';
      var line  = L.polyline(seg.wpts, {
        color: color, weight: 8, opacity: 0,
        lineCap: 'round', lineJoin: 'round'
      }).bindTooltip('Step '+(idx+1)+': '+seg.road+' ['+seg.flood+'] '+seg.dist_m+'m').addTo(map);
      routeLayers.push(line);

      // Step badge — only at road name changes, not every OSM segment
      var prevRoad = idx > 0 ? segs[idx-1].road : null;
      if (idx === 0 || seg.road !== prevRoad) {
        var turnNum = 1;
        for (var ti=0; ti<idx; ti++) {
          if (segs[ti].road !== (ti>0?segs[ti-1].road:null)) turnNum++;
        }
        var badgePt = seg.wpts[0];
        var badgeHtml =
          '<div class="evac-badge" style="background:'+color+';color:#000;font-weight:bold;'+
          'font-size:11px;width:22px;height:22px;line-height:22px;border-radius:50%;'+
          'border:2px solid white;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.5);">'+turnNum+'</div>';
        var badge = L.marker(badgePt, {
          icon: L.divIcon({html: badgeHtml, iconSize:[26,26], iconAnchor:[13,13], className:''}),
          interactive: false
        }).addTo(map);
        routeLayers.push(badge);
      }

      var op = 0;
      var fade = setInterval(function() {
        op += 0.15;
        line.setStyle({opacity: Math.min(op, 0.95)});
        if (op >= 0.95) {
          clearInterval(fade);
          var t = setTimeout(function(){ drawSeg(idx+1); }, 60);
          routeTimers.push(t);
        }
      }, 20);
      routeTimers.push(fade);
    }
    drawSeg(0);
  }

  // ── Panel update ──────────────────────────────────────────────────────────
  function updatePanel(segs, shelterId, fromLabel) {
    var panel = document.getElementById('route-panel');
    if (!panel) return;
    var sh = GD.nodes[shelterId] || ['','','Unknown','',0];
    var totalDist = 0;
    segs.forEach(function(s){ totalDist += s.dist_m; });
    var walkMin = Math.round(totalDist / 1.1 / 60);
    var fr = GD.flood_risk;
    var maxR = 0;
    segs.forEach(function(s){ if((fr[s.flood]||0)>maxR) maxR=fr[s.flood]||0; });
    var rlMap = {0:'DRY',0.2:'LOW',0.4:'MODERATE',0.7:'HIGH',1.0:'CRITICAL'};
    var rl = rlMap[maxR] || 'DRY';
    var emoji = {DRY:'✅',LOW:'🟢',MODERATE:'🟠',HIGH:'🔴',CRITICAL:'⛔'}[rl]||'';
    var stepsHtml = segs.map(function(s,i){
      var c = GD.flood_colors[s.flood]||'#888';
      return '<div style="margin:3px 0"><b>'+(i+1)+'.</b> '+s.road+
        ' <span style="color:'+c+';font-weight:bold;">['+s.flood+']</span>'+
        '<br>&nbsp;&nbsp;'+s.dist_m+'m</div>';
    }).join('');
    panel.style.borderColor = '#00cc55';
    panel.innerHTML =
      '<div style="color:#00ff88;font-size:15px;font-weight:bold;margin-bottom:8px;">⭐ RECOMMENDED ROUTE</div>'+
      '<div>📍 <b>'+fromLabel.slice(0,50)+'</b></div>'+
      '<div>🏥 → <b>'+sh[2]+'</b></div>'+
      '<div>👥 Capacity: '+sh[4]+' persons</div>'+
      '<div>📏 '+totalDist+'m &nbsp;|&nbsp; ⏱ ~'+walkMin+' min walk</div>'+
      '<div style="margin-top:8px;border-top:1px solid #006622;padding-top:7px;">'+stepsHtml+'</div>'+
      '<div style="margin-top:7px;font-size:10px;color:#556;border-top:1px solid #1a3a5c;padding-top:5px;">'+
        '✅ Dry &nbsp;🟢 Low &nbsp;🟠 Moderate &nbsp;🔴 High &nbsp;⛔ Blocked</div>'+
      (maxR >= 0.7 ?
        '<div style="margin-top:8px;padding:8px;background:rgba(200,30,0,0.18);border:1px solid #cc2200;border-radius:7px;">'+
        '<div style="color:#ff4422;font-weight:bold;font-size:12px;">⚠️ HIGH FLOOD RISK ROUTE</div>'+
        '<div style="font-size:11px;margin-top:4px;color:#ffaa88;">📞 NDRRMC Hotline: <b>8-911</b></div>'+
        '<div style="font-size:11px;color:#ffaa88;">📞 '+GD.drrmo_lgu+': <b>'+GD.drrmo_number+'</b></div>'+
        '<div style="font-size:11px;margin-top:4px;color:#ffcc88;">If forced to use this route, prepare:</div>'+
        '<div style="font-size:10px;color:#ffcc88;">• Life vest or floatation device</div>'+
        '<div style="font-size:10px;color:#ffcc88;">• Waterproof bag for documents & phone</div>'+
        '<div style="font-size:10px;color:#ffcc88;">• Rope (10m+) for group safety</div>'+
        '<div style="font-size:10px;color:#ffcc88;">• Whistle & flashlight</div>'+
        '<div style="font-size:10px;color:#ffcc88;">• First aid kit</div>'+
        '</div>' : '')+
      '<div style="margin-top:8px;font-size:11px;color:#ff9900;border-top:1px solid #1a3a5c;padding-top:6px;">'+
        '🚶 <b>Drag the orange person</b> to re-route!</div>'+
      '<div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;">'+
        '<button onclick="deRoute()" style="background:#1a3a6a;border:1px solid #4488cc;color:#88ccff;padding:5px 10px;border-radius:6px;font-size:11px;cursor:pointer;font-family:monospace;">🔀 Different Route</button>'+
        '<button onclick="showAllShelters()" style="background:#1a3a6a;border:1px solid #4488cc;color:#88ccff;padding:5px 10px;border-radius:6px;font-size:11px;cursor:pointer;font-family:monospace;">📋 All Shelters</button>'+
      '</div>';

    // ── Notify parent page to update its panels ──────────────────────────────
    try {
      window.parent.postMessage({
        type:     'EVAC_ROUTE_UPDATE',
        shelter:  sh[2],
        dist_m:   totalDist,
        capacity: sh[4],
        flood:    rl,
        segs:     segs.map(function(s){
          return {road: s.road, flood: s.flood, dist_m: s.dist_m};
        })
      }, '*');
    } catch(e) {}
  }

  function noRoutePanel() {
    var panel = document.getElementById('route-panel');
    if (!panel) return;
    panel.style.borderColor = '#ff0000';
    panel.innerHTML =
      '<div style="color:#ff3300;font-size:16px;font-weight:bold;margin-bottom:8px;">⛔ NO SAFE ROUTE</div>'+
      '<div>No path to any shelter from here.</div>'+
      '<div style="margin-top:6px;">➤ Try dragging to a different spot.</div>'+
      '<div style="color:#ff9900;font-weight:bold;margin-top:5px;">📞 '+GD.drrmo_lgu+': '+GD.drrmo_number+'</div>'+
      '<div style="color:#ff9900;margin-top:2px;font-size:11px;">📞 NDRRMC: 8-911</div>'+
      '<div style="margin-top:8px;font-size:11px;color:#ff9900;">'+
        '🚶 <b>Drag the orange person</b> to re-route!</div>';
  }

  // ── Shared re-route state ─────────────────────────────────────────────────
  var _startId  = null;
  var _skipped  = [];
  var _mapRef   = null;

  function _dijkstraAll(startId) {
    var dist={}, prev={};
    Object.keys(GD.nodes).forEach(function(n){dist[n]=Infinity;prev[n]=null;});
    dist[startId]=0;
    var pq=new PQ(); pq.push(0,startId);
    while (!pq.empty()) {
      var top=pq.pop(), cost=top[0], u=top[1];
      if (cost>dist[u]) continue;
      (adj[u]||[]).forEach(function(e){
        var alt=dist[u]+e.W;
        if (alt<dist[e.to]){dist[e.to]=alt;prev[e.to]={from:u,flood:e.flood,dist_m:e.dist_m,road:e.road,wpts:e.wpts};pq.push(alt,e.to);}
      });
    }
    return {dist:dist,prev:prev};
  }

  function _traceSegs(prev, startId, endId) {
    var segs=[], node=endId;
    while (node!==startId) { var p=prev[node]; if(!p) return []; segs.unshift(p); node=p.from; }
    return segs;
  }

  function deRoute() {
    if (!_startId||!_mapRef) return;
    var dp=_dijkstraAll(_startId);
    var best=null,bc=Infinity;
    GD.shelters.forEach(function(s){
      if (_skipped.indexOf(s)===-1&&dp.dist[s]<bc&&s!==_startId){bc=dp.dist[s];best=s;}
    });
    if (!best) { _skipped=[]; deRoute(); return; }
    var segs=_traceSegs(dp.prev,_startId,best);
    _skipped.push(best);
    clearRoutes(_mapRef);
    if (segs.length) { drawRoutes(_mapRef,segs); var nd=GD.nodes[_startId]; updatePanel(segs,best,nd?nd[2]:'Your location'); }
    else noRoutePanel();
  }

  function showAllShelters() {
    if (!_startId) return;
    var dp=_dijkstraAll(_startId);
    var list=GD.shelters
      .filter(function(s){return dp.dist[s]<Infinity&&s!==_startId;})
      .map(function(s){
        var segs=_traceSegs(dp.prev,_startId,s);
        return {id:s,segs:segs,td:segs.reduce(function(a,x){return a+x.dist_m;},0)};
      }).sort(function(a,b){return a.td-b.td;});
    var panel=document.getElementById('route-panel'); if(!panel) return;
    var html='<div style="color:#00ff88;font-weight:bold;margin-bottom:8px;">📋 All Shelters ('+list.length+')</div>';
    list.forEach(function(x,i){
      var sh=GD.nodes[x.id]||['','','Unknown','',0];
      html+='<div class="sh-list-item" data-sid="'+x.id+'" style="margin:4px 0;padding:4px 6px;background:rgba(0,100,50,0.15);border-radius:4px;cursor:pointer;">'+(i+1)+'. '+sh[2].slice(0,35)+
        '<br><span style="font-size:10px;color:#88ccaa;">'+x.td+'m ~'+Math.round(x.td/66)+'min Cap:'+sh[4]+'</span></div>';
    });
    html+='<div style="margin-top:8px;"><button id="restore-best-btn" style="background:#1a3a6a;border:1px solid #4488cc;color:#88ccff;padding:4px 8px;border-radius:5px;font-size:10px;cursor:pointer;">Back to Best</button></div>';
    panel.innerHTML=html;
    // Wire up clicks via event delegation — no inline onclick needed
    panel.addEventListener('click', function(e){
      var item=e.target.closest('.sh-list-item');
      if(item){ routeTo(item.getAttribute('data-sid')); return; }
      if(e.target.id==='restore-best-btn'){ restoreBest(); }
    });
  }

  function routeTo(sid) {
    if (!_startId||!_mapRef) return;
    var dp=_dijkstraAll(_startId);
    if (dp.dist[sid]>=Infinity) { noRoutePanel(); return; }
    var segs=_traceSegs(dp.prev,_startId,sid);
    clearRoutes(_mapRef);
    if (segs.length) {
      drawRoutes(_mapRef,segs);
      _skipped=GD.shelters.filter(function(s){return s!==sid;});
      var nd=GD.nodes[_startId]; updatePanel(segs,sid,nd?nd[2]:'Your location');
    } else noRoutePanel();
  }

  function restoreBest() {
    if (!_startId||!_mapRef) return;
    _skipped=[];
    var r=dijkstra(_startId);
    clearRoutes(_mapRef);
    if (r&&r.segs.length) { drawRoutes(_mapRef,r.segs); var nd=GD.nodes[_startId]; updatePanel(r.segs,r.shelter,nd?nd[2]:'Your location'); }
  }

  // ── Person marker — injected directly via Leaflet after map loads ──────────
  var PERSON_SVG =
    '<div style="width:30px;height:42px;position:relative;cursor:grab;filter:drop-shadow(0 3px 6px rgba(0,0,0,0.5));">'+
      '<div style="position:absolute;top:0;left:1px;width:28px;height:28px;'+
        'background:#FF4500;border:3px solid #fff;border-radius:50% 50% 50% 0;'+
        'transform:rotate(-45deg);"></div>'+
      '<div style="position:absolute;top:7px;left:8px;width:12px;height:12px;'+
        'background:#fff;border-radius:50%;"></div>'+
    '</div>';

  var personIcon = L.divIcon({
    html: PERSON_SVG,
    iconSize: [30,42], iconAnchor: [15,42], className: 'evac-person'
  });

  var attempts = 0;
  var poll = setInterval(function() {
    attempts++;
    if (attempts > 100) { clearInterval(poll); return; }
    // Use the map variable directly by name — no window scanning needed.
    // Folium defines it as a global var in the last script block.
    var mapObj = (typeof window[_MAPVAR] !== 'undefined') ? window[_MAPVAR] : null;
    if (!mapObj || typeof mapObj.getCenter !== 'function') return;

    clearInterval(poll);

    // Expose re-route functions to window so onclick= attributes can reach them
    window.deRoute         = deRoute;
    window.showAllShelters = showAllShelters;
    window.routeTo         = routeTo;
    window.restoreBest     = restoreBest;

    // Get start coords from map center
    var center = mapObj.getCenter();

    // Add draggable person marker
    var person = L.marker([center.lat, center.lng], {
      draggable: true,
      icon: personIcon,
      zIndexOffset: 9000
    }).addTo(mapObj);

    person.bindTooltip('🚶 Drag me anywhere to re-route!', {
      permanent: false, direction: 'top', offset: [0, -50]
    });

    // Hide step badges when zoomed out (too cluttered), show when zoomed in
    function updateBadgeVisibility() {
      var zoom = mapObj.getZoom();
      var els = document.querySelectorAll('.evac-badge');
      for (var i=0; i<els.length; i++) {
        els[i].style.opacity = zoom >= 16 ? '1' : '0';
        els[i].style.pointerEvents = zoom >= 16 ? 'auto' : 'none';
      }
    }
    mapObj.on('zoomend', updateBadgeVisibility);

    // Trigger initial route from the starting position
    setTimeout(function() {
      var initSnap = nearest(center.lat, center.lng);
      if (initSnap) {
        // Snap person marker visually to the nearest road node
        var initNd = GD.nodes[initSnap];
        if (initNd) { person.setLatLng([initNd[0], initNd[1]]); }
        var initResult = dijkstra(initSnap);
        if (initResult && initResult.segs.length > 0) {
          _startId = initSnap; _skipped = []; _mapRef = mapObj;
          drawRoutes(mapObj, initResult.segs);
          var initLabel = initNd ? initNd[2] : ('('+center.lat.toFixed(5)+', '+center.lng.toFixed(5)+')');
          updatePanel(initResult.segs, initResult.shelter, initLabel);
        }
      }
    }, 200);

    // Shelter click-to-route via event delegation
    mapObj.getContainer().addEventListener('click', function(evt) {
      var el = evt.target.closest('[data-sid]');
      if (!el) return;
      var sid = el.getAttribute('data-sid');
      if (sid && _startId) routeTo(sid);
    });

    person.on('dragstart', function() {
      person.getElement() && (person.getElement().style.cursor = 'grabbing');
    });

    person.on('dragend', function(e) {
      var ll = e.target.getLatLng();
      var lat = ll.lat, lon = ll.lng;

      // Snap to nearest graph node
      var snapId = nearest(lat, lon);
      if (!snapId) { noRoutePanel(); return; }

      // Move the person marker to the snapped road node
      var snapNd = GD.nodes[snapId];
      if (snapNd) { person.setLatLng([snapNd[0], snapNd[1]]); }

      var panel = document.getElementById('route-panel');
      if (panel) {
        panel.style.borderColor = '#0088ff';
        panel.innerHTML = '<div style="color:#0088ff;font-size:14px;">⏳ Calculating route...</div>';
      }

      setTimeout(function() {
        isFirstRoute = false;  // after first drag, use free best-shelter selection
        var result = dijkstra(snapId);
        clearRoutes(mapObj);
        if (!result || result.segs.length === 0) { noRoutePanel(); return; }
        _startId = snapId; _skipped = []; _mapRef = mapObj;
        drawRoutes(mapObj, result.segs);
        var label = snapNd ? snapNd[2] : ('('+lat.toFixed(5)+', '+lon.toFixed(5)+')');
        updatePanel(result.segs, result.shelter, label);
      }, 30);
    });


  }, 100);

})();
</script>
"""
    m.get_root().html.add_child(folium.Element(drag_js))


    # ── 3D Buildings (canvas overlay synced to Leaflet) ────────────────────
    if buildings:
        import json as _bj
        bld_json = _bj.dumps(buildings)
        building_js = f"""
<script>
(function() {{
  var BUILDINGS = {bld_json};
  var FLOOR_H   = 3.5;   // metres per level (visual)

  // Wait for the Leaflet map to be ready
  var poll = setInterval(function() {{
    var mapObj = null;
    for (var k in window) {{
      try {{
        var v = window[k];
        if (v && typeof v === 'object' && v._leaflet_id !== undefined &&
            typeof v.addLayer === 'function') {{ mapObj = v; break; }}
      }} catch(e) {{}}
    }}
    if (!mapObj) return;
    clearInterval(poll);

    // Create canvas overlay
    var BuildingLayer = L.Layer.extend({{
      onAdd: function(map) {{
        this._map = map;
        var pane = map.getPane('overlayPane');
        this._canvas = L.DomUtil.create('canvas', '', pane);
        this._canvas.style.position = 'absolute';
        this._canvas.style.pointerEvents = 'none';
        this._ctx = this._canvas.getContext('2d');
        map.on('moveend zoomend resize', this._redraw, this);
        this._redraw();
      }},
      onRemove: function(map) {{
        L.DomUtil.remove(this._canvas);
        map.off('moveend zoomend resize', this._redraw, this);
      }},
      _redraw: function() {{
        var map   = this._map;
        var size  = map.getSize();
        var cvs   = this._canvas;
        cvs.width  = size.x;
        cvs.height = size.y;
        cvs.style.left = '0px';
        cvs.style.top  = '0px';
        var ctx   = this._ctx;
        var zoom  = map.getZoom();

        // Only render buildings at zoom >= 16
        if (zoom < 16) return;

        // Pixel height of one metre at this zoom
        var metersPerPx = 156543.03 * Math.cos(map.getCenter().lat * Math.PI / 180) / Math.pow(2, zoom);
        var pxPerMeter  = 1 / metersPerPx;

        var offset = map.containerPointToLayerPoint([0, 0]);
        L.DomUtil.setPosition(cvs, offset);

        for (var bi = 0; bi < BUILDINGS.length; bi++) {{
          var b    = BUILDINGS[bi];
          var pts  = b.coords;
          var flrs = b.levels || 1;
          var btype= b.type || 'yes';

          // project footprint
          var fpx = [];
          for (var ci = 0; ci < pts.length; ci++) {{
            var p = map.latLngToContainerPoint([pts[ci][0], pts[ci][1]]);
            fpx.push(p);
          }}
          if (fpx.length < 3) continue;

          // building height in pixels
          var hpx = flrs * FLOOR_H * pxPerMeter;
          hpx = Math.max(hpx, 2);

          // colour by type
          var wallColor, roofColor;
          if (btype === 'civic' || btype === 'government') {{
            wallColor = 'rgba(80,130,200,0.75)';
            roofColor = 'rgba(60,100,180,0.9)';
          }} else if (btype === 'school' || btype === 'university') {{
            wallColor = 'rgba(180,140,60,0.75)';
            roofColor = 'rgba(160,120,40,0.9)';
          }} else {{
            wallColor = 'rgba(160,155,145,0.72)';
            roofColor = 'rgba(140,130,115,0.88)';
          }}

          // draw side faces (extrude each edge upward)
          ctx.fillStyle = wallColor;
          for (var ei = 0; ei < fpx.length - 1; ei++) {{
            var ax = fpx[ei].x,   ay = fpx[ei].y;
            var bx = fpx[ei+1].x, by2= fpx[ei+1].y;
            ctx.beginPath();
            ctx.moveTo(ax, ay);
            ctx.lineTo(bx, by2);
            ctx.lineTo(bx, by2 - hpx);
            ctx.lineTo(ax, ay  - hpx);
            ctx.closePath();
            ctx.fill();
            ctx.strokeStyle = 'rgba(80,80,80,0.3)';
            ctx.lineWidth = 0.4;
            ctx.stroke();
          }}

          // draw roof
          ctx.beginPath();
          ctx.moveTo(fpx[0].x, fpx[0].y - hpx);
          for (var ri = 1; ri < fpx.length; ri++) {{
            ctx.lineTo(fpx[ri].x, fpx[ri].y - hpx);
          }}
          ctx.closePath();
          ctx.fillStyle = roofColor;
          ctx.fill();
          ctx.strokeStyle = 'rgba(60,60,60,0.5)';
          ctx.lineWidth = 0.6;
          ctx.stroke();
        }}
      }}
    }});

    new BuildingLayer().addTo(mapObj);
  }}, 100);
}})();
</script>"""
        m.get_root().html.add_child(folium.Element(building_js))

    out = "ph_evac_map.html"
    m.save(out)
    print(f"\n  ✅  Map saved → {out}")
    print(f"      🚶  Drag the orange person marker on the map to re-route from any location!")
    webbrowser.open("file://" + os.path.abspath(out))






# ─────────────────────────────────────────────────────────────────────────────
#  PHILIPPINE GEOGRAPHIC HIERARCHY
#  Island Group → Region → Province → Municipality/City → Barangay
#  Uses the PSGC (Philippine Standard Geographic Code) naming.
# ─────────────────────────────────────────────────────────────────────────────

PH_GEO = {
    "LUZON": {
        "NCR — National Capital Region": {
            "Metro Manila (NCR)": [
                "Caloocan","Las Piñas","Makati","Malabon","Mandaluyong",
                "Manila","Marikina","Muntinlupa","Navotas","Parañaque",
                "Pasay","Pasig","Pateros","Quezon City","San Juan",
                "Taguig","Valenzuela",
            ],
        },
        "CAR — Cordillera Administrative Region": {
            "Abra":         ["Bangued","Boliney","Bucay","Bucloc","Daguioman","Danglas","La Paz","Lagayan","Langiden","Licuan-Baay","Luba","Malibcong","Manabo","Peñarrubia","Pidigan","Pilar","Sallapadan","San Isidro","San Juan","San Quintin","Tayum","Tineg","Tubo","Villaviciosa"],
            "Apayao":       ["Calanasan","Conner","Flora","Kabugao","Luna","Pudtol","Santa Marcela"],
            "Benguet":      ["Atok","Baguio City","Bakun","Bokod","Buguias","Itogon","Kabayan","Kapangan","Kibungan","La Trinidad","Mankayan","Sablan","Tuba","Tublay"],
            "Ifugao":       ["Aguinaldo","Alfonso Lista","Asipulo","Banaue","Hingyon","Hungduan","Kiangan","Lagawe","Lamut","Mayoyao","Tinoc"],
            "Kalinga":      ["Balbalan","Lubuagan","Pasil","Pinukpuk","Rizal","Tabuk City","Tanudan","Tinglayan"],
            "Mountain Province": ["Barlig","Bauko","Besao","Bontoc","Natonin","Paracelis","Sabangan","Sadanga","Sagada","Tadian"],
        },
        "Region I — Ilocos Region": {
            "Ilocos Norte":  ["Laoag City","Adams","Bacarra","Badoc","Bangui","Banna","Burgos","Carasi","Currimao","Dingras","Dumalneg","Marcos","Nueva Era","Pagudpud","Paoay","Pasuquin","Piddig","Pinili","San Nicolas","Sarrat","Solsona","Vintar"],
            "Ilocos Sur":    ["Vigan City","Alilem","Banayoyo","Bantay","Burgos","Cabugao","Caoayan","Cervantes","Galimuyod","Gregorio del Pilar","Lidlidda","Magsingal","Nagbukel","Narvacan","Quirino","Salcedo","San Emilio","San Esteban","San Ildefonso","San Juan","San Vicente","Santa","Santa Catalina","Santa Cruz","Santa Lucia","Santa Maria","Santiago","Santo Domingo","Sigay","Sinait","Sugpon","Suyo","Tagudin"],
            "La Union":      ["San Fernando City","Agoo","Aringay","Bacnotan","Bagulin","Balaoan","Bangar","Bauang","Burgos","Caba","Luna","Naguilian","Pugo","Rosario","San Gabriel","San Juan","Santo Tomas","Santol","Sudipen","Tubao"],
            "Pangasinan":    ["Dagupan City","San Carlos City","Urdaneta City","Agno","Aguilar","Alcala","Anda","Asingan","Balungao","Bani","Basista","Bautista","Bayambang","Binalonan","Binmaley","Bolinao","Bugallon","Burgos","Calasiao","Dasol","Infanta","Labrador","Laoac","Lingayen","Mabini","Malasiqui","Manaoag","Mangaldan","Mangatarem","Mapandan","Natividad","Pozorrubio","Rosales","San Fabian","San Jacinto","San Manuel","San Nicolas","San Quintin","Santa Barbara","Santa Maria","Santo Tomas","Sison","Sual","Tayug","Umingan","Urbiztondo","Villasis"],
        },
        "Region II — Cagayan Valley": {
            "Batanes":       ["Basco","Itbayat","Ivana","Mahatao","Sabtang","Uyugan"],
            "Cagayan":       ["Tuguegarao City","Abulug","Alcala","Allacapan","Amulung","Aparri","Baggao","Ballesteros","Buguey","Calayan","Camalaniugan","Claveria","Enrile","Gattaran","Gonzaga","Iguig","Lal-lo","Lasam","Pamplona","Peñablanca","Piat","Rizal","Sanchez-Mira","Santa Ana","Santa Praxedes","Santa Teresita","Santo Niño","Solana","Tuao"],
            "Isabela":       ["Ilagan City","Cauayan City","Santiago City","Alicia","Angadanan","Aurora","Benito Soliven","Burgos","Cabagan","Cabatuan","Cordon","Delfin Albano","Dinapigue","Divilacan","Echague","Gamu","Jones","Luna","Maconacon","Mallig","Naguilian","Palanan","Quezon","Quirino","Ramon","Reina Mercedes","Roxas","San Agustin","San Guillermo","San Isidro","San Manuel","San Mariano","San Mateo","San Pablo","Santa Maria","Santo Tomas","Tumauini"],
            "Nueva Vizcaya": ["Bayombong","Ambaguio","Aritao","Bagabag","Bambang","Diadi","Dupax del Norte","Dupax del Sur","Kasibu","Kayapa","Quezon","Santa Fe","Solano","Villaverde"],
            "Quirino":       ["Cabarroguis","Aglipay","Diffun","Maddela","Nagtipunan","Saguday"],
        },
        "Region III — Central Luzon": {
            "Aurora":        ["Baler","Casiguran","Dilasag","Dinalungan","Dingalan","Dipaculao","Maria Aurora","San Luis"],
            "Bataan":        ["Balanga City","Abucay","Bagac","Dinalupihan","Hermosa","Limay","Mariveles","Morong","Orani","Orion","Pilar","Samal"],
            "Bulacan":       ["Malolos City","San Jose del Monte City","Meycauayan City","Angat","Balagtas","Baliuag","Bocaue","Bulakan","Bustos","Calumpit","Doña Remedios Trinidad","Guiguinto","Hagonoy","Marilao","Norzagaray","Obando","Pandi","Plaridel","Pulilan","San Ildefonso","San Miguel","San Rafael","Santa Maria"],
            "Nueva Ecija":   ["Cabanatuan City","Gapan City","Muñoz City","Palayan City","Science City of Muñoz","Aliaga","Bongabon","Cabiao","Carranglan","Cuyapo","Gabaldon","General Mamerto Natividad","General Tinio","Guimba","Jaen","Laur","Licab","Llanera","Lupao","Nampicuan","Pantabangan","Peñaranda","Quezon","Rizal","San Antonio","San Isidro","San Jose City","San Leonardo","Santa Rosa","Santo Domingo","Talavera","Talugtug","Zaragoza"],
            "Pampanga":      ["Angeles City","San Fernando City","Apalit","Arayat","Bacolor","Candaba","Floridablanca","Guagua","Lubao","Mabalacat City","Macabebe","Magalang","Masantol","Mexico","Minalin","Porac","San Luis","San Simon","Santa Ana","Santa Rita","Santo Tomas","Sasmuan"],
            "Tarlac":        ["Tarlac City","Anao","Bamban","Camiling","Capas","Concepcion","Gerona","La Paz","Mayantoc","Moncada","Paniqui","Pura","Ramos","San Clemente","San Jose","San Manuel","Santa Ignacia","Victoria"],
            "Zambales":      ["Olongapo City","Botolan","Cabangan","Candelaria","Castillejos","Iba","Masinloc","Olongapo City","Palauig","San Antonio","San Felipe","San Marcelino","San Narciso","Santa Cruz","Subic"],
        },
        "Region IV-A — CALABARZON": {
            "Batangas":      ["Batangas City","Lipa City","Tanauan City","Agoncillo","Alitagtag","Balayan","Balete","Batangas City","Bauan","Calaca","Calatagan","Cuenca","Ibaan","Laurel","Lemery","Lian","Lobo","Mabini","Malvar","Mataas na Kahoy","Nasugbu","Padre Garcia","Rosario","San Jose","San Juan","San Luis","San Nicolas","San Pascual","Santa Teresita","Santo Tomas","Taal","Talisay","Taysan","Tingloy","Tuy"],
            "Cavite":        ["Cavite City","Tagaytay City","Trece Martires City","Alfonso","Amadeo","Bacoor City","Carmona","Dasmariñas City","General Emilio Aguinaldo","General Mariano Alvarez","General Trias City","Imus City","Indang","Kawit","Magallanes","Maragondon","Mendez","Naic","Noveleta","Rosario","Silang","Tanza","Ternate"],
            "Laguna":        ["San Pablo City","Calamba City","Santa Rosa City","Biñan City","Cabuyao City","Alaminos","Bay","Calauan","Cavinti","Famy","Kalayaan","Liliw","Los Baños","Luisiana","Lumban","Mabitac","Magdalena","Majayjay","Nagcarlan","Paete","Pagsanjan","Pakil","Pangil","Pila","Rizal","Santa Cruz","Santa Maria","Siniloan","Victoria"],
            "Quezon":        ["Lucena City","Tayabas City","Agdangan","Alabat","Atimonan","Buenavista","Burdeos","Calauag","Candelaria","Catanauan","Dolores","General Luna","General Nakar","Guinayangan","Gumaca","Infanta","Jomalig","Lopez","Lucban","Macalelon","Mauban","Mulanay","Padre Burgos","Pagbilao","Panukulan","Patnanungan","Perez","Pitogo","Plaridel","Polis","Quezon","Real","Sampaloc","San Andres","San Antonio","San Francisco","San Narciso","Sariaya","Tagkawayan","Tiaong","Unisan"],
            "Rizal":         ["Antipolo City","Angono","Baras","Binangonan","Cainta","Cardona","Jalajala","Morong","Pililla","Rodriguez","San Mateo","Tanay","Taytay","Teresa"],
        },
        "Region IV-B — MIMAROPA": {
            "Marinduque":    ["Boac","Buenavista","Gasan","Mogpog","Santa Cruz","Torrijos"],
            "Occidental Mindoro": ["Mamburao","Abra de Ilog","Calintaan","Looc","Lubang","Magsaysay","Paluan","Rizal","Sablayan","San Jose","Santa Cruz"],
            "Oriental Mindoro": ["Calapan City","Baco","Bansud","Bongabong","Bulalacao","Gloria","Mansalay","Naujan","Pinamalayan","Pola","Puerto Galera","Roxas","San Teodoro","Socorro","Victoria"],
            "Palawan":       ["Puerto Princesa City","Aborlan","Agutaya","Araceli","Balabac","Bataraza","Brooke's Point","Buliluyan","Cagayancillo","Coron","Culion","Cuyo","Dumaran","El Nido","Espanola","Kalayaan","Linapacan","Magsaysay","Narra","Quezon","Rizal","Roxas","San Vicente","Sofronio Española","Taytay"],
            "Romblon":       ["Romblon","Alcantara","Banton","Cajidiocan","Calatrava","Concepcion","Corcuera","Ferrol","Looc","Magdiwang","Odiongan","San Agustin","San Andres","San Fernando","San Jose","Santa Fe","Santa Maria"],
        },
        "Region V — Bicol Region": {
            "Albay":         ["Legazpi City","Ligao City","Tabaco City","Bacacay","Camalig","Daraga","Guinobatan","Jovellar","Libon","Malilipot","Malinao","Manito","Oas","Pioduran","Polangui","Rapu-Rapu","Santo Domingo","Tiwi"],
            "Camarines Norte": ["Daet","Basud","Capalonga","Jose Panganiban","Labo","Mercedes","Paracale","San Lorenzo Ruiz","San Vicente","Santa Elena","Talisay","Vinzons"],
            "Camarines Sur": ["Naga City","Iriga City","Baao","Balatan","Bato","Bombon","Buhi","Bula","Camaligan","Canaman","Caramoan","Del Gallego","Gainza","Garchitorena","Goa","Lagonoy","Libmanan","Lupi","Magarao","Milaor","Minalabac","Nabua","Ocampo","Pamplona","Pasacao","Pili","Presentacion","Ragay","Sagñay","San Fernando","San Jose","Sipocot","Siruma","Tigaon","Tinambac"],
            "Catanduanes":   ["Virac","Bagamanoc","Baras","Bato","Caramoran","Gigmoto","Pandan","Panganiban","San Andres","San Miguel","Viga"],
            "Masbate":       ["Masbate City","Aroroy","Baleno","Balud","Batuan","Cataingan","Cawayan","Claveria","Dimasalang","Esperanza","Mandaon","Milagros","Mobo","Monreal","Palanas","Pio V. Corpuz","Placer","San Fernando","San Jacinto","San Pascual","Uson"],
            "Sorsogon":      ["Sorsogon City","Barcelona","Bulan","Bulusan","Casiguran","Castilla","Donsol","Gubat","Irosin","Juban","Magallanes","Matnog","Pilar","Prieto Diaz","Santa Magdalena"],
        },
    },

    "VISAYAS": {
        "Region VI — Western Visayas": {
            "Aklan":         ["Kalibo","Altavas","Balete","Banga","Batan","Buruanga","Ibajay","Lezo","Libacao","Madalag","Makato","Malay","Malinao","Nabas","New Washington","Numancia","Tangalan"],
            "Antique":       ["San Jose de Buenavista","Anini-y","Barbaza","Belison","Bugasong","Caluya","Culasi","Hamtic","Laua-an","Libertad","Pandan","Patnongon","San Remigio","Sebaste","Sibalom","Tibiao","Tobias Fornier","Valderrama"],
            "Capiz":         ["Roxas City","Cuartero","Dao","Dumalag","Dumarao","Ivisan","Jamindan","Ma-ayon","Mambusao","Panay","Panitan","Pilar","Pontevedra","President Roxas","Sapian","Sigma","Tapaz"],
            "Guimaras":      ["Jordan","Buenavista","Nueva Valencia","San Lorenzo","Sibunag"],
            "Iloilo":        ["Iloilo City","Passi City","Ajuy","Alimodian","Anilao","Badiangan","Balasan","Banate","Barotac Nuevo","Barotac Viejo","Batad","Bingawan","Cabatuan","Calinog","Carles","Concepcion","Dingle","Dueñas","Dumangas","Estancia","Guimbal","Igbaras","Janiuay","Lambunao","Leganes","Lemery","Leon","Maasin","Miagao","Mina","New Lucena","Oton","Pavia","Pototan","San Dionisio","San Enrique","San Joaquin","San Miguel","San Rafael","Santa Barbara","Sara","Tigbauan","Tubungan","Zarraga"],
            "Negros Occidental": ["Bacolod City","Bago City","Cadiz City","Escalante City","Himamaylan City","Kabankalan City","La Carlota City","Sagay City","San Carlos City","Silay City","Sipalay City","Talisay City","Victorias City","Binalbagan","Calatrava","Candoni","Cauayan","Enrique B. Magalona","Hinigaran","Hinoba-an","Ilog","Isabela","Manapla","Moises Padilla","Murcia","Pontevedra","Pulupandan","Salvador Benedicto","San Enrique","Toboso","Valladolid"],
        },
        "Region VII — Central Visayas": {
            "Bohol":         ["Tagbilaran City","Alburquerque","Alicia","Anda","Antequera","Baclayon","Balilihan","Batuan","Bien Unido","Bilar","Buenavista","Calape","Candijay","Carmen","Catigbian","Clarin","Corella","Cortes","Dagohoy","Danao","Dauis","Dimiao","Duero","Garcia Hernandez","Getafe","Guindulman","Inabanga","Jagna","Jetafe","Lila","Loay","Loboc","Loon","Mabini","Maribojoc","Panglao","Pilar","Pitogo","President Carlos P. Garcia","Sagbayan","San Isidro","San Miguel","Sevilla","Sierra Bullones","Sikatuna","Talibon","Trinidad","Tubigon","Ubay","Valencia"],
            "Cebu":          ["Cebu City","Mandaue City","Lapu-Lapu City","Toledo City","Carcar City","Danao City","Bogo City","Naga City","Talisay City","Alcantara","Alcoy","Alegria","Aloguinsan","Argao","Asturias","Badian","Balamban","Bantayan","Barili","Borbon","Catmon","Compostela","Consolacion","Cordova","Daanbantayan","Dalaguete","Dumanjug","Ginatilan","Liloan","Madridejos","Malabuyoc","Medellin","Minglanilla","Moalboal","Oslob","Pilar","Pinamungajan","Poro","Ronda","Samboan","San Fernando","San Francisco","San Remigio","Santa Fe","Santander","Sibonga","Sogod","Tabogon","Tabuelan","Tuburan","Tudela"],
            "Negros Oriental": ["Dumaguete City","Bais City","Bayawan City","Canlaon City","Guihulngan City","Tanjay City","Amlan","Ayungon","Bacong","Basay","Bindoy","Dauin","Jimalalud","La Libertad","Mabinay","Manjuyod","Pamplona","San Jose","Santa Catalina","Siaton","Sibulan","Tayasan","Valencia","Vallehermoso","Zamboanguita"],
            "Siquijor":      ["Siquijor","Enrique Villanueva","Larena","Lazi","Maria","San Juan"],
        },
        "Region VIII — Eastern Visayas": {
            "Biliran":       ["Naval","Almeria","Biliran","Caibiran","Culaba","Kawayan","Maripipi","Villaba"],
            "Eastern Samar": ["Borongan City","Arteche","Balangiga","Balangkayan","Can-avid","Dolores","General MacArthur","Giporlos","Guiuan","Hernani","Jipapad","Lawaan","Llorente","Maslog","Maydolong","Mercedes","Oras","Quinapondan","Salcedo","San Julian","San Policarpo","Sulat","Taft"],
            "Leyte":         ["Tacloban City","Baybay City","Ormoc City","Abuyog","Alangalang","Albuera","Babatngon","Bato","Barugo","Burauen","Calubian","Capoocan","Carigara","Dagami","Dulag","Hilongos","Hindang","Inopacan","Isabel","Jaro","Javier","Julita","Kananga","La Paz","Leyte","MacArthur","Mahaplag","Matag-ob","Matalom","Mayorga","Merida","Palo","Palompon","Pastrana","San Isidro","San Miguel","Santa Fe","Tabango","Tabontabon","Tanauan","Tolosa","Tunga","Villaba"],
            "Northern Samar": ["Catarman","Allen","Biri","Bobon","Capul","Catubig","Gamay","Laoang","Lapinig","Las Navas","Lavezares","Lope de Vega","Mapanas","Mondragon","Palapag","Pambujan","Rosario","San Antonio","San Isidro","San Jose","San Roque","San Vicente","Silvino Lobos","Victoria"],
            "Samar":         ["Catbalogan City","Basey","Calbayog City","Calbiga","Daram","Gandara","Hinabangan","Jiabong","Langkag","Marabut","Matuguinao","Motiong","Pagsanghan","Paranas","Pinabacdao","San Jorge","San Jose de Buan","San Sebastian","Santa Margarita","Santa Rita","Santo Niño","Talalora","Tarangnan","Villareal","Zumarraga"],
            "Southern Leyte": ["Maasin City","Anahawan","Bontoc","Hinunangan","Hinundayan","Libagon","Liloan","Limasawa","Macrohon","Malitbog","Padre Burgos","Pintuyan","Saint Bernard","San Francisco","San Juan","San Ricardo","Silago","Sogod","Tomas Oppus"],
        },
    },

    "MINDANAO": {
        "Region IX — Zamboanga Peninsula": {
            "Zamboanga del Norte": ["Dipolog City","Dapitan City","Baliguian","Godod","Gutalac","Jose Dalman","Kalawit","Katipunan","La Libertad","Labason","Leon B. Postigo","Liloy","Manukan","Mutia","Piñan","Polanco","Pres. Manuel A. Roxas","Rizal","Salug","San Miguel","San Pablo","Sergio Osmeña Sr.","Siayan","Sibuco","Sibutad","Sindangan","Siocon","Sirawai","Tampilisan"],
            "Zamboanga del Sur":   ["Pagadian City","Aurora","Bayog","Dimataling","Dinas","Dumalinao","Dumingag","Guipos","Josefina","Kumalarang","Labangan","Lapuyan","Mahayag","Margosatubig","Midsalip","Molave","Pitogo","Ramon Magsaysay","San Miguel","San Pablo","Sominot","Tabina","Tambulig","Tigbao","Tukuran","Vincenzo A. Sagun","Zamboanga City"],
            "Zamboanga Sibugay":   ["Ipil","Alicia","Buug","Diplahan","Imelda","Kabasalan","Mabuhay","Malangas","Naga","Olutanga","Payao","Roseller Lim","Siay","Talusan","Titay","Tungawan"],
        },
        "Region X — Northern Mindanao": {
            "Bukidnon":      ["Malaybalay City","Valencia City","Baungon","Cabanglasan","Damulog","Dangcagan","Don Carlos","Impasug-ong","Kadingilan","Kalilangan","Kibawe","Kitaotao","Lantapan","Libona","Malitbog","Manolo Fortich","Maramag","Pangantucan","Quezon","San Fernando","Sumilao","Talakag"],
            "Camiguin":      ["Mambajao","Catarman","Guinsiliban","Mahinog","Sagay"],
            "Lanao del Norte": ["Iligan City","Bacolod","Baloi","Baroy","Kapatagan","Kauswagan","Kolambugan","Lala","Linamon","Magsaysay","Maigo","Matungao","Munai","Nunungan","Pantao Ragat","Pantar","Poona Piagapo","Salvador","Sapad","Sultan Naga Dimaporo","Tagoloan","Tangcal","Tubod"],
            "Misamis Occidental": ["Oroquieta City","Ozamiz City","Tangub City","Aloran","Baliangao","Bonifacio","Calamba","Clarin","Concepcion","Don Victoriano Chiongbian","Jimenez","Lopez Jaena","Panaon","Plaridel","Sapang Dalaga","Sinacaban","Tudela"],
            "Misamis Oriental":   ["Cagayan de Oro City","Gingoog City","Alubijid","Balingasag","Balingoan","Binuangan","Claveria","El Salvador City","Gitagum","Initao","Jasaan","Kinoguitan","Lagonglong","Laguindingan","Libertad","Lugait","Magsaysay","Manticao","Medina","Naawan","Opol","Salay","Sugbongcogon","Tagoloan","Talisayan","Villanueva"],
        },
        "Region XI — Davao Region": {
            "Davao de Oro":  ["Nabunturan","Compostela","Laak","Mabini","Maco","Maragusan","Mawab","Monkayo","Montevista","New Bataan","Pantukan"],
            "Davao del Norte": ["Tagum City","Panabo City","Island Garden City of Samal","Asuncion","Braulio E. Dujali","Carmen","Kapalong","New Corella","San Isidro","Santo Tomas","Talaingod"],
            "Davao del Sur": ["Digos City","Bansalan","Don Marcelino","Hagonoy","Jose Abad Santos","Kiblawan","Magsaysay","Malalag","Malita","Matanao","Padada","Santa Cruz","Sulop"],
            "Davao City":    ["Davao City"],
            "Davao Occidental": ["Malita","Don Marcelino","Jose Abad Santos","Santa Maria","Sarangani"],
            "Davao Oriental": ["Mati City","Baganga","Banaybanay","Boston","Caraga","Cateel","Governor Generoso","Lupon","Manay","San Isidro","Tarragona"],
        },
        "Region XII — SOCCSKSARGEN": {
            "Cotabato":      ["Kidapawan City","Alamada","Aleosan","Arakan","Banisilan","Carmen","Kabacan","Libungan","Magpet","Makilala","Matalam","Midsayap","Milan","Mlang","Munai","Pigkawayan","Pikit","President Roxas","Tulunan"],
            "Sarangani":     ["Alabel","Glan","Kiamba","Maasim","Maitum","Malapatan","Malungon"],
            "South Cotabato": ["Koronadal City","Banga","Lake Sebu","Norala","Polomolok","Santo Niño","Surallah","T'boli","Tampakan","Tantangan","Tupi"],
            "Sultan Kudarat": ["Isulan","Bagumbayan","Columbio","Esperanza","Kalamansig","Lambayong","Lebak","Lutayan","Palimbang","President Quirino","Sen. Ninoy Aquino","Sultan Sumagka"],
        },
        "Region XIII — Caraga": {
            "Agusan del Norte": ["Butuan City","Cabadbaran City","Buenavista","Carmen","Jabonga","Kitcharao","Las Nieves","Magallanes","Nasipit","Remedios T. Romualdez","Santiago","Tubay"],
            "Agusan del Sur": ["Prosperidad","Bayugan City","Bunawan","Esperanza","La Paz","Loreto","Rosario","San Francisco","San Luis","Santa Josefa","Sibagat","Talacogon","Trento","Veruela"],
            "Dinagat Islands": ["San Jose","Basilisa","Cagdianao","Dinagat","Libjo","Loreto","Tubajon"],
            "Surigao del Norte": ["Surigao City","Alegria","Bacuag","Burgos","Claver","Dapa","Del Carmen","General Luna","Gigaquit","Mainit","Malimono","Pilar","Placer","San Benito","San Francisco","San Isidro","Santa Monica","Sison","Socorro","Tagana-an","Tubod"],
            "Surigao del Sur": ["Tandag City","Bislig City","Barobo","Bayabas","Cagwait","Cantilan","Carmen","Carrascal","Cortes","Hinatuan","Lanuza","Lianga","Lingig","Madrid","Marihatag","San Agustin","San Miguel","Tagbina","Tago"],
        },
        "BARMM — Bangsamoro Autonomous Region": {
            "Basilan":       ["Isabela City","Akbar","Al-Barka","Hadji Mohammad Ajul","Hadji Muhtamad","Lantawan","Maluso","Sumisip","Tabuan-Lasa","Tipo-Tipo","Tuburan","Ungkaya Pukan"],
            "Lanao del Sur": ["Marawi City","Bacolod-Kalawi","Balabagan","Balindong","Bayang","Binidayan","Buadiposo-Buntong","Bubong","Bumbaran","Butig","Calanogas","Ditsaan-Ramain","Ganassi","Kapai","Kapatagan","Lumba-Bayabao","Lumbaca-Unayan","Lumbatan","Lumbayanague","Madalum","Madamba","Maguing","Malabang","Marantao","Marogong","Masiu","Mulondo","Pagayawan","Piagapo","Picong","Poona Bayabao","Pualas","Saguiaran","Sultan Dumalondong","Sultan Gumander","Tagoloan II","Tamparan","Taraka","Tubaran","Tugaya","Wao"],
            "Maguindanao del Norte": ["Cotabato City","Barira","Buldon","Datu Blah T. Sinsuat","Datu Odin Sinsuat","Kabuntalan","Matanog","Northern Kabuntalan","Parang","Sultan Kudarat","Sultan Mastura","Upi"],
            "Maguindanao del Sur": ["Buluan","Datu Abdullah Sangki","Datu Anggal Midtimbang","Datu Hoffer Ampatuan","Datu Paglas","Datu Piang","Datu Salibo","Datu Saudi-Ampatuan","Datu Unsay","General Salipada K. Pendatun","Guindulungan","Mamasapano","Mangudadatu","Pagalungan","Paglat","Pandag","Rajah Buayan","Shariff Aguak","Shariff Saydona Mustapha","South Upi","Sultan sa Barongis","Talayan","Talitay"],
            "Sulu":          ["Jolo","Hadji Panglima Tahil","Indanan","Kalingalan Caluang","Lugus","Luuk","Maimbung","Old Panamao","Omar","Pandami","Pata","Parang","Siasi","Talipao","Tapul","Tongkil"],
            "Tawi-Tawi":     ["Bongao","Languyan","Mapun","Panglima Sugala","Sapa-Sapa","Sibutu","Simunul","Sitangkai","South Ubian","Tandubas","Turtle Islands"],
        },
    },
}


def _pick_from_list(items, prompt="  Pick: ", zero_label="Go back"):
    """Display a numbered list and return the chosen item, or None for 0."""
    items = list(items)
    cols  = 3
    rows  = math.ceil(len(items) / cols)
    # Print in column-major order so reading left-to-right gives alphabetical
    col_w = 28
    for r in range(rows):
        line = ""
        for c in range(cols):
            idx = c * rows + r
            if idx < len(items):
                label = f"{idx+1:>3}. {items[idx]}"
                line += label.ljust(col_w + 5)
        print(" ", line)
    print(f"\n   0. {zero_label}")
    while True:
        try:
            ch = int(input(f"\n{prompt}").strip())
            if ch == 0:  return None
            if 1 <= ch <= len(items): return items[ch - 1]
        except ValueError:
            pass
        print(f"  ⚠  Enter 0–{len(items)}.")


def _pick_barangay(municipality, province):
    """Fetch barangay list from Nominatim and let user pick, or skip."""
    print(f"\n  🔍  Looking up barangays in {municipality}, {province}...")
    params = {
        "q":           f"{municipality}, {province}, Philippines",
        "format":      "json",
        "limit":       1,
        "countrycodes":"ph",
        "addressdetails": 1,
    }
    try:
        resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=10)
        results = resp.json()
    except Exception:
        results = []

    # Use Overpass to find named places tagged as barangay within the municipality bbox
    # First geocode the municipality to get a bbox
    if not results:
        print("  ⚠  Could not geocode municipality. Skipping barangay selection.")
        return None

    bbox_str = results[0].get("boundingbox","")
    if len(bbox_str) == 4:
        S, N, W, E = bbox_str
    else:
        print("  ⚠  No bounding box. Skipping barangay selection.")
        return None

    query = f"""
[out:json][timeout:30];
(
  node["place"~"village|suburb|neighbourhood|barangay"]({S},{W},{N},{E});
  way["place"~"village|suburb|neighbourhood|barangay"]({S},{W},{N},{E});
);
out center;
"""
    try:
        brgys = []
        for el in _overpass_query(query):
            name = el.get("tags",{}).get("name","")
            if not name: continue
            if el["type"] == "node":
                brgys.append((name, el["lat"], el["lon"]))
            elif el["type"] == "way" and "center" in el:
                brgys.append((name, el["center"]["lat"], el["center"]["lon"]))
        brgys.sort(key=lambda x: x[0])
    except Exception:
        brgys = []

    if not brgys:
        print("  ⚠  No barangay data found. Will use municipality center.")
        return None

    print(f"\n  BARANGAYS in {municipality} ({len(brgys)} found):")
    print("  (Enter 0 to use the municipality/city center instead)")
    names = [b[0] for b in brgys]
    chosen = _pick_from_list(names, "  Pick your barangay: ",
                             zero_label="Use municipality/city center")
    if chosen is None:
        return None
    match = next((b for b in brgys if b[0] == chosen), None)
    return match   # (name, lat, lon)


def pick_location():
    """
    Drill-down location picker:
      Method A — Island Group → Region → Province → Municipality → (Barangay)
      Method B — Free-text search
      Method C — GPS coordinates
    Returns (lat, lon, display_name, radius_m).
    """
    print("\n  ┌─────────────────────────────────────────────────┐")
    print("  │        SET YOUR EVACUATION START POINT          │")
    print("  └─────────────────────────────────────────────────┘")
    print("\n  HOW DO YOU WANT TO FIND YOUR LOCATION?")
    print("  1. 🗺️   Browse by Island Group → Region → Province → Municipality")
    print("  2. 🔍   Free-text search (type an address or place name)")
    print("  3. 📌   Enter GPS coordinates manually")

    while True:
        method = input("\n  Select (1/2/3): ").strip()
        if method in ("1","2","3"): break
        print("  ⚠  Enter 1, 2, or 3.")

    lat = lon = None
    display_name = ""

    # ── METHOD A: Drill-down ──────────────────────────────────────────────────
    if method == "1":
        # Island Group
        island_groups = list(PH_GEO.keys())
        print("\n  ISLAND GROUP:")
        chosen_group = _pick_from_list(island_groups, "  Pick island group: ")
        if not chosen_group:
            return pick_location()

        # Region
        regions = list(PH_GEO[chosen_group].keys())
        print(f"\n  REGIONS in {chosen_group}:")
        chosen_region = _pick_from_list(regions, "  Pick region (0 = go back): ")
        if not chosen_region:
            return pick_location()

        # Province
        provinces = list(PH_GEO[chosen_group][chosen_region].keys())
        print(f"\n  PROVINCES / AREAS in {chosen_region}:")
        chosen_province = _pick_from_list(provinces, "  Pick province (0 = go back): ")
        if not chosen_province:
            return pick_location()

        # Municipality / City
        munis = PH_GEO[chosen_group][chosen_region][chosen_province]
        print(f"\n  MUNICIPALITIES / CITIES in {chosen_province}:")
        chosen_muni = _pick_from_list(munis, "  Pick municipality/city (0 = go back): ")
        if not chosen_muni:
            return pick_location()

        # Barangay — always fetched automatically after picking municipality
        brgy_result = _pick_barangay(chosen_muni, chosen_province)

        if brgy_result:
            brgy_name, lat, lon = brgy_result
            display_name = f"{brgy_name}, {chosen_muni}, {chosen_province}"
        else:
            # No barangay selected — geocode the municipality center
            print(f"\n  🌐  Geocoding {chosen_muni}, {chosen_province}...")
            result = geocode_address(f"{chosen_muni}, {chosen_province}")
            if result:
                lat, lon, display_name = result
            else:
                print("  ⚠  Geocoding failed. Try free-text search instead.")
                return pick_location()

    # ── METHOD B: Free-text ───────────────────────────────────────────────────
    elif method == "2":
        while True:
            q = input("\n  🔍  Address / place name: ").strip()
            if not q: continue
            result = geocode_address(q)
            if result:
                lat, lon, display_name = result
                break
            print("  ⚠  No results. Try again.")

    # ── METHOD C: GPS ─────────────────────────────────────────────────────────
    else:
        while True:
            try:
                lat = float(input("\n  Latitude  (e.g. 14.5995): ").strip())
                lon = float(input("  Longitude (e.g. 120.9842): ").strip())
                display_name = reverse_geocode(lat, lon)
                print(f"\n  ✅  {display_name[:80]}")
                break
            except ValueError:
                print("  ⚠  Use decimal numbers.")

    print(f"\n  ✅  Location set: {display_name[:70]}")
    print(f"      Coordinates : ({lat:.5f}, {lon:.5f})")

    # ── Search radius ─────────────────────────────────────────────────────────
    print("\n  SEARCH RADIUS (how far to look for roads & shelters):")
    print("  1. 500 m — tight barangay / very dense urban (RECOMMENDED for SJDM)")
    print("  2. 1 km  — standard barangay (default)")
    print("  3. 2 km  — wider area / rural")
    print("  4. 3 km  — large rural area (slow, many markers)")
    print("  ⚠  Larger radius = more data = slower load + crowded map")
    radius_map = {"1":500,"2":1000,"3":2000,"4":3000}
    while True:
        rc = input("\n  Select (1–4) [default 2]: ").strip() or "2"
        if rc in radius_map:
            radius = radius_map[rc]; break
        print("  ⚠  Enter 1–4.")

    return lat, lon, display_name, radius


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
#  FEATURE 1: EMBEDDED MINI MONTE CARLO
#  Runs 50 quick simulations from nearby random nodes after every route search
#  to give a confidence score for the recommended route.
# ─────────────────────────────────────────────────────────────────────────────

def embedded_mini_montecarlo(start_lat, start_lon, ways, shelters,
                              flood_multiplier, alpha, beta, gamma, delta,
                              n=50, seed=99):
    """
    Run n quick simulations from random nearby nodes with DYNAMIC SPEED VARIATION.
    Each simulation randomly assigns a speed profile to simulate a real community
    evacuation where different people move at different speeds.
    Returns validation stats including per-profile time breakdown.
    """
    import random
    rng = random.Random(seed)

    # Collect nearby road nodes within 500m
    nearby = []
    for way in ways:
        for lat, lon in way["geom"]:
            if haversine_m(start_lat, start_lon, lat, lon) < 500:
                nearby.append((round(lat,6), round(lon,6)))
    if not nearby:
        return None

    successes  = 0
    dists      = []
    risks      = []
    times_by_profile = {pk: [] for pk in SPEED_PROFILES}

    # Speed weights — simulate realistic community distribution
    # More walkers and elderly than runners in a real evacuation
    profile_weights = {"1":0.10,"2":0.35,"3":0.20,"4":0.20,"5":0.05,"6":0.10}
    profile_keys    = list(profile_weights.keys())
    profile_wts     = [profile_weights[k] for k in profile_keys]

    for _ in range(n):
        pt = rng.choice(nearby)
        # Randomly assign a speed profile weighted by realistic distribution
        chosen_pk = rng.choices(profile_keys, weights=profile_wts, k=1)[0]
        chosen_spd = SPEED_PROFILES[chosen_pk]["speed"]

        try:
            g, ni, sh, _ = build_graph(pt[0], pt[1], ways, shelters,
                                        flood_multiplier, alpha, beta, gamma, delta)
            s = next((nid for nid,nd in ni.items() if nd[3]=="start"), None)
            if not s: continue
            _, segs, _ = find_best(g, s, sh)
            if segs:
                successes += 1
                dist = sum(x["dist_m"] for x in segs)
                dists.append(dist)
                risks.append(max(FLOOD_RISK[x["flood"]] for x in segs))
                # Record time for this profile
                times_by_profile[chosen_pk].append(dist / chosen_spd / 60)
        except Exception:
            continue

    if not dists:
        return None

    rate  = successes / n * 100
    avg_d = sum(dists) / len(dists)
    avg_r = sum(risks) / len(risks)

    # Compute avg time per profile
    avg_times = {}
    for pk, pv in SPEED_PROFILES.items():
        if times_by_profile[pk]:
            avg_times[pk] = sum(times_by_profile[pk]) / len(times_by_profile[pk])
        else:
            # Estimate from avg distance if no samples
            avg_times[pk] = avg_d / pv["speed"] / 60

    if rate >= 85 and avg_r < 0.3:   label = "HIGH"
    elif rate >= 60 and avg_r < 0.5: label = "MODERATE"
    else:                             label = "LOW"

    return {
        "success_rate": rate,
        "avg_dist_m":   avg_d,
        "avg_risk":     avg_r,
        "confidence":   label,
        "n":            n,
        "avg_times":    avg_times,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  FEATURE 2: NETWORK RESILIENCE
#  If the best route has HIGH/CRITICAL segments, auto-finds alternative routes
#  and ranks them by resilience score.
# ─────────────────────────────────────────────────────────────────────────────

def assess_network_resilience(graph, start, shelter_ids, node_info, segs):
    """
    Assess how resilient the network is around the recommended route.
    Returns resilience report dict.
    """
    if not segs:
        return {"status": "NO_ROUTE", "score": 0, "alternatives": 0}

    # Count critical/high risk segments in recommended route
    critical_segs = [s for s in segs if FLOOD_RISK[s["flood"]] >= 0.7]
    high_segs     = [s for s in segs if 0.4 <= FLOOD_RISK[s["flood"]] < 0.7]

    # Find how many alternative shelters are reachable
    all_routes = find_all_shelter_routes(graph, start, shelter_ids)
    n_alternatives = len(all_routes) - 1  # exclude best

    # Resilience score (0-100)
    penalty = len(critical_segs) * 20 + len(high_segs) * 10
    alt_bonus = min(n_alternatives * 10, 40)
    score = max(0, min(100, 80 - penalty + alt_bonus))

    if score >= 70:   status = "RESILIENT"
    elif score >= 40: status = "MODERATE"
    else:             status = "VULNERABLE"

    return {
        "status":        status,
        "score":         score,
        "critical_segs": len(critical_segs),
        "high_segs":     len(high_segs),
        "alternatives":  n_alternatives,
        "alt_routes":    all_routes[1:4],  # top 3 alternatives
    }


def print_resilience_report(report, node_info):
    """Print network resilience assessment."""
    status_emoji = {"RESILIENT":"🟢","MODERATE":"🟠","VULNERABLE":"🔴"}
    print(f"\n  NETWORK RESILIENCE ASSESSMENT")
    print(f"  {'-'*45}")
    print(f"  Status        : {status_emoji.get(report['status'],'')} {report['status']}")
    print(f"  Resilience Score: {report['score']}/100")
    print(f"  Critical segments in route: {report['critical_segs']}")
    print(f"  High-risk segments        : {report['high_segs']}")
    print(f"  Alternative shelters      : {report['alternatives']}")

    if report["alt_routes"]:
        print(f"\n  TOP ALTERNATIVE ROUTES:")
        for i, (sid, sp, ss, sc, td) in enumerate(report["alt_routes"], 1):
            sn  = node_info[sid]
            tm  = td / SPEED_MS / 60
            mfl = max(FLOOD_RISK[s["flood"]] for s in ss) if ss else 0
            rl  = next(k for k,v in FLOOD_RISK.items() if v==mfl)
            print(f"  {i}. {sn[2][:35]} | {td}m | ~{tm:.0f}min | {FLOOD_EMOJI.get(rl,'')} {rl}")


# ─────────────────────────────────────────────────────────────────────────────
#  FEATURE 3: ROUTE DECISION ACCURACY SCORING
#  Scores each segment on how good the routing decision was and gives
#  an overall route quality rating.
# ─────────────────────────────────────────────────────────────────────────────

def score_route_accuracy(segs, node_info, alpha, beta, gamma, delta):
    """
    Score each segment decision and compute overall route quality.
    Returns accuracy report dict.
    """
    if not segs:
        return None

    seg_scores = []
    for s in segs:
        R  = FLOOD_RISK[s["flood"]]
        # Penalize flood risk heavily
        flood_penalty  = R * beta * 100
        # Reward shorter segments
        dist_score     = max(0, 100 - (s["dist_m"] / 10))
        # Combined segment score
        seg_score = max(0, dist_score - flood_penalty)
        seg_scores.append({
            "road":       s["road"],
            "flood":      s["flood"],
            "dist_m":     s["dist_m"],
            "score":      round(seg_score, 1),
            "decision":   "GOOD" if seg_score > 60 else
                          "ACCEPTABLE" if seg_score > 30 else "RISKY"
        })

    overall = sum(s["score"] for s in seg_scores) / len(seg_scores)
    total_d = sum(s["dist_m"] for s in segs)
    flood_d = sum(s["dist_m"] for s in segs if FLOOD_RISK[s["flood"]] > 0)
    flood_pct = flood_d / total_d * 100 if total_d else 0

    if overall >= 70:   rating = "EXCELLENT"
    elif overall >= 50: rating = "GOOD"
    elif overall >= 30: rating = "ACCEPTABLE"
    else:               rating = "POOR"

    return {
        "overall_score": round(overall, 1),
        "rating":        rating,
        "flood_pct":     round(flood_pct, 1),
        "seg_scores":    seg_scores,
        "good_decisions":    sum(1 for s in seg_scores if s["decision"]=="GOOD"),
        "risky_decisions":   sum(1 for s in seg_scores if s["decision"]=="RISKY"),
    }


def print_accuracy_report(report):
    """Print route decision accuracy report."""
    rating_emoji = {"EXCELLENT":"⭐","GOOD":"✅","ACCEPTABLE":"🟠","POOR":"🔴"}
    print(f"\n  ROUTE DECISION ACCURACY")
    print(f"  {'-'*45}")
    print(f"  Overall Score : {report['overall_score']}/100")
    print(f"  Rating        : {rating_emoji.get(report['rating'],'')} {report['rating']}")
    print(f"  Good decisions: {report['good_decisions']}/{len(report['seg_scores'])} segments")
    print(f"  Risky decisions: {report['risky_decisions']}/{len(report['seg_scores'])} segments")
    print(f"  % Route on flooded roads: {report['flood_pct']}%")



def main():
    print(); print(SEP)
    print("  🌊  PHILIPPINES FLOOD EVACUATION ROUTE OPTIMIZER")
    print("      Works for any barangay / city / municipality")
    print(SEP)

    print("  ℹ️   Using road-type estimation for flood risk.")

    while True:
        lat, lon, area_name, radius_m = pick_location()

        print("\n  FLOOD SCENARIO:")
        for k, v in FLOOD_SCENARIOS.items():
            print(f"  {k}. {v['name']}")
        while True:
            fs = input("\n  Select (1/2/3/4): ").strip()
            if fs in FLOOD_SCENARIOS: break
            print("  ⚠  Enter 1–4.")
        fd = FLOOD_SCENARIOS[fs]

        print("\n  OPTIMIZATION MODE  (W = αD + βR + γC + δP)")
        print(f"  {'#':<3} {'Name':<24} {'α':>5} {'β':>5} {'γ':>5} {'δ':>5}  Description")
        print(f"  {'-'*80}")
        for k, v in SCENARIOS.items():
            print(f"  {k:<3} {v['name']:<24} {v['alpha']:>5.2f} {v['beta']:>5.2f}"
                  f" {v['gamma']:>5.2f} {v['delta']:>5.2f}  {v['desc']}")
        while True:
            sc = input(f"\n  Select (1–{len(SCENARIOS)}): ").strip()
            if sc in SCENARIOS: break
            print(f"  ⚠  Enter 1–{len(SCENARIOS)}.")
        opt = SCENARIOS[sc]

        # ── Speed Profile (like Google Maps transport mode) ──────────────────
        print("\n  EVACUATION PROFILE  (select your movement type)")
        print(f"  {'#':<3} {'Profile':<28} {'Speed':>8}  Description")
        print(f"  {'-'*65}")
        for k, v in SPEED_PROFILES.items():
            print(f"  {k:<3} {v['name']:<28} {v['speed']:>6.1f}m/s  {v['desc']}")
        while True:
            sp = input(f"\n  Select (1-{len(SPEED_PROFILES)}) [default 2]: ").strip() or "2"
            if sp in SPEED_PROFILES: break
            print(f"  Enter 1-{len(SPEED_PROFILES)}.")
        profile     = SPEED_PROFILES[sp]
        profile_spd = profile["speed"]
        print(f"  Speed set: {profile['name']} ({profile_spd} m/s)")

        show_all = input("\n  Show all shelter routes? (y/n): ").strip().lower() == "y"

        bbox = bbox_from_point(lat, lon, radius_m)
        ways, shelters = fetch_osm_data(bbox)

        if not ways:
            print("\n  ❌  No road data. Check internet or try a different location.")
            if input("  🔁  Try again? (y/n): ").strip().lower() == "y": continue
            break

        if not shelters:
            print("\n  ⚠  No shelters found. Try increasing the radius.")

        print("\n  ⚙  Building graph...")
        graph, node_info, shelter_ids, raw_edges = build_graph(
            lat, lon, ways, shelters,
            fd["multiplier"], opt["alpha"], opt["beta"], opt["gamma"], opt["delta"]
        )

        start = next((nid for nid,nd in node_info.items() if nd[3]=="start"), None)
        if not start:
            print("  ❌  Could not place start node."); continue

        print(f"  ✅  {len(graph)} nodes | {sum(len(v) for v in graph.values())} edges"
              f" | {len(shelter_ids)} shelters")

        path, segs, cost = find_best(graph, start, shelter_ids)

        print(f"\n{SEP}")
        print(f"  📌 From   : {area_name[:60]}")
        print(f"  🌧  Flood  : {fd['name']}")
        print(f"  ⚙  Mode   : {opt['name']}")
        print(SEP)

        if path:
            dstn = node_info[path[-1]]
            td   = sum(s["dist_m"] for s in segs)
            tm   = walk_time(segs)
            mfl  = max(FLOOD_RISK[s["flood"]] for s in segs)
            rl   = next(k for k,v in FLOOD_RISK.items() if v==mfl)
            tm_profile = walk_time(segs, profile_spd)
            print(f"\n  ✅  BEST SHELTER : {dstn[2]}")
            print(f"     Capacity      : {dstn[4]} persons")
            print(f"     Distance      : {td} m")
            print(f"     Max road risk : {FLOOD_EMOJI[rl]} {rl}")
            print(f"\n  ESTIMATED TRAVEL TIME BY PROFILE:")
            for pk, pv in SPEED_PROFILES.items():
                t = walk_time(segs, pv["speed"])
                marker = " ◄ YOUR SELECTION" if pk == sp else ""
                print(f"  {pv['name']:<28} ~{t:.0f} min{marker}")
            print("\n  STEP-BY-STEP:")
            for i, s in enumerate(segs, 1):
                seg_time = s["dist_m"] / profile_spd / 60
                print(f"  {i}. {s['road']}  [{s['flood']}]  {s['dist_m']}m  (~{seg_time:.1f}min)")

            # FEATURE 3: Route Decision Accuracy
            acc = score_route_accuracy(segs, node_info,
                                       opt["alpha"], opt["beta"],
                                       opt["gamma"], opt["delta"])
            if acc:
                print_accuracy_report(acc)

            # FEATURE 2: Network Resilience
            resilience = assess_network_resilience(
                graph, start, shelter_ids, node_info, segs)
            if resilience:
                print_resilience_report(resilience, node_info)

            # FEATURE 1: Embedded Mini Monte Carlo
            run_mc = input("\n  Run quick validation? (mini Monte Carlo ~30sec) (y/n): ").strip().lower()
            if run_mc == "y":
                print("  Running 50 quick simulations nearby...")
                mc = embedded_mini_montecarlo(
                    lat, lon, ways, shelters,
                    fd["multiplier"],
                    opt["alpha"], opt["beta"], opt["gamma"], opt["delta"]
                )
                if mc:
                    conf_emoji = {"HIGH":"🟢","MODERATE":"🟠","LOW":"🔴"}
                    print(f"\n  MINI MONTE CARLO VALIDATION (n={mc['n']})")
                    print(f"  {'-'*50}")
                    print(f"  Success rate  : {mc['success_rate']:.1f}%")
                    print(f"  Avg distance  : {mc['avg_dist_m']:.0f}m")
                    print(f"  Avg flood risk: {mc['avg_risk']:.3f}")
                    print(f"  Confidence    : {conf_emoji.get(mc['confidence'],'')} {mc['confidence']}")
                    print(f"\n  ESTIMATED EVACUATION TIME BY PROFILE:")
                    print(f"  (based on dynamic speed simulation)")
                    for pk, pv in SPEED_PROFILES.items():
                        t = mc['avg_times'].get(pk, mc['avg_dist_m']/pv['speed']/60)
                        marker = " ◄" if pk == sp else ""
                        print(f"  {pv['name']:<28} ~{t:.0f} min{marker}")
                else:
                    print("  Not enough nearby road nodes for validation.")
        else:
            print("\n  ⛔  NO SAFE ROUTE — All paths blocked!")
            print("  ➤  Call NDRRMC: 8-911 / +632-8911-1406")

        if show_all:
            all_routes = find_all_shelter_routes(graph, start, shelter_ids)
            if all_routes:
                print("\n  ALL REACHABLE SHELTERS:")
                print(f"  {'#':<3} {'Shelter':<40} {'Score':>7} {'Dist':>7} {'Time':>6}  Risk")
                print(f"  {'-'*72}")
                for rank, (sid, sp, ss, sc2, std) in enumerate(all_routes, 1):
                    sn2 = node_info[sid]
                    stm = std / SPEED_MS / 60
                    rl2 = "DRY"
                    if ss:
                        mf  = max(FLOOD_RISK[sg["flood"]] for sg in ss)
                        rl2 = next(k for k,v in FLOOD_RISK.items() if v==mf)
                    mark = " ◄ BEST" if rank==1 else ""
                    print(f"  {rank:<3} {sn2[2][:40]:<40} {sc2:>7.4f}"
                          f" {std:>6}m {stm:>5.0f}m  {FLOOD_EMOJI.get(rl2,'')} {rl2}{mark}")
            else:
                print("\n  ⛔  No shelters reachable.")

        draw_map(start, path, segs, node_info, raw_edges,
                 fd["name"], opt["name"],
                 opt["alpha"], opt["beta"], opt["gamma"], opt["delta"],
                 area_name, drrmo_info=get_drrmo_info(area_name))

        if input("\n  🔁  Search another route? (y/n): ").strip().lower() != "y":
            print("\n  Stay safe! Laging handa. 🙏\n")
            break


if __name__ == "__main__":
    main()
