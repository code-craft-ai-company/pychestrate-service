
dist-clean:
	rm -fr dist

dist-build:
	poetry build

dist-publish:
	poetry publish

docs-html:
	$(MAKE) -C docs html

docs-clean:
	rm -fr docs/_build docs/extensions/protocols docs/extensions/resources
