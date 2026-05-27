import unittest

from app import app


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_overview_exposes_tool_source_metadata(self):
        response = self.client.get('/api/overview?days=30')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(
            payload['token_total_definition'],
            'input + output assistant-message tokens; cache read/write excluded',
        )
        self.assertEqual(payload['active_tool'], 'opencode')
        self.assertEqual(payload['active_tool_label'], 'OpenCode')

        sources = {item['id']: item for item in payload['tool_sources']}
        self.assertEqual(sources['opencode']['status'], 'active')
        self.assertEqual(sources['opencode']['color'], '#3B82F6')
        self.assertEqual(sources['codex']['status'], 'placeholder')
        self.assertEqual(sources['codex']['color'], '#BA68C8')
        self.assertEqual(sources['hermes']['status'], 'placeholder')
        self.assertEqual(sources['hermes']['color'], '#EAB308')

    def test_models_and_history_include_tool_color(self):
        models_response = self.client.get('/api/models?days=30')
        self.assertEqual(models_response.status_code, 200)
        models = models_response.get_json()
        self.assertTrue(models)
        self.assertEqual(models[0]['tool'], 'OpenCode')
        self.assertEqual(models[0]['tool_id'], 'opencode')
        self.assertEqual(models[0]['tool_color'], '#3B82F6')

        history_response = self.client.get('/api/usage-history?limit=5')
        self.assertEqual(history_response.status_code, 200)
        history = history_response.get_json()
        self.assertTrue(history)
        self.assertEqual(history[0]['tool'], 'OpenCode')
        self.assertEqual(history[0]['tool_id'], 'opencode')
        self.assertEqual(history[0]['tool_color'], '#3B82F6')

    def test_settings_page_describes_current_cost_and_token_rules(self):
        response = self.client.get('/settings')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Total tokens are defined as input + output assistant-message tokens.', html)
        self.assertIn('Cost is estimated from matched OpenRouter pricing when available.', html)

    def test_overview_page_includes_clickable_metric_tooltips(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('class="meta-info-wrap"', html)
        self.assertIn('class="meta-tooltip"', html)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn('bindMetaInfoInteractions', html)

    def test_simulated_mode_returns_synthetic_dashboard_data(self):
        overview = self.client.get('/api/overview?simulate=1&days=31')
        self.assertEqual(overview.status_code, 200)
        payload = overview.get_json()
        self.assertEqual(payload['active_tool_label'], 'OpenCode (simulated)')
        self.assertEqual(payload['source_path'], 'simulated dataset')
        self.assertGreater(payload['total_tokens'], 0)

        models = self.client.get('/api/models?simulate=1&days=31').get_json()
        self.assertTrue(models)
        self.assertEqual(models[0]['source_path'], 'simulated dataset')

        daily = self.client.get('/api/daily?simulate=1&days=31&top_n=4').get_json()
        self.assertEqual(len(daily['dates']), 31)
        self.assertLessEqual(len(daily['models']), 5)

        history = self.client.get('/api/usage-history?simulate=1&limit=5').get_json()
        self.assertEqual(len(history), 5)
        self.assertTrue(all(item['id'].startswith('sim-') for item in history))


if __name__ == '__main__':
    unittest.main()
