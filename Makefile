ADDON_ID := blender_shell_generator
VERSION  := $(shell grep '^version' blender_manifest.toml | grep -o '"[^"]*"' | tr -d '"')
OUT      := dist/$(ADDON_ID)-$(VERSION).zip

SOURCES := __init__.py blender_manifest.toml $(shell find modules -name "*.py")

.PHONY: all clean release

all: $(OUT)

# Usage: make release VERSION=1.2.0
release:
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=x.y.z" && exit 1)
	@sed -i '' 's/^version = ".*"/version = "$(VERSION)"/' blender_manifest.toml
	@git add blender_manifest.toml
	@git commit -m "Release v$(VERSION)"
	@git tag -a "v$(VERSION)" -m "Release v$(VERSION)"
	@echo "Done. Push with: git push && git push --tags"

$(OUT): $(SOURCES)
	@mkdir -p dist
	@rm -f $(OUT)
	$(eval TMPDIR := $(shell mktemp -d))
	@mkdir $(TMPDIR)/$(ADDON_ID)
	@cp __init__.py blender_manifest.toml $(TMPDIR)/$(ADDON_ID)/
	@cp -r modules $(TMPDIR)/$(ADDON_ID)/modules
	@find $(TMPDIR) -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@(cd $(TMPDIR) && zip -r $(CURDIR)/$(OUT) $(ADDON_ID))
	@rm -rf $(TMPDIR)
	@echo "Built: $(OUT)"

clean:
	rm -rf dist
