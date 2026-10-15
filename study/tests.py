from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

import requests as real_requests
from django.contrib.auth.models import User
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import GoogleCredential, Note
from .planner import ScheduleError, build_study_plan, study_statistics

PASSWORD = 'S3cure-pass!'


def patch_requests():
    """Replace the HTTP client used by integrations, keeping its real exception class."""
    return mock.patch('study.integrations.requests',
                      new_callable=lambda: mock.Mock(RequestException=real_requests.RequestException))


def fake_response(status=200, json=None):
    response = mock.Mock(status_code=status, ok=200 <= status < 300)
    response.json.return_value = json
    return response


class AuthenticatedTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', 'alice@example.com', PASSWORD)
        self.login(self.user)

    def login(self, user):
        token = self.client.post('/api/token/', {'username': user.username, 'password': PASSWORD}).data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class AuthTests(APITestCase):
    def test_register_login_refresh_logout(self):
        registered = self.client.post('/api/register/', {'username': 'bob', 'email': 'bob@example.com', 'password': PASSWORD})
        self.assertEqual(registered.status_code, 201)
        self.assertIn('access', registered.data)

        tokens = self.client.post('/api/token/', {'username': 'bob', 'password': PASSWORD}).data
        self.assertIn('access', self.client.post('/api/token/refresh/', {'refresh': tokens['refresh']}).data)

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')
        self.assertEqual(self.client.post('/api/logout/', {'refresh': tokens['refresh']}).status_code, 204)
        # A blacklisted refresh token can no longer issue access tokens
        self.assertEqual(self.client.post('/api/token/refresh/', {'refresh': tokens['refresh']}).status_code, 401)

    def test_weak_password_rejected(self):
        response = self.client.post('/api/register/', {'username': 'bob', 'password': '123'})
        self.assertEqual(response.status_code, 400)

    def test_endpoints_require_login(self):
        self.assertEqual(self.client.get('/api/tasks/').status_code, 401)


