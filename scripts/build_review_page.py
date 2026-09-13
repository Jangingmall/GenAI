#!/usr/bin/env python3
"""Build an interactive, self-contained HTML human review page for pilot evaluation.

Reads run_index.json, result_summary.json for each case, and review_sheet.csv header,
and generates review.html in the specified pilot directory.
All styles and scripts are completely inline (no external dependencies) and
all asset paths are relative, allowing review.html to be viewed directly via file://.
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import os
import sys
from pathlib import Path
from typing import Any


def escape(val: Any) -> str:
    """Escape HTML entities safely."""
    if val is None:
        return ""
    return html.escape(str(val))


def find_case_photos(case_dir: Path, pilot_dir: Path) -> list[dict[str, Any]]:
    """Find the 8 photos for a case and return their roles, relative paths, and metadata."""
    photos_dir = case_dir / "photos"
    roles_order = [
        ("01-hero", "hero", "원본 보존 대표컷", "source_composite", False),
        ("02-packshot", "packshot", "원본 보존 팩샷", "source_composite", False),
        ("03-detail", "detail", "원본 디테일 크롭", "source_crop", False),
        ("04-lifestyle", "lifestyle", "AI 생성 활용 장면", "generated_scene", True),
        ("05-detail-02", "detail-02", "AI 생성 디테일 1", "generated_view", True),
        ("06-detail-03", "detail-03", "AI 생성 디테일 2", "generated_view", True),
        ("07-detail-04", "detail-04", "AI 생성 디테일 3", "generated_view", True),
        ("08-detail-05", "detail-05", "AI 생성 디테일 4", "generated_view", True),
    ]

    result = []
    for prefix, role_id, label, asset_mode, is_generated in roles_order:
        matches = list(photos_dir.glob(f"{prefix}.*"))
        if matches:
            photo_file = matches[0]
            rel_path = os.path.relpath(photo_file, pilot_dir)
            result.append({
                "prefix": prefix,
                "role_id": role_id,
                "label": label,
                "asset_mode": asset_mode,
                "is_generated": is_generated,
                "filename": photo_file.name,
                "rel_path": rel_path,
            })
    return result


def load_pilot_data(pilot_dir: Path) -> dict[str, Any]:
    """Load run_index and all result_summary.json files from the pilot directory."""
    run_index_file = pilot_dir / "run_index.json"
    if not run_index_file.exists():
        raise FileNotFoundError(f"run_index.json not found in {pilot_dir}")

    with open(run_index_file, "r", encoding="utf-8") as f:
        run_index = json.load(f)

    # Load review_sheet.csv header if present to ensure exact column compatibility
    review_sheet_file = pilot_dir / "review_sheet.csv"
    columns = []
    if review_sheet_file.exists():
        with open(review_sheet_file, "r", encoding="utf-8-sig") as f:
            first_line = f.readline().strip()
            columns = [col.strip() for col in first_line.split(",") if col.strip()]

    if not columns:
        columns = [
            "case_id", "category", "asset_id", "입력 이미지 경로", "산출물 경로",
            "실행 성공 여부", "에러 메시지",
            "검수자A_사실성", "검수자A_명료성", "검수자A_상품성", "검수자A_시각품질", "검수자A_코멘트",
            "검수자B_사실성", "검수자B_명료성", "검수자B_상품성", "검수자B_시각품질", "검수자B_코멘트",
            "합의_사실성", "합의_명료성", "합의_상품성", "합의_시각품질", "합의_메모"
        ]

    cases_data = []
    for case_meta in run_index.get("cases", []):
        case_id = case_meta.get("case_id")
        case_dir = pilot_dir / case_id
        summary_file = case_dir / "result_summary.json"

        summary_data = {}
        if summary_file.exists():
            with open(summary_file, "r", encoding="utf-8") as f:
                summary_data = json.load(f)

        prod = summary_data.get("product", {})
        photos = find_case_photos(case_dir, pilot_dir)

        # Relative paths
        orig_img_path = case_meta.get("image_path", "")
        rel_orig_img = os.path.relpath(orig_img_path, pilot_dir) if orig_img_path else ""
        rel_detail_png = os.path.relpath(case_dir / "detail_page.png", pilot_dir)

        cases_data.append({
            "case_id": case_id,
            "category": case_meta.get("category", ""),
            "asset_id": case_meta.get("asset_id", ""),
            "input_image_path": orig_img_path,
            "rel_input_image": rel_orig_img,
            "output_dir": str(case_dir),
            "rel_detail_page": rel_detail_png,
            "success": case_meta.get("success", True),
            "duration_seconds": case_meta.get("duration_seconds", 0.0),
            "product_type": prod.get("product_type", ""),
            "display_name": prod.get("display_name", ""),
            "is_traditional_craft": prod.get("is_traditional_craft", False),
            "craft_type": prod.get("craft_type") or "해당 없음",
            "classification_confidence": prod.get("classification_confidence", 0.0),
            "classification_reason": prod.get("classification_reason", ""),
            "layout_id": prod.get("layout_id", "editorial-split"),
            "summary": prod.get("summary", ""),
            "uncertain_information": prod.get("uncertain_information", []),
            "safety_notes": prod.get("safety_notes", []),
            "page_plan": prod.get("page_plan", []),
            "photos": photos,
        })

    return {
        "pilot_id": run_index.get("pilot_id", ""),
        "started_at": run_index.get("started_at", ""),
        "ended_at": run_index.get("ended_at", ""),
        "total_cases": run_index.get("total_cases", len(cases_data)),
        "successful_cases": run_index.get("successful_cases", len(cases_data)),
        "columns": columns,
        "cases": cases_data,
    }


def generate_html(data: dict[str, Any]) -> str:
    """Generate self-contained review HTML page with embedded CSS, JS, and JSON."""
    pilot_id = escape(data["pilot_id"])
    cases_json = json.dumps(data["cases"], ensure_ascii=False)
    columns_json = json.dumps(data["columns"], ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>상세페이지 AI 사람 검수 킷 — {pilot_id}</title>
<style>
  :root {{
    --bg-main: #0f141c;
    --bg-card: #18202c;
    --bg-card-sub: #1e2838;
    --bg-card-subtle: #253346;
    --border: #2e3d52;
    --border-highlight: #465b7a;
    --text-primary: #f0f4f8;
    --text-secondary: #9cb0c6;
    --text-muted: #62778f;
    --accent-blue: #3b82f6;
    --accent-blue-hover: #2563eb;
    --accent-green: #10b981;
    --accent-green-dark: #064e3b;
    --accent-yellow: #f59e0b;
    --accent-red: #ef4444;
    --accent-purple: #8b5cf6;
    --font-stack: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  }}

  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}

  body {{
    font-family: var(--font-stack);
    background-color: var(--bg-main);
    color: var(--text-primary);
    line-height: 1.5;
    padding-bottom: 80px;
  }}

  /* Top Sticky Bar */
  .sticky-top-bar {{
    position: sticky;
    top: 0;
    z-index: 1000;
    background-color: rgba(15, 20, 28, 0.96);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    padding: 12px 24px;
  }}

  .header-main-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 16px;
  }}

  .header-title-group {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}

  .header-title {{
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #fff;
  }}

  .pilot-badge {{
    background: #1e293b;
    border: 1px solid #334155;
    color: #38bdf8;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 12px;
    font-family: monospace;
    font-weight: 600;
  }}

  .reviewer-controls {{
    display: flex;
    align-items: center;
    gap: 12px;
    background: var(--bg-card);
    padding: 6px 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
  }}

  .reviewer-controls label {{
    font-size: 13px;
    color: var(--text-secondary);
    font-weight: 600;
  }}

  .reviewer-select, .reviewer-input {{
    background: var(--bg-card-sub);
    border: 1px solid var(--border);
    color: #fff;
    padding: 5px 10px;
    border-radius: 6px;
    font-size: 13px;
    outline: none;
  }}

  .reviewer-select:focus, .reviewer-input:focus {{
    border-color: var(--accent-blue);
  }}

  .header-actions {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  .btn {{
    background: var(--bg-card-sub);
    border: 1px solid var(--border);
    color: var(--text-primary);
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }}

  .btn:hover {{
    background: var(--border);
    border-color: var(--border-highlight);
    color: #fff;
  }}

  .btn-primary {{
    background: var(--accent-blue);
    border-color: var(--accent-blue-hover);
    color: #fff;
  }}

  .btn-primary:hover {{
    background: var(--accent-blue-hover);
  }}

  .btn-danger {{
    background: rgba(239, 68, 68, 0.15);
    border-color: rgba(239, 68, 68, 0.4);
    color: #fca5a5;
  }}

  .btn-danger:hover {{
    background: rgba(239, 68, 68, 0.3);
  }}

  /* Case Navigation Pills */
  .case-nav-row {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 10px;
    overflow-x: auto;
    padding-bottom: 4px;
  }}

  .nav-pill {{
    display: flex;
    align-items: center;
    gap: 6px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    color: var(--text-secondary);
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 12px;
    text-decoration: none;
    white-space: nowrap;
    transition: all 0.15s ease;
  }}

  .nav-pill:hover {{
    background: var(--bg-card-sub);
    border-color: var(--border-highlight);
    color: #fff;
  }}

  .nav-pill-status {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #64748b;
  }}

  .nav-pill-status.done {{
    background: var(--accent-green);
  }}

  .nav-pill-status.fail {{
    background: var(--accent-red);
  }}

  /* Collapsible Guidelines */
  .guidelines-wrapper {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-top: 10px;
    overflow: hidden;
  }}

  .guidelines-toggle {{
    width: 100%;
    background: var(--bg-card-sub);
    border: none;
    color: var(--text-primary);
    padding: 8px 16px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}

  .guidelines-content {{
    padding: 16px;
    display: none;
    border-top: 1px solid var(--border);
    font-size: 13px;
    color: var(--text-secondary);
  }}

  .guidelines-content.open {{
    display: block;
  }}

  .guidelines-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
  }}

  .guide-box {{
    background: var(--bg-card-sub);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
  }}

  .guide-box h4 {{
    font-size: 13px;
    color: #fff;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}

  .guide-score-row {{
    margin-bottom: 6px;
    line-height: 1.4;
  }}

  .guide-score-badge {{
    display: inline-block;
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    margin-right: 4px;
  }}

  .badge-1 {{ background: #7f1d1d; color: #fca5a5; }}
  .badge-3 {{ background: #78350f; color: #fde68a; }}
  .badge-5 {{ background: #064e3b; color: #a7f3d0; }}

  /* Gate Warning Box */
  .gate-box {{
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 6px;
    padding: 12px;
    margin-top: 12px;
  }}

  .gate-box h4 {{
    color: #f87171;
    font-size: 13px;
    margin-bottom: 6px;
  }}

  .gate-list {{
    list-style: none;
    padding-left: 0;
  }}

  .gate-list li {{
    margin-bottom: 4px;
    display: flex;
    align-items: baseline;
    gap: 6px;
  }}

  /* Main Container */
  .container {{
    max-width: 1720px;
    margin: 24px auto;
    padding: 0 24px;
  }}

  /* Case Card */
  .case-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-bottom: 40px;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3);
    overflow: hidden;
  }}

  .case-header {{
    background: var(--bg-card-sub);
    border-bottom: 1px solid var(--border);
    padding: 14px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
  }}

  .case-title-area {{
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }}

  .case-index {{
    background: var(--accent-blue);
    color: #fff;
    font-size: 12px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 12px;
  }}

  .case-id {{
    font-size: 16px;
    font-weight: 700;
    color: #fff;
    font-family: monospace;
  }}

  .tag {{
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 6px;
    font-weight: 600;
  }}

  .tag-category {{ background: #1e3a8a; color: #93c5fd; }}
  .tag-craft {{ background: #14532d; color: #86efac; }}
  .tag-general {{ background: #374151; color: #d1d5db; }}
  .tag-layout {{ background: #312e81; color: #c7d2fe; }}
  .tag-confidence {{ background: #1e293b; color: #cbd5e1; border: 1px solid #475569; }}

  /* 3-Column Layout */
  .case-grid {{
    display: grid;
    grid-template-columns: 460px 1fr 380px;
    gap: 20px;
    padding: 20px;
  }}

  @media (max-width: 1400px) {{
    .case-grid {{
      grid-template-columns: 1fr 1fr;
    }}
    .col-scoring {{
      grid-column: span 2;
    }}
  }}

  @media (max-width: 900px) {{
    .case-grid {{
      grid-template-columns: 1fr;
    }}
    .col-scoring {{
      grid-column: span 1;
    }}
  }}

  /* Column 1: Images */
  .col-images {{
    display: flex;
    flex-direction: column;
    gap: 16px;
  }}

  .image-compare-box {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    background: var(--bg-card-sub);
    padding: 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
  }}

  .img-frame {{
    display: flex;
    flex-direction: column;
  }}

  .img-frame-label {{
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}

  .orig-img-container {{
    width: 100%;
    height: 380px;
    background: #000;
    border-radius: 6px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    cursor: zoom-in;
  }}

  .orig-img-container img {{
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }}

  .detail-scroll-container {{
    width: 100%;
    height: 380px;
    background: #1e1e1e;
    border-radius: 6px;
    overflow-y: auto;
    border: 1px solid var(--border);
    position: relative;
    cursor: zoom-in;
  }}

  .detail-scroll-container img {{
    width: 100%;
    display: block;
  }}

  /* Photos 8 Gallery */
  .photos-gallery-box {{
    background: var(--bg-card-sub);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
  }}

  .photos-gallery-title {{
    font-size: 12px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 8px;
    display: flex;
    justify-content: space-between;
  }}

  .photos-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
  }}

  .photo-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
    cursor: zoom-in;
    transition: transform 0.15s ease;
  }}

  .photo-card:hover {{
    transform: scale(1.03);
    border-color: var(--border-highlight);
  }}

  .photo-card.verified {{
    border-left: 3px solid var(--accent-green);
  }}

  .photo-card.generated {{
    border-left: 3px solid var(--accent-purple);
  }}

  .photo-thumb-wrap {{
    width: 100%;
    height: 80px;
    background: #0b0f14;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }}

  .photo-thumb-wrap img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
  }}

  .photo-meta {{
    padding: 4px 6px;
    font-size: 10px;
  }}

  .photo-role {{
    font-weight: 700;
    color: #fff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  .photo-badge {{
    font-size: 9px;
    font-weight: 600;
    padding: 1px 3px;
    border-radius: 3px;
    display: inline-block;
    margin-top: 2px;
  }}

  .photo-badge.verified {{
    background: rgba(16, 185, 129, 0.2);
    color: #6ee7b7;
  }}

  .photo-badge.generated {{
    background: rgba(139, 92, 246, 0.2);
    color: #c4b5fd;
  }}

  /* Column 2: Content & Copy */
  .col-copy {{
    display: flex;
    flex-direction: column;
    gap: 16px;
  }}

  .meta-summary-box {{
    background: var(--bg-card-sub);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px;
    font-size: 13px;
  }}

  .meta-field {{
    margin-bottom: 6px;
    display: flex;
    gap: 8px;
  }}

  .meta-label {{
    color: var(--text-secondary);
    font-weight: 600;
    width: 110px;
    flex-shrink: 0;
  }}

  .meta-val {{
    color: var(--text-primary);
    word-break: break-word;
  }}

  /* Copy Plan Stream */
  .copy-stream-box {{
    background: var(--bg-card-sub);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px;
    max-height: 750px;
    overflow-y: auto;
  }}

  .copy-stream-title {{
    font-size: 14px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}

  .block-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    margin-bottom: 10px;
  }}

  .block-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
  }}

  .block-type-badge {{
    font-size: 11px;
    font-weight: 700;
    background: var(--bg-card-subtle);
    color: #93c5fd;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: monospace;
  }}

  .block-eyebrow {{
    font-size: 11px;
    font-weight: 700;
    color: var(--accent-yellow);
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-bottom: 2px;
  }}

  .block-title {{
    font-size: 14px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 6px;
  }}

  .block-body {{
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.5;
  }}

  .block-items {{
    margin-top: 8px;
    border-top: 1px dashed var(--border);
    padding-top: 8px;
  }}

  .block-item {{
    font-size: 12px;
    margin-bottom: 4px;
    display: flex;
    align-items: baseline;
    gap: 6px;
  }}

  .item-label {{
    color: #e2e8f0;
    font-weight: 600;
  }}

  .item-val {{
    color: var(--text-secondary);
  }}

  .item-evidence {{
    font-size: 10px;
    padding: 1px 4px;
    border-radius: 3px;
    background: #334155;
    color: #cbd5e1;
  }}

  /* Column 3: Scoring Form */
  .col-scoring {{
    background: var(--bg-card-sub);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }}

  .scoring-header {{
    border-bottom: 1px solid var(--border);
    padding-bottom: 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}

  .scoring-header h3 {{
    font-size: 15px;
    font-weight: 700;
    color: #fff;
  }}

  .score-group {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
  }}

  .score-label {{
    font-size: 13px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
  }}

  .score-options {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 4px;
  }}

  .score-option-label {{
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 6px 2px;
    border-radius: 4px;
    background: var(--bg-card-sub);
    border: 1px solid var(--border);
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    transition: all 0.15s ease;
  }}

  .score-option-label:hover {{
    background: var(--border);
    border-color: var(--border-highlight);
  }}

  .score-option-label input {{
    display: none;
  }}

  .score-option-label.checked {{
    background: var(--accent-blue);
    border-color: var(--accent-blue-hover);
    color: #fff;
  }}

  .score-subtext {{
    font-size: 10px;
    color: var(--text-muted);
    margin-top: 2px;
  }}

  .score-option-label.checked .score-subtext {{
    color: #dbeafe;
  }}

  /* Gate Checkboxes in Card */
  .gates-section {{
    background: rgba(239, 68, 68, 0.05);
    border: 1px solid rgba(239, 68, 68, 0.25);
    border-radius: 6px;
    padding: 10px 12px;
  }}

  .gates-title {{
    font-size: 12px;
    font-weight: 700;
    color: #f87171;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 4px;
  }}

  .gate-check-item {{
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 12px;
    color: #cbd5e1;
    margin-bottom: 6px;
    cursor: pointer;
  }}

  .gate-check-item input {{
    margin-top: 3px;
  }}

  .gate-fail-alert {{
    display: none;
    background: #dc2626;
    color: #fff;
    font-size: 12px;
    font-weight: 700;
    padding: 6px 10px;
    border-radius: 4px;
    margin-top: 6px;
    text-align: center;
  }}

  .gate-fail-alert.active {{
    display: block;
  }}

  /* Comment Area */
  .comment-group {{
    display: flex;
    flex-direction: column;
    gap: 4px;
  }}

  .comment-group label {{
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
  }}

  .comment-area {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: #fff;
    padding: 8px 10px;
    font-size: 12px;
    font-family: var(--font-stack);
    height: 70px;
    resize: vertical;
    outline: none;
  }}

  .comment-area:focus {{
    border-color: var(--accent-blue);
  }}

  /* Card Action Buttons */
  .card-actions {{
    display: flex;
    gap: 8px;
    margin-top: 4px;
  }}

  .card-actions .btn {{
    flex: 1;
    justify-content: center;
  }}

  /* Modal Viewer */
  .modal-overlay {{
    display: none;
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.85);
    z-index: 2000;
    justify-content: center;
    align-items: center;
    padding: 20px;
  }}

  .modal-overlay.active {{
    display: flex;
  }}

  .modal-content {{
    max-width: 95%;
    max-height: 95%;
    background: #111;
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: auto;
    position: relative;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.8);
  }}

  .modal-content img {{
    max-width: 100%;
    display: block;
  }}

  .modal-close-btn {{
    position: absolute;
    top: 12px;
    right: 12px;
    background: rgba(0, 0, 0, 0.7);
    border: 1px solid #444;
    color: #fff;
    font-size: 16px;
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
  }}

  /* Toast Notification */
  .toast {{
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--accent-blue);
    color: #fff;
    padding: 10px 18px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
    z-index: 3000;
    opacity: 0;
    transform: translateY(10px);
    transition: all 0.2s ease;
    pointer-events: none;
  }}

  .toast.show {{
    opacity: 1;
    transform: translateY(0);
  }}
</style>
</head>
<body>

<!-- Sticky Header -->
<header class="sticky-top-bar">
  <div class="header-main-row">
    <div class="header-title-group">
      <span class="header-title">상세페이지 AI 사람 검수 킷</span>
      <span class="pilot-badge">{pilot_id}</span>
      <span class="tag tag-category">cma_real_v1 (6건)</span>
    </div>

    <div class="reviewer-controls">
      <label for="reviewerRole">검수 역할:</label>
      <select id="reviewerRole" class="reviewer-select" onchange="onReviewerRoleChange()">
        <option value="검수자A" selected>검수자 A</option>
        <option value="검수자B">검수자 B</option>
        <option value="합의">합의 (Consensus)</option>
      </select>
      <label for="reviewerName">이름:</label>
      <input type="text" id="reviewerName" class="reviewer-input" placeholder="검수자 성명" oninput="saveReviewerMeta()">
      <span id="progressBadge" class="tag tag-layout">완료: 0 / 6건</span>
    </div>

    <div class="header-actions">
      <button type="button" class="btn" onclick="toggleGuidelines()">📋 판정 기준 / P0 가이드</button>
      <button type="button" class="btn btn-primary" onclick="copyAllCsvRows()">💾 전체 6건 CSV 복사</button>
      <button type="button" class="btn btn-danger" onclick="confirmResetAll()">초기화</button>
    </div>
  </div>

  <!-- Case Nav Pills -->
  <div class="case-nav-row" id="caseNavRow">
    <!-- Rendered dynamically -->
  </div>

  <!-- Collapsible Guidelines Box -->
  <div class="guidelines-wrapper" id="guidelinesWrapper">
    <button type="button" class="guidelines-toggle" onclick="toggleGuidelines()">
      <span>📘 4대 축 판정 기준 및 P0/P1 배포 차단 5대 원칙 (클릭하여 접기/펼치기)</span>
      <span id="guidelinesToggleIcon">▼</span>
    </button>
    <div class="guidelines-content" id="guidelinesContent">
      <div class="guidelines-grid">
        <div class="guide-box">
          <h4>1. 사실성 (Factuality) <span class="tag tag-category">목표 ≥4.0</span></h4>
          <div class="guide-score-row"><span class="guide-score-badge badge-1">1점</span> 입력에 없는 가격·배송·관리법 날조, 원본과 정반대 서술, 허위 인증·효능</div>
          <div class="guide-score-row"><span class="guide-score-badge badge-3">3점</span> 시각적 불확실한 요소 단정, 비시각 출처와 시각 관찰 모호 혼재, 30% 이상 수정 필요</div>
          <div class="guide-score-row"><span class="guide-score-badge badge-5">5점</span> 100% 원본 입증, 날조 전무, 비시각/시각 사실 엄격 구분, 보수적 서술</div>
        </div>

        <div class="guide-box">
          <h4>2. 명료성 (Clarity) <span class="tag tag-category">목표 ≥4.0</span></h4>
          <div class="guide-score-row"><span class="guide-score-badge badge-1">1점</span> 비문 난무, 기계 번역투, 3회 이상 단어 중복, JSON/HTML 노출</div>
          <div class="guide-score-row"><span class="guide-score-badge badge-3">3점</span> 대략적 제품은 파악되나 섹션 간 논리 어색, 만연체, 주의사항 스펙 불명확</div>
          <div class="guide-score-row"><span class="guide-score-badge badge-5">5점</span> 일목요연하고 리듬감 있는 문장, 헤드라인/본문 위계 완벽, 3초 내 이해 가능</div>
        </div>

        <div class="guide-box">
          <h4>3. 상품성 (Marketability) <span class="tag tag-category">목표 ≥4.0</span></h4>
          <div class="guide-score-row"><span class="guide-score-badge badge-1">1점</span> 상업적 가치 전무, 박물관 도록 설명문 복사 수준, 구매 욕구 저해</div>
          <div class="guide-score-row"><span class="guide-score-badge badge-3">3점</span> 기본 설명은 있으나 타깃층 및 인테리어/선물/실사용 제안 모호, MD 보강 필요</div>
          <div class="guide-score-row"><span class="guide-score-badge badge-5">5점</span> 과장 없이 고유 가치·스토리 전달, 신뢰감과 매력적 제안 조화, 즉시 판매 가능</div>
        </div>

        <div class="guide-box">
          <h4>4. 시각 품질 (Visual Quality) <span class="tag tag-category">목표 ≥4.0</span></h4>
          <div class="guide-score-row"><span class="guide-score-badge badge-1">1점</span> 이미지 깨짐/클리핑, 텍스트 겹침, 생성 컷에서 제품 일그러짐</div>
          <div class="guide-score-row"><span class="guide-score-badge badge-3">3점</span> 레이아웃 붕괴는 없으나 여백 어색, 생성 라이프스타일 컷의 광원/원근 이질적</div>
          <div class="guide-score-row"><span class="guide-score-badge badge-5">5점</span> 전문 디자이너 수준 조판, 여백, 타이포 위계, 원본 디테일 강조 및 자연스러운 연출</div>
        </div>
      </div>

      <div class="gate-box">
        <h4>⚠️ P0/P1 배포 차단 조건 5가지 (단 1건이라도 적발 시 평균 점수와 무관하게 즉시 FAIL)</h4>
        <ul class="gate-list">
          <li><strong>1. 미확인 법적/안전성 주장:</strong> 증빙 없는 친환경, 유기농, 인체무해, 항균, 의료효능, 미검증 식기류 식기 사용 가능 단정.</li>
          <li><strong>2. 허위 진품성·문화재 지위 날조:</strong> 공인되지 않은 인간문화재, 명장, 국가 지정 유물 지위 부여, "공식 인증 진품" 과장.</li>
          <li><strong>3. 거절 자산(REJECTED) 누출:</strong> 렌더러나 검증 단계에서 탈락한 결함 자산이 최종 캔버스에 유입된 경우.</li>
          <li><strong>4. 원본 제품의 임의적 형태 왜곡:</strong> 원본 사진의 비율 왜곡, 색상 변조, 주요 장식이나 각인의 무단 삭제/변형.</li>
          <li><strong>5. AI 생성 자산 미표시:</strong> AI 연출 컷(lifestyle, detail-02~05)에 AI 생성 자산 표시(product_generated)가 누락되어 실물로 오인될 위험이 있는 경우.</li>
        </ul>
      </div>
    </div>
  </div>
</header>

<!-- Main Case List -->
<main class="container">
""" + _render_cases_html(data["cases"]) + """
</main>

<!-- Image Modal Viewer -->
<div id="imageModal" class="modal-overlay" onclick="closeImageModal()">
  <div class="modal-content" onclick="event.stopPropagation()">
    <button type="button" class="modal-close-btn" onclick="closeImageModal()">✕ 닫기 (Esc)</button>
    <img id="modalImg" src="" alt="확대 이미지">
  </div>
</div>

<!-- Toast Feedback -->
<div id="toast" class="toast">클립보드에 복사되었습니다.</div>

<!-- Client Script & Inlined Data -->
<script>
  const REVIEW_CASES = """ + cases_json + """;
  const REVIEW_COLUMNS = """ + columns_json + """;
  const STORAGE_KEY_PREFIX = "team3_review_""" + escape(data["pilot_id"]).replace("-", "_") + """_";

  let currentRole = "검수자A";
  let reviewerName = "";
  let reviewState = {};

  function init() {
    loadReviewerMeta();
    loadAllReviewState();
    renderCaseNav();
    updateAllCardsFromState();
    updateProgress();
  }

  function getStorageKey() {
    return STORAGE_KEY_PREFIX + currentRole;
  }

  function loadReviewerMeta() {
    const savedRole = localStorage.getItem(STORAGE_KEY_PREFIX + "meta_role");
    if (savedRole) {
      currentRole = savedRole;
      document.getElementById("reviewerRole").value = savedRole;
    }
    const savedName = localStorage.getItem(STORAGE_KEY_PREFIX + "meta_name");
    if (savedName) {
      reviewerName = savedName;
      document.getElementById("reviewerName").value = savedName;
    }
  }

  function saveReviewerMeta() {
    reviewerName = document.getElementById("reviewerName").value.trim();
    localStorage.setItem(STORAGE_KEY_PREFIX + "meta_name", reviewerName);
  }

  function onReviewerRoleChange() {
    currentRole = document.getElementById("reviewerRole").value;
    localStorage.setItem(STORAGE_KEY_PREFIX + "meta_role", currentRole);
    loadAllReviewState();
    updateAllCardsFromState();
    updateProgress();
    showToast("검수 역할이 '" + currentRole + "'(으)로 변경되었습니다.");
  }

  function loadAllReviewState() {
    const raw = localStorage.getItem(getStorageKey());
    if (raw) {
      try {
        reviewState = JSON.parse(raw);
      } catch (e) {
        reviewState = {};
      }
    } else {
      reviewState = {};
    }
  }

  function saveAllReviewState() {
    localStorage.setItem(getStorageKey(), JSON.stringify(reviewState));
    updateProgress();
  }

  function getCaseState(caseId) {
    if (!reviewState[caseId]) {
      reviewState[caseId] = {
        factuality: "",
        clarity: "",
        marketability: "",
        visual: "",
        comment: "",
        gates: []
      };
    }
    return reviewState[caseId];
  }

  function updateAllCardsFromState() {
    REVIEW_CASES.forEach(c => {
      const state = getCaseState(c.case_id);
      ["factuality", "clarity", "marketability", "visual"].forEach(axis => {
        const val = state[axis] || "";
        const radios = document.getElementsByName(axis + "_" + c.case_id);
        radios.forEach(r => {
          r.checked = (r.value === val);
          const parent = r.closest(".score-option-label");
          if (parent) {
            if (r.value === val) {
              parent.classList.add("checked");
            } else {
              parent.classList.remove("checked");
            }
          }
        });
      });

      const commentEl = document.getElementById("comment_" + c.case_id);
      if (commentEl) {
        commentEl.value = state.comment || "";
      }

      for (let g = 1; g <= 5; g++) {
        const checkEl = document.getElementById("gate_" + g + "_" + c.case_id);
        if (checkEl) {
          checkEl.checked = (state.gates || []).includes(g);
        }
      }

      updateCardStatus(c.case_id);
    });
  }

  function onScoreChange(caseId, axis, score) {
    const state = getCaseState(caseId);
    state[axis] = score;

    const radios = document.getElementsByName(axis + "_" + caseId);
    radios.forEach(r => {
      const parent = r.closest(".score-option-label");
      if (parent) {
        if (r.value === score) {
          parent.classList.add("checked");
        } else {
          parent.classList.remove("checked");
        }
      }
    });

    saveAllReviewState();
    updateCardStatus(caseId);
  }

  function onGateChange(caseId, gateNum, isChecked) {
    const state = getCaseState(caseId);
    state.gates = state.gates || [];
    if (isChecked) {
      if (!state.gates.includes(gateNum)) state.gates.push(gateNum);
    } else {
      state.gates = state.gates.filter(g => g !== gateNum);
    }
    saveAllReviewState();
    updateCardStatus(caseId);
  }

  function onCommentChange(caseId, text) {
    const state = getCaseState(caseId);
    state.comment = text;
    saveAllReviewState();
  }

  function updateCardStatus(caseId) {
    const state = getCaseState(caseId);
    const badgeEl = document.getElementById("cardStatus_" + caseId);
    const navPillStatus = document.getElementById("navStatus_" + caseId);
    const gateAlertEl = document.getElementById("gateAlert_" + caseId);

    const hasGateFail = state.gates && state.gates.length > 0;
    if (gateAlertEl) {
      if (hasGateFail) {
        gateAlertEl.classList.add("active");
      } else {
        gateAlertEl.classList.remove("active");
      }
    }

    const isFullyScored = state.factuality && state.clarity && state.marketability && state.visual;

    if (hasGateFail) {
      if (badgeEl) {
        badgeEl.textContent = "🚨 [FAIL] P0/P1 위반";
        badgeEl.className = "tag badge-1";
      }
      if (navPillStatus) {
        navPillStatus.className = "nav-pill-status fail";
      }
    } else if (isFullyScored) {
      const avg = ((parseInt(state.factuality) + parseInt(state.clarity) + parseInt(state.marketability) + parseInt(state.visual)) / 4).toFixed(1);
      if (badgeEl) {
        badgeEl.textContent = "✅ 완료 (" + avg + "점)";
        badgeEl.className = "tag badge-5";
      }
      if (navPillStatus) {
        navPillStatus.className = "nav-pill-status done";
      }
    } else {
      if (badgeEl) {
        badgeEl.textContent = "미채점";
        badgeEl.className = "tag tag-general";
      }
      if (navPillStatus) {
        navPillStatus.className = "nav-pill-status";
      }
    }

    updateProgress();
  }

  function updateProgress() {
    let doneCount = 0;
    REVIEW_CASES.forEach(c => {
      const s = getCaseState(c.case_id);
      if (s.factuality && s.clarity && s.marketability && s.visual) {
        doneCount++;
      }
    });
    const badge = document.getElementById("progressBadge");
    if (badge) {
      badge.textContent = "채점 완료: " + doneCount + " / " + REVIEW_CASES.length + "건";
    }
  }

  function renderCaseNav() {
    const navRow = document.getElementById("caseNavRow");
    navRow.innerHTML = "";
    REVIEW_CASES.forEach((c, idx) => {
      const pill = document.createElement("a");
      pill.href = "#case_" + c.case_id;
      pill.className = "nav-pill";
      pill.innerHTML = `
        <span class="nav-pill-status" id="navStatus_${c.case_id}"></span>
        <span>#${idx + 1} ${c.category} (${c.product_type})</span>
      `;
      navRow.appendChild(pill);
    });
  }

  function toggleGuidelines() {
    const content = document.getElementById("guidelinesContent");
    const icon = document.getElementById("guidelinesToggleIcon");
    if (content.classList.contains("open")) {
      content.classList.remove("open");
      icon.textContent = "▼";
    } else {
      content.classList.add("open");
      icon.textContent = "▲";
    }
  }

  function escapeCsvCell(text) {
    if (text === null || text === undefined) return "";
    const str = String(text);
    const q = String.fromCharCode(34);
    if (str.indexOf(",") !== -1 || str.indexOf(q) !== -1 || str.indexOf("\\n") !== -1 || str.indexOf("\\r") !== -1) {
      return q + str.split(q).join(q + q) + q;
    }
    return str;
  }

  function generateCsvRow(caseMeta) {
    const s = getCaseState(caseMeta.case_id);
    let fullComment = s.comment || "";
    if (s.gates && s.gates.length > 0) {
      const gateLabels = [
        "1.미확인법적안전", "2.허위진품성", "3.거절자산누출", "4.원본형태왜곡", "5.참고라벨누락"
      ];
      const violated = s.gates.map(g => gateLabels[g - 1]).join(";");
      fullComment = "[P0/P1 FAIL: " + violated + "] " + fullComment;
    }

    const rowObj = {};
    REVIEW_COLUMNS.forEach(col => rowObj[col] = "");

    rowObj["case_id"] = caseMeta.case_id;
    rowObj["category"] = caseMeta.category;
    rowObj["asset_id"] = caseMeta.asset_id;
    rowObj["입력 이미지 경로"] = caseMeta.input_image_path;
    rowObj["산출물 경로"] = caseMeta.output_dir;
    rowObj["실행 성공 여부"] = caseMeta.success ? "성공" : "실패";
    rowObj["에러 메시지"] = "";

    if (currentRole === "검수자A") {
      rowObj["검수자A_사실성"] = s.factuality || "";
      rowObj["검수자A_명료성"] = s.clarity || "";
      rowObj["검수자A_상품성"] = s.marketability || "";
      rowObj["검수자A_시각품질"] = s.visual || "";
      rowObj["검수자A_코멘트"] = fullComment;
    } else if (currentRole === "검수자B") {
      rowObj["검수자B_사실성"] = s.factuality || "";
      rowObj["검수자B_명료성"] = s.clarity || "";
      rowObj["검수자B_상품성"] = s.marketability || "";
      rowObj["검수자B_시각품질"] = s.visual || "";
      rowObj["검수자B_코멘트"] = fullComment;
    } else if (currentRole === "합의") {
      rowObj["합의_사실성"] = s.factuality || "";
      rowObj["합의_명료성"] = s.clarity || "";
      rowObj["합의_상품성"] = s.marketability || "";
      rowObj["합의_시각품질"] = s.visual || "";
      rowObj["합의_메모"] = fullComment;
    }

    return REVIEW_COLUMNS.map(col => escapeCsvCell(rowObj[col])).join(",");
  }

  function copySingleCaseCsv(caseId) {
    const c = REVIEW_CASES.find(item => item.case_id === caseId);
    if (!c) return;
    const row = generateCsvRow(c);
    navigator.clipboard.writeText(row).then(() => {
      showToast(caseId + " (" + currentRole + " 열) CSV 행이 복사되었습니다.");
    }).catch(err => {
      alert("복사 실패: " + err);
    });
  }

  function copyAllCsvRows() {
    const rows = REVIEW_CASES.map(c => generateCsvRow(c));
    const fullText = rows.join("\\n");
    navigator.clipboard.writeText(fullText).then(() => {
      showToast("전체 6건 (" + currentRole + " 기준) CSV 데이터가 복사되었습니다.");
    }).catch(err => {
      alert("복사 실패: " + err);
    });
  }

  function resetCase(caseId) {
    if (!confirm("케이스 " + caseId + " 의 현재 검수자(" + currentRole + ") 입력을 초기화하시겠습니까?")) return;
    reviewState[caseId] = {
      factuality: "",
      clarity: "",
      marketability: "",
      visual: "",
      comment: "",
      gates: []
    };
    saveAllReviewState();
    updateAllCardsFromState();
    showToast(caseId + " 입력이 초기화되었습니다.");
  }

  function confirmResetAll() {
    if (!confirm("현재 검수 역할('" + currentRole + "')의 6건 전체 입력을 모두 초기화하시겠습니까?")) return;
    reviewState = {};
    saveAllReviewState();
    updateAllCardsFromState();
    showToast("'" + currentRole + "' 입력이 초기화되었습니다.");
  }

  function openImageModal(imgSrc) {
    const modal = document.getElementById("imageModal");
    const modalImg = document.getElementById("modalImg");
    modalImg.src = imgSrc;
    modal.classList.add("active");
  }

  function closeImageModal() {
    const modal = document.getElementById("imageModal");
    modal.classList.remove("active");
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeImageModal();
    }
  });

  function showToast(msg) {
    const toast = document.getElementById("toast");
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => {
      toast.classList.remove("show");
    }, 2800);
  }

  window.addEventListener("DOMContentLoaded", init);
</script>

</body>
</html>
"""


