.PHONY: doctor lint scan report daily release full-audit orals intake-watch intake-discover intake-plan intake-run enrich-arxiv-orals enrich-plan enrich-run enrich-battle hooks export-tracking validate-skills

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

intake-watch:
	python3 scripts/bibops.py run-profile --profile ops/profiles/intake-watch.toml

intake-discover:
	@[ -n "$(TARGETS)" ] || (echo "Usage: make intake-discover TARGETS='iclr:2025 neurips:2025'" && exit 1)
	python3 scripts/bibops.py intake discover $(TARGETS)

intake-plan:
	@[ -n "$(TARGETS)" ] || (echo "Usage: make intake-plan TARGETS='iclr:2025 neurips:2025'" && exit 1)
	python3 scripts/bibops.py intake plan $(TARGETS)

intake-run:
	@[ -n "$(TARGETS)" ] || (echo "Usage: make intake-run TARGETS='iclr:2025 neurips:2025'" && exit 1)
	python3 scripts/bibops.py intake run $(TARGETS) --write --fail-on-gap

enrich-arxiv-orals:
	python3 scripts/enrich-arxiv.py collections/orals/*/*.bib

enrich-plan:
	@[ -n "$(FILE)" ] || (echo "Usage: make enrich-plan FILE=conferences/iclr/2024.bib" && exit 1)
	python3 scripts/enrich-pipeline.py plan "$(FILE)"

enrich-run:
	@[ -n "$(FILE)" ] || (echo "Usage: make enrich-run FILE=conferences/iclr/2024.bib" && exit 1)
	python3 scripts/enrich-pipeline.py run "$(FILE)"

enrich-battle:
	python3 scripts/enrichment/battle_test.py --mode $(or $(MODE),standard)

hooks:
	python3 scripts/bibops.py install-hooks

export-tracking:
	python3 scripts/bibops.py export-tracking

validate-skills:
	python3 scripts/validate-skills.py