class CrudTests(AuthenticatedTestCase):
    # endpoint -> (valid create payload, field to update with PATCH)
    ENDPOINTS = {
        'tasks': ({'task': 'Finish essay', 'goal_date': '2026-11-01'}, {'status': True}),
        'subjects-lessons': ({'subject': 'Math', 'lesson': 'Quadratics'}, {'lesson': 'Limits'}),
        'subjects-diary': ({'subject': 'Physics', 'note': 'Confusing'}, {'note': 'Better now'}),
        'study-schedule': ({'study_date': '2026-11-01', 'study_hours': 3, 'subjects': 'Math,Physics'}, {'study_hours': 4}),
        'study-resources': ({'title': 'Docs', 'url': 'https://example.com', 'subject': 'CS', 'resource_type': 'article'}, {'title': 'New'}),
        'study-break': ({'study_duration': 50, 'break_duration': 10}, {'break_duration': 15}),
        'study-progress': ({'study_session_date': '2026-11-01', 'subject': 'Math', 'completed': True, 'study_hours': 2}, {'study_hours': 3}),
        'study-challenges': ({'challenge_description': 'Daily 2h', 'start_date': '2026-11-01', 'end_date': '2026-11-07'}, {'challenge_description': 'Daily 3h'}),
        'study/quiz': ({'subject': 'Science', 'quiz_content': 'What is ATP?'}, {'quiz_content': 'What is DNA?'}),
        'study-prompt': ({'subject': 'History', 'prompt': 'Causes of WW2'}, {'prompt': 'Causes of WW1'}),
        'study-reflection': ({'reflection_date': '2026-11-01', 'strengths': 'Focus', 'areas_for_improvement': 'Sleep'}, {'strengths': 'Consistency'}),
        'course-grades': ({'course_name': 'Math', 'grade': 95.5}, {'grade': 97}),
        'notes': ({'subject': 'Biology', 'note_content': 'Mitosis'}, {'note_content': 'Meiosis'}),
    }

    def test_crud_on_every_endpoint(self):
        for endpoint, (payload, change) in self.ENDPOINTS.items():
            with self.subTest(endpoint=endpoint):
                created = self.client.post(f'/api/{endpoint}/', payload, format='json')
                self.assertEqual(created.status_code, 201, created.data)
                detail = f'/api/{endpoint}/{created.data["id"]}/'

                self.assertEqual(len(self.client.get(f'/api/{endpoint}').data), 1)  # no trailing slash works too
                patched = self.client.patch(detail, change, format='json')
                self.assertEqual(patched.status_code, 200, patched.data)
                key, value = next(iter(change.items()))
                self.assertEqual(patched.data[key], value)
                self.assertEqual(self.client.put(detail, payload, format='json').status_code, 200)
                self.assertEqual(self.client.delete(detail).status_code, 204)
                self.assertEqual(self.client.get(detail).status_code, 404)

    def test_missing_fields_return_400(self):
        self.assertEqual(self.client.post('/api/notes/', {}).status_code, 400)

    def test_users_only_see_their_own_records(self):
        note_id = self.client.post('/api/notes/', {'subject': 'Bio', 'note_content': 'secret'}).data['id']
        self.login(User.objects.create_user('mallory', password=PASSWORD))
        self.assertEqual(self.client.get('/api/notes/').data, [])
        self.assertEqual(self.client.get(f'/api/notes/{note_id}/').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/notes/{note_id}/').status_code, 404)

    def test_challenge_end_before_start_rejected(self):
        response = self.client.post('/api/study-challenges/', {
            'challenge_description': 'x', 'start_date': '2026-11-07', 'end_date': '2026-11-01'})
        self.assertEqual(response.status_code, 400)


class PlannerTests(SimpleTestCase):
    def test_breaks_between_study_blocks_but_not_at_the_end(self):
        plan = build_study_plan(['Math'], 2, study_minutes=60, break_minutes=10)
        self.assertEqual([(b['type'], b['start_time'], b['end_time']) for b in plan], [
            ('study', '08:00', '09:00'), ('break', '09:00', '09:10'), ('study', '09:10', '10:10'),
        ])

    def test_hours_split_across_subjects_and_lunch_inserted(self):
        plan = build_study_plan(['Math', 'Physics'], 4.5, study_minutes=60, break_minutes=10)
        studied = {}
        for block in plan:
            if block['type'] == 'study':
                studied[block['subject']] = studied.get(block['subject'], 0) + block['duration_minutes']
        self.assertEqual(studied, {'Math': 135, 'Physics': 135})
        lunch = [b for b in plan if b['type'] == 'lunch']
        self.assertEqual((lunch[0]['start_time'], lunch[0]['end_time']), ('12:00', '13:00'))

    def test_too_many_hours_rejected(self):
        with self.assertRaises(ScheduleError):
            build_study_plan(['Math'], 15, study_minutes=50, break_minutes=10)

    def test_statistics(self):
        stats = study_statistics([('Math', 90), ('Math', 100), ('Physics', 70)], [('Math', 2), ('History', 1), ('Math', 3)])
        self.assertEqual(stats['highest_grade'], {'subject': 'Math', 'grade': 95})
        self.assertEqual(stats['lowest_grade'], {'subject': 'Physics', 'grade': 70})
        self.assertEqual(stats['most_studied_subject'], {'subject': 'Math', 'study_hours': 5})
        self.assertEqual(stats['least_studied_subject'], {'subject': 'History', 'study_hours': 1})

    def test_statistics_empty(self):
        self.assertIsNone(study_statistics([], [])['highest_grade'])


class GeneratedEndpointTests(AuthenticatedTestCase):
    def test_generate_schedule(self):
        schedule = self.client.post('/api/study-schedule/', {'study_date': '2026-11-01', 'study_hours': 2, 'subjects': 'Math'}).data
        timer = self.client.post('/api/study-break/', {'study_duration': 60, 'break_duration': 10}).data
        response = self.client.get(f'/api/generate-study-schedule/{schedule["id"]}/{timer["id"]}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['schedule']), 3)
        self.assertEqual(self.client.get(f'/api/generate-study-schedule/999/{timer["id"]}/').status_code, 404)

    def test_statistics_only_count_completed_sessions(self):
        self.client.post('/api/study-progress/', {'study_session_date': '2026-11-01', 'subject': 'Math', 'completed': True, 'study_hours': 2})
        self.client.post('/api/study-progress/', {'study_session_date': '2026-11-01', 'subject': 'Art', 'completed': False, 'study_hours': 9})
        data = self.client.get('/api/generate-study-statistics/').data
        self.assertEqual(data['most_studied_subject'], {'subject': 'Math', 'study_hours': 2})


@patch_requests()
class PublicApiTests(AuthenticatedTestCase):
    def test_motivation(self, requests):
        requests.get.return_value = fake_response(json=[{'q': 'Keep going.', 'a': 'Someone'}])
        self.assertEqual(self.client.get('/api/motivation/').data, {'quote': 'Keep going.', 'author': 'Someone'})

    def test_motivation_upstream_down(self, requests):
        requests.get.side_effect = real_requests.Timeout('timeout')
        self.assertEqual(self.client.get('/api/motivation/').status_code, 502)

    def test_trivia_decodes_html(self, requests):
        requests.get.return_value = fake_response(json={'response_code': 0, 'results': [{
            'question': 'What&#039;s the capital of &quot;France&quot;?', 'correct_answer': 'Paris',
            'incorrect_answers': ['Rome'], 'difficulty': 'easy'}]})
        response = self.client.get('/api/resources/quiz/?subject=Geography')
        self.assertEqual(response.data['questions'][0]['question'], 'What\'s the capital of "France"?')
        self.assertEqual(requests.get.call_args.kwargs['params']['category'], 22)

    def test_trivia_unknown_subject(self, requests):
        self.assertEqual(self.client.get('/api/resources/quiz/?subject=astrology').status_code, 400)
        requests.get.assert_not_called()

    @override_settings(CORE_API_KEY='')
    def test_core_without_key(self, requests):
        self.assertEqual(self.client.get('/api/study-resources-recommendations/articles/?subject=ai').status_code, 503)

    @override_settings(CORE_API_KEY='core-key')
    def test_core_search(self, requests):
        requests.get.return_value = fake_response(json={'results': [
            {'id': 1, 'title': 'Neural nets', 'downloadUrl': 'https://core.ac.uk/download/1.pdf', 'documentType': 'research'}]})
        response = self.client.get('/api/study-resources-recommendations/articles/?subject=ai')
        self.assertEqual(response.data, [{'title': 'Neural nets', 'url': 'https://core.ac.uk/download/1.pdf', 'type': 'research'}])
        self.assertEqual(requests.get.call_args.kwargs['headers'], {'Authorization': 'Bearer core-key'})


@override_settings(GOOGLE_CLIENT_ID='client-id', GOOGLE_CLIENT_SECRET='client-secret')
@patch_requests()
class GoogleTests(AuthenticatedTestCase):
    TOKENS = {'access_token': 'access', 'refresh_token': 'refresh', 'expires_in': 3600,
              'scope': 'https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/calendar.events'}

    def connect(self, expires_in=3600):
        GoogleCredential.objects.create(user=self.user, access_token='access', refresh_token='refresh',
                                        expires_at=timezone.now() + timedelta(seconds=expires_in),
                                        scopes=self.TOKENS['scope'])

    def test_full_oauth_flow(self, requests):
        url = self.client.get('/api/oauth/redirect/').data['authorization_url']
        state = parse_qs(urlparse(url).query)['state'][0]

        requests.post.return_value = fake_response(json=self.TOKENS)
        self.client.credentials()  # the browser hitting the callback has no JWT
        response = self.client.get(f'/api/oauth/callback/?code=abc&state={state}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(GoogleCredential.objects.get(user=self.user).refresh_token, 'refresh')

    def test_callback_rejects_forged_state(self, requests):
        self.client.credentials()
        self.assertEqual(self.client.get('/api/oauth/callback/?code=abc&state=forged').status_code, 400)

    def test_send_notes_requires_google_login(self, requests):
        note = Note.objects.create(user=self.user, subject='Bio', note_content='Mitosis')
        response = self.client.post('/api/send-study-notes/', {'to_email': 'a@example.com', 'note_id': note.id})
        self.assertEqual(response.status_code, 401)

    def test_send_notes(self, requests):
        self.connect()
        note = Note.objects.create(user=self.user, subject='Bio', note_content='Mitosis')
        requests.post.return_value = fake_response(json={'id': 'msg'})
        response = self.client.post('/api/send-study-notes/', {'to_email': 'a@example.com', 'note_id': note.id})
        self.assertEqual(response.status_code, 200)
        self.assertIn('raw', requests.post.call_args.kwargs['json'])

    def test_cannot_send_someone_elses_note(self, requests):
        self.connect()
        other = User.objects.create_user('mallory', password=PASSWORD)
        note = Note.objects.create(user=other, subject='Bio', note_content='private')
        response = self.client.post('/api/send-study-notes/', {'to_email': 'a@example.com', 'note_id': note.id})
        self.assertEqual(response.status_code, 404)

    def test_expired_token_is_refreshed(self, requests):
        self.connect(expires_in=-10)
        requests.post.side_effect = [fake_response(json={'access_token': 'fresh', 'expires_in': 3600}),
                                     fake_response(json={'htmlLink': 'https://calendar.google.com/event'})]
        response = self.client.post('/api/add-exam-to-calendar/', {'exam_date': '2026-12-15', 'exam_time': '09:00', 'subject': 'Math'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(requests.post.call_args.kwargs['headers'], {'Authorization': 'Bearer fresh'})
        event = requests.post.call_args.kwargs['json']
        self.assertEqual(event['start']['dateTime'], '2026-12-15T09:00:00')
        self.assertEqual(event['end']['dateTime'], '2026-12-15T11:00:00')

    def test_invalid_exam_time(self, requests):
        response = self.client.post('/api/add-exam-to-calendar/', {'exam_date': '2026-12-15', 'exam_time': '9am', 'subject': 'Math'})
        self.assertEqual(response.status_code, 400)
