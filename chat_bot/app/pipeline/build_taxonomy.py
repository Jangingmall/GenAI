"""app/pipeline/taxonomy.py 생성기 — 실데이터에서 카테고리 대조용 사전을 자동으로 뽑는다.

손으로 키워드를 추측해 적지 않고 장인몰_샘플_category.csv·장인몰_샘플_product.csv에서
직접 뽑아 커밋한다 — eval/build_fixtures.py의 "생성물 커밋 + --check" 패턴을 따른다.

카테고리를 유일하게 특정하는 재질·세부품목 단어만 신호로 쓴다. 여러 카테고리에 걸친
단어("옹기토"·"소반"·"문갑"·"트레이")는 잘못 매칭돼 멀쩡한 후보를 지우는 게 매칭을
놓치는 것보다 위험해서 뺀다. 1글자 단어("은"·"면"·"함")도 뺀다 — 조사("그릇은")나
어미("사면"), 일상어("살펴볼게요")에 흔히 섞여 있어 평범한 문장 대부분에서 오탐된다.

실행:
    python app/pipeline/build_taxonomy.py           # taxonomy.py 재생성
    python app/pipeline/build_taxonomy.py --check    # 커밋본과 같은지만 확인(CI·커밋 전 훅용)
"""

from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"
CATEGORY_CSV = DATA_DIR / "장인몰_샘플_category.csv"
PRODUCT_CSV = DATA_DIR / "장인몰_샘플_product.csv"
OUT = Path(__file__).resolve().parent / "taxonomy.py"


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# 이보다 짧은 단어는 신호로 안 쓴다 — "은"(조사)·"면"(어미)·"함"(일상어)처럼 평범한
# 문장 대부분에 섞여 있어 오탐 위험이 크다.
MIN_SIGNAL_LENGTH = 2


def build() -> dict:
    """category.csv·product.csv → {labels, signals, ambiguous}."""
    categories = _read_csv(CATEGORY_CSV)
    products = _read_csv(PRODUCT_CSV)

    labels = {c["category_code"]: c["name"] for c in categories}

    mat_to_cats: dict[str, set[str]] = collections.defaultdict(set)
    sub_to_cats: dict[str, set[str]] = collections.defaultdict(set)
    for p in products:
        mat_to_cats[p["material"]].add(p["category_code"])
        sub_to_cats[p["subcategory_code"]].add(p["category_code"])

    # 우선순위: 카테고리 한글명 → 재질 → 세부품목 순으로 채운다(뒤에서 덮어씀).
    # 실데이터에서 이름이 겹치는 사례는 없지만, 겹치면 더 구체적인 세부품목 쪽을 우선한다.
    signals: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}

    for code, name in labels.items():
        signals[name] = code

    # dict 리터럴 병합(**)은 같은 키가 재질·세부품목 양쪽에 있으면 한쪽 집합을 조용히
    # 덮어써 버린다. 지금 실데이터엔 겹치는 이름이 없지만, 있어도 안전하도록 합집합으로 합친다.
    merged: dict[str, set[str]] = collections.defaultdict(set)
    for term, cats in mat_to_cats.items():
        merged[term] |= cats
    for term, cats in sub_to_cats.items():
        merged[term] |= cats

    for term, cats in merged.items():
        if len(term) < MIN_SIGNAL_LENGTH:
            ambiguous[term] = ["(1글자 — 오탐 위험으로 제외)"]
        elif len(cats) == 1:
            signals[term] = next(iter(cats))
        else:
            ambiguous[term] = sorted(cats)

    return {"labels": labels, "signals": signals, "ambiguous": ambiguous}


def _render(data: dict) -> str:
    labels_src = "\n".join(f"    {k!r}: {v!r}," for k, v in sorted(data["labels"].items()))
    signals_src = "\n".join(f"    {k!r}: {v!r}," for k, v in sorted(data["signals"].items()))
    ambiguous_src = "\n".join(
        f"    {k!r}: {v!r}," for k, v in sorted(data["ambiguous"].items())
    )
    return f'''"""build_taxonomy.py 생성물 — 직접 수정 금지.

data/장인몰_샘플_category.csv · 장인몰_샘플_product.csv 에서 자동으로 뽑았다.
실데이터가 바뀌면 재생성: python app/pipeline/build_taxonomy.py
"""

CATEGORY_LABELS: dict[str, str] = {{
{labels_src}
}}

# 소비자가 쓸 법한 단어(카테고리 한글명 + 카테고리를 유일하게 특정하는 재질·세부품목)
# → 카테고리 코드. generate.py의 카테고리 대조 방어가 이 사전으로 사용자 발화에서
# 카테고리를 뽑는다.
CATEGORY_SIGNALS: dict[str, str] = {{
{signals_src}
}}

# CATEGORY_SIGNALS에서 뺀 단어 — 값이 카테고리 코드 2개 이상이면 "여러 카테고리에 걸침"
# (예: "옹기토"는 POTTERY·ONGGI 양쪽 다 쓰인다), 안내문 하나뿐이면 "1글자라 오탐 위험"
# (예: "은"은 조사 "그릇은"과 구별 안 됨)이라는 뜻이다. 잘못 매칭돼 멀쩡한 후보를
# 지우는 게 매칭을 놓치는 것보다 위험해서 신호에서 제외했다.
AMBIGUOUS_TERMS: dict[str, list[str]] = {{
{ambiguous_src}
}}
'''


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="카테고리 대조 사전 생성")
    parser.add_argument(
        "--check", action="store_true", help="재생성 결과가 커밋된 taxonomy.py 와 같은지만 확인"
    )
    args = parser.parse_args(argv)

    data = build()
    fresh = _render(data)

    if args.check:
        if not OUT.exists():
            print(f"{OUT} 없음 — 먼저 --check 없이 실행", file=sys.stderr)
            return 1
        if OUT.read_text(encoding="utf-8") == fresh:
            print("OK: taxonomy.py 가 실데이터와 일치")
            return 0
        print(
            "불일치: 실데이터가 바뀌었다. "
            "`python app/pipeline/build_taxonomy.py` 로 재생성 후 함께 커밋",
            file=sys.stderr,
        )
        return 1

    OUT.write_text(fresh, encoding="utf-8")
    print(
        f"생성: {OUT.relative_to(ROOT)} "
        f"(signals {len(data['signals'])}개, ambiguous {len(data['ambiguous'])}개)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
