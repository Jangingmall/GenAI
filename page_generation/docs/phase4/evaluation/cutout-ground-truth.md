# 컷아웃 품질 독립 감사 정답 집합 (Ground Truth 60건)

> [!NOTE]
> **스냅샷 기준**: 이 문서는 `/Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/generated/evaluation/full60-20260910-204433` 디렉터리에 저장된 **냉동 산출물(Frozen Outputs)** 을 기준으로 원본 이미지와 디스크 상의 산출물(`photos/01-hero.*`, `result_summary.json`)을 직접 비교하여 구축한 불변 정답 집합 스냅샷입니다. 코드 수정과 무관하게 고정된 기준선으로 유지됩니다.

- 대상 디렉토리: `/Users/jmllem/PycharmProjects/Team3_EcommerceSystemAI/generated/evaluation/full60-20260910-204433`
- 총 케이스 수: 60건 (Composite 9건, Fallback 51건)
- 관리자 육안 검증 5건 일치율: 5/5 (100%)

## 60건 전체 판정표

| No | case_id | 카테고리 | 모드 | 축 A (제품 침식) | 축 B (배경 잔존) | 근거 (정량 수치) | 관리자 일치 | 기존 게이트 판정 | 게이트 오류 분류 |
|---|---|---|---|---|---|---|---|---|---|
| 01 | `analysis-cma-102980` | textile | 합성 | **none** | **none** | 제품 형태 온전 보존 (내부 홀 0px, 소실 화소 없음) | 배경 깨끗이 제거됨 (테두리 접촉 없음, 고리 잔존 없음) | - | OK | `TRUE_NEGATIVE` |
| 02 | `analysis-cma-156983` | textile | 합성 | **none** | **none** | 제품 형태 온전 보존 (내부 홀 0px, 소실 화소 없음) | 배경 깨끗이 제거됨 (테두리 접촉 없음, 고리 잔존 없음) | - | OK | `TRUE_NEGATIVE` |
| 03 | `analysis-cma-157123` | textile | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 04 | `analysis-cma-165266` | textile | 합성 | **partial** | **none** | 직물 크림색 평직 바탕이 배경으로 오인되어 광범위 침식 (자수 문양만 부유) | 배경 깨끗이 제거됨 (테두리 접촉 없음, 고리 잔존 없음) | 일치 | 부분 손실 | `TRUE_POSITIVE_EROSION` |
| 05 | `analysis-cma-165267` | textile | 합성 | **partial** | **none** | 직물 크림색 평직 바탕이 배경으로 오인되어 광범위 침식 (자수 문양만 부유) | 배경 깨끗이 제거됨 (테두리 접촉 없음, 고리 잔존 없음) | 일치 | 부분 손실 | `TRUE_POSITIVE_EROSION` |
| 06 | `analysis-cma-165268` | textile | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 07 | `analysis-cma-165269` | textile | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 08 | `analysis-cma-165270` | textile | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 09 | `analysis-cma-165271` | textile | 합성 | **partial** | **none** | 직물 크림색 평직 바탕이 배경으로 오인되어 광범위 침식 (자수 문양만 부유) | 배경 깨끗이 제거됨 (테두리 접촉 없음, 고리 잔존 없음) | 일치 | 부분 손실 | `TRUE_POSITIVE_EROSION` |
| 10 | `analysis-cma-165272` | textile | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 11 | `analysis-cma-101636` | box | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 12 | `analysis-cma-139742` | box | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 13 | `analysis-cma-142759` | box | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 14 | `analysis-cma-142761` | box | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 15 | `analysis-cma-144690` | box | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 16 | `analysis-cma-148725` | box | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 17 | `analysis-cma-148828` | box | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 18 | `analysis-cma-169510` | box | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 19 | `analysis-cma-94136` | box | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 20 | `analysis-cma-96890` | box | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 21 | `analysis-cma-114971` | metalware | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 22 | `analysis-cma-119326` | metalware | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 23 | `analysis-cma-122920` | metalware | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 24 | `analysis-cma-122925` | metalware | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 25 | `analysis-cma-143819` | metalware | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 26 | `analysis-cma-149041` | metalware | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 27 | `analysis-cma-149146` | metalware | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 28 | `analysis-cma-149950` | metalware | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 29 | `analysis-cma-150698` | metalware | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 30 | `analysis-cma-154255` | metalware | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 31 | `analysis-cma-122443` | ceramic | 합성 | **partial** | **edge** | 도자기 짙은 청색 유약이 배경과 유사하여 체류홀 침식 (18,429px 내부 홀) | 받침대/바닥면이 전경에 포함되어 테두리 잔존 (좌:391px, 우:439px 접촉, 총 830px) | - | OK | `FALSE_NEGATIVE_BOTH` |
| 32 | `analysis-cma-123616` | ceramic | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 33 | `analysis-cma-136303` | ceramic | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 34 | `analysis-cma-142466` | ceramic | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 35 | `analysis-cma-145937` | ceramic | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 36 | `analysis-cma-159994` | ceramic | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 37 | `analysis-cma-300665` | ceramic | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 38 | `analysis-cma-520329` | ceramic | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 39 | `analysis-cma-93161` | ceramic | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 40 | `analysis-cma-99259` | ceramic | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 41 | `analysis-cma-109609` | jewelry | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 42 | `analysis-cma-124415` | jewelry | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 43 | `analysis-cma-130076` | jewelry | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 44 | `analysis-cma-131719` | jewelry | 합성 | **none** | **enclosed** | 제품 형태 온전 보존 (내부 홀 1px, 소실 화소 없음) | 폐곡선 고리 안쪽에 스튜디오 배경 잔존 (268,201px, 마스크의 83.3%) | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 45 | `analysis-cma-140406` | jewelry | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 46 | `analysis-cma-156849` | jewelry | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 47 | `analysis-cma-159023` | jewelry | 합성 | **none** | **enclosed** | 제품 형태 온전 보존 (내부 홀 1180px, 소실 화소 없음) | 폐곡선 고리 안쪽에 스튜디오 배경 잔존 (112,907px, 마스크의 30.2%) | 일치 | 부분 손실 | `FALSE_POSITIVE_EROSION_MISSED_REMNANT` |
| 48 | `analysis-cma-161405` | jewelry | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 49 | `analysis-cma-168479` | jewelry | 합성 | **none** | **none** | 제품 형태 온전 보존 (내부 홀 497px, 소실 화소 없음) | 배경 깨끗이 제거됨 (테두리 접촉 없음, 고리 잔존 없음) | 일치 | 부분 손실 | `FALSE_POSITIVE_EROSION` |
| 50 | `analysis-cma-692273` | jewelry | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 51 | `analysis-cma-110793` | furniture | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 52 | `analysis-cma-137166` | furniture | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 53 | `analysis-cma-142748` | furniture | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 54 | `analysis-cma-142749` | furniture | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 55 | `analysis-cma-150985` | furniture | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 56 | `analysis-cma-151001` | furniture | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 57 | `analysis-cma-151452` | furniture | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 58 | `analysis-cma-152787` | furniture | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 59 | `analysis-cma-154214` | furniture | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |
| 60 | `analysis-cma-678264` | furniture | 폴백 | **none** | **edge** | 폴백 모드(asset_mode: source, 냉동 산출물). 원본 사진과 100% 바이트 일치(01-hero.jpg). 제품 침식 없음(0px). 원본 스튜디오/배경이 4면 테두리까지 100% 잔존. | - | OK | `FALSE_NEGATIVE_REMNANT` |

