#!/usr/bin/env python3
"""
Quick installation test for Guaraci.
"""

def test_imports():
    """Test that all core imports work."""
    try:
        import guaraci
        print(f"✅ Guaraci version: {guaraci.__version__}")
        
        from guaraci.datasus import SinanDataSource
        print("✅ SinanDataSource import successful")
        
        from guaraci.core.config import GuaraciConfig
        print("✅ GuaraciConfig import successful")
        
        from guaraci.utils.mapping import utility_mapping
        print("✅ Utility mapping import successful")
        
        # Test basic functionality
        config = GuaraciConfig()
        print(f"✅ Config initialized: {config.data_root}")
        
        # Test UF mapping
        result = utility_mapping(35)
        assert result == 'SP', f"Expected 'SP', got {result}"
        print("✅ UF mapping working correctly")
        
        # Test SINAN initialization (may warn about PySUS)
        try:
            sinan = SinanDataSource()
            print("✅ SinanDataSource initialized")
        except ImportError as e:
            print(f"⚠️ SinanDataSource limited functionality: {e}")
        
        print("\n🎉 All core imports and basic functionality working!")
        return True
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_imports()
    exit(0 if success else 1)