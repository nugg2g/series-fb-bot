import unittest
import json
import web_server

class TestWebServer(unittest.TestCase):
    def setUp(self):
        web_server.app.config['TESTING'] = True
        self.client = web_server.app.test_client()
        web_server.clear_failed_attempts('127.0.0.1')
        self.pin = web_server.ACCESS_PIN
        self.bot_token = web_server.SYNC_SECRET_TOKEN
        self.auth_token = web_server.generate_session_token(self.pin)
        self.auth_headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }

    def test_index_page(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Reels Bot', res.data)
        self.assertIn(b'Manager', res.data)

    def test_auth_login_and_check(self):
        # 1. Invalid PIN
        res = self.client.post('/api/auth/login', json={"pin": "wrong123"})
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data['success'])

        # 2. Correct PIN
        res = self.client.post('/api/auth/login', json={"pin": self.pin})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        token = data.get('token')
        self.assertTrue(token)

        # 3. Check auth status with token
        res = self.client.get('/api/auth/check', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get("authenticated"))

        # 4. Check auth status without token
        res = self.client.get('/api/auth/check')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.get_json().get("authenticated"))

    def test_unauthorized_endpoints(self):
        # /api/state requires auth
        res = self.client.get('/api/state')
        self.assertEqual(res.status_code, 401)

        # /api/action/* requires auth
        res = self.client.post('/api/action/start')
        self.assertEqual(res.status_code, 401)

    def test_api_state(self):
        res = self.client.get('/api/state', headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('status', data)
        self.assertIn('progress_pct', data)
        self.assertIn('page_groups', data)

    def test_api_actions_and_sanitization(self):
        # 1. Start action
        res = self.client.post('/api/action/start', headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        # 2. Switch page with invalid ID
        res = self.client.post('/api/action/switch_page', 
                               json={"page_id": "abc"}, 
                               headers=self.auth_headers)
        self.assertEqual(res.status_code, 400)

        # 3. Switch page with valid ID
        res = self.client.post('/api/action/switch_page', 
                               json={"group_id": "group_shared_3pages", "page_id": "999888777", "page_name": "Test Page 2"}, 
                               headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        # 4. Update settings with clamping
        res = self.client.post('/api/action/update_settings',
                               json={"min_delay": 5, "max_delay": 99999, "title_prefix": "[ເຕັມເລື່ອງ]"},
                               headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

    def test_api_sync_security_and_flow(self):
        sync_payload = {
            "status": "uploading",
            "progress_pct": 45,
            "progress_text": "ອັບໂຫຼດ 45%",
            "page_name": "Test Page 2",
            "page_id": "999888777"
        }

        # 1. Sync without X-Bot-Token -> 403 Forbidden
        res = self.client.post('/api/sync', json=sync_payload)
        self.assertEqual(res.status_code, 403)

        # 2. Sync with wrong token -> 403 Forbidden
        res = self.client.post('/api/sync', json=sync_payload, headers={"X-Bot-Token": "wrong-secret"})
        self.assertEqual(res.status_code, 403)

        # 3. Trigger action first from mobile
        self.client.post('/api/action/stop', headers=self.auth_headers)

        # 4. Sync with correct X-Bot-Token -> 200 OK
        res = self.client.post('/api/sync', json=sync_payload, headers={"X-Bot-Token": self.bot_token})
        self.assertEqual(res.status_code, 200)
        sync_data = res.get_json()
        self.assertTrue(sync_data['success'])
        commands = sync_data.get('commands', [])
        self.assertTrue(any(c['action'] == 'stop' for c in commands))

        # 5. Check state updated
        res = self.client.get('/api/state', headers=self.auth_headers)
        state_data = res.get_json()
        self.assertEqual(state_data['status'], 'uploading')
        self.assertEqual(state_data['progress_pct'], 45)
        self.assertTrue(state_data['bot_connected'])

    def test_brute_force_rate_limiting(self):
        # 5 failed attempts within window triggers 429
        web_server.clear_failed_attempts('127.0.0.1')
        for i in range(5):
            res = self.client.post('/api/auth/login', json={"pin": f"wrong_{i}"})
            self.assertEqual(res.status_code, 401)
        
        # 6th attempt should be blocked with 429 Too Many Requests
        res = self.client.post('/api/auth/login', json={"pin": "wrong_6"})
        self.assertEqual(res.status_code, 429)
        self.assertIn("ບລັອກ IP", res.get_json().get("message", ""))
        
        # Reset after test
        web_server.clear_failed_attempts('127.0.0.1')

if __name__ == '__main__':
    unittest.main()
