import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

import app as dashboard_app


HOME_PREFIX = f"{Path.home()}/"


def display_like_app(path: Path) -> str:
    raw = str(path)
    return raw.replace(HOME_PREFIX, "~/", 1) if raw.startswith(HOME_PREFIX) else raw


def write_message(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    created_ms: int,
    role: str,
    model_id: str | None = None,
    provider_id: str | None = None,
    tokens_input: int = 0,
    tokens_output: int = 0,
    cache_read: int = 0,
    cache_write: int = 0,
) -> None:
    payload = {
        "role": role,
        "tokens": {
            "input": tokens_input,
            "output": tokens_output,
            "cache": {
                "read": cache_read,
                "write": cache_write,
            },
        },
    }
    if model_id is not None:
        payload["modelID"] = model_id
    if provider_id is not None:
        payload["providerID"] = provider_id
    conn.execute(
        "INSERT INTO message (session_id, time_created, data) VALUES (?, ?, ?)",
        (session_id, created_ms, json.dumps(payload)),
    )


class DashboardApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tmpdir.name) / "opencode-test.db"
        cls.original_db_path = dashboard_app.DB_PATH
        cls._build_test_db(cls.db_path)
        dashboard_app.DB_PATH = str(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        dashboard_app.DB_PATH = cls.original_db_path
        cls.tmpdir.cleanup()

    @classmethod
    def _build_test_db(cls, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE session (
                id TEXT PRIMARY KEY,
                title TEXT,
                directory TEXT,
                model TEXT,
                tokens_input INTEGER,
                tokens_output INTEGER,
                summary_files INTEGER,
                summary_additions INTEGER,
                summary_deletions INTEGER,
                time_created INTEGER,
                time_updated INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                time_created INTEGER NOT NULL,
                data TEXT NOT NULL
            )
            """
        )

        now_ms = int(time.time() * 1000)
        session_rows = [
            {
                "id": "sess-1",
                "title": "Daily usage dashboard cleanup",
                "directory": "/tmp/project-one",
                "model": json.dumps({"id": "kimi-k2.6", "providerID": "opencode-go"}),
                "tokens_input": 1200,
                "tokens_output": 3400,
                "summary_files": 2,
                "summary_additions": 24,
                "summary_deletions": 6,
                "time_created": now_ms - 2 * 86400000,
                "time_updated": now_ms - 2 * 86400000 + 120000,
            },
            {
                "id": "sess-2",
                "title": "Legend accessibility pass",
                "directory": "/tmp/project-two",
                "model": json.dumps({"id": "deepseek-v4-flash", "providerID": "opencode-go"}),
                "tokens_input": 900,
                "tokens_output": 1600,
                "summary_files": 1,
                "summary_additions": 12,
                "summary_deletions": 3,
                "time_created": now_ms - 86400000,
                "time_updated": now_ms - 86400000 + 180000,
            },
        ]
        for row in session_rows:
            conn.execute(
                """
                INSERT INTO session (
                    id, title, directory, model, tokens_input, tokens_output,
                    summary_files, summary_additions, summary_deletions,
                    time_created, time_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["title"],
                    row["directory"],
                    row["model"],
                    row["tokens_input"],
                    row["tokens_output"],
                    row["summary_files"],
                    row["summary_additions"],
                    row["summary_deletions"],
                    row["time_created"],
                    row["time_updated"],
                ),
            )

        write_message(
            conn,
            session_id="sess-1",
            created_ms=now_ms - 2 * 86400000,
            role="assistant",
            model_id="kimi-k2.6",
            provider_id="opencode-go",
            tokens_input=1200,
            tokens_output=3400,
            cache_read=300,
            cache_write=125,
        )
        write_message(
            conn,
            session_id="sess-1",
            created_ms=now_ms - 2 * 86400000 + 60000,
            role="user",
        )
        write_message(
            conn,
            session_id="sess-2",
            created_ms=now_ms - 86400000,
            role="assistant",
            model_id="deepseek-v4-flash",
            provider_id="opencode-go",
            tokens_input=900,
            tokens_output=1600,
            cache_read=75,
            cache_write=40,
        )
        conn.commit()
        conn.close()

    def setUp(self):
        self.client = dashboard_app.app.test_client()

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
        self.assertEqual(payload['source_path'], display_like_app(self.db_path))

        sources = {item['id']: item for item in payload['tool_sources']}
        self.assertEqual(sources['opencode']['status'], 'active')
        self.assertEqual(sources['opencode']['color'], '#3B82F6')
        self.assertEqual(sources['opencode']['source_path'], display_like_app(self.db_path))
        self.assertEqual(sources['codex']['status'], 'placeholder')
        self.assertEqual(sources['codex']['color'], '#BA68C8')
        self.assertEqual(sources['codex']['source_path'], 'TBD')
        self.assertIsNone(sources['codex']['issue'])
        self.assertEqual(sources['hermes']['status'], 'placeholder')
        self.assertEqual(sources['hermes']['color'], '#EAB308')
        self.assertEqual(sources['hermes']['source_path'], 'TBD')
        self.assertIsNone(sources['hermes']['issue'])

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

    def test_dashboard_template_uses_button_based_accessible_controls(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("document.createElement('button')", html)
        self.assertIn("className = 'chart-focus-button'", html)
        self.assertIn('item.className = `legend-item', html)
        self.assertIn("button.textContent = active ? 'Clear focus' : 'Focus chart'", html)
        self.assertNotIn('role="button" data-chart-model-id', html)

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
