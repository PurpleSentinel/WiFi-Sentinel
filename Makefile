.PHONY: install test demo serve build-firmware
install:
	python3 -m pip install -e './collector[dev]'
test:
	python3 -m pytest -q collector/tests
demo:
	python3 -m wids.cli demo
serve:
	python3 -m wids.cli serve
build-firmware:
	cd firmware && idf.py set-target esp32c5 && idf.py build
# demo/serve targets require collector/ installed into the active Python env.
