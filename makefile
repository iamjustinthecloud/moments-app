SHELL := /bin/bash
SNAPSHOT_DIR := tests/unit/snapshots/test_stack_snapshot/synthesized

# Run tests with coverage
test:
	@if [ -z "$(stack)" ]; then \
  		echo "❌ ERROR: Please specify a stack name, e.g. make test stack=moments_app"; \
  		exit 1; \
  	fi
	@echo "🧹 Running black --check"
	poetry run black --check $(stack)
	@echo "🧪 Running pytest with coverage for stack: $(stack)"
	PYTHONPATH=. poetry run pytest \
		--cov=$(stack) \
		--cov-report=term-missing \
		--cov-report=xml \
		tests/

# Open coverage report (macOS: 'open', Linux: 'xdg-open')
coverage:
	@if [ -f build/coverage-html/index.html ]; then \
	  (open build/coverage-html/index.html 2>/dev/null || xdg-open build/coverage-html/index.html 2>/dev/null || echo "Coverage report generated at build/coverage-html/index.html"); \
	else \
	  echo "Coverage report not found. Run 'make test' first."; \
	fi

diff-moments-app:
	poetry run cdk diff MomentsAppStack

# 🔧 Generate the CloudFormation template and copy it next to the snapshot
synth-moments-app:
	@echo "🧠 Synthesizing CDK stack..."
	poetry run cdk synth MomentsAppStack > /dev/null

	@echo "📦 Copying synthesized template to snapshot directory..."
	mkdir -p tests/unit/snapshots/test_stack_snapshot/synthesized
	cp cdk.out/MomentsAppStack.template.json tests/unit/snapshots/test_stack_snapshot/synthesized/

	@echo "✅ Synth complete — template copied to:"
	@echo "   tests/unit/snapshots/test_stack_snapshot/synthesized/MomentsAppStack.template.json"

mentor:
	@echo "🧭 Opening mentor session files..."
	open learning/learning_plan.md
	open learning/mentor_session_notes.md
	@echo "✅ Ready to learn and reflect!"