def _render_cases_html(cases: list[dict[str, Any]]) -> str:
    """Render the HTML markup for each case card."""
    cards_html = []
    for idx, c in enumerate(cases, 1):
        cid = escape(c["case_id"])
        category = escape(c["category"])
        product_type = escape(c["product_type"])
        display_name = escape(c["display_name"])
        is_craft = c["is_traditional_craft"]
        craft_type = escape(c["craft_type"])
        layout_id = escape(c["layout_id"])
        confidence = f"{c['classification_confidence']:.2f}"
        reason = escape(c["classification_reason"])
        summary = escape(c["summary"])

        craft_tag = f'<span class="tag tag-craft">전통공예 ({craft_type})</span>' if is_craft else '<span class="tag tag-general">일반 공산품</span>'

        # Photos gallery
        photos_cards = []
        for p in c["photos"]:
            p_rel = escape(p["rel_path"])
            role_id = escape(p["role_id"])
            p_label = escape(p["label"])
            is_gen = p["is_generated"]
            cls_name = "generated" if is_gen else "verified"
            badge_text = "AI 생성" if is_gen else "원본 보존"

            photos_cards.append(f"""
              <div class="photo-card {cls_name}" onclick="openImageModal('{p_rel}')" title="클릭하여 원본 크기 확대">
                <div class="photo-thumb-wrap">
                  <img src="{p_rel}" alt="{role_id}" loading="lazy">
                </div>
                <div class="photo-meta">
                  <div class="photo-role">{role_id}</div>
                  <span class="photo-badge {cls_name}">{badge_text}</span>
                </div>
              </div>
            """)
        photos_html = "\n".join(photos_cards)

        # Page Plan Blocks
        blocks_html = []
        for b in c["page_plan"]:
            b_sec = escape(b.get("section_id", ""))
            b_type = escape(b.get("block_type", ""))
            b_eyebrow = escape(b.get("eyebrow", ""))
            b_title = escape(b.get("title", ""))
            b_body = escape(b.get("body", ""))

            items_markup = ""
            if b.get("items"):
                items_list = []
                for it in b["items"]:
                    it_label = escape(it.get("label", ""))
                    it_val = escape(it.get("value", ""))
                    it_desc = escape(it.get("description", ""))
                    it_ev = escape(it.get("evidence", ""))
                    items_list.append(f"""
                      <div class="block-item">
                        <span class="item-label">{it_label}:</span>
                        <span class="item-val">{it_val} ({it_desc})</span>
                        <span class="item-evidence">{it_ev}</span>
                      </div>
                    """)
                items_markup = f'<div class="block-items">{"".join(items_list)}</div>'

            eyebrow_markup = f'<div class="block-eyebrow">{b_eyebrow}</div>' if b_eyebrow else ""
            blocks_html.append(f"""
              <div class="block-card">
                <div class="block-header">
                  <span class="block-type-badge">{b_sec} ({b_type})</span>
                </div>
                {eyebrow_markup}
                <div class="block-title">{b_title}</div>
                <div class="block-body">{b_body}</div>
                {items_markup}
              </div>
            """)
        copy_stream_html = "\n".join(blocks_html)

        rel_orig = escape(c["rel_input_image"])
        rel_detail = escape(c["rel_detail_page"])

        cards_html.append(f"""
<article class="case-card" id="case_{cid}">
  <div class="case-header">
    <div class="case-title-area">
      <span class="case-index">#{idx}</span>
      <span class="case-id">{cid}</span>
      <span class="tag tag-category">{category}</span>
      <span style="font-weight:700; color:#fff;">{display_name}</span>
      <span style="color:var(--text-secondary); font-size:13px;">({product_type})</span>
      {craft_tag}
      <span class="tag tag-layout">{layout_id}</span>
      <span class="tag tag-confidence">신뢰도: {confidence}</span>
    </div>
    <div style="display:flex; align-items:center; gap:8px;">
      <span id="cardStatus_{cid}" class="tag tag-general">미채점</span>
      <button type="button" class="btn" onclick="copySingleCaseCsv('{cid}')">📋 이 행 복사</button>
    </div>
  </div>

  <div class="case-grid">
    <!-- Column 1: Images -->
    <div class="col-images">
      <div class="image-compare-box">
        <div class="img-frame">
          <div class="img-frame-label">
            <span>📸 원본 입력 이미지</span>
            <button type="button" class="btn" style="padding:1px 6px; font-size:11px;" onclick="openImageModal('{rel_orig}')">확대</button>
          </div>
          <div class="orig-img-container" onclick="openImageModal('{rel_orig}')" title="클릭하여 원본 확대">
            <img src="{rel_orig}" alt="원본 이미지">
          </div>
        </div>

        <div class="img-frame">
          <div class="img-frame-label">
            <span>📄 상세페이지 (스크롤)</span>
            <button type="button" class="btn" style="padding:1px 6px; font-size:11px;" onclick="openImageModal('{rel_detail}')">전체확대</button>
          </div>
          <div class="detail-scroll-container" onclick="openImageModal('{rel_detail}')" title="클릭하여 원본 크기 확대">
            <img src="{rel_detail}" alt="최종 상세페이지">
          </div>
        </div>
      </div>

      <!-- Photos 8 Gallery -->
      <div class="photos-gallery-box">
        <div class="photos-gallery-title">
          <span>🖼️ 자산 8장 (초록: 원본보존/크롭 | 보라: AI 연출 참고컷)</span>
          <span style="color:var(--text-muted); font-size:11px;">P0 #5 AI 생성 표시 검수</span>
        </div>
        <div class="photos-grid">
          {photos_html}
        </div>
      </div>
    </div>

    <!-- Column 2: Content & Copy -->
    <div class="col-copy">
      <div class="meta-summary-box">
        <div class="meta-field">
          <span class="meta-label">판정 사유:</span>
          <span class="meta-val">{reason}</span>
        </div>
        <div class="meta-field">
          <span class="meta-label">요약:</span>
          <span class="meta-val">{summary}</span>
        </div>
      </div>

      <div class="copy-stream-box">
        <div class="copy-stream-title">
          <span>📝 카피 전문 (page_plan {len(c["page_plan"])}개 블록)</span>
          <span style="font-size:11px; color:var(--text-muted);">사실성·명료성 원문 대조용</span>
        </div>
        {copy_stream_html}
      </div>
    </div>

    <!-- Column 3: Scoring & Gates -->
    <div class="col-scoring">
      <div class="scoring-header">
        <h3>평가 및 채점</h3>
        <span style="font-size:12px; color:var(--text-muted);">1점(불가) ~ 5점(탁월)</span>
      </div>

      <!-- 사실성 -->
      <div class="score-group">
        <div class="score-label">
          <span>1. 사실성 (Factuality)</span>
        </div>
        <div class="score-options">
          {_render_score_options(cid, "factuality")}
        </div>
      </div>

      <!-- 명료성 -->
      <div class="score-group">
        <div class="score-label">
          <span>2. 명료성 (Clarity)</span>
        </div>
        <div class="score-options">
          {_render_score_options(cid, "clarity")}
        </div>
      </div>

      <!-- 상품성 -->
      <div class="score-group">
        <div class="score-label">
          <span>3. 상품성 (Marketability)</span>
        </div>
        <div class="score-options">
          {_render_score_options(cid, "marketability")}
        </div>
      </div>

      <!-- 시각품질 -->
      <div class="score-group">
        <div class="score-label">
          <span>4. 시각품질 (Visual Quality)</span>
        </div>
        <div class="score-options">
          {_render_score_options(cid, "visual")}
        </div>
      </div>

      <!-- P0/P1 Gates Checklist -->
      <div class="gates-section">
        <div class="gates-title">
          <span>⚠️ P0/P1 배포 차단 검사 (체크 시 FAIL)</span>
        </div>
        <label class="gate-check-item">
          <input type="checkbox" id="gate_1_{cid}" onchange="onGateChange('{cid}', 1, this.checked)">
          <span>1. 미확인 법적·안전성·식기안전 주장</span>
        </label>
        <label class="gate-check-item">
          <input type="checkbox" id="gate_2_{cid}" onchange="onGateChange('{cid}', 2, this.checked)">
          <span>2. 허위 진품성·문화재 지위 날조</span>
        </label>
        <label class="gate-check-item">
          <input type="checkbox" id="gate_3_{cid}" onchange="onGateChange('{cid}', 3, this.checked)">
          <span>3. 거절 자산(REJECTED) 유출</span>
        </label>
        <label class="gate-check-item">
          <input type="checkbox" id="gate_4_{cid}" onchange="onGateChange('{cid}', 4, this.checked)">
          <span>4. 원본 제품 형태·색상·비율 왜곡</span>
        </label>
        <label class="gate-check-item">
          <input type="checkbox" id="gate_5_{cid}" onchange="onGateChange('{cid}', 5, this.checked)">
          <span>5. 연출 컷 AI 생성 미표시</span>
        </label>

        <div id="gateAlert_{cid}" class="gate-fail-alert">
          🚨 배포 차단 조건(P0/P1) 위반 — 릴리즈 불가(FAIL)
        </div>
      </div>

      <!-- Comment -->
      <div class="comment-group">
        <label for="comment_{cid}">검수 코멘트 (3점 이하 시 구체적 결함 사유 필수):</label>
        <textarea id="comment_{cid}" class="comment-area" placeholder="결함 사유, 수정 필요 사항 또는 특이사항 기록" oninput="onCommentChange('{cid}', this.value)"></textarea>
      </div>

      <!-- Case Actions -->
      <div class="card-actions">
        <button type="button" class="btn btn-primary" onclick="copySingleCaseCsv('{cid}')">📋 CSV 행 복사</button>
        <button type="button" class="btn btn-danger" onclick="resetCase('{cid}')">초기화</button>
      </div>
    </div>
  </div>
</article>
""")
    return "\n".join(cards_html)


