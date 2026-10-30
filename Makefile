.PHONY: install test assess

install:
	cd backend && pip install -e ".[dev]"

test:
	cd backend && python -m pytest -q

# Score the demo business against both lender policies
assess:
	cd backend && python -m app.engine.cli examples/bakery_supplier.json
	cd backend && python -m app.engine.cli examples/bakery_supplier.json --policy digital_lender_invoice
