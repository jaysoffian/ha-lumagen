#!/usr/bin/env python3
"""Verify that the coordinator has the correct get_labels() call."""

def check_coordinator():
    """Check if coordinator.py has the correct get_labels() call."""
    with open('custom_components/ha_lumagen/coordinator.py', 'r') as f:
        content = f.read()
    
    # Check for the incorrect call
    if 'get_labels(get_all=' in content:
        print("❌ FOUND INCORRECT CALL: get_labels(get_all=...)")
        print("   The code still has the old API call")
        return False
    
    # Check for the correct call
    if 'get_labels()' in content:
        print("✅ CORRECT: get_labels() is called without parameters")
        return True
    
    print("⚠️  WARNING: Could not find get_labels() call")
    return False

if __name__ == '__main__':
    if check_coordinator():
        print("\nThe code is correct. Please restart Home Assistant to load the updated code.")
    else:
        print("\nThe code needs to be fixed.")
