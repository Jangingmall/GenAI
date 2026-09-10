#!/usr/bin/env python3
"""원격 검수자용 단일 HTML 생성기.

이미지와 카피를 전부 인라인해 자체 완결 페이지를 만든다. 점수는 페이지가
Artifact db 로 저장하므로, 검수자는 저장소 접근 없이 링크만으로 채점한다.
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ROLE_LABEL = {
    "hero": ("대표", "source"), "packshot": ("팩샷", "source"),
    "detail": ("디테일", "source"), "lifestyle": ("활용 장면", "generated"),
    "detail-02": ("디테일 02", "generated"), "detail-03": ("디테일 03", "generated"),
    "detail-04": ("디테일 04", "generated"), "detail-05": ("디테일 05", "generated"),
}
AXES = [("factuality", "사실성"), ("clarity", "명료성"),
        ("commerce", "상품성"), ("visual", "시각 품질")]

TYPE_CONTRACT = {
    (40.0, 700, 1.25): "hero 제목", (30.0, 700, 1.35): "섹션 제목",
    (19.0, 600, 1.4): "카드 제목", (16.0, 400, 1.7): "본문", (13.0, 500, 1.5): "라벨",
}
DESIGN_ITEMS = [
    "타이포 위계가 계약 값(40/30/19/16/13)을 지키고, 이탈이 있다면 카피 길이상 불가피한가",
    "섹션 padding 40px, 주요 섹션 간격 24가 일관되게 적용됐는가",
    "피처 카드가 3열 grid(gap 16), 카드 내부 gap 12 · padding 20 · radius 12인가",
    "eyebrow·제목·본문이 한 텍스트 그룹, 이미지는 별도 그룹으로 묶였는가",
    "제목·본문·figure의 기본 마진이 0이고 간격이 부모 gap/padding으로 관리되는가",
    "흑백 기반에 cool grey와 jade blue 액센트가 일관되게 쓰였는가",
    "이미지 크롭·비율 왜곡이 없고 774 캔버스에서 어색한 여백이 없는가",
]
DESIGN_SCORES = [("layout", "레이아웃 완성도"), ("brand", "브랜드 일관성")]
GATES = [
    "미확인 법적·안전성 주장 (친환경·항균·의료 효능, 검증 없는 식기 사용 가능 서술)",
    "허위 진품성·문화재 지위 날조 (인간문화재·명장·국보급 재현 등)",
    "거절 자산(REJECTED)이 최종 캔버스에 유입",
    "원본 제품의 임의적 형태 왜곡 (비율·색상 변조, 장식 삭제)",
    "생성 참고 컷에 '참고용' 표시 누락",
]


def encode(path: Path, max_width: int, quality: int = 74) -> str:
    image = Image.open(path).convert("RGB")
    if image.width > max_width:
        height = round(image.height * max_width / image.width)
        image = image.resize((max_width, height), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def photo_role(name: str) -> str:
    return name.split("-", 1)[1].rsplit(".", 1)[0]


def contract_check(document_path: Path) -> list[dict]:
    """react_document 의 실제 스타일 값을 계약과 대조한다."""
    import collections
    document = json.loads(document_path.read_text(encoding="utf-8"))
    fonts: collections.Counter = collections.Counter()
    pads: collections.Counter = collections.Counter()
    gaps: collections.Counter = collections.Counter()
    grids: collections.Counter = collections.Counter()
    radii: collections.Counter = collections.Counter()

    def walk(node: dict) -> None:
        if node.get("type") != "element":
            return
        props = node.get("props", {})
        style = props.get("style") or {}
        layout = props.get("layout") or {}
        if style.get("fontSize"):
            fonts[(style["fontSize"], style.get("fontWeight"), style.get("lineHeight"))] += 1
        if style.get("padding"):
            pads[tuple(style["padding"][k] for k in ("top", "right", "bottom", "left"))] += 1
        if style.get("borderRadius") is not None:
            radii[style["borderRadius"]] += 1
        if layout.get("gap") is not None:
            gaps[layout["gap"]] += 1
        if layout.get("display") == "grid":
            grids[(layout.get("columns"), layout.get("gap"))] += 1
        for child in node.get("children", []):
            walk(child)

    for node in document["root"]:
        walk(node)

    rows = []
    for combo, count in sorted(fonts.items(), key=lambda kv: -kv[0][0]):
        known = TYPE_CONTRACT.get(combo)
        rows.append({
            "item": known or "계약 밖 조합",
            "want": f"{combo[0]:.0f} / {combo[1]} / {combo[2]}" if known else "계약에 없음",
            "got": f"{combo[0]:.0f} / {combo[1]} / {combo[2]} × {count}",
            "ok": bool(known),
        })
    grid_rows = ", ".join(f"{c}열 gap {g:.0f} × {n}" for (c, g), n in grids.items())
    rows.append({"item": "피처 카드 grid", "want": "3열 · gap 16",
                 "got": grid_rows or "없음",
                 "ok": all(c == 3 and g == 16 for (c, g) in grids)})
    rows.append({"item": "섹션 padding", "want": "40px",
                 "got": ", ".join(f"{p[0]:.0f}px × {n}" for p, n in pads.items()) or "없음",
                 "ok": any(p[0] == 40 for p in pads)})
    rows.append({"item": "카드 radius", "want": "12",
                 "got": ", ".join(f"{r:.0f} × {n}" for r, n in radii.items()) or "없음",
                 "ok": all(r == 12 for r in radii) if radii else False})
    rows.append({"item": "layout gap", "want": "섹션 24 · 카드 12 · grid 16",
                 "got": ", ".join(f"{g:.0f} × {n}" for g, n in sorted(gaps.items())) or "없음",
                 "ok": {24.0, 16.0, 12.0} >= set(gaps.keys())})
    return rows


def collect(pilot_dir: Path) -> list[dict]:
    index = json.loads((pilot_dir / "run_index.json").read_text(encoding="utf-8"))
    cases = []
    for entry in index["cases"]:
        out = Path(entry["output_dir"])
        summary = json.loads((out / "result_summary.json").read_text(encoding="utf-8"))
        product = summary.get("product", {})
        photos = []
        for photo in sorted(p for p in out.glob("photos/*") if p.suffix.lower() in {".png", ".jpg", ".jpeg"}):
            role = photo_role(photo.name)
            label, origin = ROLE_LABEL.get(role, (role, "generated"))
            photos.append({"label": label, "origin": origin, "src": encode(photo, 460)})
        cases.append({
            "id": entry["case_id"],
            "category": entry["category"],
            "asset": entry["asset_id"],
            "seconds": entry["duration_seconds"],
            "success": entry["success"],
            "error": entry.get("error"),
            "name": product.get("display_name", ""),
            "type": product.get("product_type", ""),
            "craft": product.get("is_traditional_craft"),
            "craft_type": product.get("craft_type") or "-",
            "confidence": product.get("classification_confidence"),
            "reason": product.get("classification_reason", ""),
            "layout": product.get("layout_id", ""),
            "plan": product.get("page_plan", []),
            "source": encode(Path(entry["image_path"]), 460),
            "page": encode(out / "detail_page.png", 620),
            "contract": contract_check(out / "react_document.json"),
            "photos": photos,
        })
    return cases


def render_plan(plan: list[dict]) -> str:
    blocks = []
    for section in plan:
        items = section.get("items") or []
        item_html = ""
        if items:
            rows = "".join(
                f"<li>{html.escape(str(i.get('title', '') if isinstance(i, dict) else i))}"
                + (f" — {html.escape(str(i.get('description', '')))}" if isinstance(i, dict) and i.get("description") else "")
                + "</li>"
                for i in items
            )
            item_html = f"<ul class='plan-items'>{rows}</ul>"
        blocks.append(
            "<article class='plan-block'>"
            f"<p class='plan-meta'><span class='sid'>{html.escape(section.get('section_id',''))}</span>"
            f"<span class='btype'>{html.escape(section.get('block_type',''))}</span></p>"
            + (f"<p class='plan-eyebrow'>{html.escape(section.get('eyebrow',''))}</p>" if section.get("eyebrow") else "")
            + (f"<h4>{html.escape(section.get('title',''))}</h4>" if section.get("title") else "")
            + (f"<p class='plan-body'>{html.escape(section.get('body',''))}</p>" if section.get("body") else "")
            + item_html
            + "</article>"
        )
    return "".join(blocks)


def build(cases: list[dict], template: Path) -> str:
    case_html = []
    for index, case in enumerate(cases, start=1):
        photos = "".join(
            f"<figure class='shot {p['origin']}'><img src='{p['src']}' alt='{html.escape(p['label'])}' loading='lazy'>"
            f"<figcaption>{html.escape(p['label'])}"
            f"<span class='origin'>{'생성' if p['origin']=='generated' else '원본'}</span></figcaption></figure>"
            for p in case["photos"]
        )
        axes = "".join(
            f"<div class='axis' data-axis='{key}'><span class='axis-name'>{label}</span>"
            "<div class='scale' role='radiogroup' aria-label='" + label + "'>"
            + "".join(
                f"<button type='button' class='pt' data-v='{v}' role='radio' aria-checked='false'>{v}</button>"
                for v in range(1, 6)
            )
            + "</div></div>"
            for key, label in AXES
        )
        gates = "".join(
            f"<label class='gate'><input type='checkbox' data-gate='{gi}'><span>{html.escape(text)}</span></label>"
            for gi, text in enumerate(GATES)
        )
        contract_rows = "".join(
            f"<tr class='{'ok' if row['ok'] else 'off'}'><td>{html.escape(row['item'])}</td>"
            f"<td class='m'>{html.escape(row['want'])}</td><td class='m'>{html.escape(row['got'])}</td>"
            f"<td>{'일치' if row['ok'] else '이탈'}</td></tr>"
            for row in case["contract"]
        )
        design_items = "".join(
            f"<div class='ditem'><p>{html.escape(text)}</p>"
            "<div class='verdict' role='radiogroup'>"
            + "".join(
                f"<button type='button' class='vb' data-d='{di}' data-v='{v}' role='radio' aria-checked='false'>{label}</button>"
                for v, label in (("ok", "준수"), ("off", "이탈"), ("na", "판단 불가"))
            )
            + "</div></div>"
            for di, text in enumerate(DESIGN_ITEMS)
        )
        design_scores = "".join(
            f"<div class='axis' data-axis='{key}'><span class='axis-name'>{label}</span>"
            "<div class='scale' role='radiogroup'>"
            + "".join(
                f"<button type='button' class='pt' data-v='{v}' role='radio' aria-checked='false'>{v}</button>"
                for v in range(1, 6)
            )
            + "</div></div>"
            for key, label in DESIGN_SCORES
        )
        case_html.append(f"""
