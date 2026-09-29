# 실제 공개 이미지 평가셋 — CMA real v1

> 2026-09-08 계약 점검: 이 입력셋은 분석·렌더링의 실제 이미지 후보이며, 결과에는 공통으로
> 제한형 `react_document` 출력 검사를 적용한다. `schemaVersion: "2.0"`, 허용 tag·트리 관계,
> 고유 node id·깊이/노드 제한, `props.imageId` 자산 해석, camelCase 직렬화를 확인한다.

## 범위와 상태

Cleveland Museum of Art Open Access API에서 내려받은 **실물 소장품 60점의 실제 사진**이다. 합성 이미지나 기존 3상품의 crop 증식이 아니다. 직물·상자·금속공예·도자/유리·장신구·가구 각 10점이다. 카테고리는 검색어와 제목/유형/기법으로 자동 선정했으므로 세부 분류의 사람 검수가 필요하다. `ceramic` 코드는 유리 화병도 포함하며, 가구에는 미니어처 의자와 의자 부품이 포함된다.

분석 60건과 렌더링 60건은 **동일한 60개 실물을 공유**한다. 독립 상품 120개라고 보고하지 않는다. 이 버전에는 API·안전성 전용 60건을 새로 수집했다고 주장하지 않는다. 기존 회귀 fixture는 별도로 유지한다.

현대 쇼핑몰 상품이 아닌 역사적 공예품이므로 시각적 형태·근거 없는 설명·원본 보존 평가의 보조 holdout이다. 가격·재고·배송·인증·현대 상품 관리법의 평가 정답은 없다. 실제 판매상품의 대표 성능이나 상용 출시 통과를 이 데이터만으로 주장하면 안 된다.

## 파일

- `manifest.json`: 60개 자산의 원본 URL, CC0 표시, 취득 시각, SHA-256, 크기, 참조 사실.
- `images/`: 원격 URL 만료와 무관하게 사용할 로컬 JPEG 원본(web 크기). 변형하지 않았다.
- `sources/`: API 검색 응답과 개별 소장품 메타데이터 스냅샷.
- `license-policy.html`: 수집 당시 공식 공개 정책. 해시는 manifest에 보관.
- `analysis_60.jsonl`: 초안 생성용 이미지·실제 생성 DTO metadata·검수 항목.
- `rendering_60.jsonl`: 동일 이미지의 렌더링 평가 준비 입력. 승인된 초안 자체는 포함하지 않는다.
- `validation-report.json`: 파일·중복·라이선스 표시·DTO 검증 결과. 모델 점수가 아니다.
- `excluded/`: 검수에서 제외한 정물화 1점의 보존 기록. 평가 입력에는 포함하지 않는다.

모든 `image_path`, `source_record`, `reference_record`는 이 폴더 기준이다. source_metadata는 평가자 전용으로 모델 입력에 자동 주입하지 않는다. `user_hints={}`로 이미지에서 확인하지 못하는 사실을 추측하는지 점검한다.

## 사용

저장소 루트에서 오프라인 무결성 검사:

```sh
PYTHONPATH=src .venv/bin/python scripts/setup_real_eval_dataset.py --validate
```

최초 수집 명령은 위 명령에서 `--validate`를 뺀 것이다. 이미 완성된 snapshot은 덮어쓰지 않는다. 수집에는 네트워크가 필요하며 검증에는 필요하지 않다.

평가 실행 순서:

1. `analysis_60.jsonl` 각 행의 `metadata`를 JSON 문자열로, 로컬 `image_path`를 `product_image`로 내부 생성 API에 multipart 전송한다. 인증은 환경에 주입하고 결과 파일에 기록하지 않는다.
2. 응답의 실제 job_id/status_url을 사용해 DRAFT_READY 또는 FAILED까지 제한된 시간 동안 조회한다. 임의 draft_id를 만들지 않는다. 실행별 idempotency_key에 run_id를 붙여 기존 결과 재사용을 피한다.
3. 생성 결과와 모델·프롬프트 버전, 지연, 실패를 별도 run 폴더에 저장한다. 원본 JSONL의 null 점수를 자동 성공으로 처리하지 않는다.
4. 평가자는 원본 사진과 source_record를 비교한다. 박물관 기록으로만 아는 제작 연도/소재/크기는 이미지에서 관찰한 사실로 인정하지 않는다. 한국어 표현은 영어 제목과 exact match로 채점하지 않는다.
5. 렌더링 영역은 해당 실물의 생성 초안을 사람이 검수·저장한 뒤 실제 draft_id와 승인 DTO로 승인 API를 호출한다. JSONL metadata는 생성 단계용이며 승인 API에 그대로 전송할 수 없다.
6. 렌더링 PNG를 디코딩하고 글자 잘림·실물 형태 변형을 검수한다. `react_document` schema/tree/image reference gate도 실행별로 기록한다. 이 사진들은 단일 시점이므로 다각도 정확성 검증은 N/A로 보고한다.

API 호출/모델 평가/렌더링은 수집 스크립트가 실행하지 않는다. 비용 발생 없이 데이터만 세팅한다. 지표는 [정의서](../../../docs/phase2/metrics-definition.md)를 따른다. 성공률은 실패를 포함한 전체 시도 수와 영역별 분모를 함께 기록한다.

## 출처·권리·정제

공식 [Open Access 정책](https://www.clevelandart.org/open-access), [API 안내](https://www.clevelandart.org/open-access-api), [이용 조건](https://www.clevelandart.org/terms-and-conditions)을 참고한다. 각 레코드의 `share_license_status=CC0`와 실제 이미지 URL 존재를 확인한 것만 수집했다. CC0는 인격권·상표권 등의 일괄 보증이 아니며 박물관 보증/제휴를 암시하지 않는다. attribution은 법적 의무로 단정하지 않지만 원본 소장품 URL과 기관명을 항상 보존한다.

정제: CC0 필터 → 제목/유형/기법 검색어 확인 → object ID 중복 제거 → 이미지 다운로드/디코딩 → 최소 짧은 변 224px → 바이트 SHA-256 중복 제거 → 기존 assets/samples와 동일 바이트 중복 검사. 이미지 확대나 가짜 추가 시점은 만들지 않는다. 원문 HTML 설명은 참조 스냅샷에만 보존하고 실행하지 않는다.

한 기관의 검색 상위 결과를 이용하므로 랜덤 표본이 아니며 유사 시리즈/한 벌의 서로 다른 부품이 포함될 수 있다. object ID는 관리용 그룹이지 통계적 독립성 보장이 아니다. train/dev로 나누지 않고 전량 평가 전용으로 둔다. 기존 원본과의 바이트 중복 0은 모델 사전학습 오염이나 지각적 유사성이 없다는 뜻이 아니다. 사람은 시리즈 그룹, 카테고리 적합성, 사실과 시각적 근거를 검수한 뒤 gold 상태를 승인해야 한다.
