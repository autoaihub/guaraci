#!/usr/bin/env python3
try:
    import pysus
    print("✅ PySUS is available")
    print(f"PySUS version: {pysus.__version__}")
except ImportError as e:
    print("⚠️ PySUS is not available")
    print(f"Error: {e}")

try:
    from guaraci.datasus.sinan import SinanDataSource
    sinan = SinanDataSource()
    print("✅ SinanDataSource initialized successfully")
except Exception as e:
    print(f"⚠️ SinanDataSource error: {e}")