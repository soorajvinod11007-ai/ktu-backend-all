import sys
from pathlib import Path

# Path to college-result-pro
frontend_dir = Path(r"C:\Users\ADMIN\OneDrive\college-result-pro")

# 1. Update ResourceTable.jsx
rt_path = frontend_dir / "src" / "pages" / "admin" / "ResourceTable.jsx"
if rt_path.exists():
    content = rt_path.read_text(encoding="utf-8")
    old_students = "{ key:'program_id', label:'Program' }, { key:'batch_id', label:'Batch' }, { key:'division_id', label:'Div' }"
    new_students = "{ key:'program_id', label:'Program', render:(_, r) => r.program_code || r.program_id }, { key:'batch_id', label:'Batch', render:(_, r) => r.batch_label || r.batch_id }, { key:'division_id', label:'Div', render:(_, r) => r.division_name || '-' }"
    
    # Also faculty program_id
    old_faculty = "{ key:'program_id', label:'Program' }, statusCol"
    new_faculty = "{ key:'program_id', label:'Program', render:(_, r) => r.program_code || r.program_id }, statusCol"

    # Also course-offerings
    old_offerings = "{ key:'subject_id', label:'Subject' }, { key:'faculty_id', label:'Faculty' }, { key:'batch_id', label:'Batch' }"
    new_offerings = "{ key:'subject_id', label:'Subject', render:(_, r) => r.subject_code || r.subject_id }, { key:'faculty_id', label:'Faculty', render:(_, r) => r.faculty_name || r.faculty_id }, { key:'batch_id', label:'Batch', render:(_, r) => r.batch_label || r.batch_id }"

    # Also results
    old_results = "{ key:'student_id', label:'Student' }, { key:'subject_id', label:'Subject' }, { key:'exam_session_id', label:'Session' }"
    new_results = "{ key:'student_id', label:'Student', render:(_, r) => r.student_name || r.register_no || r.student_id }, { key:'subject_id', label:'Subject', render:(_, r) => r.subject_code || r.subject_id }, { key:'exam_session_id', label:'Session', render:(_, r) => r.exam_session_name || r.exam_session_id }"

    # Also grade-cards
    old_gc = "{ key:'student_id', label:'Student' }, { key:'semester', label:'Sem' }, { key:'exam_session_id', label:'Session' }"
    new_gc = "{ key:'student_id', label:'Student', render:(_, r) => r.student_name || r.register_no || r.student_id }, { key:'semester', label:'Sem' }, { key:'exam_session_id', label:'Session', render:(_, r) => r.exam_session_name || r.exam_session_id }"

    content = content.replace(old_students, new_students)
    content = content.replace(old_faculty, new_faculty)
    content = content.replace(old_offerings, new_offerings)
    content = content.replace(old_results, new_results)
    content = content.replace(old_gc, new_gc)

    # Toast error message improvement
    content = content.replace("toast(`Failed to load ${label}`, 'error');", "toast(`Failed to load ${label}: ${err.response?.data?.error?.message || err.message}`, 'error');")
    # check if catch (err)
    content = content.replace("} catch {\n      toast(`Failed to load", "} catch (err) {\n      toast(`Failed to load")
    content = content.replace("} catch {\r\n      toast(`Failed to load", "} catch (err) {\r\n      toast(`Failed to load")

    rt_path.write_text(content, encoding="utf-8")
    print("ResourceTable.jsx updated")

# 2. Update FlaggedStudents.jsx
fs_path = frontend_dir / "src" / "pages" / "admin" / "FlaggedStudents.jsx"
if fs_path.exists():
    fs_content = fs_path.read_text(encoding="utf-8")
    old_fs_cols = """    { key: 'register_no', label: 'Reg No',  sortable: true, className: 'font-mono text-xs' },
    { key: 'name',        label: 'Name',    sortable: true },
    { key: 'program_id',  label: 'Program' },
    { key: 'batch_id',    label: 'Batch' },
    { key: 'division_id', label: 'Div' },"""
    new_fs_cols = """    { key: 'register_no', label: 'Reg No',  sortable: true, className: 'font-mono text-xs' },
    { key: 'name',        label: 'Name',    sortable: true },
    { key: 'program_id',  label: 'Program', render: (_, r) => r.program_code || r.program_id },
    { key: 'batch_id',    label: 'Batch',   render: (_, r) => r.batch_label || r.batch_id },
    { key: 'division_id', label: 'Div',     render: (_, r) => r.division_name || '-' },"""
    fs_content = fs_content.replace(old_fs_cols, new_fs_cols)
    fs_path.write_text(fs_content, encoding="utf-8")
    print("FlaggedStudents.jsx updated")

print("All updates applied successfully.")
