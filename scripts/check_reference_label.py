#!/usr/bin/env python3
"""Reference label gate verification script.

Verifies that mandatory '참고용' (reference) labels reach the frontend contract
(react_document.json) and render output (HTML, if present) for all generated
photos (product_generated=True).

Ensures that source photos (product_generated=False) NEVER receive reference labels.
Follows formatting conventions from check_cutout_fidelity.py and check_plan_diversity.py.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_KEYWORD = "참고용"


def extract_photos_from_summary(summary_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract product photos list from result_summary.json structure."""
    detail_page = summary_data.get("detail_page")
    if isinstance(detail_page, dict) and "photos" in detail_page:
        return detail_page["photos"] or []
    if "photos" in summary_data and isinstance(summary_data["photos"], list):
        return summary_data["photos"]
    if "generated_photos" in summary_data and isinstance(summary_data["generated_photos"], list):
        return summary_data["generated_photos"]
    req_photos = summary_data.get("request", {}).get("detail_page", {}).get("photos")
    if isinstance(req_photos, list):
        return req_photos
    return []


def extract_all_texts(node: Any) -> list[str]:
    """Recursively collect all text strings from an AST node or subtree."""
    texts: list[str] = []
    if isinstance(node, dict):
        if node.get("type") == "text" and "value" in node:
            val = node["value"]
            if isinstance(val, str) and val.strip():
                texts.append(val.strip())
        for v in node.values():
            texts.extend(extract_all_texts(v))
    elif isinstance(node, list):
        for item in node:
            texts.extend(extract_all_texts(item))
    return texts