def _render_score_options(case_id: str, axis: str) -> str:
    """Render 1..5 radio option buttons for a scoring axis."""
    subtexts = ["사용불가", "중대수정", "상당수정", "경미수정", "수정불필요"]
    options = []
    for score in range(1, 6):
        st = subtexts[score - 1]
        options.append(f"""
          <label class="score-option-label" id="lbl_{axis}_{case_id}_{score}">
            <input type="radio" name="{axis}_{case_id}" value="{score}" onchange="onScoreChange('{case_id}', '{axis}', '{score}')">
            <span>{score}점</span>
            <span class="score-subtext">{st}</span>
          </label>
        """)
    return "\n".join(options)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pilot-dir",
        type=Path,
        default=Path("generated/evaluation/pilot-20260909-224737"),
        help="Path to pilot evaluation directory containing run_index.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to output HTML file (defaults to <pilot-dir>/review.html)",
    )

    args = parser.parse_args()
    pilot_dir = args.pilot_dir.resolve()
    output_path = args.output.resolve() if args.output else pilot_dir / "review.html"

    print(f"Loading pilot data from {pilot_dir}...")
    data = load_pilot_data(pilot_dir)
    print(f"Loaded {len(data['cases'])} cases from {pilot_dir.name}.")

    print("Generating self-contained HTML...")
    html_content = generate_html(data)

    output_path.write_text(html_content, encoding="utf-8")
    print(f"Successfully generated human review page: {output_path}")
    print(f"Size: {len(html_content):,} characters ({output_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
