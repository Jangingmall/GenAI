# Round 09 · 추론 API 영향 — 근거 기반 원형 선택

| 항목 | 값 |
| --- | --- |
| 차수 | 09 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-164008` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-161310` (8차) |
| 이미지 재생성 | 예 (Flux 9B 전체 재생성, 27.6분 소요) |
| 기록 시각 | 2026-09-10 |

## 1. 모델 호출 계약 변화

### 1) 프롬프트 템플릿의 후보 풀 제시
`SECTION_PLAN_PROMPT`가 단일 원형 주입에서 4개 후보 원형 주입 방식으로 확장되었다. 프롬프트에는 해시로 선정된 4개 원형의 식별자, `when` 조건, `avoid_when` 조건, 블록 시퀀스 및 variant가 모두 포함된다:
```
[Candidate Layout Archetypes]
Candidate 1: <id>
- When to use: ...
- Avoid when: ...
- Sequence: hero (paper) -> ...
...
```

### 2) 모델의 판단 및 생성 계약
모델은 앞선 턴에서 관찰한 `product_type`, `craft_type`, `observations`를 위 4개 후보의 조건과 대조하여 가장 타당한 1개를 선택한 뒤, 해당 원형의 블록 구성을 따라 `PagePlanDto`를 출력해야 한다.

### 3) DTO 스키마 호환성
출력 DTO에 `selected_archetype_id` 같은 신규 필드를 추가하지 않았다. 모델은 기존과 동일한 `page_plan` 배열만을 출력하며, 어떤 원형을 선택했는지는 백엔드 코드(`match_selected_archetype`)가 사후 대조한다.

## 2. 호출 횟수 및 소요 시간
- **호출 횟수**: 6개 케이스에 대해 텍스트 추론 및 Flux 이미지 생성 전체 수행.
- **소요 시간**: 총 27.6분 소요 (케이스당 약 4.6분).
- 프롬프트에 4개 원형 메타데이터가 추가되었으나 토큰 증가량이 미미하여 텍스트 추론 지연은 체감되지 않았다.

## 3. 하위 호환성
DTO 인터페이스와 모델 응답 JSON 스키마가 기존과 100% 동일하므로 API 클라이언트는 아무런 수정 없이 동작한다.
