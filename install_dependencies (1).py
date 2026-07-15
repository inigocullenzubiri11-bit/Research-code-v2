"""
=============================================================================
  DEPENDENCY INSTALLER
  Flood Evacuation Route Optimization System — Philippines Edition
=============================================================================
  HOW TO USE:
    1. Make sure Python is installed (https://python.org)
    2. Run this file:  python install_dependencies.py
    3. Wait for everything to finish
    4. Then run:       python Ph_evac_route.py
                       python testing_suite.py
=============================================================================
"""

import subprocess
import sys
import importlib
import os

# ─────────────────────────────────────────────────────────────────────────────
#  PACKAGES TO INSTALL
# ─────────────────────────────────────────────────────────────────────────────

PACKAGES = [
    # (pip install name,   import name,       what it's used for)
    ("folium",             "folium",          "Interactive map generation (HTML evacuation maps)"),
    ("requests",           "requests",        "Fetching road/OSM data from the internet"),
    ("matplotlib",         "matplotlib",      "Charts and graphs in the testing suite"),
    ("numpy",              "numpy",           "Math operations for flood modeling"),
    ("geopandas",          "geopandas",       "Loading flood risk shapefiles (optional but recommended)"),
    ("shapely",            "shapely",         "Geometry calculations for flood zones (optional)"),
]

# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

W = 60  # column width for pretty printing

def header(text):
    print()
    print("=" * W)
    print(f"  {text}")
    print("=" * W)

def check(import_name):
    """Return True if the package is already installed."""
    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False

def install(pip_name):
    """Run pip install and return (success, output)."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", pip_name],
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stdout + result.stderr

# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    header("FLOOD EVACUATION SYSTEM — DEPENDENCY INSTALLER")
    print(f"\n  Python: {sys.version.split()[0]}")
    print(f"  Path:   {sys.executable}\n")

    # ── Step 1: Check what's already installed ─────────────────────────────
    header("Step 1 — Checking existing packages")
    already_installed = []
    needs_install     = []

    for pip_name, import_name, desc in PACKAGES:
        if check(import_name):
            print(f"  ✔  {pip_name:<18} already installed")
            already_installed.append(pip_name)
        else:
            print(f"  ✘  {pip_name:<18} MISSING — will install")
            needs_install.append((pip_name, import_name, desc))

    if not needs_install:
        print("\n  All packages are already installed!")
        verify_and_exit()
        return

    # ── Step 2: Install missing packages ──────────────────────────────────
    header("Step 2 — Installing missing packages")
    failed = []

    for pip_name, import_name, desc in needs_install:
        print(f"\n  Installing {pip_name}...")
        print(f"  ({desc})")
        print(f"  {'─' * (W - 4)}")

        ok, output = install(pip_name)

        if ok and check(import_name):
            print(f"  ✔  {pip_name} installed successfully")
        else:
            print(f"  ✘  {pip_name} FAILED to install")
            # Print last few lines of pip output for debugging
            lines = [l for l in output.strip().splitlines() if l.strip()]
            for line in lines[-4:]:
                print(f"     {line}")
            failed.append(pip_name)

    # ── Step 3: Final verification ─────────────────────────────────────────
    header("Step 3 — Final verification")
    all_ok = True

    for pip_name, import_name, desc in PACKAGES:
        ok = check(import_name)
        status = "✔  OK" if ok else "✘  FAIL"
        print(f"  {status}   {pip_name:<18} {desc[:30]}")
        if not ok:
            all_ok = False

    # ── Summary ────────────────────────────────────────────────────────────
    print()
    print("=" * W)
    if all_ok:
        print("  ✔  All packages installed successfully!")
        print()
        print("  You can now run:")
        print("    python Ph_evac_route.py     ← main evacuation app")
        print("    python testing_suite.py     ← testing + charts")
    else:
        print("  ✘  Some packages failed to install:")
        for p in failed:
            print(f"       pip install {p}")
        print()
        print("  Try running those commands manually in your terminal.")
        print("  If geopandas fails, that's okay — it's optional.")
        print("  The main app will still work without it.")
    print("=" * W)
    print()

    if os.name == "nt":  # Windows — keep window open
        input("  Press Enter to close...")


def verify_and_exit():
    header("Verification")
    for pip_name, import_name, desc in PACKAGES:
        ok = check(import_name)
        status = "✔  OK" if ok else "✘  MISSING"
        print(f"  {status}   {pip_name}")
    print()
    print("  You can now run:")
    print("    python Ph_evac_route.py")
    print("    python testing_suite.py")
    print()
    if os.name == "nt":
        input("  Press Enter to close...")


if __name__ == "__main__":
    main()
