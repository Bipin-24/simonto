.PHONY: install test validate demo docs serve
install:
	pip install -e ".[dev]"
test:
	python -m pytest -q
validate:
	python -m simonto validate
demo:
	python -m simonto demo
docs:
	python -m simonto tools > docs/tools.json
	python -m simonto diagram > docs/workflow.mmd
	python -m simonto readiness --markdown > docs/readiness_report.md
serve:
	python -m simonto serve
