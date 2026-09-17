# 원본 제품 보존형 상세페이지 생성 시스템 설계

작성일: 2026-08-27

> 2026-09-08 구현 반영: 원본 보존 사진·HTML 역할 정책에 더해, 현재 FE 구조 출력은
> 승인 draft에서 조립한 `react_document` schema v2.0 제한 AST다. `page_plan`은 입력/호환
> 계획으로 유지하고, React AST는 `imageId` 자산 참조·허용 tag/tree·safe URL 검증을 통과한
> 뒤 FE/BE 경계로 전달한다. 상세 필드와 전달 위치는 [BE/FE 연동 명세](../../api/be-fe-ai-integration-spec.md)를 따른다.
> 이 문서에 남아 있는 Bedrock 예시는 당시 확장 설계이며, 현재 실행 경로는 로컬 Gemma + Flux2
> MLX Serve다. 외부 provider는 현재 활성 계약에 포함하지 않는다.

## 1. 목적

상품 이미지에서 설명과 상세페이지를 생성하되, 대표·팩샷·디테일의 제품 형태, 문양,
색상, 부품 또는 비율은 원본 픽셀로 보존한다. 단일 제품 lifestyle은 원본 컷아웃을
생성 배경에 합성하고, 세트 상품 lifestyle은 별도 `generated_scene` 참고용 장면으로
새롭게 연출할 수 있다. 생성형 lifestyle은 원본 상품의 정확한 증명 이미지로 취급하지
않으며 FE/BE에 생성 여부와 원본 해시를 함께 전달한다.

이 설계는 기존 AI-FE, AI-BE 계약과 HTML/CSS 렌더러를 유지하면서 이미지 자산 생성,
검증, 저장, 재전송 구조를 운영 가능한 수준으로 개선한다.

## 2. 성공 기준

- 생성형 이미지 모델은 최종 제품 영역을 생성하거나 수정하지 않는다.
- 제품 영역에는 원본 컷아웃과 이동, 균일 확대·축소, 크롭만 허용한다.
- `hero`, `packshot`, `detail`, `lifestyle`, `scale`의 출처와 변환 기록을 남긴다.
- 단일 입력에서 보이지 않는 측면과 후면을 생성하지 않는다.
- 원본 보존 검증에 실패하면 생성 자산 대신 원본 기반 안전 자산을 사용한다.
- HTML 렌더러는 각 사진 역할을 명시적으로 사용하고, 역할 간 암묵적 대체를 하지 않는다.
- FE와 BE DTO에 자산 출처, 원본 해시, 변환, 검증 상태를 전달한다.
- 작업 상태와 BE 재전송 데이터는 프로세스 재시작 뒤에도 복구할 수 있다.
- 실제 비밀값은 예제 파일, 소스, 로그에 남지 않는다.
- 단위, 통합, 렌더링 테스트에서 위 규칙을 자동 검증한다.

## 3. 고려한 접근

### 3.1 프롬프트 강화와 낮은 image-to-image strength

구현이 가장 작지만 채택하지 않는다. 실제 시험에서 낮은 strength에서도 문양과 부품이
달라졌으며, strength를 올리면 제품 구조가 더 크게 바뀌었다. 프롬프트와 negative prompt는
확률적 지시이므로 제품 동일성을 보장하는 통제 수단이 아니다.

### 3.2 단일 이미지 기반 신규 구도·3D 재구성

측면과 후면 이미지를 만들 수 있지만 채택하지 않는다. 입력에 없는 면을 추정해야 하므로
원본 보존 조건과 충돌한다. 향후 정면, 측면, 후면 원본이 모두 제공될 때 별도 기능으로
검토한다.

### 3.3 원본 컷아웃과 생성 배경의 결정적 합성

채택한다. 배경 제거 단계는 알파 마스크만 만들고 제품 RGB는 원본에서 복사한다. AI 배경과
비교 대상은 제품과 분리해 생성하고, 최종 합성은 로컬 이미지 처리기로 수행한다. 결과의
출처와 변환을 검증할 수 있고 실패 시 원본으로 안전하게 되돌릴 수 있다.

## 4. 목표 데이터 흐름

