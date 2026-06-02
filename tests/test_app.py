import json
import sqlite3
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import app as dashboard_app
from dashboard import config as dashboard_config
from dashboard import pricing as dashboard_pricing
from dashboard.daily import build_daily_from_model_records


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
        cls.original_db_path = dashboard_config.DB_PATH
        cls.original_codex_state_path = dashboard_config.CODEX_STATE_PATH
        cls.original_codex_sessions_dir = dashboard_config.CODEX_SESSIONS_DIR
        cls.original_codex_source_path = dashboard_config.CODEX_SOURCE_PATH
        cls.original_hermes_state_path = dashboard_config.HERMES_STATE_PATH
        cls.codex_state_path = Path(cls.tmpdir.name) / "missing-codex-state.sqlite"
        cls.hermes_state_path = Path(cls.tmpdir.name) / "missing-hermes-state.db"
        cls.codex_sessions_dir = Path(cls.tmpdir.name) / "codex-sessions"
        cls._build_test_db(cls.db_path)
        dashboard_config.DB_PATH = str(cls.db_path)
        dashboard_config.CODEX_STATE_PATH = str(cls.codex_state_path)
        dashboard_config.CODEX_SESSIONS_DIR = str(cls.codex_sessions_dir)
        dashboard_config.CODEX_SOURCE_PATH = str(cls.codex_state_path)
        dashboard_config.HERMES_STATE_PATH = str(cls.hermes_state_path)

    @classmethod
    def tearDownClass(cls):
        dashboard_config.DB_PATH = cls.original_db_path
        dashboard_config.CODEX_STATE_PATH = cls.original_codex_state_path
        dashboard_config.CODEX_SESSIONS_DIR = cls.original_codex_sessions_dir
        dashboard_config.CODEX_SOURCE_PATH = cls.original_codex_source_path
        dashboard_config.HERMES_STATE_PATH = cls.original_hermes_state_path
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
        dashboard_config.CODEX_STATE_PATH = str(self.codex_state_path)
        dashboard_config.CODEX_SESSIONS_DIR = str(self.codex_sessions_dir)
        dashboard_config.CODEX_SOURCE_PATH = str(self.codex_state_path)
        dashboard_config.HERMES_STATE_PATH = str(self.hermes_state_path)
        self.client = dashboard_app.app.test_client()

    def test_overview_exposes_tool_source_metadata(self):
        response = self.client.get('/api/overview?days=30')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(
            payload['token_total_definition'],
            'total token volume = input tokens + output tokens; includes cache read/write',
        )
        self.assertEqual(payload['input_token_definition'], 'input tokens = non-cache input + cache read + cache write')
        self.assertEqual(payload['session_token_definition'], 'session tokens = non-cache input + output assistant-message tokens')
        self.assertEqual(payload['non_cache_input'], 2100)
        self.assertEqual(payload['total_output'], 5000)
        self.assertEqual(payload['cache_read'], 375)
        self.assertEqual(payload['cache_write'], 165)
        self.assertEqual(payload['session_tokens'], 7100)
        self.assertEqual(payload['total_input'], 2640)
        self.assertEqual(payload['total_tokens'], 7640)
        self.assertEqual(payload['active_tool'], 'opencode')
        self.assertEqual(payload['active_tool_label'], 'OpenCode')
        self.assertEqual(payload['source_path'], display_like_app(self.db_path))

        sources = {item['id']: item for item in payload['tool_sources']}
        self.assertEqual(sources['opencode']['status'], 'active')
        self.assertEqual(sources['opencode']['status_label'], 'Active source')
        self.assertEqual(sources['opencode']['color'], '#3B82F6')
        self.assertEqual(sources['opencode']['source_path'], display_like_app(self.db_path))
        self.assertEqual(sources['opencode']['repo_url'], 'https://github.com/anomalyco/opencode/')
        self.assertEqual(sources['codex']['status'], 'placeholder')
        self.assertEqual(sources['codex']['status_label'], 'Planned adapter')
        self.assertEqual(sources['codex']['color'], '#BA68C8')
        self.assertEqual(sources['codex']['source_path'], 'TBD')
        self.assertEqual(sources['codex']['repo_url'], 'https://github.com/openai/codex/')
        self.assertIsNone(sources['codex']['issue'])
        self.assertEqual(sources['hermes']['status'], 'placeholder')
        self.assertEqual(sources['hermes']['status_label'], 'Planned adapter')
        self.assertEqual(sources['hermes']['color'], '#EAB308')
        self.assertEqual(sources['hermes']['source_path'], 'TBD')
        self.assertEqual(sources['hermes']['repo_url'], 'https://github.com/NousResearch/hermes-agent/')
        self.assertIsNone(sources['hermes']['issue'])

    def test_codex_tool_source_filter_returns_empty_result_when_data_missing(self):
        response = self.client.get('/api/daily?days=30&tool_id=codex')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload['selected_tool_id'], 'codex')
        self.assertEqual(payload['selected_tool_label'], 'Codex CLI')
        self.assertEqual(payload['models'], [])
        self.assertEqual(payload['data'], {})
        self.assertEqual(payload['error'], 'Codex CLI data is unavailable.')

    def test_hermes_tool_source_filter_returns_empty_result_when_data_missing(self):
        response = self.client.get('/api/daily?days=30&tool_id=hermes')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload['selected_tool_id'], 'hermes')
        self.assertEqual(payload['selected_tool_label'], 'Hermes')
        self.assertEqual(payload['models'], [])
        self.assertEqual(payload['data'], {})
        self.assertEqual(payload['error'], 'Hermes data is unavailable.')

    def test_unknown_tool_source_filter_returns_http_400(self):
        response = self.client.get('/api/daily?days=30&tool_id=unknown')
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()

        self.assertEqual(payload['models'], [])
        self.assertEqual(payload['data'], {})
        self.assertEqual(payload['error'], 'Unsupported tool_id: unknown.')

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

    def test_models_api_cost_breakdown_supports_top_level_aggregate_summary(self):
        self._write_codex_fixture()
        response = self.client.get('/api/models?days=30')
        self.assertEqual(response.status_code, 200)
        models = response.get_json()

        priced = [
            item
            for item in models
            if item['estimated_cost'] is not None and item.get('cost_breakdown')
        ]
        self.assertTrue(priced)

        estimated_total = sum(item['estimated_cost'] for item in priced)
        breakdown_total = sum(sum(item['cost_breakdown'].values()) for item in priced)
        self.assertAlmostEqual(estimated_total, breakdown_total)

        component_totals = {
            'input': sum(item['cost_breakdown']['input'] for item in priced),
            'output': sum(item['cost_breakdown']['output'] for item in priced),
            'cache_read': sum(item['cost_breakdown']['cache_read'] for item in priced),
            'cache_write': sum(item['cost_breakdown']['cache_write'] for item in priced),
        }
        self.assertGreater(component_totals['input'], 0)
        self.assertGreater(component_totals['output'], 0)
        self.assertGreaterEqual(component_totals['cache_read'], 0)
        self.assertGreaterEqual(component_totals['cache_write'], 0)

    def test_usage_history_applies_offset_after_merging_sources(self):
        response = self.client.get('/api/usage-history?limit=1&offset=1')
        self.assertEqual(response.status_code, 200)
        history = response.get_json()

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['id'], 'sess-1')

    def test_daily_other_zero_bucket_preserves_cache_fields(self):
        payload = build_daily_from_model_records([
            {
                'date': '2026-05-29',
                'chart_model_id': 'provider/top-model',
                'label': 'top-model',
                'model_id': 'top-model',
                'provider': 'provider',
                'sessions': 1,
                'messages': 1,
                'tokens_input': 1000,
                'tokens_output': 500,
                'tokens_total': 1500,
                'cache_read': 100,
                'cache_write': 25,
            },
            {
                'date': '2026-05-30',
                'chart_model_id': 'provider/other-model',
                'label': 'other-model',
                'model_id': 'other-model',
                'provider': 'provider',
                'sessions': 1,
                'messages': 1,
                'tokens_input': 100,
                'tokens_output': 50,
                'tokens_total': 150,
                'cache_read': 10,
                'cache_write': 5,
            },
        ], top_n=1, selected_model_id=None, selected_tool_id=None)
        other = payload['data']['2026-05-29']['other']

        self.assertEqual(other['tokens_total'], 0)
        self.assertEqual(other['cache_read'], 0)
        self.assertEqual(other['cache_write'], 0)

    def test_daily_ordering_uses_effective_tokens(self):
        payload = build_daily_from_model_records([
            {
                'date': '2026-05-30',
                'chart_model_id': 'provider/high-cache',
                'label': 'high-cache',
                'model_id': 'high-cache',
                'provider': 'provider',
                'sessions': 1,
                'messages': 1,
                'tokens_input': 900,
                'tokens_output': 100,
                'tokens_total': 1000,
                'cache_read': 7_000,
                'cache_write': 25,
            },
            {
                'date': '2026-05-30',
                'chart_model_id': 'provider/high-total',
                'label': 'high-total',
                'model_id': 'high-total',
                'provider': 'provider',
                'sessions': 1,
                'messages': 1,
                'tokens_input': 6_000,
                'tokens_output': 700,
                'tokens_total': 6_700,
                'cache_read': 10,
                'cache_write': 5,
            },
        ], top_n=1, selected_model_id=None, selected_tool_id=None)

        self.assertEqual(payload['models'][0]['id'], 'provider/high-cache')


    def _write_codex_fixture(
        self,
        *,
        created_ms: int | None = None,
        updated_ms: int | None = None,
        thread_id: str = "codex-1",
    ) -> None:
        state = Path(self.tmpdir.name) / "codex-state.sqlite"
        if state.exists():
            state.unlink()
        rollout = Path(self.tmpdir.name) / f"{thread_id}-rollout.jsonl"
        created_ms = created_ms if created_ms is not None else int(time.time() * 1000) - 3600000
        updated_ms = updated_ms if updated_ms is not None else created_ms + 120000
        rollout.write_text(
            '\n'.join([
                json.dumps({"timestamp": "2026-05-30T00:00:00Z", "type": "session_meta", "payload": {"id": thread_id}}),
                json.dumps({"timestamp": "2026-05-30T00:01:00Z", "type": "event_msg", "payload": {"type": "task_complete", "info": {"total_token_usage": {"input_tokens": 1000, "cached_input_tokens": 250, "output_tokens": 125, "reasoning_output_tokens": 25, "total_tokens": 1125}}}}),
                json.dumps({"timestamp": "2026-05-30T00:02:00Z", "type": "event_msg", "payload": {"type": "task_complete", "info": {"total_token_usage": {"input_tokens": 1500, "cached_input_tokens": 400, "output_tokens": 225, "reasoning_output_tokens": 40, "total_tokens": 1725}}}}),
            ]) + '\n'
        )
        conn = sqlite3.connect(state)
        conn.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                rollout_path TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                created_at_ms INTEGER,
                updated_at_ms INTEGER,
                source TEXT NOT NULL,
                model_provider TEXT NOT NULL,
                cwd TEXT NOT NULL,
                title TEXT NOT NULL,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                preview TEXT NOT NULL DEFAULT '',
                model TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO threads (
                id, rollout_path, created_at, updated_at, created_at_ms, updated_at_ms,
                source, model_provider, cwd, title, tokens_used, preview, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id, str(rollout), created_ms // 1000, updated_ms // 1000, created_ms, updated_ms,
                "cli", "openai", "/tmp/codex-project", "Codex adapter spike", 1725, "Codex adapter spike", "gpt-5.5",
            ),
        )
        conn.commit()
        conn.close()
        dashboard_config.CODEX_STATE_PATH = str(state)
        dashboard_config.CODEX_SOURCE_PATH = str(state)

    def test_codex_records_flow_into_sources_models_daily_and_history(self):
        self._write_codex_fixture()

        overview = self.client.get('/api/overview?days=30').get_json()
        sources = {item['id']: item for item in overview['tool_sources']}
        self.assertEqual(sources['codex']['status'], 'active')
        self.assertEqual(sources['codex']['status_label'], 'Active source')
        self.assertEqual(sources['codex']['source_type'], 'SQLite state + JSONL rollouts')
        self.assertEqual(sources['codex']['sessions'], 1)
        self.assertEqual(sources['codex']['tokens_input'], 1500)
        self.assertEqual(sources['codex']['non_cache_input'], 1100)
        self.assertEqual(sources['codex']['tokens_output'], 225)
        self.assertEqual(sources['codex']['session_tokens'], 1325)
        self.assertEqual(sources['codex']['tokens_total'], 1725)
        self.assertEqual(sources['codex']['cache_read'], 400)
        self.assertIsNone(sources['codex']['cache_write'])

        models = self.client.get('/api/models?days=30').get_json()
        codex_model = next(item for item in models if item['tool_id'] == 'codex')
        self.assertEqual(codex_model['chart_model_id'], 'openai/gpt-5.5')
        self.assertEqual(codex_model['tokens_input'], 1100)
        self.assertEqual(codex_model['tokens_total'], 1325)
        self.assertEqual(codex_model['tokens_effective_total'], 1725)
        self.assertEqual(codex_model['pricing_model_id'], 'openai/gpt-5.5')
        self.assertEqual(codex_model['pricing_status'], 'priced')
        self.assertIsNotNone(codex_model['estimated_cost'])
        self.assertFalse(codex_model['cache_write_available'])

        daily = self.client.get('/api/daily?days=30&tool_id=codex').get_json()
        self.assertEqual(daily['selected_tool_id'], 'codex')
        self.assertEqual(daily['models'][0]['id'], 'openai/gpt-5.5')
        first_day = daily['dates'][0]
        self.assertEqual(daily['data'][first_day]['openai/gpt-5.5']['tokens_total'], 1325)
        self.assertEqual(daily['data'][first_day]['openai/gpt-5.5']['tokens_effective_total'], 1725)

        history = self.client.get('/api/usage-history?limit=20').get_json()
        codex_history = next(item for item in history if item['tool_id'] == 'codex')
        self.assertEqual(codex_history['tokens_input'], 1100)
        self.assertIsNone(codex_history['cache_write'])

    def test_codex_records_use_updated_timestamp_for_window_and_display_date(self):
        now_ms = int(time.time() * 1000)
        created_ms = now_ms - 40 * 86400000
        updated_ms = now_ms - 3600000
        self._write_codex_fixture(created_ms=created_ms, updated_ms=updated_ms, thread_id="codex-long-lived")

        records = dashboard_app.codex_records(days=30)
        self.assertEqual(len(records), 1)
        record = records[0]
        expected_updated_date = time.strftime('%Y-%m-%d', time.localtime(updated_ms / 1000))
        old_created_date = time.strftime('%Y-%m-%d', time.localtime(created_ms / 1000))

        self.assertEqual(record['id'], 'codex-long-lived')
        self.assertEqual(record['timestamp'], updated_ms)
        self.assertEqual(record['date'], expected_updated_date)
        self.assertTrue(record['created'].startswith(expected_updated_date))
        self.assertNotEqual(record['date'], old_created_date)

    def _write_hermes_fixture(self, *, started_at: float | None = None, session_id: str = 'hermes-1') -> None:
        state = Path(self.tmpdir.name) / 'hermes-state.db'
        if state.exists():
            state.unlink()
        started_at = started_at if started_at is not None else time.time() - 3600
        conn = sqlite3.connect(state)
        conn.execute(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                user_id TEXT,
                model TEXT,
                model_config TEXT,
                system_prompt TEXT,
                parent_session_id TEXT,
                started_at REAL NOT NULL,
                ended_at REAL,
                end_reason TEXT,
                message_count INTEGER DEFAULT 0,
                tool_call_count INTEGER DEFAULT 0,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_write_tokens INTEGER DEFAULT 0,
                reasoning_tokens INTEGER DEFAULT 0,
                billing_provider TEXT,
                billing_base_url TEXT,
                billing_mode TEXT,
                estimated_cost_usd REAL,
                actual_cost_usd REAL,
                cost_status TEXT,
                cost_source TEXT,
                pricing_version TEXT,
                title TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO sessions (
                id, source, model, started_at, ended_at, message_count,
                tool_call_count, input_tokens, output_tokens, cache_read_tokens,
                cache_write_tokens, billing_provider, estimated_cost_usd,
                cost_status, cost_source, title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, 'cli', 'gpt-5.5', started_at, started_at + 120,
                7, 3, 2000, 500, 8000, 125, 'openai-codex', 0.42,
                'estimated', 'session accounting', 'Hermes adapter implementation',
            ),
        )
        conn.commit()
        conn.close()
        dashboard_config.HERMES_STATE_PATH = str(state)

    def test_hermes_records_flow_into_sources_models_daily_and_history(self):
        self._write_hermes_fixture()

        overview = self.client.get('/api/overview?days=30').get_json()
        self.assertEqual(overview['active_tool_label'], 'OpenCode + Hermes')
        sources = {item['id']: item for item in overview['tool_sources']}
        self.assertEqual(sources['hermes']['status'], 'active')
        self.assertEqual(sources['hermes']['status_label'], 'Active source')
        self.assertEqual(sources['hermes']['source_type'], 'Hermes session SQLite database')
        self.assertEqual(sources['hermes']['sessions'], 1)
        self.assertEqual(sources['hermes']['tokens_input'], 10125)
        self.assertEqual(sources['hermes']['non_cache_input'], 2000)
        self.assertEqual(sources['hermes']['tokens_output'], 500)
        self.assertEqual(sources['hermes']['session_tokens'], 2500)
        self.assertEqual(sources['hermes']['tokens_total'], 10625)
        self.assertEqual(sources['hermes']['cache_read'], 8000)
        self.assertEqual(sources['hermes']['cache_write'], 125)

        models = self.client.get('/api/models?days=30').get_json()
        hermes_model = next(item for item in models if item['tool_id'] == 'hermes')
        self.assertEqual(hermes_model['chart_model_id'], 'openai-codex/gpt-5.5')
        self.assertEqual(hermes_model['tokens_input'], 2000)
        self.assertEqual(hermes_model['tokens_total'], 2500)
        self.assertEqual(hermes_model['tokens_effective_total'], 10625)
        self.assertEqual(hermes_model['pricing_model_id'], 'openai-codex/gpt-5.5')
        self.assertEqual(hermes_model['pricing_status'], 'priced')
        self.assertEqual(hermes_model['pricing_source'], 'Hermes session accounting')
        self.assertEqual(hermes_model['estimated_cost'], 0.42)
        self.assertEqual(hermes_model['cost_breakdown'], None)
        self.assertEqual(hermes_model['label'], 'gpt-5.5 (openai-codex)')
        self.assertTrue(hermes_model['cache_write_available'])

        daily = self.client.get('/api/daily?days=30&tool_id=hermes').get_json()
        self.assertEqual(daily['selected_tool_id'], 'hermes')
        self.assertEqual(daily['models'][0]['id'], 'openai-codex/gpt-5.5')
        first_day = daily['dates'][0]
        self.assertEqual(daily['data'][first_day]['openai-codex/gpt-5.5']['tokens_total'], 2500)
        self.assertEqual(daily['data'][first_day]['openai-codex/gpt-5.5']['tokens_effective_total'], 10625)
        self.assertEqual(daily['data'][first_day]['openai-codex/gpt-5.5']['cache_write'], 125)

        all_daily = self.client.get('/api/daily?days=30').get_json()
        self.assertEqual(all_daily['data'][first_day]['openai-codex/gpt-5.5']['cache_write'], 125)

        history = self.client.get('/api/usage-history?limit=20').get_json()
        hermes_history = next(item for item in history if item['tool_id'] == 'hermes')
        self.assertEqual(hermes_history['tokens_input'], 2000)
        self.assertEqual(hermes_history['cache_write'], 125)
        self.assertIn('Hermes session totals', hermes_history['metrics_note'])

    def test_hermes_model_cost_is_partial_when_any_grouped_session_lacks_accounting(self):
        started_at = time.time() - 3600
        self._write_hermes_fixture(started_at=started_at, session_id='hermes-priced')
        conn = sqlite3.connect(dashboard_config.HERMES_STATE_PATH)
        conn.execute(
            """
            INSERT INTO sessions (
                id, source, model, started_at, ended_at, message_count,
                tool_call_count, input_tokens, output_tokens, cache_read_tokens,
                cache_write_tokens, billing_provider, estimated_cost_usd,
                actual_cost_usd, cost_status, cost_source, title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                'hermes-unpriced', 'cli', 'gpt-5.5', started_at + 60, started_at + 180,
                4, 1, 3000, 700, 9000, 0, 'openai-codex', None, None,
                None, None, 'Hermes session without accounting',
            ),
        )
        conn.commit()
        conn.close()

        models = self.client.get('/api/models?days=30').get_json()
        hermes_model = next(item for item in models if item['tool_id'] == 'hermes')

        self.assertEqual(hermes_model['sessions'], 2)
        self.assertEqual(hermes_model['tokens_total'], 6200)
        self.assertEqual(hermes_model['pricing_status'], 'partial')
        self.assertIsNone(hermes_model['estimated_cost'])
        self.assertIn('OpenRouter /api/v1/models', hermes_model['pricing_source'])
        self.assertIn('Hermes session accounting covers 1/2 sessions', hermes_model['pricing_source'])
        self.assertEqual(hermes_model['pricing_model_id'], 'openai/gpt-5.5')
        self.assertEqual(hermes_model['partial_cost_usd'], 0.0695)
        self.assertEqual(hermes_model['session_accounting_partial_cost_usd'], 0.42)
        self.assertEqual(hermes_model['cost_basis'], 'api_equivalent_estimate_with_partial_session_accounting')
        self.assertAlmostEqual(hermes_model['cost_breakdown']['input'], 0.025)
        self.assertAlmostEqual(hermes_model['cost_breakdown']['output'], 0.036)
        self.assertAlmostEqual(hermes_model['cost_breakdown']['cache_read'], 0.0085)
        self.assertEqual(hermes_model['accounted_sessions'], 1)
        self.assertEqual(hermes_model['unaccounted_sessions'], 1)
        self.assertEqual(hermes_model['accounted_tokens_total'], 2500)
        self.assertEqual(hermes_model['unaccounted_tokens_total'], 3700)

    def test_hermes_unknown_none_zero_cost_uses_pricing_fallback(self):
        self._write_hermes_fixture()
        conn = sqlite3.connect(dashboard_config.HERMES_STATE_PATH)
        conn.execute(
            """
            UPDATE sessions
            SET estimated_cost_usd = 0.0,
                actual_cost_usd = NULL,
                cost_status = 'unknown',
                cost_source = 'none',
                billing_provider = 'openai-codex'
            WHERE id = 'hermes-1'
            """
        )
        conn.commit()
        conn.close()

        models = self.client.get('/api/models?days=30').get_json()
        hermes_model = next(item for item in models if item['tool_id'] == 'hermes')

        self.assertEqual(hermes_model['pricing_status'], 'partial')
        self.assertIn('missing prices for input_cache_write', hermes_model['pricing_source'])
        self.assertEqual(hermes_model['pricing_model_id'], 'openai/gpt-5.5')
        self.assertEqual(hermes_model['accounted_sessions'], 0)
        self.assertEqual(hermes_model['unaccounted_sessions'], 1)
        self.assertIsNone(hermes_model['estimated_cost'])
        self.assertGreater(hermes_model['partial_cost_usd'], 0)

    def test_hermes_records_use_started_timestamp_for_window_and_display_date(self):
        started_at = time.time() - 40 * 86400
        self._write_hermes_fixture(started_at=started_at, session_id='hermes-old')

        records = dashboard_app.hermes_records(days=30)
        self.assertEqual(records, [])


    def test_settings_page_describes_current_cost_and_token_rules(self):
        response = self.client.get('/settings')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Overview Total Tokens include session tokens plus cache read/write', html)
        self.assertIn('table/session totals use session-token semantics when labeled', html)
        self.assertIn('Codex CLI becomes active when', html)
        self.assertIn('Hermes becomes active when', html)
        self.assertNotIn('OpenCode is the active source today', html)
        self.assertIn('Cost is an API-equivalent estimate from matched provider pricing when available', html)
        self.assertIn('not necessarily actual subscription billing', html)

    def test_overview_page_includes_clickable_metric_tooltips(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('class="meta-info-wrap"', html)
        self.assertIn('class="meta-tooltip"', html)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn('Input Tokens', html)
        self.assertIn('Top cards show full token volume', html)
        self.assertIn('Total token volume = input tokens + output tokens', html)
        self.assertIn('bindMetaInfoInteractions', html)
        self.assertIn('<link rel="icon" href="/favicon.ico" type="image/svg+xml">', html)

    def test_favicon_route_returns_svg_icon(self):
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/svg+xml')
        self.assertIn('<svg', response.get_data(as_text=True))

    def test_dashboard_template_uses_button_based_accessible_controls(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("document.createElement('button')", html)
        self.assertIn("className = 'chart-focus-button'", html)
        self.assertIn('item.className = `legend-item', html)
        self.assertIn("button.textContent = active ? 'Clear focus' : 'Focus chart'", html)
        self.assertIn('role="img" aria-label="Daily effective token volume by model (input + output + cache read + cache write)"', html)
        self.assertIn('role="group" aria-label="Usage date range"', html)
        self.assertIn('API-Equivalent Cost', html)
        self.assertLess(html.index('Total Tokens'), html.index('API-Equivalent Cost'))
        self.assertLess(html.index('API-Equivalent Cost'), html.index('Input Tokens'))
        self.assertLess(html.index('Output Tokens'), html.index('Sessions'))
        self.assertIn('Partial estimate', html)
        self.assertIn('estimate-badge', html)
        self.assertIn('of ${total} models priced', html)
        self.assertIn("keepTogether(fmtTokens(sessionTokens), 'direct')", html)
        self.assertIn('cacheShare(cacheTotal, totalTokens)', html)
        self.assertIn("keepTogether(fmtTokens(cacheRead), 'cache read')", html)
        self.assertIn('Direct/session tokens = non-cache input + output', html)
        self.assertIn('Rows show canonical totals: non-cache input + output. Ranking and chart use effective volume including cache. API-equivalent cost is priced from matched provider rates.', html)
        self.assertIn('Breakdown: input ${fmtCost(costParts.input)}', html)
        self.assertIn('<meta name="theme-color" content="#08090a">', html)
        self.assertIn('color-scheme: dark', html)
        self.assertIn('name="custom-days" type="number"', html)
        self.assertIn('inputmode="numeric" autocomplete="off" placeholder="e.g. 45…"', html)
        self.assertNotIn('transition: all', html)
        self.assertNotIn('Loading...', html)
        self.assertIn('Loading…', html)
        self.assertIn("button.setAttribute('aria-pressed', active ? 'true' : 'false')", html)
        self.assertIn("item.addEventListener('focus', () => setLegendHover(item.dataset.modelId))", html)
        self.assertIn('prefers-reduced-motion: reduce', html)
        self.assertIn('class="table-scroll" role="region" aria-label="Model breakdown table"', html)
        self.assertIn('class="table-scroll" role="region" aria-label="Usage history table"', html)
        self.assertNotIn('role="button" data-chart-model-id', html)
        self.assertIn('if (!r.ok)', html)
        self.assertIn("document.getElementById('chart-note').textContent = chartData.error", html)
        self.assertIn('active sources:', html)
        self.assertIn("document.getElementById('db-path-display').textContent = `${sourceLabel} · ${sourcePath}`", html)
        self.assertNotIn('OpenCode · ~/.local/share/opencode/opencode.db</span>', html)

    def test_dashboard_template_includes_cost_breakdown_tooltip_logic(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn("const breakdown = m.cost_breakdown || {};", html)
        self.assertIn("const breakdownTitle = m.cost_breakdown", html)
        self.assertIn("input ${fmtCost(breakdown.input)}, output ${fmtCost(breakdown.output)}, cache read ${fmtCost(breakdown.cache_read)}, cache write ${fmtCost(breakdown.cache_write)}", html)
        self.assertIn("const sessionAccounting = m.session_accounting_note ? `; ${m.session_accounting_note}` : '';", html)
        self.assertIn("known subtotal ${fmtCost(m.partial_cost_usd)}", html)

    def test_tool_source_render_moves_source_path_into_info_tooltip(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('className = \'tool-source-summary\'', html)
        self.assertIn('source details', html)
        self.assertIn('tooltip.textContent = `${sourceType} · Source: ${sourcePath}`', html)
        self.assertNotIn('meta.textContent = `${sourceType} · Source: ${sourcePath}`', html)
        self.assertNotIn('card.addEventListener(\'click\'', html)

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

    def test_estimate_cost_marks_paid_cache_write_without_price_partial(self):
        original_cache = dict(dashboard_pricing.PRICING_CACHE)
        try:
            dashboard_pricing.PRICING_CACHE.update({
                "fetched_at": time.time(),
                "prices": {
                    "openai/gpt-5.5": {
                        "prompt": "0.000005",
                        "completion": "0.00003",
                        "input_cache_read": "0.0000005",
                        "input_cache_write": "0",
                    }
                },
            })

            result = dashboard_pricing.estimate_cost(
                "openai-codex",
                "gpt-5.5",
                tokens_input=1000,
                tokens_output=100,
                cache_read=50,
                cache_write=25,
            )
        finally:
            dashboard_pricing.PRICING_CACHE.clear()
            dashboard_pricing.PRICING_CACHE.update(original_cache)

        self.assertEqual(result["pricing_status"], "partial")
        self.assertIsNone(result["estimated_cost"])
        self.assertGreater(result["partial_cost_usd"], 0)
        self.assertIn("input_cache_write", result["missing_price_buckets"])


class ReviewScriptGuardTests(unittest.TestCase):
    def test_review_script_blocks_main_branch_in_full_mode(self):
        import os
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / 'scripts' / 'review.sh'
        self.assertTrue(script.exists(), 'scripts/review.sh should exist')

        # Exercise the guard by faking the git binary with a shim that reports
        # the current branch as "main" no matter what. This keeps the test
        # self-contained and avoids recursing into scripts/review.sh from inside
        # the suite it is testing.
        with tempfile.TemporaryDirectory() as fake_bin:
            shim = Path(fake_bin) / 'git'
            shim.write_text('#!/usr/bin/env bash\necho main\nexit 0\n')
            shim.chmod(0o755)
            env = {**os.environ, 'PATH': f"{fake_bin}:{os.environ.get('PATH', '')}", 'REVIEW_MODE': 'full'}

            result = subprocess.run(
                ['bash', str(script)],
                cwd=str(repo_root),
                env=env,
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0, msg=result.stdout)
            self.assertIn('must run from a feature branch, not main', result.stderr + result.stdout)
            self.assertIn('REVIEW_MODE=docs', result.stderr + result.stdout)

    def test_review_script_allows_main_branch_in_docs_mode(self):
        import os
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / 'scripts' / 'review.sh'

        with tempfile.TemporaryDirectory() as fake_bin:
            shim = Path(fake_bin) / 'git'
            shim.write_text('#!/usr/bin/env bash\necho main\nexit 0\n')
            shim.chmod(0o755)
            env = {**os.environ, 'PATH': f"{fake_bin}:{os.environ.get('PATH', '')}", 'REVIEW_MODE': 'docs'}

            result = subprocess.run(
                ['bash', str(script)],
                cwd=str(repo_root),
                env=env,
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            self.assertIn('Docs-only review mode complete', result.stdout)

    def test_review_script_guarding_logic_blocks_main_branch(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / 'scripts' / 'review.sh'
        content = script.read_text()
        self.assertIn('CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)', content)
        self.assertIn('[[ "$CURRENT_BRANCH" == "main" && "$MODE" != "docs" ]]', content)
        self.assertIn('must run from a feature branch, not main', content)
        self.assertIn('git worktree add ../worktrees/<branch-slug> -b <branch> origin/main', content)


if __name__ == '__main__':
    unittest.main()
