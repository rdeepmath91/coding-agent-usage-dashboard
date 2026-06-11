from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / 'README.md'
PYPROJECT = ROOT / 'pyproject.toml'
UV_LOCK = ROOT / 'uv.lock'
AGENTS = ROOT / 'AGENTS.md'
GITIGNORE = ROOT / '.gitignore'
SCREENSHOT = ROOT / 'docs' / 'dashboard-screenshot.png'


class ReadmeTests(unittest.TestCase):
    def test_readme_documents_uv_sync_run_and_snapshot_steps(self):
        content = README.read_text()
        self.assertIn('## Screenshot', content)
        self.assertIn('docs/dashboard-screenshot.png', content)
        self.assertIn('width="800"', content)
        self.assertIn('Simulated dataset via `?simulate=1`', content)
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

    def test_readme_screenshot_asset_exists(self):
        self.assertTrue(SCREENSHOT.exists(), 'README screenshot should be committed')
        self.assertGreater(SCREENSHOT.stat().st_size, 100_000, 'README screenshot should be a real dashboard capture')

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
        self.assertIn('Hermes via `~/.hermes/state.db`', content)
        self.assertIn('Overview `Total Tokens` means full token volume', content)
        self.assertIn('Session/model-history totals may still use `Session Tokens` semantics', content)
        self.assertNotIn('Total tokens means `input + output assistant-message tokens`', content)

    def test_agent_guidance_requires_worktree_workflow(self):
        content = AGENTS.read_text()

        self.assertIn('Work in a worktree, not in the `main` checkout.', content)
        self.assertIn('git worktree add ../worktrees/<branch-slug> -b <branch> origin/main', content)
        self.assertIn('The on-disk path does not need to be `../worktrees/`, but it must not be inside the repo', content)
        self.assertIn('When a worktree lives inside the repo, never stage or commit its directory.', content)
        self.assertIn('The script refuses to run from `main` outside `REVIEW_MODE=docs`', content)
        self.assertIn('Keep the `main` checkout clean.', content)
        self.assertIn('`git worktree list`', content)
        self.assertIn('`git worktree remove <path>`', content)
        self.assertNotIn('Do not push straight to `main`.\n- Make the smallest change that fully solves the problem.', content)

    def test_gitignore_excludes_worktree_directory(self):
        self.assertTrue(GITIGNORE.exists(), '.gitignore should be committed')
        content = GITIGNORE.read_text()
        self.assertIn('.worktrees/', content)


if __name__ == '__main__':
    unittest.main()
