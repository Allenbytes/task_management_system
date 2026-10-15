from rest_framework.test import APITestCase


class TaskApiTests(APITestCase):
    def register(self, username):
        response = self.client.post('/api/v1/register/', {
            'username': username, 'email': f'{username}@example.com', 'password': 'S3cure-pass!',
        })
        self.assertEqual(response.status_code, 201)
        return response.data['token']

    def test_full_flow(self):
        token = self.register('alice')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')

        created = self.client.post('/api/v1/tasks/', {'title': 'Buy milk', 'description': '2 litres'})
        self.assertEqual(created.status_code, 201)
        task_id = created.data['id']

        self.assertEqual(self.client.get('/api/v1/tasks/').data['count'], 1)
        self.assertEqual(self.client.get('/api/v1/tasks/?status=completed').data['count'], 0)
        self.assertEqual(self.client.get('/api/v1/tasks/?search=milk').data['count'], 1)

        patched = self.client.patch(f'/api/v1/tasks/{task_id}/', {'status': 'completed'})
        self.assertEqual(patched.data['status'], 'completed')

        self.assertEqual(self.client.delete(f'/api/v1/tasks/{task_id}/').status_code, 204)

        self.assertEqual(self.client.post('/api/v1/logout/').status_code, 204)
        self.assertEqual(self.client.get('/api/v1/tasks/').status_code, 401)

    def test_login_returns_token(self):
        self.register('bob')
        response = self.client.post('/api/v1/login/', {'username': 'bob', 'password': 'S3cure-pass!'})
        self.assertIn('token', response.data)

    def test_users_cannot_see_each_others_tasks(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.register("alice")}')
        task_id = self.client.post('/api/v1/tasks/', {'title': 'Private', 'description': 'x'}).data['id']

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.register("mallory")}')
        self.assertEqual(self.client.get(f'/api/v1/tasks/{task_id}/').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/v1/tasks/{task_id}/').status_code, 404)
