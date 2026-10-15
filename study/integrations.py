"""
Calls to third-party APIs: ZenQuotes, Open Trivia DB, CORE, Gmail and Google Calendar.

Failures are raised as DRF exceptions, so views can call these functions directly
and the client gets a clear JSON error with a meaningful status code.
"""
import base64
import html
from datetime import timedelta
from email.message import EmailMessage
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from .models import GoogleCredential

TIMEOUT = 10  # seconds


class ExternalServiceError(APIException):
    status_code = 502
    default_detail = 'An external service failed to respond.'


class ServiceNotConfigured(APIException):
    status_code = 503
    default_detail = 'This feature is not configured on the server.'


class GoogleAuthRequired(APIException):
    status_code = 401
    default_detail = 'Connect your Google account first: GET /api/oauth/redirect/ and open the returned URL.'


class GoogleScopeMissing(APIException):
    status_code = 403
    default_detail = 'Your Google account did not grant the required permission. Reconnect via /api/oauth/redirect/.'


def _get_json(url, service, **kwargs):
    try:
        response = requests.get(url, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise ExternalServiceError(f'Could not reach {service}.') from exc
    if response.status_code in (401, 403):
        raise ExternalServiceError(f'{service} rejected the request. Check the API key.')
    if not response.ok:
        raise ExternalServiceError(f'{service} returned HTTP {response.status_code}.')
    try:
        return response.json()
    except ValueError as exc:
        raise ExternalServiceError(f'{service} returned an invalid response.') from exc


# --- ZenQuotes -------------------------------------------------------------

def get_random_quote():
    data = _get_json('https://zenquotes.io/api/random', 'ZenQuotes')
    try:
        return {'quote': data[0]['q'], 'author': data[0]['a']}
    except (IndexError, KeyError, TypeError) as exc:
        raise ExternalServiceError('ZenQuotes returned an unexpected response.') from exc


# --- Open Trivia DB --------------------------------------------------------

# Open Trivia DB only knows fixed categories, so subjects are mapped onto them.
TRIVIA_CATEGORIES = {
    'general knowledge': 9, 'books': 10, 'literature': 10, 'film': 11, 'music': 12,
    'science': 17, 'nature': 17, 'biology': 17, 'chemistry': 17, 'physics': 17,
    'computers': 18, 'computer science': 18, 'programming': 18, 'technology': 18,
    'mathematics': 19, 'math': 19, 'mythology': 20, 'sports': 21, 'geography': 22,
    'history': 23, 'politics': 24, 'art': 25, 'animals': 27, 'vehicles': 28,
}


def fetch_trivia_questions(subject, amount=10):
    category = TRIVIA_CATEGORIES.get(subject.strip().lower())
    if category is None:
        raise ValidationError({'subject': f'Unsupported subject. Choose one of: {", ".join(sorted(TRIVIA_CATEGORIES))}.'})

    data = _get_json('https://opentdb.com/api.php', 'Open Trivia DB',
                     params={'amount': amount, 'category': category})
    if data.get('response_code') == 5:
        raise ExternalServiceError('Open Trivia DB allows one request every 5 seconds. Try again shortly.')
    if data.get('response_code') != 0:
        raise ExternalServiceError('Open Trivia DB returned no questions.')

    # Questions come HTML-encoded, e.g. "&quot;" instead of '"'
    return [
        {
            'question': html.unescape(q['question']),
            'correct_answer': html.unescape(q['correct_answer']),
            'incorrect_answers': [html.unescape(a) for a in q['incorrect_answers']],
            'difficulty': q['difficulty'],
        }
        for q in data['results']
    ]


# --- CORE ------------------------------------------------------------------

def search_core(subject, resource_type=None, limit=10):
    if not settings.CORE_API_KEY:
        raise ServiceNotConfigured('CORE_API_KEY is not set. Add it to the .env file.')

    data = _get_json('https://api.core.ac.uk/v3/search/works', 'CORE',
                     params={'q': subject, 'limit': limit},
                     headers={'Authorization': f'Bearer {settings.CORE_API_KEY}'})
    results = []
    for work in data.get('results', []):
        display_links = [link['url'] for link in work.get('links', []) if link.get('type') == 'display']
        results.append({
            'title': work.get('title'),
            'url': work.get('downloadUrl') or next(iter(display_links), f'https://core.ac.uk/works/{work.get("id")}'),
            'type': work.get('documentType') or resource_type or 'article',
        })
    return results


# --- Google OAuth ----------------------------------------------------------

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GMAIL_SCOPE = 'https://www.googleapis.com/auth/gmail.send'
CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar.events'
STATE_SALT = 'study.google-oauth'
STATE_MAX_AGE = 10 * 60  # the login link expires after 10 minutes


def _require_google_config():
    if not (settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET):
        raise ServiceNotConfigured('GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are not set. Add them to the .env file.')


def build_google_auth_url(user):
    """
    The browser that finishes the Google login carries no JWT, so the user's id
    travels in `state`, signed so it cannot be forged or reused after it expires.
    """
    _require_google_config()
    params = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': f'{GMAIL_SCOPE} {CALENDAR_SCOPE}',
        'access_type': 'offline',  # also return a refresh token
        'prompt': 'consent',
        'include_granted_scopes': 'true',
        'state': signing.dumps(user.pk, salt=STATE_SALT),
    }
    return f'{GOOGLE_AUTH_URL}?{urlencode(params)}'


