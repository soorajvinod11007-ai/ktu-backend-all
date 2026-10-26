from pathlib import Path

p = Path(r"C:\Users\ADMIN\OneDrive\college-result-pro\src\utils\formatters.js")
content = p.read_text(encoding="utf-8")

# Fix statusBadge to include result statuses (pass/fail/absent/withheld/tbp)
old_map = """export const statusBadge = (status) => {
  const map = {
    active:    'badge-success',
    completed: 'badge-success',
    passed:    'badge-success',
    pending:   'badge-warning',
    processing:'badge-warning',
    failed:    'badge-danger',
    error:     'badge-danger',
    inactive:  'badge-default',
  };
  return map[status?.toLowerCase()] ?? 'badge-default';
};"""

new_map = """export const statusBadge = (status) => {
  const map = {
    // student / user statuses
    active:    'badge-success',
    completed: 'badge-success',
    passed:    'badge-success',
    pending:   'badge-warning',
    processing:'badge-warning',
    failed:    'badge-danger',
    error:     'badge-danger',
    inactive:  'badge-default',
    graduated: 'badge-info',
    // result statuses (KTU)
    pass:      'badge-success',
    fail:      'badge-danger',
    absent:    'badge-warning',
    withheld:  'badge-warning',
    tbp:       'badge-default',
    // upload log statuses
    done:      'badge-success',
    confirmed: 'badge-success',
    pending_confirm: 'badge-warning',
  };
  return map[status?.toLowerCase()] ?? 'badge-default';
};"""

content = content.replace(old_map, new_map)
p.write_text(content, encoding="utf-8")
print("Updated statusBadge in formatters.js")