## 요약 통계

### 축 A. 제품 침식 (Product Erosion)
- `none` (온전 보존): **56건** (93.3%)
- `partial` (부분 소실): **4건** (6.7%) — `analysis-cma-165266`, `165267`, `165271` (평직 바탕 소실), `122443` (도자기 유약 홀 소실)
- `severe` (심각 소실): **0건** (0.0%)
- `uncertain` (불확실): **0건** (0.0%)

### 축 B. 배경 잔존 (Background Remnant)
- `none` (완전 제거): **6건** (10.0%) — `102980`, `156983`, `165266`, `165267`, `165271`, `168479`
- `enclosed` (폐곡선 내부 잔존): **2건** (3.3%) — `analysis-cma-159023` (68,223px 고리 내부), `131719` (217,155px 목걸이 체인 내부, 마스크의 82.6%)
- `edge` (테두리 닿음 잔존): **52건** (86.7%) — 폴백 51건(100% 미제거) + 합성 `122443` (받침대 테두리 접촉 758px)
- `uncertain` (불확실): **0건** (0.0%)

### 기존 게이트(`check_cutout_fidelity.py`) 실패 심층 분석
- 기존 게이트 플래그(부분 손실): 총 5건
  - **참 긍정 (True Positive)**: 3건 (`165266`, `165267`, `165271`) — 실제 직물 침식을 정확히 포착
  - **오탐 (False Positive - 침식 왜곡)**: 2건
    - `analysis-cma-168479`: 제품 100% 온전 보존이나 배경 제거로 인한 전체 잉크 감소를 '부분 손실(35.3%)'로 오판
    - `analysis-cma-159023`: 제품 침식이 아닌 '고리 내부 배경 잔존' 결함을 '부분 손실(53.2%)'로 잘못 진단
- 기존 게이트 합격(OK): 총 55건
  - **미탐 (False Negative - 침식)**: **1건** (`analysis-cma-122443`: 짙은 유약 침식 홀 14,346px이 발생했음에도 64.1% OK로 통과)
  - **미탐 (False Negative - 배경 잔존)**: **53건**
    - `analysis-cma-131719`: 목걸이 체인 안쪽 배경 217,155px(82.6%) 잔존을 66.6% OK로 통과
    - `analysis-cma-122443`: 받침대 테두리 잔존 758px을 64.1% OK로 통과
    - **폴백 51건 전건**: 원본 이미지를 그대로 출력하므로 보존율 100.0%로 측정되어, 배경이 전혀 제거되지 않았음에도 전건 'OK'로 통과
  - **진정한 정상 합격 (True Negative)**: 단 **2건** (`analysis-cma-102980`, `156983`)