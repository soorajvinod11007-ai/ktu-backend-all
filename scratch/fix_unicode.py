from pathlib import Path

p = Path(r"C:\Users\ADMIN\OneDrive\college-result-pro\src\pages\admin\ResourceTable.jsx")
content = p.read_text(encoding="utf-8")

# Fix garbled em-dash/en-dash characters that are corrupted
# Replace any broken unicode placeholders with simple '-'
import re

# The broken characters appear as various sequences - fix them all
content = content.replace('\u00e2\u0080\u0093', '-')   # UTF-8 en-dash mis-decoded
content = content.replace('\u00e2\u0080\u0094', '-')   # UTF-8 em-dash mis-decoded
content = content.replace('\ufffd', '-')                # replacement char
content = content.replace('\u2013', '-')                # en-dash
content = content.replace('\u2014', '-')                # em-dash

# Also ensure gradeBadge is in imports
if 'gradeBadge' not in content.split('\n')[8]:  # line 9 is the formatters import
    content = content.replace(
        "import { RESOURCE_LABELS, statusBadge, fmtDate, fmtPct, downloadBlob } from '../../utils/formatters';",
        "import { RESOURCE_LABELS, statusBadge, gradeBadge, fmtDate, fmtPct, downloadBlob } from '../../utils/formatters';"
    )

p.write_text(content, encoding="utf-8")
print("Fixed ResourceTable.jsx")
print("First 500 chars of results section:")
idx = content.find("results:   [")
print(repr(content[idx:idx+400]))
