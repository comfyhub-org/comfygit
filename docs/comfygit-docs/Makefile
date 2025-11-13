.PHONY: help serve build generate-cli clean

help:
	@echo "ComfyGit Documentation"
	@echo ""
	@echo "Available targets:"
	@echo "  serve        - Start development server"
	@echo "  build        - Build documentation site"
	@echo "  generate-cli - Generate CLI reference from argparse"
	@echo "  clean        - Remove build artifacts"

serve: generate-cli
	.venv/bin/mkdocs serve

build: generate-cli
	.venv/bin/mkdocs build

generate-cli:
	@echo "Generating CLI reference documentation..."
	cd ../.. && .venv/bin/python docs/comfygit-docs/scripts/generate_cli_reference.py

clean:
	rm -rf site/
	rm -rf docs/cli-reference/*.md
