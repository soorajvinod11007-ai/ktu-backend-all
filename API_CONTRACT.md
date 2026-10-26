# College Result Analysis: API Contract

For the frontend team. Backend: FastAPI. Base URL: `http://localhost:8000/api/v1`
Live docs once the backend runs: `http://localhost:8000/docs` (Swagger) and `/openapi.json`.

## 1. Two users, two screens

| Role | Can do | Cannot do |
|---|---|---|
| **admin** | Everything: login, dashboard, full CRUD on all tables, file uploads, reports, exports | n/a |
| **principal** | Login, view reports, export PDF/Excel, view dashboard summary | Create, edit, delete, or upload anything |

The login response includes `role`. The frontend shows the admin app or the principal app based on it. The backend enforces it too (wrong role returns 403).

## 2. Conventions

- All requests and responses are JSON, except file uploads (`multipart/form-data`) and exports (file download).
- Auth header on every request except login and health: `Authorization: Bearer <access_token>`
- Dates are ISO 8601. Percentages are numbers with 2 decimals (e.g. `57.41`).
- Deleting is a soft delete. Deleted rows disappear from lists but can be restored by admin.

**Standard error (every failure uses this shape):**
```json
{
  "error": {
    "code": "DUPLICATE",
    "message": "Register number NIE22CS045 already exists",
    "details": [{"field": "register_no", "issue": "duplicate"}],
    "request_id": "b3f1c2d4-..."
  }
}
```
Error codes: `VALIDATION_FAILED` (422), `NOT_FOUND` (404), `DUPLICATE` (409), `CONFLICT` (409, e.g. deleting a student who has results), `UNAUTHORIZED` (401), `PERMISSION_DENIED` (403), `PARSE_ERROR` (422, includes `page` and `row`), `INTERNAL_ERROR` (500).
On 401 the frontend should try `/auth/refresh` once, then go to the login screen.

**List response (every list endpoint):**
```json
{
  "items": [ ... ],
  "total": 214,
  "page": 1,
  "page_size": 25
}
```
List query params (all optional): `page`, `page_size` (max 100), `search`, `sort` (e.g. `name` or `-created_at`), plus resource filters listed below.

## 3. Auth (both roles)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/auth/login` | Login with username and password |
| POST | `/auth/refresh` | Get a new access token |
| POST | `/auth/logout` | Invalidate refresh token |
| GET | `/auth/me` | Current user and role |
| POST | `/auth/change-password` | Change own password |

Login request: `{"username": "admin", "password": "..."}`
Login response:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {"id": 1, "username": "admin", "role": "admin"}
}
```

## 4. Admin: dashboard summary

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/admin/dashboard` | Record counts per table, recent uploads, flagged students count |

Response:
```json
{
  "counts": {"students": 1306, "faculty": 40, "subjects": 85, "results": 20450, "batches": 7},
  "flagged_students": 3,
  "recent_uploads": [
    {"id": 12, "file_name": "result_NIE.pdf", "file_type": "result", "status": "completed",
     "rows_parsed": 120, "rows_failed": 2, "uploaded_at": "2026-09-18T10:40:00Z"}
  ]
}
```

## 5. Admin: CRUD for every table

