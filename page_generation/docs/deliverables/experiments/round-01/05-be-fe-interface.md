# Round 01 · BE/FE Interface — page_plan 계약 유지

| 항목 | 값 |
| --- | --- |
| 차수 | 01 |
| 파일럿 디렉터리 | `generated/evaluation/pilot-20260910-102346` |
| 직전 차수 기준 | `generated/evaluation/pilot-20260909-224737` (baseline) |
| 이미지 재생성 | 예 |
| 기록 시각 | 2026-09-10 |

## 변경 없음

이 차수는 BE·FE가 소비하는 스키마를 바꾸지 않고 validation의 계획 보존 동작만 바꿨다.

- `page_plan`의 허용 `block_type` 어휘는 `hero`, `statement`, `feature_grid`, `detail_split`, `wide_image`, `gallery`, `usage_scene`, `scale_reference`, `palette`, `recommendation`, `info_table`, `notice`, `closing`으로 유지됐다.
- `PageBlockVariant` 허용값과 `react_document` 스키마는 변경하지 않았다.
- `ProductProfileDto`의 최대 14블록 제한, hero 첫 블록·closing 마지막 블록, gallery의 `photo_ids` 계약을 유지했다.
- `layout_id`는 backward-compatible style hint로 남았고 기존 소비자가 읽는 필드와 하위 호환됐다.

## 영향

모델이 만든 중간 블록 종류와 순서가 충분한 경우 더 많이 보존됐지만, 필드와 어휘가 바뀐 것은 아니다. 기존 BE·FE 소비자는 같은 계약으로 결과를 읽는다.
