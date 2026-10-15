# Study Helper API

A Django REST Framework API that helps students plan, track and improve their studying:
CRUD for tasks, lessons, notes, grades, schedules and more; generated study schedules and
statistics; and integrations with ZenQuotes, Open Trivia DB, CORE, Gmail and Google Calendar.

## Quick start

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # then fill in the values (see below)
python manage.py migrate
python manage.py runserver
```

The API runs at `http://127.0.0.1:8000/api/`. Run the tests with `python manage.py test study`.

Import `Study Helper API v2.postman_collection.json` into Postman. Run **Auth > Register** (or
**Login**) first; the tokens are saved automatically and used by every other request.

## Configuration (`.env`)

| Variable | Needed for | How to get it |
|---|---|---|
| `DJANGO_SECRET_KEY` | everything | `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` |
| `CORE_API_KEY` | `/study-resources-recommendations` | Free key from https://core.ac.uk/services/api (sent by email) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Gmail and Calendar | Google Cloud setup below |
| `GOOGLE_REDIRECT_URI` | Gmail and Calendar | Leave as `http://127.0.0.1:8000/api/oauth/callback/` |
| `CALENDAR_TIME_ZONE` | `/add-exam-to-calendar` | IANA time zone, e.g. `Asia/Manila` |

ZenQuotes and Open Trivia DB need no keys. Restart `runserver` after editing `.env`.

### Google Cloud setup (Gmail + Calendar)

1. Go to https://console.cloud.google.com and create a project.
2. **APIs & Services > Library**: enable **Gmail API** and **Google Calendar API**.
3. **Google Auth Platform** (also called *OAuth consent screen*): set an app name and your email,
   choose **External** as the audience. Under **Audience > Test users**, add the Gmail address you will log in with.
4. **Clients > Create client**: type **Web application**. Under **Authorized redirect URIs** add
   `http://127.0.0.1:8000/api/oauth/callback/` exactly.
5. Copy the client ID and client secret into `.env` (the secret may only be shown once; download the JSON as a backup).

To connect: in Postman run **1. Connect Google account**, open the returned `authorization_url` in
your browser, sign in, and allow access. Google will warn the app is unverified; choose **Continue**
(normal for apps in testing). In testing mode Google expires the connection after 7 days; just connect again.

## Endpoints

All endpoints except register, token, token/refresh and the OAuth callback need
`Authorization: Bearer <access token>`. Users only ever see their own records (others return 404).
Every path works with or without a trailing slash.

| Endpoint | Description |
|---|---|
| `POST /api/register/` | Create an account; returns access and refresh tokens |
| `POST /api/token/`, `POST /api/token/refresh/` | Log in / refresh the 1-hour access token |
| `POST /api/logout/` | Blacklist the refresh token (`{"refresh": "..."}`) |
| `/api/tasks/`, `/subjects-lessons/`, `/subjects-diary/`, `/study-schedule/`, `/study-resources/`, `/study-break/`, `/study-progress/`, `/study-challenges/`, `/study/quiz/`, `/study-prompt/`, `/study-reflection/`, `/course-grades/`, `/notes/` | Full CRUD (`GET`, `POST`, `GET/PUT/PATCH/DELETE <id>/`) |
| `GET /api/generate-study-statistics/` | Highest/lowest average grade, most/least studied subject (completed sessions only) |
| `GET /api/generate-study-schedule/<schedule_id>/<timer_id>/` | Timetable from 08:00 splitting hours across subjects with study/break intervals, lunch 12:00 and dinner 18:00 |
| `GET /api/motivation/` | Random quote (ZenQuotes) |
| `GET /api/resources/quiz/?subject=` | Trivia questions (Open Trivia DB) |
| `GET /api/study-resources-recommendations/<type>/?subject=` | Research works (CORE) |
| `GET /api/oauth/redirect/` | Returns the Google login URL |
| `POST /api/send-study-notes/` | Email a note via Gmail (`to_email`, `note_id`) |
| `POST /api/add-exam-to-calendar/` | Add an exam event (`exam_date`, `exam_time` HH:MM, `subject`, optional `duration_minutes`) |

Error codes for integrations: **401** Google not connected, **403** Google permission missing,
**502** the external service failed, **503** the server is missing that service's key.

## Code layout

| File | Contents |
|---|---|
| `study/models.py` | Database models; `OwnedModel` gives each record an owner and timestamp |
| `study/views.py` | API views; `OwnedViewSet` limits every CRUD endpoint to the logged-in user |
| `study/planner.py` | Schedule generation and statistics (plain Python, no Django) |
| `study/integrations.py` | All third-party HTTP calls and the Google OAuth flow |
| `study/tests.py` | Tests; external services are mocked so tests run offline |