Every resource below supports the **same five operations**, so the frontend can build one reusable table screen.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/admin/{resource}` | List (paginated, searchable, sortable, filterable) |
| GET | `/admin/{resource}/{id}` | Get one |
| POST | `/admin/{resource}` | Create |
| PATCH | `/admin/{resource}/{id}` | Update (send only changed fields) |
| DELETE | `/admin/{resource}/{id}` | Soft delete (409 if other data depends on it) |
| POST | `/admin/{resource}/{id}/restore` | Restore a deleted row |
| GET | `/admin/{resource}/export` | Download Excel of the current filtered list |
| POST | `/admin/{resource}/import` | Bulk create from Excel/CSV (returns a preview first, see section 6) |

**Resources and their filters**

| `{resource}` | Main fields | Extra filters |
|---|---|---|
| `users` | username, email, role, is_active | `role` |
| `programs` | code, name, is_active | none |
| `batches` | start_year, end_year, label | none |
| `divisions` | program_id, batch_id, name | `program_id`, `batch_id` |
| `students` | register_no, name, program_id, batch_id, division_id, status, is_flagged | `program_id`, `batch_id`, `division_id`, `status`, `is_flagged` |
| `faculty` | ktu_id, name, email, phone, program_id, is_active | `program_id`, `is_active` |
| `subjects` | code, name, credits, semester, scheme, type | `semester`, `scheme`, `type` |
| `course-offerings` | subject_id, faculty_id, batch_id, division_id, program_id, semester, academic_year, slot, part_label, is_main_faculty | `program_id`, `batch_id`, `division_id`, `semester`, `academic_year`, `faculty_id` |
| `exam-sessions` | name, exam_type, scheme, published_on | `exam_type` |
| `results` | student_id, subject_id, exam_session_id, semester, grade, status | `student_id`, `subject_id`, `exam_session_id`, `semester`, `status` |
| `grade-cards` | student_id, semester, exam_session_id, earned_credits, cumulative_credits, sgpa, cgpa | `student_id`, `semester`, `exam_session_id` |
| `result-history` | read-only: old/new grade, change_type | `semester_result_id` |
| `upload-logs` | read-only: file, type, user, counts, status | `file_type`, `status` |

Example: create a student
```
POST /admin/students
{"register_no": "NIE22CS045", "name": "SHEHZNA T B", "program_id": 1, "batch_id": 4, "division_id": 1, "status": "active"}
```
Example: list CS students of batch 4, division A
```
GET /admin/students?program_id=1&batch_id=4&division_id=1&page=1&page_size=25&search=shehz&sort=register_no
```
Dropdown helper for forms (returns `[{id, label}]`, no pagination): `GET /admin/options/{resource}`

## 6. Admin: file uploads (two steps: preview, then confirm)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/uploads/preview` | Upload a file, get parsed rows and errors, nothing saved yet |
| POST | `/uploads/{upload_id}/confirm` | Save the previewed data |
| DELETE | `/uploads/{upload_id}` | Cancel a preview |
| GET | `/uploads` | Upload history |

Preview request (`multipart/form-data`): `file` (the file), `file_type` = `student_list` | `course_book` | `grade_card` | `result` | `revaluation`. Optional: `exam_session_id`.

Preview response:
```json
{
  "upload_id": 31,
  "file_type": "grade_card",
  "summary": {"rows_total": 52, "rows_ok": 50, "rows_with_errors": 2, "new": 48, "updates": 2},
  "sample_rows": [ {"register_no": "NIE22CS045", "sgpa": 5.94, "cgpa": 5.94} ],
  "errors": [
    {"page": 2, "row": 11, "code": "UNKNOWN_REGISTER_NO", "message": "SGI22CS013 not in student list"}
  ]
}
```
UI idea: a table of rows, errors highlighted in red, and a **Confirm** button. Confirm is disabled until the admin accepts or fixes the errors (the admin can choose "skip error rows").

## 7. Reports (principal and admin)

All reports are `GET`, return JSON, and have `.pdf` and `.xlsx` versions that use the NiCE printed layout.

| Report | JSON | Download |
|---|---|---|
| Course-wise Faculty-wise Performance | `/reports/course-faculty-performance` | add `/pdf` or `/xlsx` |
| Faculty Performance History | `/reports/faculty-history` | add `/pdf` or `/xlsx` |
| Student-wise Supplementary Status | `/reports/supplementary-status` | add `/pdf` or `/xlsx` |
| Program & Semester-wise | `/reports/program-semester` | add `/pdf` or `/xlsx` |
| Graduation Statistics | `/reports/graduation` | add `/pdf` or `/xlsx` |

Example download: `GET /reports/program-semester/pdf?academic_year=2025-26`

**Filters per report**

| Report | Required | Optional |
|---|---|---|
| course-faculty-performance | `program_id`, `batch_id`, `semester`, `academic_year` | `division_id` |
| faculty-history | `faculty_id` | `academic_year` |
| supplementary-status | `program_id`, `batch_id` | `division_id` |
| program-semester | `academic_year` | `program_id` |
| graduation | none | `batch_id`, `program_id` |

Note: CS division A and B are separate. When `division_id` is not sent for CS, the response contains both divisions as separate sections.

**Dropdown data for the filter bar** (no pagination): `GET /reports/filters` returns programs, batches, divisions, academic years, semesters, and faculty.

**Response: course-faculty-performance**
```json
{
  "header": {"program": "Computer Science and Engineering", "batch": "2022-26", "division": "A", "semester": "S1", "academic_year": "2022-23"},
  "rows": [
    {"sl_no": 1, "course_code": "MAT101", "course_title": "LINEAR ALGEBRA AND CALCULUS",
     "faculty": "Ms Anu Jose", "registered": 53, "appeared": 50, "absent": 3,
     "pass": 28, "fail": 22, "withheld": 0,
     "pass_pct_registered": 52.83, "pass_pct_appeared": 56.00, "remarks": ""}
  ],
  "supply_status": {"0": 12, "1": 8, "2": 10, "3": 6, "4": 5, "5": 4, "6": 3, "7": 2, "8": 1, "total": 51},
  "overall": {"registered": 53, "appeared": 53, "cleared_all": 12, "class_all_pass_pct": 22.64},
  "toppers": [{"rank": 1, "name": "ROSHNI SOORIAN", "sgpa": 8.76}]
}
```