```text
FE 이미지 업로드
  ↓
입력 검증 + 원본 자산 영속 저장 + SHA-256
  ↓
Bedrock Nova 분석 → ProductProfileDto + 분류 confidence
  ↓
공예 후보 confidence가 기준 이상이면 근거 검색
  ↓
제품 컷아웃 생성
  ├─ 배경 제거기는 알파 마스크만 생성
  └─ RGB는 원본에서 복사
  ↓
PhotoPlan 생성
  ├─ hero: 원본 컷아웃 + 중립 배경
  ├─ packshot: 원본 컷아웃 + #FFFFFF
  ├─ detail: 원본 이미지의 실제 영역 크롭
  ├─ lifestyle: 단일 제품이면 AI 배경 + 원본 컷아웃, 세트면 생성형 활용 장면
  ├─ scale: 단일 제품이면 AI 배경/비교 대상 + 원본 컷아웃, 세트면 원본 배열 보존
  └─ alternate: 추가 원본 구도가 있을 때만 사용
  ↓
제품 보존 검증
  ├─ source/cutout 해시와 변환 기록
  ├─ 제품 영역 생성 금지 확인
  └─ 실패 시 원본 기반 fallback
  ↓
HTML/CSS 렌더 → 전체 PNG + 섹션 PNG
  ↓
자산 저장 → FE URL/Base64 결과 + BE outbox
  ↓
BE 멱등 적재 및 재시도
```

## 5. 컴포넌트 경계

### 5.1 SourceAssetStore

원본과 생성 결과를 영속 저장한다. 인터페이스는 `put`, `get`, `exists`를 제공하고 자산 ID,
MIME type, 크기, SHA-256, 저장 위치를 반환한다.

- 개발 기본 구현: 프로젝트 외부 또는 설정된 데이터 디렉터리의 파일 저장소
- 테스트 구현: 메모리 저장소
- 운영 구현 경계: S3 저장소와 signed URL 발급
- 같은 SHA-256 원본은 중복 저장하지 않는다.

### 5.2 ProductCutoutExtractor

입력 이미지에서 제품 알파 마스크를 만든다. 추출기는 RGB 이미지를 새로 생성하지 않는다.
마스크가 비어 있거나, 전체 프레임을 덮거나, 신뢰 기준을 만족하지 못하면 실패한다.

초기 구현은 흰색 또는 단색 배경에 대한 결정적 마스크 추출을 제공한다. 복잡한 배경에서는
안전하게 실패해 원본 이미지를 사용한다. 외부 배경 제거 모델은 동일 인터페이스 뒤에 둘 수
있지만 출력은 마스크로만 수용한다.

### 5.3 BackgroundGenerator

단일 제품의 `lifestyle`과 `scale`에는 제품 없는 배경만 생성한다. 세트 상품의 `lifestyle`에는
완성된 활용 장면을 생성할 수 있으며 이때 출력은 별도 `generated_scene` 자산으로 표시한다.
완성 장면 생성 요청에는 원본 제품 바이트를 전달하지 않고, 분석된 구성품·사용 맥락만 단서로
사용한다. 따라서 세트 lifestyle은 상품 식별·디테일 검증용이 아니라 실제 사용 맥락을 보여주는
참고용 이미지다.
프로필의 `usage_scene`, 제품 크기 인상, 공예 맥락을 사용하되 제품이나 유사 제품을 배경에
그리지 않도록 한다. 결과에 제품처럼 보이는 주 피사체가 포함될 가능성이 있으면 합성 전에
검토 또는 fallback한다. 프로필이 `catalog-grid`이고 세트·컬렉션이거나 보이는 구성품이
3개 이상이면 생성 배경을 사용하지 않고 입력 이미지의 실제 배열을 `FALLBACK`으로 보존한다.
여러 제품의 접점·겹침·상대 크기를 생성 모델이 바꾸지 못하게 하는 안전 정책이다.

### 5.4 SourcePreservingPhotoComposer

컷아웃과 배경을 합성한다. 허용 변환은 이동, 균일 확대·축소, 크롭, 알파 합성이다. 제품
RGB의 색보정, 재조명, 왜곡, 회전 원근 변형, 생성형 인페인팅은 금지한다.

컷별 정책:

- `hero`: 원본과 동일한 시점, 중립 배경, 제품 중심 배치
- `packshot`: 흰 배경, 제품 중심 배치
- `detail`: 원본 관찰 또는 feature evidence가 가리키는 영역의 크롭 1컷
- `detail-02`: 사진이 부족할 때만 좌측 사선 각도 보존을 프롬프트로 생성하는 `generated_view` 참고 자산
- `detail-03`: 표면·문양 매크로 `generated_view` 참고 자산
- `detail-04`: 제품별 실제 사용 상황 `generated_view` 참고 자산
- `detail-05`: 탑뷰·에디토리얼 배치 `generated_view` 참고 자산
- 생성 실패 시 각 슬롯은 원본 크롭으로 대체
- `lifestyle`: 단일 제품은 실제 사용 배경 위에 원본 컷아웃을 낮은 표면에 접지해 배치; 세트는 생성형 활용 장면을 `generated_scene`으로 생성
- `scale`: 단일 제품은 비교 대상과 겹치지 않게 원본 컷아웃 배치; 세트는 원본 배열 보존
- `alternate`: 사용자가 제공한 추가 원본 이미지가 있을 때만 생성

