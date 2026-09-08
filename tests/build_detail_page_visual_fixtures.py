"""Offline HTML fixtures for the browser regression test; no model calls."""
import argparse
import io
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from detail_page_ai.dto import PageBlockDto, ProductProfileDto
from detail_page_ai.html_renderer import build_detail_page_html


def build(output: Path, include_local_demo: bool = False):
    output.mkdir(parents=True, exist_ok=True)
    photo = io.BytesIO()
    Image.new("RGB", (200, 1000), "#87aaa5").save(photo, format="PNG")
    # Max-length unbroken labels expose min-content overflow in grids/tables.
    title = "긴제목" * 40
    body = ("형태와 문양을 원본 사진에서 자세히 확인해 보세요. " * 20)[:500]
    item = {"label": "긴항목" * 26, "value": "설명" * 90}
    profile = ProductProfileDto(
        product_type="공예 소품", display_name="레이아웃 검증용 소품", summary=body,
        features=[{"title": "문양", "description": "사진에서 확인되는 문양"}],
        copy_sections=[{"section_type": "hero", "title": title[:80], "description": body[:300]}],
    )
    for layout in ("editorial-split", "image-first", "catalog-grid", "adaptive"):
        current = profile.model_copy(update={"layout_id": layout if layout != "adaptive" else "editorial-split"})
        if layout == "adaptive":
            current = current.model_copy(update={"page_plan": [
                PageBlockDto(section_id="hero", block_type="hero", title=title, body=body),
                PageBlockDto(section_id="intro", block_type="statement", title=title, body=body),
                PageBlockDto(section_id="features", block_type="feature_grid", title=title, items=[item] * 3),
                PageBlockDto(section_id="detail", block_type="detail_split", title=title, body=body),
                PageBlockDto(section_id="usage", block_type="usage_scene", variant="full-bleed", title=title, body=body),
                PageBlockDto(section_id="gallery", block_type="gallery", title="상세 사진"),
                PageBlockDto(section_id="recommend", block_type="recommendation", items=[item] * 3),
                PageBlockDto(section_id="info", block_type="info_table", title=title, items=[item]),
                PageBlockDto(section_id="notice", block_type="notice", title=title, body=body, items=[item]),
                PageBlockDto(section_id="closing", block_type="closing", title=title, body=body),
            ]})
        (output / f"{layout}.html").write_text(build_detail_page_html(current, photo.getvalue(), mime_type="image/png"))
    for name, image_path, profile_path in (
        ("najeon", "assets/samples/najeon-box.jpeg", "generated/samples/najeon_box_profile.json"),
        ("tea", "assets/samples/images-2.jpeg", "generated/samples/images-2/product-profile.json"),
    ):
        sample = ProductProfileDto.model_validate_json((ROOT / profile_path).read_text())
        (output / f"{name}.html").write_text(build_detail_page_html(sample, (ROOT / image_path).read_bytes()))
    # Optional local demo: reuse saved copy and its primary source only. This is
    # not a new model run or an assertion about old generated-view provenance.
    fan_run = ROOT / "generated/runs/local_detail_page/shop1_ea2db062a3c5a91aecc2aedd6e5d9c3d_2026-09-04_input_priority"
    if include_local_demo:
        saved = json.loads((fan_run / "result_summary.json").read_text())["product"]
        saved["safety_notes"] = saved.pop("warnings", [])
        fan = ProductProfileDto.model_validate(saved)
        (output / "fan.html").write_text(build_detail_page_html(fan, (fan_run / "photos/01-hero.jpg").read_bytes()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--include-local-demo", action="store_true")
    args = parser.parse_args()
    build(args.output, args.include_local_demo)
