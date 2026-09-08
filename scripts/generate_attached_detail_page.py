"""Generate a self-contained detail page for a supplied product image.

This path intentionally uses a hand-checked, image-grounded profile when the
local vision model is unavailable. It does not invent product specifications
and it does not call a paid or remote model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from detail_page_ai.dto import GenerationOptions, PageBlockDto, ProductProfileDto
from detail_page_ai.html_renderer import HtmlDetailPageRenderer, build_detail_page_html
from detail_page_ai.source_photos import SourcePreservingProductPhotoGenerator


def build_profile() -> ProductProfileDto:
    features = [
        {
            "title": "부드러운 분홍 컬러",
            "description": "넓게 펼쳐진 면 전체에 연한 분홍색이 이어지고, 가장자리에는 조금 더 선명한 분홍색 선이 보입니다.",
            "evidence": "image-visible",
            "confidence": 0.99,
        },
        {
            "title": "촘촘한 세로 주름",
            "description": "중심에서 가장자리로 퍼지는 촘촘한 세로 주름이 표면에 반복됩니다.",
            "evidence": "image-visible",
            "confidence": 0.98,
        },
        {
            "title": "길게 이어진 손잡이",
            "description": "면의 중심 아래로 짙은 나무색 손잡이가 길게 뻗어 단정한 세로 실루엣을 만듭니다.",
            "evidence": "image-visible",
            "confidence": 0.98,
        },
    ]
    feature_items = [
        {"label": feature["title"], "value": feature["description"], "evidence": feature["evidence"]}
        for feature in features
    ]
    plan = [
        PageBlockDto(
            section_id="hero", block_type="hero", eyebrow="FORM & COLOR",
            title="분홍빛 곡선으로 완성한 손잡이 부채",
            body="연한 분홍색 면에 촘촘한 세로 주름이 이어지고, 길게 뻗은 손잡이가 형태를 완성합니다.",
            variant="paper", photo_id="hero",
        ),
        PageBlockDto(
            section_id="statement", block_type="statement", eyebrow="OBJECT DETAIL",
            title="손끝에 남는 부드러운 곡선",
            body="넓게 펼쳐지는 부채 면과 곧게 이어진 손잡이가 대비를 이루는 오브제입니다.",
            variant="light",
        ),
        PageBlockDto(
            section_id="features", block_type="feature_grid", eyebrow="VISIBLE DETAILS",
            title="가까이 볼수록 선명해지는 형태",
            body="사진에서 직접 확인되는 색과 표면, 실루엣을 중심으로 구성했습니다.",
            variant="paper", items=feature_items,
        ),
        PageBlockDto(
            section_id="surface-detail", block_type="detail_split", eyebrow="DETAIL 01",
            title="주름이 만드는 입체감",
            body="부채 면을 따라 반복되는 세로 주름이 빛을 부드럽게 나누며 표면에 리듬을 만듭니다.",
            variant="dark", photo_id="detail",
        ),
        PageBlockDto(
            section_id="handle-detail", block_type="detail_split", eyebrow="DETAIL 02",
            title="손잡이로 이어지는 긴 실루엣",
            body="면의 중심에서 아래로 이어지는 짙은 손잡이가 전체 비례를 길고 단정하게 정리합니다.",
            variant="image-right", photo_id="detail-02",
        ),
        PageBlockDto(
            section_id="wide-view", block_type="wide_image", eyebrow="WIDE VIEW",
            title="전체 실루엣을 한눈에",
            body="둥글게 퍼지는 면과 가느다란 손잡이의 비율을 살펴보세요.",
            variant="light", photo_id="packshot",
        ),
        PageBlockDto(
            section_id="gallery", block_type="gallery", eyebrow="PRODUCT GALLERY",
            title="분홍색과 표면의 결",
            body="원본 사진에서 확인되는 색과 주름을 가까이에서 볼 수 있습니다.",
            variant="paper", photo_ids=["detail", "detail-02", "detail-03"],
        ),
        PageBlockDto(
            section_id="usage-scene", block_type="usage_scene", eyebrow="EVERYDAY SCENE",
            title="조용한 공간에 놓이는 포인트",
            body="선반이나 테이블 위에 세워 두거나 손에 들고 사용하는 장면을 상상해 볼 수 있습니다. 실제 사용 방식과 안정성은 별도 확인이 필요합니다.",
            variant="full-bleed", photo_id="lifestyle",
        ),
        PageBlockDto(
            section_id="info", block_type="info_table", eyebrow="CHECK BEFORE SALE",
            title="판매 전에 확인할 정보",
            body="이미지에서 확인되지 않는 항목은 판매자 정보로 보완해 주세요.",
            variant="paper", items=[
                {"label": "정확한 소재", "value": "이미지만으로 확인 불가", "evidence": "unknown"},
                {"label": "제품 규격", "value": "이미지만으로 확인 불가", "evidence": "unknown"},
                {"label": "가격·구성", "value": "이미지만으로 확인 불가", "evidence": "unknown"},
                {"label": "사용·보관 방법", "value": "판매자 안내 필요", "evidence": "unknown"},
            ],
        ),
        PageBlockDto(
            section_id="notice", block_type="notice", eyebrow="IMAGE-BASED NOTE",
            title="사진에서 확인되는 범위",
            body="형태와 색감은 사진을 기준으로 소개하며, 보이지 않는 상품 정보는 단정하지 않습니다.",
            variant="dark", items=[
                {"label": "안내", "value": "정확한 소재·규격·가격은 별도 확인이 필요합니다.", "evidence": "unknown"},
                {"label": "안내", "value": "사진 한 장만으로 실제 부채 기능이나 내구성을 판단할 수 없습니다.", "evidence": "unknown"},
            ],
        ),
        PageBlockDto(
            section_id="closing", block_type="closing", eyebrow="CLOSING",
            title="손끝에 머무는 분홍빛 곡선",
            body="단정한 실루엣과 반복되는 주름이 만들어낸 조용한 존재감입니다.",
            variant="paper",
        ),
    ]
    return ProductProfileDto(
        product_type="손잡이 부채",
        display_name="분홍 곡선 손잡이 부채",
        summary="연한 분홍색의 곡선 면과 촘촘한 세로 주름, 길게 이어진 손잡이가 보이는 손잡이형 부채입니다.",
        keywords=["분홍색", "곡선 실루엣", "세로 주름", "손잡이 부채"],
        observations={
            "colors": ["연한 분홍색", "흰색에 가까운 밝은 색", "나무색", "회색 배경"],
            "shape": "넓게 펼쳐진 곡선 면과 긴 손잡이",
            "visible_components": ["부채 면", "세로 주름", "손잡이"],
            "visible_surface": "주름이 반복되는 밝은 분홍색 표면",
        },
        features=features,
        copy_sections=[{
            "section_type": "hero",
            "title": "분홍빛 곡선으로 완성한 손잡이 부채",
            "description": "연한 분홍색 면에 촘촘한 세로 주름이 이어지고, 길게 뻗은 손잡이가 형태를 완성합니다.",
            "evidence": "image-visible",
        }],
        usage_scene="선반이나 테이블 위에 세워 두거나 손에 들고 사용하는 장면을 상상해 볼 수 있습니다.",
        uncertain_information=["정확한 소재", "제품 규격", "가격·구성", "실제 사용 가능 여부", "사용·보관 방법"],
        safety_notes=["사진 한 장만으로 기능·내구성·안전성을 판단하지 않음", "이미지에서 확인되지 않는 정보를 사실처럼 표현하지 않음"],
        page_plan=plan,
    )


def generate(image_path: Path, output_dir: Path) -> None:
    source = image_path.read_bytes()
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    profile = build_profile()
    options = GenerationOptions()
    photos = SourcePreservingProductPhotoGenerator(
        include_scale=False,
        photo_roles=("hero", "packshot", "detail", "lifestyle"),
    ).generate(
        source_image=source, source_mime_type=mime_type,
        profile=profile, options=options,
    )
    rendered = HtmlDetailPageRenderer().render(
        source_image=source, source_mime_type=mime_type,
        template_image=None, profile=profile, options=options,
        photo_set=photos,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "input.jpg").write_bytes(source)
    (output_dir / "product-profile.json").write_text(
        profile.model_dump_json(indent=2), encoding="utf-8"
    )
    (output_dir / "detail_page.html").write_text(
        build_detail_page_html(profile, source, mime_type=mime_type, photo_set=photos),
        encoding="utf-8",
    )
    (output_dir / "detail_page.png").write_bytes(rendered.data)
    sections_dir = output_dir / "sections"
    sections_dir.mkdir(exist_ok=True)
    for section in rendered.sections:
        (sections_dir / f"{section.order:02d}-{section.section_id}.png").write_bytes(section.data)
    photos_dir = output_dir / "photos"
    photos_dir.mkdir(exist_ok=True)
    for photo in rendered.photos:
        extension = "jpg" if photo.mime_type == "image/jpeg" else "png"
        (photos_dir / f"{photo.order:02d}-{photo.photo_id}.{extension}").write_bytes(photo.data)
    (output_dir / "result_summary.json").write_text(json.dumps({
        "generation_mode": "image-grounded-profile-plus-source-preserving-renderer",
        "model_run": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(image_path),
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "profile": "product-profile.json",
        "detail_page": {"file": "detail_page.png", "mime_type": rendered.mime_type,
                        "width": rendered.width, "height": rendered.height,
                        "sections": len(rendered.sections)},
        "photos": [{"photo_id": photo.photo_id, "asset_mode": photo.asset_mode,
                    "product_generated": photo.product_generated,
                    "fidelity_status": photo.fidelity_status,
                    "source_sha256": photo.source_sha256}
                   for photo in rendered.photos],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "generated/runs/attached_671da9da26c699dfea1f767962bea070")
    args = parser.parse_args()
    generate(args.image, args.output_dir)