### 5.5 ProductFidelityValidator

각 자산이 `source`, `source_crop`, `source_composite` 중 하나인지 확인한다. 생성 참고 자산은
`lifestyle/generated_scene`과 `detail-02~detail-05/generated_view` 조합만 허용한다. 두 모드 모두
`product_generated=true`·`background_generated=true`·원본 해시가 맞을 때만 허용한다.
검증 결과는 `VERIFIED`, `FALLBACK`, `GENERATED`, `REJECTED`로 기록한다.

균일 확대·축소는 보간 때문에 바이트 단위 동일 비교가 불가능하므로, 원본 자산 해시,
컷아웃 해시, 알파 마스크 해시, 변환 행렬을 기록하고 동일 입력으로 재합성했을 때 같은
결과가 나오는지 검증한다.

### 5.6 JobRepository와 DeliveryOutbox

현재 프로세스 메모리 작업 저장을 대체하는 인터페이스다. 개발 기본은 SQLite로 구현한다.
작업 상태, 요청 ID, 원본 자산 ID, 결과 자산 ID, 오류, BE 전송 payload를 저장한다.

BE 전송은 outbox 상태 `PENDING`, `DELIVERING`, `DELIVERED`, `FAILED`를 갖고 재시작 뒤에도
같은 `generation_id`로 재시도한다. 실제 분산 큐나 SQS는 이 저장소 위의 별도 worker로
교체할 수 있게 한다.

## 6. API와 DTO 변경

### 6.1 FE 입력

기존 `product_image`는 기본 원본으로 유지한다. 추가 구도가 있는 경우 선택 필드
`product_images`를 반복 multipart file로 받는다. 첫 번째 이미지는 primary이며 각 추가
이미지는 사용자가 촬영한 원본일 때만 alternate 후보가 된다.

### 6.2 사진 자산 메타데이터

각 제품 사진에 다음 정보를 추가한다.

```json
{
  "photo_id": "lifestyle",
  "asset_mode": "generated_scene",
  "source_asset_id": "asset-uuid",
  "source_sha256": "...",
  "cutout_sha256": null,
  "mask_sha256": null,
  "background_generated": true,
  "product_generated": true,
  "transform": {
    "scale": 0.72,
    "x": 132,
    "y": 240,
    "crop": null
  },
  "fidelity_status": "GENERATED"
}
```

`asset_mode`은 `source`, `source_crop`, `source_composite`, `generated_scene`,
`generated_view`를 사용한다. `generated_scene`은 `lifestyle`, `generated_view`는
`detail-02`·`detail-03`·`detail-04`·`detail-05`에만 허용되는 참고용 자산이다.

### 6.3 FE 결과

작은 개발 환경에서는 기존 Base64를 유지할 수 있다. 자산 저장소가 URL을 제공하면 URL을
우선 반환하고 Base64는 생략한다. 전체 상세페이지와 섹션, 제품 사진을 모두 Base64로
중복 반환하지 않도록 응답 모드를 설정으로 선택한다.

### 6.4 BE 적재

BE 메타데이터에는 source asset과 photo provenance를 포함한다. 렌더 전 실제 원본
SHA-256, crop 범위/픽셀, composite cutout·mask hash와 불투명 제품 픽셀을 검증한다.
검증되지 않았거나 `fidelity_status`가 `REJECTED`인 자산은 multipart에 포함하지 않는다.
`FALLBACK`은 원본 기반 안전 자산임을 표시해 저장할 수 있다.

## 7. HTML 렌더링 정책

렌더러는 명시적인 역할 매핑만 사용한다.

- `HERO_IMAGE` → `hero`
- `PACKSHOT_IMAGE` → `packshot`
- `USAGE_IMAGE` → `lifestyle`
- `SCALE_IMAGE` → `scale`
- `DETAIL_IMAGE` → `detail`

요청한 역할이 없으면 원본 이미지로 fallback한다. `lifestyle`이 없다고 `alternate`를 대신
사용하지 않는다. 상세 gallery는 원본 detail crop만 사용하고 생성 배경 이미지를 제품
디테일로 표시하지 않는다.

## 8. 분석과 공예 검색

`ProductProfileDto`에 제품 분류와 공예 분류 confidence, 분류 근거, 후보 유형을 추가한다.
공예 검색은 단일 boolean이 아니라 다음 조건 중 하나를 만족할 때 실행한다.

- `is_traditional_craft=true`
- 공예 confidence가 설정 기준 이상
- 후보 유형 또는 키워드가 공예 분류 사전에 포함

낮은 confidence 결과는 단정형 문구 대신 `가능성이 있는`, `이미지상 확인되는` 표현을
사용한다. 검색 자료는 상품 자체의 진품성 또는 제작기법 증거로 사용하지 않는다.

