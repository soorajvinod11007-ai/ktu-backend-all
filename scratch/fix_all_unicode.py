from pathlib import Path

frontend_src = Path(r"C:\Users\ADMIN\OneDrive\college-result-pro\src")

# Find all jsx and js files with corrupted characters
files = list(frontend_src.rglob("*.jsx")) + list(frontend_src.rglob("*.js"))

fixed_count = 0
for f in files:
    try:
        content = f.read_text(encoding="utf-8")
        original = content

        # Replace the corrupted placeholder sequences
        # The em-dash/en-dash often shows as garbled bytes
        content = content.replace('\u00e2\u0080\u0093', '-')
        content = content.replace('\u00e2\u0080\u0094', '-')
        content = content.replace('\ufffd', '-')

        # Fix the specific corrupt placeholder used in render functions
        # It appears as '?' followed by escaped quote
        import re
        # Pattern: a string literal containing the broken placeholder
        # Replace '—' (em-dash encoded weirdly) with '-'
        content = re.sub(r"'\?\"'", "'-'", content)
        content = re.sub(r'"\?\""', '"-"', content)

        if content != original:
            f.write_text(content, encoding="utf-8")
            print(f"Fixed: {f.name}")
            fixed_count += 1
    except Exception as e:
        print(f"Error processing {f}: {e}")

print(f"\nTotal files fixed: {fixed_count}")
