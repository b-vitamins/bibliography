.PHONY: doctor lint scan report daily release full-audit orals enrich-arxiv-orals enrich-plan enrich-run hooks export-tracking validate-skills

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

orals:
	python3 scripts/bibops.py --config ops/bibops-orals.toml run-profile --profile ops/profiles/orals.toml

enrich-arxiv-orals:
	python3 scripts/enrich-arxiv.py collections/orals/*/*.bib

enrich-plan:
	@[ -n "$(FILE)" ] || (echo "Usage: make enrich-plan FILE=conferences/iclr/2024.bib" && exit 1)
	python3 scripts/enrich-pipeline.py plan "$(FILE)"

enrich-run:
	@[ -n "$(FILE)" ] || (echo "Usage: make enrich-run FILE=conferences/iclr/2024.bib" && exit 1)
	python3 scripts/enrich-pipeline.py run "$(FILE)"

hooks:
	python3 scripts/bibops.py install-hooks

export-tracking:
	python3 scripts/bibops.py export-tracking

validate-skills:
	python3 scripts/validate-skills.py
