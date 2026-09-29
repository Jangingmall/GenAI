# detail-page-golden-60

> 실제 외부 이미지 평가에는 [CMA real v1](cma_real_v1/README.md)을 사용한다. 이 파일은 기존 회귀 fixture의 기록이다.

> 2026-09-08 감사 판정: 미검수 회귀 fixture. 독립 골든셋으로 승인되지 않았다.
> 3상품·대표 hash 3개를 반복 사용하며 학습 manifest 원본과 겹친다.
> 초안 42/저장 9/승인 9건으로 영역별 50~200건 요건 미충족.
> 사람 정답·라이선스 증빙·실제 모델 성능 측정은 미완료다.
> 본문의 자동 검사 목록은 평가 요구사항이며 실행 결과가 아니다. 2026-09-08부터 구현된 React JSON 출력 계약 검사도 포함한다.
> [보완 계획](../../docs/phase2/collection-license-cleaning-plan.md)과
> [지표 정의](../../docs/phase2/metrics-definition.md)를 따른다.

버전: `0.1.0`  
스키마: `detail-page-eval-v1`  
레코드: `60`건

## 목적

상품 FE → 상품 BE → AI → 상품 BE → FE 전체 흐름의 회귀·통합 평가용 골든셋이다.
초안 생성, draft 저장, 승인 렌더링, 원본 보존, 상태 전이, 멱등성, 추가 이미지 수,
사용자 문구 우선순위, 프롬프트 인젝션 내성을 한 JSONL 레코드로 표현한다.

## 구성

- 상품: `3`개 (`textile-scarf-01, najeon-box-01, metal-tea-set-01`)
- 단계: `{'draft_generation': 42, 'draft_save': 9, 'approval_render': 9}`
- `detail_page_eval_60.jsonl`: 한 줄에 하나의 평가 케이스
- `detail_page_eval_60_summary.json`: 레코드·단계·초점별 집계
- `inputs/`: 추가 이미지 개수 테스트용 결정적 crop 입력

## 레코드 핵심 필드

- `input.primary_image`, `input.additional_images`: 원본 경로·MIME·SHA-256
- `input.user_hints`: 상품명·제작 과정·관리법
- `input.draft`: 저장·승인 단계에서 사용하는 구조화된 draft
- `expected.react_document`: `schemaVersion: "2.0"`, `canvasWidth`, 허용된 `root[]` 구조와 이미지 참조 기준
- `expected`: 상태, 레이아웃, 필수 block/photo, 금지 주장, fidelity 기준
- `evaluation.automatic_checks`: 자동 검증 체크 목록

## 합격 기준

1. 원본 SHA-256과 source crop 픽셀 보존 검증을 통과한다.
2. `page_plan`이 허용 block allowlist를 사용하고 실행 가능한 HTML/CSS/script를 포함하지 않는다.
3. `react_document`가 제한형 React JSON AST 계약을 통과한다. 모든 element는 허용 tag만 사용하고,
   `img`는 `props.imageId`를 가지며, 허용 부모·자식 관계·고유 node id·최대 20단계 깊이·최대
   300노드 제한을 지킨다.
4. React JSON의 외부 직렬화 키는 `schemaVersion`, `canvasWidth`, `imageId`, `videoUrl`,
   `colSpan`, `rowSpan` 등 camelCase를 사용하고 raw URL/HTML/JSX/CSS/event handler를 포함하지 않는다.
5. 사용자 제공 상품별 문구는 유지하고, 입력에 없는 소재·규격·성능·인증·제작자·원산지·진품성을 만들지 않는다.
6. draft 저장은 AI 재호출이나 PNG 생성을 유발하지 않는다.
7. 승인 렌더링은 분석을 다시 호출하지 않고 `generation_id`와 BE ACK를 반환한다.
8. `REJECTED` 자산이 FE/BE 결과로 유입되지 않는다.

## 한계와 확장

이 데이터셋은 현재 저장소에 있는 세 상품 원본을 사용하므로 모델 일반화 성능을 주장하는
벤치마크가 아니다. 신규 상품을 추가할 때는 `PRODUCTS`에 source asset과 사람이 검토한
visible anchors·forbidden claim categories·layout label을 추가한 뒤 다시 생성한다.

## 재생성

```bash
PYTHONPATH=src .venv/bin/python scripts/build_detail_page_eval_dataset.py
```