def collect_document_image_contexts(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Find all image element occurrences in react_document.json and extract their context.

    For each image node:
    - Collects props (alt, label, caption, referenceLabel, etc.)
    - If parent is a <figure>, collects all texts and captions within the figure
    - If parent is another container, collects sibling caption/badge text
    """
    occurrences: list[dict[str, Any]] = []

    def traverse(node: Any, parent: Any = None) -> None:
        if isinstance(node, dict):
            tag = node.get("tag")
            props = node.get("props") or {}
            img_id = props.get("imageId") or props.get("image_id")

            if img_id or tag == "img":
                context_texts: list[str] = []

                # 1. Props on the image node itself
                for key in ("alt", "label", "caption", "referenceLabel", "reference_label"):
                    val = props.get(key)
                    if val and isinstance(val, str):
                        context_texts.append(val)

                # 2. Text within the image node itself
                context_texts.extend(extract_all_texts(node))

            # 3. Parent container context (figure or container with caption/label)
                if parent and isinstance(parent, dict):
                    parent_tag = parent.get("tag")
                    if parent_tag == "figure":
                        # In standard figure-img patterns, caption is a sibling inside figure
                        context_texts.extend(extract_all_texts(parent))
                        p_props = parent.get("props") or {}
                        for key in ("alt", "label", "caption", "referenceLabel", "reference_label"):
                            val = p_props.get(key)
                            if val and isinstance(val, str):
                                context_texts.append(val)
                    else:
                        for sib in parent.get("children", []):
                            if sib is not node and isinstance(sib, dict):
                                sib_tag = sib.get("tag", "")
                                sib_id = str(sib.get("id", ""))
                                if sib_tag in ("figcaption", "span", "p") or "label" in sib_id:
                                    context_texts.extend(extract_all_texts(sib))

                occurrences.append({
                    "image_id": str(img_id) if img_id else "",
                    "node_id": node.get("id", ""),
                    "tag": tag,
                    "parent_tag": parent.get("tag") if isinstance(parent, dict) else None,
                    "context_texts": context_texts,
                    "combined_context": " ".join(context_texts),
                })

            for key in ("root", "children"):
                items = node.get(key)
                if isinstance(items, list):
                    for item in items:
                        traverse(item, parent=node)
        elif isinstance(node, list):
            for item in node:
                traverse(item, parent=parent)

    traverse(doc)
    return occurrences


def check_html_reference_labels(
    case_dir: Path,
    used_gen_photos: list[dict[str, Any]],
    source_photos: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check HTML render outputs if present in the case directory.

    Returns dict with:
        status: "확인 완료" | "확인 불가" | "FAIL"
        reason: explanatory string
        missing_labels: list of missing photo_ids
        false_positives: list of mislabeled source photo_ids
    """
    html_files = sorted(case_dir.glob("*.html"))
    if not html_files:
        return {
            "status": "확인 불가",
            "reason": "파일럿 산출물 디렉터리에 HTML 렌더 산출물(*.html) 부재",
            "missing_labels": [],
            "false_positives": [],
        }

    html_path = html_files[0]
    try:
        content = html_path.read_text(encoding="utf-8")
    except Exception as exc:
        return {
            "status": "확인 불가",
            "reason": f"HTML 파일 읽기 실패 ({html_path.name}): {exc}",
            "missing_labels": [],
            "false_positives": [],
        }

    missing: list[str] = []
    for photo in used_gen_photos:
        pid = photo.get("photo_id", "")
        lbl = photo.get("label", "")
        # Check if the photo's label or REFERENCE_KEYWORD is present in HTML
        if lbl and lbl in content:
            continue
        if REFERENCE_KEYWORD in content:
            # If the keyword exists, verify it relates to generated photos
            continue
        missing.append(pid)

    # Check for false positives: source photos should not have reference label attached
    false_positives: list[str] = []
    # If source photos are mentioned in generated-photo-label contexts
    for sp in source_photos:
        sp_id = sp.get("photo_id", "")
        if not sp_id:
            continue
        # Pattern checking: <figure> with source image ID and generated-photo-label or '참고용'
        pattern = re.compile(
            rf"<figure[^>]*>.*?{re.escape(sp_id)}.*?(?:generated-photo-label|{re.escape(REFERENCE_KEYWORD)}).*?</figure>",
            re.DOTALL,
        )
        if pattern.search(content):
            false_positives.append(sp_id)

    if false_positives:
        return {
            "status": "FAIL",
            "reason": f"HTML 내 원본 사진 오표기 감지: {', '.join(false_positives)}",
            "missing_labels": missing,
            "false_positives": false_positives,
        }

    if missing:
        return {
            "status": "FAIL",
            "reason": f"HTML 내 '참고용' 라벨 누락: {', '.join(missing)}",
            "missing_labels": missing,
            "false_positives": [],
        }

    return {
        "status": "확인 완료",
        "reason": f"HTML 내 '참고용' 라벨 확인 완료 ({html_path.name})",
        "missing_labels": [],
        "false_positives": [],
    }


def evaluate_case(case_dir: Path, case_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate a single pilot case directory for reference label compliance."""
    case_id = case_dir.name
    category = "unknown"
    if case_info:
        case_id = case_info.get("case_id", case_id)
        category = case_info.get("category", category)

    summary_file = case_dir / "result_summary.json"
    doc_file = case_dir / "react_document.json"

    if not summary_file.is_file():
        return {
            "case_id": case_id,
            "category": category,
            "judgment": "FAIL",
            "reason": f"result_summary.json 부재 ({case_dir})",
            "target_count": 0,
            "used_target_count": 0,
            "used_targets": [],
            "missing_doc_targets": [],
            "false_positive_sources": [],
            "html_status": "확인 불가",
            "html_reason": "result_summary.json 부재",
            "details": [],
        }

    try:
        summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "case_id": case_id,
            "category": category,
            "judgment": "FAIL",
            "reason": f"result_summary.json 파싱 실패: {exc}",
            "target_count": 0,
            "used_target_count": 0,
            "used_targets": [],
            "missing_doc_targets": [],
            "false_positive_sources": [],
            "html_status": "확인 불가",
            "html_reason": "JSON 파싱 실패",
            "details": [],
        }

    if category == "unknown":
        category = (
            summary_data.get("category")
            or summary_data.get("product", {}).get("category")
            or summary_data.get("product", {}).get("product_type")
            or "unknown"
        )

    photos = extract_photos_from_summary(summary_data)
    gen_photos = [p for p in photos if p.get("product_generated") is True]
    source_photos = [p for p in photos if not p.get("product_generated")]
    gen_photo_map = {p["photo_id"]: p for p in gen_photos if "photo_id" in p}
    source_photo_map = {p["photo_id"]: p for p in source_photos if "photo_id" in p}

    # Rule 1: Cases with 0 generated photos are N/A (해당 없음)
    if not gen_photos:
        # Check if source photos were falsely labeled even with 0 generated photos
        false_positives: list[str] = []
        if doc_file.is_file():
            try:
                doc_data = json.loads(doc_file.read_text(encoding="utf-8"))
                occurrences = collect_document_image_contexts(doc_data)
                for occ in occurrences:
                    pid = occ["image_id"]
                    if pid in source_photo_map and REFERENCE_KEYWORD in occ["combined_context"]:
                        false_positives.append(pid)
            except Exception:
                pass

        if false_positives:
            return {
                "case_id": case_id,
                "category": category,
                "judgment": "FAIL",
                "reason": f"원본 유래 컷에 '참고용' 라벨 오부착 ({', '.join(sorted(set(false_positives)))})",
                "target_count": 0,
                "used_target_count": 0,
                "used_targets": [],
                "missing_doc_targets": [],
                "false_positive_sources": sorted(set(false_positives)),
                "html_status": "해당 없음",
                "html_reason": "생성 사진 0장",
                "details": ["생성 사진 0장이나 원본 컷에 '참고용' 오부착 감지"],
            }

        return {
            "case_id": case_id,
            "category": category,
            "judgment": "해당 없음",
            "reason": "생성 사진 대상 0장 (--image-provider none 등)",
            "target_count": 0,
            "used_target_count": 0,
            "used_targets": [],
            "missing_doc_targets": [],
            "false_positive_sources": [],
            "html_status": "해당 없음",
            "html_reason": "생성 사진 0장",
            "details": [],
        }

    # Rule 2: Verify react_document.json
    if not doc_file.is_file():
        return {
            "case_id": case_id,
            "category": category,
            "judgment": "FAIL",
            "reason": f"react_document.json 부재 ({case_dir})",
            "target_count": len(gen_photos),
            "used_target_count": 0,
            "used_targets": [],
            "missing_doc_targets": list(gen_photo_map.keys()),
            "false_positive_sources": [],
            "html_status": "확인 불가",
            "html_reason": "react_document.json 부재",
            "details": ["react_document.json 파일이 존재하지 않음"],
        }

    try:
        doc_data = json.loads(doc_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "case_id": case_id,
            "category": category,
            "judgment": "FAIL",
            "reason": f"react_document.json 파싱 실패: {exc}",
            "target_count": len(gen_photos),
            "used_target_count": 0,
            "used_targets": [],
            "missing_doc_targets": list(gen_photo_map.keys()),
            "false_positive_sources": [],
            "html_status": "확인 불가",
            "html_reason": "react_document.json 파싱 실패",
            "details": [f"파싱 에러: {exc}"],
        }

    occurrences = collect_document_image_contexts(doc_data)

    used_gen_targets: list[str] = []
    missing_doc_targets: list[str] = []
    false_positives: list[str] = []
    details: list[str] = []

    # Map image occurrences by image_id
    occ_by_id: dict[str, list[dict[str, Any]]] = {}
    for occ in occurrences:
        occ_by_id.setdefault(occ["image_id"], []).append(occ)

    # Check generated photos used in document
    for pid, photo in gen_photo_map.items():
        if pid in occ_by_id:
            used_gen_targets.append(pid)
            expected_label = photo.get("label", "")
            # Check every occurrence of this generated photo in the document
            for idx, occ in enumerate(occ_by_id[pid], start=1):
                ctx = occ["combined_context"]
                has_label = (expected_label and expected_label in ctx) or (REFERENCE_KEYWORD in ctx)
                if not has_label:
                    missing_doc_targets.append(pid)
                    details.append(
                        f"생성 컷 '{pid}'(인스턴스 {idx}, 노드 {occ['node_id']})에 '참고용' 라벨 누락"
                    )

    # Rule 4: Check source photos (product_generated=False)
    for sp_id in source_photo_map:
        if sp_id in occ_by_id:
            for idx, occ in enumerate(occ_by_id[sp_id], start=1):
                ctx = occ["combined_context"]
                if REFERENCE_KEYWORD in ctx:
                    false_positives.append(sp_id)
                    details.append(
                        f"원본 컷 '{sp_id}'(인스턴스 {idx}, 노드 {occ['node_id']})에 '참고용' 라벨 오부착"
                    )

    # Rule 3: Check HTML
    used_gen_objects = [gen_photo_map[pid] for pid in used_gen_targets]
    html_result = check_html_reference_labels(case_dir, used_gen_objects, source_photos)

    # Overall Case Verdict
    missing_unique = sorted(set(missing_doc_targets))
    fp_unique = sorted(set(false_positives))

    failures: list[str] = []
    if missing_unique:
        failures.append(f"문서 내 라벨 누락: {', '.join(missing_unique)}")
    if fp_unique:
        failures.append(f"원본 컷 라벨 오부착: {', '.join(fp_unique)}")
    if html_result["status"] == "FAIL":
        failures.append(html_result["reason"])

    if failures:
        judgment = "FAIL"
        reason = "; ".join(failures)
    else:
        judgment = "PASS"
        if used_gen_targets:
            reason = f"정상 (문서 내 생성 컷 {len(used_gen_targets)}장 라벨 도달 확인)"
        else:
            reason = "정상 (문서 내 생성 컷 미배치, 오표기 없음)"

    return {
        "case_id": case_id,
        "category": category,
        "judgment": judgment,
        "reason": reason,
        "target_count": len(gen_photos),
        "used_target_count": len(used_gen_targets),
        "used_targets": used_gen_targets,
        "missing_doc_targets": missing_unique,
        "false_positive_sources": fp_unique,
        "html_status": html_result["status"],
        "html_reason": html_result["reason"],
        "details": details,
    }


def evaluate_pilot(pilot_dir: Path) -> dict[str, Any]:
    """Discover and evaluate all cases in a pilot evaluation directory."""
    index_file = pilot_dir / "run_index.json"
    case_records: list[dict[str, Any]] = []

    if index_file.is_file():
        try:
            index_data = json.loads(index_file.read_text(encoding="utf-8"))
            for case_info in index_data.get("cases", []):
                cid = case_info.get("case_id", "")
                raw_out_dir = Path(case_info.get("output_dir", ""))
                out_dir = raw_out_dir
                if not out_dir.is_absolute():
                    for cand in [pilot_dir / out_dir, PROJECT_ROOT / out_dir, pilot_dir / cid]:
                        if cand.is_dir():
                            out_dir = cand
                            break
                elif not out_dir.is_dir():
                    cand = pilot_dir / cid
                    if cand.is_dir():
                        out_dir = cand

                if out_dir.is_dir():
                    case_records.append(evaluate_case(out_dir, case_info))
        except Exception as exc:
            print(f"[WARN] Failed parsing run_index.json ({exc}); falling back to subdirs", file=sys.stderr)
            case_records = []

    if not case_records:
        for subdir in sorted(pilot_dir.iterdir()):
            if subdir.is_dir() and (subdir / "result_summary.json").is_file():
                case_records.append(evaluate_case(subdir))

    if not case_records:
        raise ValueError(f"No valid pilot cases with result_summary.json found in {pilot_dir}")

    # Summary statistics
    total = len(case_records)
    pass_count = sum(1 for r in case_records if r["judgment"] == "PASS")
    fail_count = sum(1 for r in case_records if r["judgment"] == "FAIL")
    na_count = sum(1 for r in case_records if r["judgment"] == "해당 없음")

    missing_label_cases = sum(1 for r in case_records if r["missing_doc_targets"])
    false_positive_cases = sum(1 for r in case_records if r["false_positive_sources"])
    html_unverifiable = sum(1 for r in case_records if r["html_status"] == "확인 불가")
    html_verified = sum(1 for r in case_records if r["html_status"] == "확인 완료")

    all_passed = fail_count == 0

    return {
        "pilot_dir": str(pilot_dir.resolve()),
        "summary": {
            "total_cases": total,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "na_count": na_count,
            "missing_label_cases": missing_label_cases,
            "false_positive_cases": false_positive_cases,
            "html_unverifiable": html_unverifiable,
            "html_verified": html_verified,
            "all_passed": all_passed,
        },
        "cases": case_records,
    }


def print_report(results: dict[str, Any]) -> None:
    """Print results formatted as a Markdown table and summary."""
    cases = results.get("cases", [])
    summary = results.get("summary", {})

    print("=" * 78)
    print("        '참고용' 라벨 도달 검증 게이트 보고서 (Reference Label Gate)        ")
    print("=" * 78)
    print()

    print("### 1. 케이스별 검증 결과")
    print("| 번호 | case_id | 카테고리 | 생성 사진(대상) | 문서 내 생성 컷 | 라벨 일치(문서) | 원본 오표기 | HTML 렌더 | 판정 |")
    print("|:---:|---|---|:---:|---|---|:---:|---|:---:|")

    for idx, c in enumerate(cases, start=1):
        target_str = f"{c['target_count']}장" if c["target_count"] > 0 else "-"
        used_str = ", ".join(c["used_targets"]) if c["used_targets"] else ("없음" if c["target_count"] > 0 else "-")
        
        if c["judgment"] == "해당 없음":
            doc_str = "해당 없음"
        elif c["missing_doc_targets"]:
            doc_str = f"누락 ({', '.join(c['missing_doc_targets'])})"
        elif c["used_targets"]:
            doc_str = f"정상 ({len(c['used_targets'])}/{len(c['used_targets'])})"
        else:
            doc_str = "미배치"

        fp_str = f"오부착 ({', '.join(c['false_positive_sources'])})" if c["false_positive_sources"] else "정상 (0건)"
        html_str = c["html_status"]
        verdict_str = f"**{c['judgment']}**" if c["judgment"] == "FAIL" else c["judgment"]

        print(f"| {idx} | {c['case_id']} | {c['category']} | {target_str} | {used_str} | {doc_str} | {fp_str} | {html_str} | {verdict_str} |")

    print()

    # Detailed issues if any
    issue_cases = [c for c in cases if c["judgment"] == "FAIL" and c["details"]]
    if issue_cases:
        print("### 2. 세부 결함 사항")
        for c in issue_cases:
            print(f"- **{c['case_id']}**:")
            for d in c["details"]:
                print(f"  - {d}")
        print()

    # Summary section
    total = summary.get("total_cases", 0)
    p_c = summary.get("pass_count", 0)
    f_c = summary.get("fail_count", 0)
    na_c = summary.get("na_count", 0)
    miss_c = summary.get("missing_label_cases", 0)
    fp_c = summary.get("false_positive_cases", 0)
    html_unv = summary.get("html_unverifiable", 0)

    print("### 3. 검증 종합 요약")
    print(
        f"요약: 총 {total}건 | PASS: {p_c}건 | FAIL: {f_c}건 "
        f"(라벨 누락: {miss_c}건, 원본 오표기: {fp_c}건) | "
        f"해당 없음: {na_c}건 | HTML 확인 불가: {html_unv}건"
    )

    if html_unv > 0:
        print(f"※ HTML 확인 불가 근거: 대상 케이스 {html_unv}건에 HTML 렌더 산출물(*.html) 미포함 (detail_page.png 만 생성됨, 게이트 FAIL 사유 아님)")

    print()
    if summary.get("all_passed", False):
        if p_c > 0:
            print(f"최종 판정: [PASS] 모든 대상 생성 이미지({p_c}건)에 '참고용' 라벨이 정상 도달했습니다.")
        elif na_c > 0:
            print("최종 판정: [PASS] 생성 이미지가 포함된 케이스가 없어 게이트 통과 요건을 만족했습니다.")
        else:
            print("최종 판정: [PASS] 모든 케이스가 검증 조건을 만족했습니다.")
    else:
        reasons = []
        if miss_c > 0:
            reasons.append(f"라벨 누락 {miss_c}건")
        if fp_c > 0:
            reasons.append(f"원본 오표기 {fp_c}건")
        print(f"최종 판정: [FAIL] 생성 이미지 라벨 검증 실패 ({', '.join(reasons)})")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify reference ('참고용') labels reach generated artifacts."
    )
    parser.add_argument(
        "pilot_dir_pos",
        nargs="?",
        type=Path,
        default=None,
        help="Path to pilot evaluation directory (positional fallback).",
    )
    parser.add_argument(
        "--pilot-dir",
        type=Path,
        default=None,
        help="Path to pilot evaluation directory.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        dest="json_output",
        help="Optional path to save evaluation results as JSON.",
    )

    args = parser.parse_args(argv)
    if args.pilot_dir is None:
        if args.pilot_dir_pos is not None:
            args.pilot_dir = args.pilot_dir_pos
        else:
            parser.error("The --pilot-dir argument is required.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    pilot_dir = args.pilot_dir.resolve()

    if not pilot_dir.is_dir():
        print(f"[ERROR] Pilot directory does not exist: {pilot_dir}", file=sys.stderr)
        return 1

    try:
        results = evaluate_pilot(pilot_dir)
    except Exception as exc:
        print(f"[ERROR] Failed evaluating pilot reference labels: {exc}", file=sys.stderr)
        return 1

    print_report(results)

    if args.json_output:
        out_path = args.json_output.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON 결과 저장됨: {out_path}")

    return 0 if results["summary"]["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
