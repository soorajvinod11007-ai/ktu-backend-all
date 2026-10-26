from pathlib import Path

p = Path(r"C:\Users\ADMIN\OneDrive\college-result-pro\src\pages\admin\ResourceTable.jsx")
c = p.read_text(encoding="utf-8")
old = "{ key:'program_id', label:'Program ID' }, { key:'batch_id', label:'Batch ID' }"
new = "{ key:'program_id', label:'Program', render:(_, r) => r.program_code || r.program_id }, { key:'batch_id', label:'Batch', render:(_, r) => r.batch_label || r.batch_id }"
c = c.replace(old, new)
p.write_text(c, encoding="utf-8")
print("Updated divisions columns in ResourceTable")
