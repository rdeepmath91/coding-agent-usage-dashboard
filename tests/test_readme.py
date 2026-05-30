from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / 'README.md'
PYPROJECT = ROOT / 'pyproject.toml'
UV_LOCK = ROOT / 'uv.lock'
AGENTS = ROOT / 'AGENTS.md'


class ReadmeTests(unittest.TestCase):
    def test_readme_documents_uv_sync_run_and_snapshot_steps(self):
        content = README.read_text()
        self.assertIn('## Setup', content)
        self.assertIn('https://docs.astral.sh/uv/', content)
        self.assertIn('curl -LsSf https://astral.sh/uv/install.sh | sh', content)
        self.assertIn('uv sync', content)
        self.assertNotIn('uv pip install -r requirements.txt', content)
        self.assertNotIn('uv venv', content)
        self.assertIn('uv run python app.py', content)
        self.assertIn('## Snapshots', content)
        self.assertIn('uv run --with playwright python scripts/snapshot_dashboard.py --url http://localhost:8321', content)
        self.assertIn('dashboard-snapshots/', content)
        self.assertIn('http://localhost:8321', content)

    def test_repo_includes_uv_project_files_for_reproducible_setup(self):
        self.assertTrue(PYPROJECT.exists(), 'pyproject.toml should be committed')
        self.assertTrue(UV_LOCK.exists(), 'uv.lock should be committed')

        pyproject = PYPROJECT.read_text()
        self.assertIn('[project]', pyproject)
        self.assertIn('dependencies = [', pyproject)
        self.assertIn('flask', pyproject)

        lock_text = UV_LOCK.read_text()
        self.assertIn('version = 1', lock_text)
        self.assertIn('name = "coding-agent-usage-dashboard"', lock_text)

    def test_agent_guidance_matches_token_and_source_contract(self):
        content = AGENTS.read_text()

        self.assertIn('Codex CLI via `~/.codex/state_5.sqlite`', content)
        self.assertIn('Total tokens means `non-cache input + output assistant-message tokens`', content)
        self.assertNotIn('Total tokens means `input + output assistant-message tokens`', content)


if __name__ == '__main__':
    unittest.main()