<section class="case" id="case-{index}" data-case="{html.escape(case['id'])}">
  <header class="case-head">
    <div>
      <p class="eyebrow">{html.escape(case['category'])} · {html.escape(case['asset'])}</p>
      <h2>{html.escape(case['name'])}</h2>
      <p class="sub">{html.escape(case['type'])} · 공예 {('예' if case['craft'] else '아니오')} ({html.escape(case['craft_type'])})
        · 신뢰도 {case['confidence']} · 레이아웃 {html.escape(case['layout'])} · {case['seconds']}초</p>
    </div>
    <p class="state" data-state>미채점</p>
  </header>
  <div class="case-body">
    <div class="evidence">
      <div class="pair">
        <figure class="src"><img src="{case['source']}" alt="원본" loading="lazy"><figcaption>원본 입력</figcaption></figure>
        <figure class="page"><div class="scroll"><img src="{case['page']}" alt="상세페이지" loading="lazy"></div><figcaption>생성된 상세페이지 (스크롤)</figcaption></figure>
      </div>
      <div class="shots">{photos}</div>
      <p class="note">‘생성’ 표시된 컷은 모델이 만든 참고 이미지입니다. 실물로 오인될 표시가 없으면 차단 조건 5번입니다.</p>
    </div>
    <div class="judge">
      <details class="copy" open>
        <summary>카피 전문 — 사실성 판정 근거</summary>
        <p class="reason">분류 근거: {html.escape(case['reason'])}</p>
        {render_plan(case['plan'])}
      </details>
      <div class="score" data-panel="content">
        <div class="axes">{axes}</div>
        <label class="comment"><span>코멘트 <em>(3점 이하는 필수)</em></span>
          <textarea rows="3" placeholder="결함 사유를 구체적으로"></textarea></label>
        <fieldset class="gates"><legend>배포 차단 조건 (해당 시 체크)</legend>{gates}</fieldset>
      </div>
      <div class="score" data-panel="design" hidden>
        <details class="contract" open>
          <summary>디자인 계약 대조 — react_document 실측</summary>
          <div class="tablewrap"><table class="ctab">
            <tr><th>항목</th><th>계약</th><th>실측</th><th></th></tr>{contract_rows}
          </table></div>
          <p class="note">계약은 “카피 길이와 실제 텍스트 영역이 요구할 때만 조정하되 위계를 보존한다”고 정합니다. 이탈이 그 예외에 해당하는지 판정해 주세요.</p>
        </details>
        <div class="ditems">{design_items}</div>
        <div class="axes">{design_scores}</div>
        <label class="comment"><span>디자인 코멘트 <em>(이탈 판정 시 필수)</em></span>
          <textarea rows="3" data-design-comment placeholder="어떤 이탈이 왜 문제인지"></textarea></label>
      </div>
      <div class="compare" data-compare hidden></div>
    </div>
  </div>
</section>""")
    return template.read_text(encoding="utf-8").replace("<!--CASES-->", "".join(case_html)).replace(
        "/*CASECOUNT*/", str(len(cases))
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="원격 검수자용 단일 HTML 생성")
    parser.add_argument("--pilot-dir", required=True, type=Path)
    parser.add_argument("--template", type=Path,
                        default=PROJECT_ROOT / "scripts" / "review_artifact_template.html")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    cases = collect(args.pilot_dir)
    args.out.write_text(build(cases, args.template), encoding="utf-8")
    size = args.out.stat().st_size / 1024 / 1024
    print(f"[OK] {args.out}  {size:.1f}MB  ({len(cases)}건)")
    if size > 15:
        print("[WARN] 16MB 한도에 근접합니다. 이미지 폭이나 품질을 낮추세요.")


if __name__ == "__main__":
    main()
