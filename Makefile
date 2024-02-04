.PHONY: docs
init:
	pip3 install hatch
	hatch env create

test:
	hatch run test

ci:
	hatch run test --junitxml=report.xml

flake8:
	hatch run python3 -m flake8 src/tunnelgraf

coverage:
	hatch run test --cov-config .coveragerc --verbose --cov-report term --cov-report xml --cov=src/requests tests

clean:
	rm -rf dist/ .pytest_cache/
	find . -name __pycache__ -delete

dev:
	hatch run python3 src/tunnelgraf/

build:
	hatch build

publish: hatch publish
