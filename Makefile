# django-cedar release helpers.
#
#   make version           print the project version
#   make bump PART=patch   bump the version (patch|minor|major), date the changelog, commit
#   make release           tag v<version>, push main + tag, create the GitHub release
#
# Publishing to PyPI is driven by the GitHub release: see .github/workflows/publish.yml.

.DEFAULT_GOAL := help
PART ?= patch
VERSION := $(shell uv version --short 2>/dev/null)
TAG := v$(VERSION)
CHANGELOG := CHANGELOG.md

# A shell with another checkout's venv activated confuses uv; always use
# this checkout's own .venv.
unexport VIRTUAL_ENV

# Print the body of this version's changelog section, trimmed of surrounding blank lines.
CHANGELOG_NOTES = awk -v h="\#\# [$(VERSION)]" \
	'substr($$0, 1, length(h)) == h { f = 1; next } \
	 /^\#\# \[/ { f = 0 } \
	 f { buf = buf $$0 "\n" } \
	 END { sub(/^\n+/, "", buf); sub(/\n+$$/, "", buf); if (buf != "") printf "%s\n", buf }' $(CHANGELOG)

.PHONY: help version bump release

help:
	@echo "Release:"
	@echo "  version            Print the project version (currently $(VERSION))"
	@echo "  bump PART=patch    Bump the version (patch|minor|major), date the changelog and commit"
	@echo "  release            Tag $(TAG), push main and the tag, create the GitHub release (publishes to PyPI)"

version:
	@echo $(VERSION)

bump:
	@[ -n "$(VERSION)" ] || \
		{ echo "Could not read the project version ('uv version --short' failed); is uv installed?"; exit 1; }
	@case "$(PART)" in patch|minor|major) ;; \
		*) echo "PART must be patch, minor or major (got '$(PART)')"; exit 1;; esac
	@[ -z "$$(git status --porcelain)" ] || \
		{ echo "Working tree is not clean; commit or stash first."; exit 1; }
	@grep -q '^## \[Unreleased\]' $(CHANGELOG) || \
		{ echo "No '## [Unreleased]' section in $(CHANGELOG)."; exit 1; }
	@awk '/^## \[Unreleased\]/ { f = 1; next } /^## \[/ { f = 0 } f && NF { found = 1 } END { exit !found }' $(CHANGELOG) || \
		{ echo "The [Unreleased] section of $(CHANGELOG) is empty; nothing to release."; exit 1; }
	uv version --bump "$(PART)"
	@new="$$(uv version --short)"; today="$$(date +%Y-%m-%d)"; \
	awk -v v="$$new" -v d="$$today" \
		'{ print } /^## \[Unreleased\]/ { print ""; print "## [" v "] - " d }' $(CHANGELOG) > $(CHANGELOG).tmp && \
	mv $(CHANGELOG).tmp $(CHANGELOG) && \
	git add pyproject.toml uv.lock $(CHANGELOG) && \
	git commit -q -m "chore: bump version to v$$new" && \
	echo "Committed v$$new. Run 'make release' to tag, push and publish."

release:
	@[ -n "$(VERSION)" ] || \
		{ echo "Could not read the project version ('uv version --short' failed); is uv installed?"; exit 1; }
	@command -v gh >/dev/null || \
		{ echo "The GitHub CLI (gh) is required to create the release."; exit 1; }
	@[ -z "$$(git status --porcelain)" ] || \
		{ echo "Working tree is not clean; commit or stash first."; exit 1; }
	@[ "$$(git rev-parse --abbrev-ref HEAD)" = "main" ] || \
		{ echo "Releases are cut from main (on $$(git rev-parse --abbrev-ref HEAD))."; exit 1; }
	@git fetch -q origin main
	@git merge-base --is-ancestor origin/main HEAD || \
		{ echo "main is behind origin/main; pull first."; exit 1; }
	@! git rev-parse -q --verify "refs/tags/$(TAG)" >/dev/null || \
		{ echo "Tag $(TAG) already exists locally; run 'make bump' first."; exit 1; }
	@[ -z "$$(git ls-remote --tags origin "refs/tags/$(TAG)")" ] || \
		{ echo "Tag $(TAG) already exists on origin; run 'make bump' first."; exit 1; }
	@grep -qE '^## \[$(subst .,\.,$(VERSION))\] - [0-9]{4}-[0-9]{2}-[0-9]{2}$$' $(CHANGELOG) || \
		{ echo "No dated '## [$(VERSION)] - YYYY-MM-DD' section in $(CHANGELOG); run 'make bump' first."; exit 1; }
	@[ -n "$$($(CHANGELOG_NOTES))" ] || \
		{ echo "The [$(VERSION)] section of $(CHANGELOG) is empty; nothing to release."; exit 1; }
	git tag -s "$(TAG)" -m "Release $(TAG)"
	git push --atomic origin main "$(TAG)"
	@notes="$$(mktemp)"; $(CHANGELOG_NOTES) > "$$notes"; \
	gh release create "$(TAG)" --verify-tag --title "$(TAG)" --notes-file "$$notes" || \
		{ rm -f "$$notes"; echo "Tag $(TAG) was pushed but the GitHub release failed; re-run the gh release create step by hand."; exit 1; }; \
	rm -f "$$notes"
	@echo "Published $(TAG). Follow the publish workflow: gh run watch"
