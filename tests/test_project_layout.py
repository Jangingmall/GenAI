import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_assets_docs_and_generated_outputs_are_grouped():
    expected_paths = [
        ROOT / "assets/samples/najeon-box.jpeg",
        ROOT / "assets/samples/product-photos",
        ROOT / "assets/references/detail-page-guide",
        ROOT / "assets/references/detail-page-template.png",
        ROOT / "assets/workflows/flux_kontext_dev_api.json",
        ROOT / "scripts/browser/test_detail_page_layout.mjs",
        ROOT / "scripts/browser/test_draft_preview.mjs",
        ROOT / "scripts/browser/test_draft_preview_remote.mjs",
        ROOT / "scripts/browser/test_input_page.mjs",
        ROOT / "scripts/dataset/build_detail_page_eval_dataset.py",
        ROOT / "scripts/dataset/build_flux2_product_scene_50.py",
        ROOT / "scripts/dataset/build_training_dataset.py",
        ROOT / "scripts/dataset/setup_real_eval_dataset.py",
        ROOT / "scripts/runtime/build_detail_page_html.py",
        ROOT / "scripts/runtime/generate_attached_detail_page.py",
        ROOT / "scripts/runtime/render_detail_page.mjs",
        ROOT / "scripts/runtime/run_local_detail_page.py",
        ROOT / "docs/api/ai-dto-contract.md",
        ROOT / "docs/api/ai-fe-io-spec.md",
        ROOT / "docs/operations/local-llm.md",
        ROOT / "docs/references/product-photography.md",
        ROOT / "generated/samples/live_najeon_box",
        ROOT / "generated/previews/ai_draft_preview.png",
        ROOT / "generated/verified/source_safe_detail_page.png",
    ]

    missing = [str(path.relative_to(ROOT)) for path in expected_paths if not path.exists()]
    assert not missing, f"missing canonical project paths: {missing}"


def test_legacy_root_locations_are_removed():
    legacy_paths = [
        ROOT / "images.jpeg",
        ROOT / "Sample Data",
        ROOT / "상세페이지 참고용",
        ROOT / "local_workflows",
        ROOT / "product-photography.md",
        ROOT / "team3_ecommercesystemai.egg-info",
        ROOT / "src/team3_ecommercesystemai.egg-info",
    ]

    remaining = [str(path.relative_to(ROOT)) for path in legacy_paths if path.exists()]
    assert not remaining, f"legacy project locations remain: {remaining}"


def test_legacy_flat_script_locations_are_removed():
    legacy_paths = [
        ROOT / "scripts/test_detail_page_layout.mjs",
        ROOT / "scripts/test_draft_preview.mjs",
        ROOT / "scripts/test_draft_preview_remote.mjs",
        ROOT / "scripts/test_input_page.mjs",
        ROOT / "scripts/build_detail_page_eval_dataset.py",
        ROOT / "scripts/build_flux2_product_scene_50.py",
        ROOT / "scripts/build_training_dataset.py",
        ROOT / "scripts/setup_real_eval_dataset.py",
        ROOT / "scripts/build_detail_page_html.py",
        ROOT / "scripts/generate_attached_detail_page.py",
        ROOT / "scripts/render_detail_page.mjs",
        ROOT / "scripts/run_local_detail_page.py",
    ]

    remaining = [str(path.relative_to(ROOT)) for path in legacy_paths if path.exists()]
    assert not remaining, f"legacy flat script locations remain: {remaining}"


def test_runtime_references_use_canonical_paths():
    checked_files = [
        ROOT / "README.md",
        ROOT / "scripts/runtime/run_local_detail_page.py",
        ROOT / "scripts/browser/test_draft_preview.mjs",
        ROOT / "scripts/browser/test_input_page.mjs",
        ROOT / "web/ai_draft_preview.js",
        ROOT / "docs/operations/local-llm.md",
    ]
    legacy_references = (
        "images.jpeg",
        "generated/local_najeon_box",
        "generated/live_najeon_box",
        "generated/ai_draft_preview.png",
        "generated/ai_input_page.png",
        "docs/ai-dto-contract.md",
    )

    found = []
    for path in checked_files:
        content = path.read_text(encoding="utf-8")
        for reference in legacy_references:
            if reference in content:
                found.append(f"{path.relative_to(ROOT)}: {reference}")

    assert not found, f"legacy path references remain: {found}"


def test_generated_and_environment_artifacts_are_ignored():
    ignored = set((ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())

    assert "generated/" in ignored
    assert "*.egg-info/" in ignored
    assert "tmp/" in ignored


def test_detail_package_has_no_module_level_local_adapter_imports():
    violations = []
    for path in sorted((ROOT / "src/detail_page_ai").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            imported_modules = []
            if isinstance(node, ast.Import):
                imported_modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules = [node.module]
            for module in imported_modules:
                if module == "local_detail_page_ai" or module.startswith(
                    "local_detail_page_ai."
                ):
                    violations.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: {module}"
                    )

    # Function-level imports are intentionally allowed: the package graph is
    # enforced at module scope, while the executable composition boundary can
    # resolve an adapter factory only when the service is requested.
    assert not violations, "module-level local adapter imports found: " + "; ".join(
        violations
    )