## 9. 오류와 fallback

- 원본 검증 실패: 요청 실패
- 분석 실패: 작업 실패, 재시도 가능 여부를 provider 오류로 판단
- 마스크 추출 실패: 원본 전체 이미지를 안전 자산으로 사용
- 배경 생성 실패 또는 생성 배경판 객체 안전성 검사 실패: 중립 단색 배경으로 합성
- fidelity 검증 실패: 해당 컷을 버리고 원본 기반 fallback 생성
- HTML 렌더 실패: 작업 실패, 저장된 원본과 profile로 재실행 가능
- BE 전송 실패: 결과를 유지하고 outbox에서 재시도

오류 메시지는 FE에 provider endpoint, credential 정보, raw 응답을 노출하지 않는다.

## 10. 보안

- `.env.example`에는 placeholder만 둔다.
- `.env`, `.env.local`, 자격 증명 파일, 생성된 민감 결과를 `.gitignore`에 등록한다.
- 이미 노출된 AWS와 Gemini 키는 폐기하고 재발급한다.
- AWS는 로컬 profile, CI OIDC, ECS/EKS/EC2 IAM role을 우선한다.
- 운영 secret은 Secrets Manager 또는 배포 플랫폼 secret으로 주입한다.
- Bedrock IAM 권한은 사용하는 분석 모델과 배경 모델 ARN으로 제한한다.
- 로그에는 키, 원본 bytes, Base64 결과, BE 인증 토큰을 기록하지 않는다.

## 11. 작업 상태와 운영

실제 단계에 맞춰 상태를 기록한다.

```text
QUEUED
→ ANALYZING
→ EXTRACTING
→ GENERATING_BACKGROUNDS
→ COMPOSING
→ VERIFYING
→ RENDERING
→ DELIVERING
→ COMPLETED | FAILED
```

비용은 분석 호출, 배경 생성 호출, fallback 수, 컷별 처리 시간을 기록한다. 요청 기본값은
`hero`, `packshot`, `detail`, `lifestyle` 네 장으로 하고, `scale`은 옵션, `alternate`는 추가
원본이 있을 때만 활성화한다.

## 12. 테스트 전략

### 단위 테스트

- 제품 컷아웃 RGB가 원본 RGB에서만 유래하는지 검증
- 단색 배경 마스크 추출 성공과 복잡 배경 fallback 검증
- 합성 transform 재현성과 provenance 해시 검증
- detail crop이 원본 범위를 벗어나지 않는지 검증
- 단일 입력에서 alternate가 생성되지 않는지 검증
- background generator에 원본 제품 bytes가 전달되지 않는지 검증
- fidelity 실패 자산이 renderer와 BE payload에서 제외되는지 검증
- HTML 역할 매핑과 원본 fallback 검증
- SQLite job/outbox 재시작 복구와 멱등 재전송 검증
- 비밀값 placeholder와 ignore 규칙 검증

### 통합 테스트

- 이미지 업로드부터 전체 페이지, 섹션, FE DTO 생성까지 실행
- backend fake server에 provenance 포함 multipart 전달
- 프로세스 재시작 후 작업 조회와 BE 재전송
- Bedrock adapter payload가 제품 이미지 없이 배경 생성만 요청하는지 검증

### 시각 회귀 테스트

- 기준 원본으로 hero, packshot, detail, lifestyle 합성 결과 저장
- 제품 영역의 문양, 부품, 비율이 원본과 일치하는지 자동 비교
- HTML 전체 페이지와 섹션 스냅샷 비교

## 13. 구현 순서

1. 비밀값 제거, ignore 규칙, 기본 source-safe 모드 적용
2. provenance DTO와 photo plan 도입
3. 마스크 추출, 컷아웃, 결정적 compositor, fidelity validator 구현
4. Bedrock provider를 제품 image-to-image에서 배경 생성 전용으로 전환
5. HTML 역할 매핑과 detail crop 사용 방식 수정
6. 다중 원본 입력과 alternate 정책 적용
7. SQLite JobRepository와 DeliveryOutbox 적용
8. 자산 저장소와 URL/Base64 응답 정책 적용
9. 공예 confidence와 검색 trigger 개선
10. 전체 단위·통합·시각 회귀 테스트와 실제 smoke test

## 14. 범위 경계

이번 구현은 코드, 로컬 영속 저장, 선택적 AWS 어댑터 경계, 문서와 테스트를 포함한다.
AWS 계정에 S3 bucket, SQS queue, IAM role 또는 Secrets Manager secret을 실제 생성하거나
배포하지 않는다. 외부 인프라 생성은 별도 배포 작업으로 다룬다.
