# 데이터 수집 계획·라이선스 점검·정제 전략

점검일: 2026-09-08. 상태: CMA 실물 snapshot 세팅 완료·권리/라벨 검수 대기. React JSON 출력 계약 점검 항목을 추가했다.
본 문서는 이용 권한이 확보되었다는 증명이나 법률 판단이 아니다.

## 1. 현재 보유 자료 점검

| 자료 | 현재 확인된 사실 | 판정 |
|---|---|---|
| assets/samples/najeon-box.jpeg | 로컬 원본 파일 존재, 학습 manifest에도 사용 | 권리 증빙 미확인 |
| assets/samples/images-2.jpeg | 로컬 원본 파일 존재, 학습 manifest에도 사용 | 권리 증빙 미확인 |
| assets/samples/product-photos/ 4장 | 동일 직물 상품 구도, 학습 manifest에도 사용 | 권리 증빙 미확인 |
| data/evaluation/inputs/ 6장 | 기존 원본에서 crop·resize·JPEG 저장한 파생 파일 | 원본 권리 상속 확인 필요 |
| data/evaluation/cma_real_v1/ | CMA Open Access 실물 60점, 6개 영역 각 10점, 원본 JPEG·source snapshot·SHA-256 보유 | 레코드에 CC0 표시와 정책 hash 있음. 기관 정책 범위·시리즈·사람 라벨 검수 필요 |
| assets/references/ 가이드 | 디자인 참고 자료 | 학습·재배포 허가 미확인 |

파일 존재, 공개 접근 가능성, manifest의 human_approved=true는 저작권자 허가 증거가 아니다.
확인 전 외부 학습 업로드·배포용 데이터셋에는 포함하지 않는다. 기존 파일을 자동 삭제하지 않는다.

## 2. 수집 목표와 단위

영역은 분석·카피, 이미지·렌더링, API·상태·안전 회귀의 세 영역으로 정의한다.
영역별 50~200건, 1차 목표는 각 60건이다. 중복 실행이나 같은 입력의 ID 변경은 신규 사례로 계산하지 않는다.
현재 `cma_real_v1` snapshot은 분석 60건과 렌더링 준비 60건을 충족하지만, API·상태·안전 전용
60건과 사람 gold 라벨은 아직 확보하지 않았다.
한 상품을 여러 영역에서 평가할 수 있지만 고유 상품 수와 원본 수를 별도 보고한다.

- 분석·카피: 독립 상품 60개, 상품당 원본 1~4장과 검수한 관찰·금지 주장·입력 설명.
- 이미지·렌더링: 위 상품 60개와 승인 draft, 사진 역할·허용 변환·시각 검수 라벨.
- API·상태·안전: 60개 고유 요청 시퀀스. 성공 20, 입력 경계 15, 버전·멱등성·장애 15, 인젝션·게시 차단 10.

상품 층화는 직물·장식/보관·금속 세트·도자/유리·액세서리·기타 생활품 각 10개를 초기 목표로 한다.
배경 복잡도, 반사, 저해상도, 추가 사진 0/1~3/4장 이상을 별도 태그로 기록한다.
추가 사진 수 시험용 crop은 실제 새 촬영 구도로 집계하지 않는다.

## 3. 수집 절차와 책임

1. 데이터 담당자가 장인/BE의 권리 확인 가능한 원본과 상품별 사실 자료를 확보한다.
2. 권리 검토 담당자가 원본 출처와 이용 범위를 승인한다.
3. 데이터 담당자가 SHA-256·크기·MIME·상품 식별자를 기록하고 격리 영역에 저장한다.
4. 장인/MD가 관찰 사실·소재 등 제공 사실·추론을 구분해 라벨링한다.
5. 다른 검수자가 라벨·권한·중복을 재확인하고 의견 불일치는 합의 후 승인한다.
6. 평가 담당자가 상품 단위 holdout을 고정하고 데이터 버전을 발행한다.

담당자 실명과 수집 일정은 팀 배정 필요. CMA 파일 수집은 완료했지만 권리 승인과 라벨 gold
승인까지 완료된 것으로 보고하지 않는다.

## 4. 라이선스 점검대장 필수 필드

asset_id, product_group_id, source_path, sha256, source_url, acquired_at,
rights_holder, license_name, license_version, evidence_path, permitted_uses,
attribution_text, modification_allowed, redistribution_allowed, provider_upload_allowed,
expires_at, reviewer, reviewed_at, review_status를 기록한다.

review_status: unverified → pending_review → approved 또는 restricted/rejected.
permitted_uses는 내부 평가, 학습, 외부 provider 전송, 상업 이용, 재배포를 각각 기록한다.
승인은 증빙 파일과 검토자가 있을 때만 가능하다. 출처 URL이 없어도 직접 제공 동의서 등 증빙을 남긴다.
철회·만료 시 원본과 파생 자산의 연결을 따라 신규 사용을 중지하고 삭제 범위를 검토한다.

## 5. 정제 전략

- 원본은 그대로 보존하고 SHA-256을 계산한다. EXIF 제거·리사이즈는 별도 파생 파일에 수행한다.
- MIME/signature/decode, 크기, 방향, 색 공간, 흐림·과노출·잘림을 검사한다.
- 손상 파일은 격리한다. 저품질이 평가 목적이면 삭제하지 않고 challenge 태그를 붙인다.
- SHA-256으로 완전 중복, perceptual hash와 상품 ID로 유사 중복을 찾고 사람이 확인한다.
- 동일 상품·원본의 crop/생성 파생물은 동일 split에 둔다. 학습 manifest와도 hash 및 상품 그룹을 대조한다.
- 사용자 문구는 공백을 정리하되 의미·출처를 유지한다. 인젝션 시험 문구는 test_payload로 보존한다.
- 개인정보·연락처·얼굴·워터마크는 검수하고 삭제/마스킹 권한과 필요성을 기록한다.
- generated_scene/view를 원본 정답으로 승격하지 않는다.
- source hash, parent_asset_id, 변환 파라미터, 도구 버전, 라벨 수정 이력을 남긴다.
- `data/evaluation/cma_real_v1/`의 `reference_facts`는 평가자용 참고 metadata이며, 모델 입력에
  자동 주입하지 않는다. 이미지에서 직접 보이지 않는 연대·소재·규격은 시각 사실 정답으로 세지 않는다.
- `react_document`에는 실제 외부 이미지 URL이나 원본 본문을 넣지 않고 `props.imageId`만 기록한다.
  image ID와 URL/파일의 연결은 photos/asset manifest와 별도로 검증하고, 라이선스·출처 provenance는
  평가 metadata와 BE 저장 레코드에 남긴다.
- 최근 사용자 제공 smoke 입력인 `Downloads/54042...jpg`, `Downloads/shop1...jpg`는 ad hoc 생성
  테스트 산출물이며, 권리 점검과 평가셋 발행 전에는 학습·평가 데이터로 포함하지 않는다.

## 6. 반출 및 완료 조건

권한 승인율 100%, 필수 metadata 누락 0, 경로/hash 오류 0, 상품 단위 학습/평가 누수 0,
라벨 검수 완료율 100%, React AST schema/tree/image reference 검증 통과율 100%를 데이터셋 발행
조건으로 한다. 현재 CMA snapshot은 파일·decode·hash·
라이선스 표시 검증은 통과했지만 사람 라벨과 최종 권리 승인은 pending이다.
측정 기준은 [평가 지표 정의서](metrics-definition.md)를 따른다.
