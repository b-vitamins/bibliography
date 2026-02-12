.PHONY: doctor lint scan report daily release full-audit hooks export-tracking validate-skills

doctor:
	python3 scripts/bibops.py doctor

scan:
	python3 scripts/bibops.py scan

lint:
	python3 scripts/bibops.py lint --fail-on-error

report:
	python3 scripts/bibops.py report

daily:
	python3 scripts/bibops.py run-profile --profile ops/profiles/daily.toml

release:
	python3 scripts/bibops.py run-profile --profile ops/profiles/release.toml

full-audit:
	python3 scripts/bibops.py --config ops/bibops-full.toml run-profile --profile ops/profiles/full-audit.toml

hooks:
	python3 scripts/bibops.py install-hooks

export-tracking:
	python3 scripts/bibops.py export-tracking

validate-skills:
	python3 scripts/validate-skills.py
