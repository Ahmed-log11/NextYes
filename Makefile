.PHONY: install test assess data docs extract-ceiling extract-eval

install:
	cd backend && pip install -e ".[dev]"

test:
	cd backend && python -m pytest -q

# Score the demo business against both lender policies
assess:
	cd backend && python -m app.engine.cli examples/bakery_supplier.json
	cd backend && python -m app.engine.cli examples/bakery_supplier.json --policy digital_lender_invoice

# Generate the 63 synthetic businesses (dev / heldout / demo)
data:
	cd backend && python -m app.synth.dataset

# Render bilingual PDF documents for every business (about a minute)
docs:
	cd backend && python -m app.synth.documents

# Extraction accuracy. oracle = perfect reader (pipeline ceiling, no API key); haiku = the real model
extract-ceiling:
	cd backend && python -m app.extract.evaluate --split dev --level all --reader oracle

extract-eval:
	cd backend && python -m app.extract.evaluate --split dev --level all --reader haiku
