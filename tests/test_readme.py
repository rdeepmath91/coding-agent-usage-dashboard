from pathlib import Path
import unittest


README = Path(__file__).resolve().parents[1] / 'README.md'


class ReadmeTests(unittest.TestCase):
    def test_readme_documents_uv_install_run_and_snapshot_steps(self):
        content = README.read_text()
        self.assertIn('## Setup', content)
        self.assertIn('https://docs.astral.sh/uv/', content)
        self.assertIn('curl -LsSf https://astral.sh/uv/install.sh | sh', content)
        self.assertIn('uv venv', content)
        self.assertIn('uv pip install -r requirements.txt', content)
        self.assertIn('uv run python app.py', content)
        self.assertIn('## Snapshots', content)
        self.assertIn('uv run --with playwright python scripts/snapshot_dashboard.py --url http://localhost:8321', content)
        self.assertIn('dashboard-snapshots/', content)
        self.assertIn('http://localhost:8321', content)


if __name__ == '__main__':
    unittest.main()
