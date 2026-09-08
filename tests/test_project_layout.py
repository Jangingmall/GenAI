from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_assets_docs_and_generated_outputs_are_grouped():
    expected_paths = [
        ROOT / "assets/samples/najeon-box.jpeg",
        ROOT / "assets/samples/product-photos",
        ROOT / "assets/references/detail-page-guide",
        ROOT / "assets/references/detail-page-template.png",
        ROOT / "assets/workflows/flux_kontext_dev_api.json",
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


def test_runtime_references_use_canonical_paths():
    checked_files = [
        ROOT / "README.md",
        ROOT / "scripts/run_local_detail_page.py",
        ROOT / "scripts/test_draft_preview.mjs",
        ROOT / "scripts/test_input_page.mjs",
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
