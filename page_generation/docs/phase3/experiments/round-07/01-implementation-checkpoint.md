# Round 07 · 구현 체크포인트 — 원형 variant 전달 경로 개방

| 항목 | 값 |
| --- | --- |
| 차수 | 07 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-153208` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-145007` (6차) |
| 이미지 재생성 | 아니오 (--image-provider none, AI 이미지 생성 없음) |
| 기록 시각 | 2026-09-10 |

## 1. 파일별 변경 내용

### 1) 프롬프트 템플릿의 variant 주입 경로 개방
- **파일**: `src/detail_page_ai/prompts.py`
- **위치**: `SECTION_PLAN_PROMPT` 구성부 (lines 140-175)
- **내용**: 선택된 원형 레이아웃의 `sequence`뿐만 아니라 각 블록에 지정된 `variants`를 `블록명 (지정_variant)` 형태로 프롬프트에 주입하도록 변경했다. 또한 "근거 부족으로 블록을 생략하는 경우를 제외하고는 지정된 variant를 변경 없이 유지하라"는 지시문을 추가하여 모델이 `paper`와 `light`로 자의적 수렴을 일으키지 못하게 제어했다.

### 2) 프롬프트 단위 테스트 추가
- **파일**: `tests/test_prompts.py`
- **위치**: `test_section_plan_prompt_includes_archetype_variants`
- **내용**: 레이아웃 원형이 주어졌을 때 프롬프트 텍스트 내에 각 블록의 variant 매핑 문자열이 정상적으로 포맷팅되어 포함되는지 검증하는 테스트를 추가했다.

## 2. 새로 추가된 산출물 목록
- 신규 파일 추가 없음 (기존 프롬프트 및 테스트 파일 수정).

## 3. 테스트 통과 현황
- 커밋(`b8d1a14`) 시점 기준 `tests/test_prompts.py` 포함 단위 테스트 전원 통과.
