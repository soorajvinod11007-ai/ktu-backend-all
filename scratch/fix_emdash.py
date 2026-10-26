from pathlib import Path

frontend_src = Path(r"C:\Users\ADMIN\OneDrive\college-result-pro\src")

# The em-dash U+2014 (0xe2 0x80 0x94 in UTF-8) is used as placeholder
EM_DASH = '\u2014'   # —
EN_DASH = '\u2013'   # –

files = list(frontend_src.rglob("*.jsx")) + list(frontend_src.rglob("*.js"))

fixed_count = 0
for f in files:
    try:
        content = f.read_text(encoding="utf-8")
        original = content
        content = content.replace(EM_DASH, '-').replace(EN_DASH, '-')
        if content != original:
            f.write_text(content, encoding="utf-8")
            print(f"Fixed: {f.name}")
            fixed_count += 1
    except Exception as e:
        print(f"Error {f.name}: {e}")

print(f"\nDone. Fixed {fixed_count} file(s).")