def user_id_from_state(state):
    """Raises django.core.signing.BadSignature if the state is forged or expired."""
    return signing.loads(state, salt=STATE_SALT, max_age=STATE_MAX_AGE)


def _request_tokens(data, error):
    payload = {**data, 'client_id': settings.GOOGLE_CLIENT_ID, 'client_secret': settings.GOOGLE_CLIENT_SECRET}
    try:
        response = requests.post(GOOGLE_TOKEN_URL, data=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ExternalServiceError('Could not reach Google.') from exc
    if not response.ok:
        raise error
    return response.json()


def _save_tokens(credential, tokens):
    credential.access_token = tokens['access_token']
    credential.expires_at = timezone.now() + timedelta(seconds=tokens.get('expires_in', 3600))
    if tokens.get('refresh_token'):
        credential.refresh_token = tokens['refresh_token']
    if tokens.get('scope'):
        credential.scopes = tokens['scope']
    credential.save()


def connect_google_account(user, code):
    _require_google_config()
    tokens = _request_tokens(
        {'code': code, 'grant_type': 'authorization_code', 'redirect_uri': settings.GOOGLE_REDIRECT_URI},
        ExternalServiceError('Google rejected the login code. Start again at /api/oauth/redirect/.'),
    )
    credential = GoogleCredential.objects.filter(user=user).first() or GoogleCredential(user=user)
    _save_tokens(credential, tokens)


def _google_access_token(user, scope):
    credential = GoogleCredential.objects.filter(user=user).first()
    if credential is None:
        raise GoogleAuthRequired()
    if scope not in credential.scopes.split():
        raise GoogleScopeMissing()
    if credential.expires_at <= timezone.now() + timedelta(seconds=60):
        if not credential.refresh_token:
            raise GoogleAuthRequired()
        _require_google_config()
        tokens = _request_tokens(
            {'grant_type': 'refresh_token', 'refresh_token': credential.refresh_token},
            GoogleAuthRequired('Your Google login expired or was revoked. Reconnect via /api/oauth/redirect/.'),
        )
        _save_tokens(credential, tokens)
    return credential.access_token


def _google_post(user, scope, url, payload, service):
    token = _google_access_token(user, scope)
    try:
        response = requests.post(url, json=payload, headers={'Authorization': f'Bearer {token}'}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ExternalServiceError(f'Could not reach {service}.') from exc
    if response.status_code == 401:
        raise GoogleAuthRequired()
    if not response.ok:
        # Surface Google's own message, e.g. "Gmail API has not been used in project ... or it is disabled"
        try:
            message = response.json()['error']['message']
        except (ValueError, KeyError, TypeError):
            message = f'HTTP {response.status_code}'
        raise ExternalServiceError(f'{service} error: {message}')
    return response.json()


# --- Gmail and Google Calendar ---------------------------------------------

def send_note_email(user, to_email, note):
    message = EmailMessage()
    message['To'] = to_email
    message['Subject'] = f'Study notes: {note.subject}'
    message.set_content(note.note_content)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    _google_post(user, GMAIL_SCOPE, 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
                 {'raw': raw}, 'Gmail')


def add_exam_event(user, subject, start, duration_minutes):
    """`start` is a naive datetime interpreted in settings.CALENDAR_TIME_ZONE."""
    end = start + timedelta(minutes=duration_minutes)
    event = {
        'summary': f'{subject} exam',
        'description': 'Added by Study Helper API',
        'start': {'dateTime': start.isoformat(), 'timeZone': settings.CALENDAR_TIME_ZONE},
        'end': {'dateTime': end.isoformat(), 'timeZone': settings.CALENDAR_TIME_ZONE},
    }
    created = _google_post(user, CALENDAR_SCOPE, 'https://www.googleapis.com/calendar/v3/calendars/primary/events',
                           event, 'Google Calendar')
    return created.get('htmlLink')
