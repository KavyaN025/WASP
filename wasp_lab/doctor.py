import sys
import os
import importlib

def run_doctor():
    print("[Doctor] Running WASP Environment Checks...")
    errors = 0
    
    # Check Python
    print(f"[OK] Python version: {sys.version.split()[0]}")
    
    # Check packages
    required = ["fastapi", "uvicorn", "websockets", "numpy", "pydantic"]
    for pkg in required:
        try:
            importlib.import_module(pkg)
            print(f"[OK] Package installed: {pkg}")
        except ImportError:
            print(f"[FAIL] Missing package: {pkg}")
            errors += 1
            
    # Check server file
    server_path = os.path.join(os.path.dirname(__file__), "server", "app.py")
    if os.path.exists(server_path):
        print(f"[OK] Server app found: {server_path}")
    else:
        print(f"[FAIL] Server app missing: {server_path}")
        errors += 1
        
    if errors == 0:
        print("\n[SUCCESS] All environment checks passed! Ready to run 'wasp server' and 'wasp terminal'.")
    else:
        print(f"\n[WARNING] {errors} checks failed.")

if __name__ == "__main__":
    run_doctor()
