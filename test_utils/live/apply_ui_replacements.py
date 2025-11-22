"""
Script to automatically replace print statements with live_ui handlers in live.py
Run this from the command line: python apply_ui_replacements.py
"""

import re
from pathlib import Path

# Define replacement patterns
replacements = [
    # SESSION category
    (r'print\(f"\[SESSION\] (.+?)"\)', r'system_log.info(f"\1", category="SESSION")'),
    (r'print\("\[SESSION\] (.+?)"\)', r'system_log.info("\1", category="SESSION")'),
    
    # VIDEO category  
    (r'print\(f"\[VIDEO\] (.+?)"\)', r'system_log.info(f"\1", category="VIDEO")'),
    (r'print\("\[VIDEO\] (.+?)"\)', r'system_log.info("\1", category="VIDEO")'),
    
    # VIDEO WARNING category (treat as VIDEO with warning text)
    (r'print\(f"\[VIDEO WARNING\] (.+?)"\)', r'system_log.info(f"WARNING: \1", category="VIDEO")'),
    
    # VIDEO ERROR category
    (r'print\(f"\[VIDEO ERROR\] (.+?)"\)', r'system_log.info(f"ERROR: \1", category="VIDEO")'),
   
    # CONNECTION category
    (r'print\(f"\[CONNECTION\] (.+?)"\)', r'system_log.info(f"\1", category="CONNECTION")'),
    (r'print\("\[CONNECTION\] (.+?)"\)', r'system_log.info("\1", category="CONNECTION")'),
    
    # INPUT category
    (r'print\(f"\[INPUT\] (.+?)"\)', r'system_log.info(f"\1", category="INPUT")'),
    (r'print\("\[INPUT\] (.+?)"\)', r'system_log.info("\1", category="INPUT")'),
    
    # TEXT category  
    (r'print\(f"\[TEXT\] (.+?)"\)', r'system_log.info(f"\1", category="TEXT")'),
    (r'print\("\[TEXT\] (.+?)"\)', r'system_log.info("\1", category="TEXT")'),
    
    # PASSIVE category
    (r'print\(f"\[PASSIVE\] (.+?)"\)', r'system_log.info(f"\1", category="PASSIVE")'),
    (r'print\("\[PASSIVE\] (.+?)"\)', r'system_log.info("\1", category="PASSIVE")'),
    
    # DEBUG category (VIDEO_DEBUG conditional)
    (r'if VIDEO_DEBUG:\s+print\(f"\[DEBUG\] (.+?)"\)', r'debug_log.debug(f"\1", category="VIDEO")'),
    (r'if VIDEO_DEBUG:\s+print\(f"\[VIDEO\] (.+?)"\)', r'debug_log.debug(f"\1", category="VIDEO")'),
    
    # System messages (no category prefix)
    (r'print\("\n\[System: (.+?)\]\\n"\)', r'system_log.info("\1", category="PASSIVE")'),
]

def apply_replacements(file_path):
    """Apply all replacements to the file."""
    print(f"Reading {file_path}...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Apply each replacement
    for pattern, replacement in replacements:
        matches = re.findall(pattern, content)
        if matches:
            print(f"  Found {len(matches)} matches for pattern: {pattern[:50]}...")
            content = re.sub(pattern, replacement, content)
    
    # Check if any changes were made
    if content != original_content:
        # Create backup
        backup_path = file_path.with_suffix('.py.backup')
        print(f"\nCreating backup: {backup_path}")
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        
        # Write modified content
        print(f"Writing changes to {file_path}...")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("\n✅ Replacements applied successfully!")
        print(f"   Backup saved to: {backup_path}")
        print(f"   If anything goes wrong, restore with:")
        print(f"   copy {backup_path} {file_path}")
    else:
        print("\n⚠️  No changes needed - all patterns already replaced!")
    
    return content != original_content

if __name__ == "__main__":
    script_dir = Path(__file__).parent
    live_py = script_dir / "live.py"
    
    if not live_py.exists():
        print(f"❌ Error: {live_py} not found!")
        exit(1)
    
    print("=" * 60)
    print("Live UI Replacement Script")
    print("=" * 60)
    print()
    
    try:
        changed = apply_replacements(live_py)
        
        if changed:
            print("\n" + "=" * 60)
            print("Next steps:")
            print("  1. Review the changes in live.py")
            print("  2. Test the script: python live.py")
            print("  3. If there are issues, restore backup")
            print("=" * 60)
    except Exception as e:
        print(f"\n❌ Error during replacement: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
