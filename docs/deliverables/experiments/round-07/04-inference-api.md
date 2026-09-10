# Round 07 · 추론 API 영향 — 원형 variant 전달 경로 개방

| 항목 | 값 |
| --- | --- |
| 차수 | 07 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-153208` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260910-145007` (6차) |
| 이미지 재생성 | 아니오 (--image-provider none, AI 이미지 생성 없음) |
| 기록 시각 | 2026-09-10 |

## 1. 모델 호출 계약 변화

### 1) 프롬프트 구조 확장
`src/detail_page_ai/prompts.py` 내의 `SECTION_PLAN_PROMPT`가 변경되었다. 기존에는 블록 시퀀스만 단순 나열되었으나, Round 07부터는 각 블록 뒤에 지정 variant가 함께 기술된다:
```
- hero (paper)
- detail_split (sand)
- gallery (light)
...
```
모델에게는 특별한 근거 부족으로 블록을 생략하는 경우를 제외하고는 지정된 variant 값을 그대로 따르도록 지시했다.

### 2) 이미지 생성 비활성화 (`--image-provider none`)
- 케이스별 `image_model`: `none` (AI 이미지 생성 호출을 수행하지 않음).
- 케이스당 생성된 사진 수: 0장 (`photos/` 미생성).
- 주의: `run_index.json` 최상위의 `image_model`은 CLI 기본 설정값(flux2)으로 표기되나 실제로는 생성 호출이 비활성화되었다.

## 2. 호출 횟수 및 소요 시간
- **호출 횟수**: 케이스당 프로필 생성, 섹션 플랜 생성, 카피 생성이 수행되었으며, 이미지 생성 호출은 비활성화되었다.
- **소요 시간**: 총 11.0분 (AI 이미지 생성 생략으로 6차 27.3분 대비 대폭 단축).
- **에러 발생**: 1건에서 `ProductProfileDto.keywords` 항목 수가 9개로 출력되어 유효성 검증 실패 발생.

## 3. 하위 호환성
프롬프트 내부 포맷팅 변경이므로 외부 API 호출 규격은 100% 호환된다.
