PY := .venv/bin/python

.PHONY: ci test lint holdout guards registry tables buildlog

# Public-release integrity gate: lint_claims + holdout_check2 + read-only grep +
# quarantine grep + secret scan + registry schema validation. (The full pytest suite and the
# decision-log check depend on held-out key material not shipped in this release.)
ci: lint holdout guards registry
	@echo "=== make ci: ALL GREEN ==="

test:
	$(PY) -m pytest -q

lint:
	$(PY) pipeline/lint_claims.py

holdout:
	$(PY) pipeline/holdout_check2.py

guards:
	$(PY) pipeline/check_readonly.py
	$(PY) pipeline/check_quarantine.py
	$(PY) pipeline/check_secrets.py

registry:
	$(PY) pipeline/validate_registry.py

buildlog:
	$(PY) pipeline/check_buildlog.py

tables:
	$(PY) pipeline/make_tables.py
