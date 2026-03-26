# Contributing to Honest Opens

We welcome contributions from the email publishing community. The goal of this project is to create a shared, transparent standard for bot filtering — the more ESPs and publishers that contribute, the better the algorithm gets for everyone.

## How to Contribute

### Report a New Bot Pattern

If you discover a bot behavior that the algorithm does not catch, open an issue with:

1. A description of the pattern (timing, volume, URL count, etc.)
2. The ESP you observed it on
3. Approximate volume (how many sends does it affect?)
4. A sample of the raw event data (anonymized — no subscriber IDs or real URLs)

### Calibrate for a New ESP

If you calibrate thresholds for an ESP not currently documented, submit a PR adding:

1. A section to `docs/ESP_DATA_GUIDE.md` with platform-specific instructions
2. A section to `docs/CALIBRATION.md` with recommended threshold adjustments
3. Optionally, a pre-built config JSON in `configs/` (e.g., `configs/mailchimp.json`)

### Improve the Algorithm

For algorithm changes, please include:

1. A clear explanation of the change and why it improves accuracy
2. Benchmark results showing the impact on FP/FN rates
3. The ESP and data volume you tested on
4. Unit tests covering the new behavior

## Development Setup

```bash
git clone https://github.com/workweek/honest-opens.git
cd honest-opens
pip install -e ".[dev]"
python -m pytest tests/
```

## Code Style

- Python 3.8+ compatible
- Type hints on all public functions
- Docstrings on all public classes and methods
- No external dependencies in the core library (stdlib only)

## Pull Request Process

1. Fork the repo and create a branch from `main`
2. Add tests for any new functionality
3. Run `python -m pytest tests/` and ensure all tests pass
4. Update documentation if you changed behavior
5. Submit the PR with a clear description

## Code of Conduct

Be respectful. This project exists to make the email industry more honest. Bring that same energy to how you interact with other contributors.