**Response: program-semester**
```json
{
  "academic_year": "2025-26",
  "rows": [
    {"sl_no": 1, "program": "Artificial Intelligence and Data Science", "batch": "2025-29",
     "semester": "S1", "registered": 54, "passed": 18, "pass_pct": 33.33}
  ],
  "total": {"registered": 1306, "passed": 642, "avg_pass_pct": 49.16}
}
```

**Response: supplementary-status**
```json
{
  "header": {"program": "Mechatronics", "batch": "2022-26", "updated_on": "2026-09-18"},
  "rows": [
    {"sl_no": 1, "register_no": "NIE22MC016", "name": "HALEEL K N",
     "supply": {"S1": 3, "S2": 0, "S3": 0, "S4": 0, "S5": 0, "S6": 0, "S7": 0, "S8": 0},
     "total_supply": 3, "total_courses": 9, "cgpa": 2.18}
  ],
  "status_summary": {"0": 4, "1": 6, "2": 3, "3": 5, "4": 2, "5": 1, "6": 0, "7": 0, "8": 0}
}
```

**Response: faculty-history**
```json
{
  "faculty": {"name": "Ms Anu Jose", "department": "CSE"},
  "rows": [
    {"sl_no": 1, "batch": "2022-26", "academic_year": "2022-23", "course_code": "MAT101",
     "course_name": "LINEAR ALGEBRA AND CALCULUS", "registered": 53, "appeared": 50, "absent": 3,
     "pass": 28, "fail": 22, "withheld": 0, "pass_pct_registered": 52.83, "pass_pct_appeared": 56.00}
  ]
}
```

**Response: graduation**
```json
{
  "rows": [
    {"sl_no": 1, "batch": "2022-26", "program": "Computer Science", "registered_s8": 54,
     "graduated_zero_supply": 42, "graduation_pct": 77.78}
  ],
  "total": {"registered_s8": 90, "graduated_zero_supply": 71, "graduation_pct": 78.89}
}
```

## 8. Health (no login)

`GET /health` returns `{"status": "ok", "database": "ok"}`

## 9. Suggested screens

**Admin app:** Login, Dashboard (counts + recent uploads), one generic Table screen reused for every resource (search, filters, add, edit, delete, restore, export), Upload screen (choose type, preview table, confirm), Upload history, Flagged students list.

**Principal app:** Login, Report home (5 report cards), filter bar plus report view, Download PDF and Excel buttons. No edit controls anywhere.

## 10. How to test the backend

**Quick check (no code)**
1. Start the backend: `uvicorn app.main:app --reload`
2. Open `http://localhost:8000/docs`
3. Call `POST /auth/login` with the seeded admin, click **Authorize** (top right), and paste the access token.
4. Try each endpoint from the page. The page lists every field and shows real responses.

**Postman or Insomnia**
1. Import `http://localhost:8000/openapi.json`. Every endpoint appears automatically.
2. Create an environment with `base_url` and `token`, and use `Bearer {{token}}` as the auth.

**curl smoke test**
```bash
# 1. login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"YOUR_PASSWORD"}'

# 2. use the token
curl http://localhost:8000/api/v1/admin/dashboard \
  -H "Authorization: Bearer TOKEN"

# 3. check permissions: principal token on a write must return 403
curl -X POST http://localhost:8000/api/v1/admin/students \
  -H "Authorization: Bearer PRINCIPAL_TOKEN" \
  -H "Content-Type: application/json" -d '{}'
```

**Automated tests (backend team)**
`pytest -q`. Minimum checks before handing over to the frontend:
- Login works and wrong password returns 401.
- Principal gets 403 on every admin write endpoint.
- Create, update, delete, restore work for each resource.
- Deleting a student with results returns 409.
- Upload preview returns errors for an unknown register number.
- `program-semester` for AY 2025-26 matches the filled printed sheet (e.g. total registered 1306, passed 642, average 49.16%).

**While the backend is not ready:** frontend can work from the sample responses above, or run a mock server from the OpenAPI file: `npx @stoplight/prism-cli mock http://localhost:8000/openapi.json`.

## 11. Rules for the frontend team

- Never hardcode program, batch, or semester lists. Load them from `/reports/filters` or `/admin/options/{resource}`.
- Show the `error.message` to the user and log the `error.request_id` (the backend team uses it to find the problem).
- Hide buttons the role cannot use, but never rely on that alone: the backend is the real gatekeeper.
- Treat percentages as numbers and format them in the UI.
