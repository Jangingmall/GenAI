# 파일럿 1차 카피 심층 분석 및 프롬프트 개선 후보 보고서

- 작성일: 2026-09-09
- 대상 실행: `generated/evaluation/pilot-20260909-191344` (6건)
- 분석 대상: 각 case의 `result_summary.json` 내 카피 (`display_name`, `classification_reason`, `summary`, `page_plan`의 모든 블록)
- 대조 근거: 
  1. 원본 이미지 (`data/evaluation/cma_real_v1/images/*`)
  2. 클리블랜드 미술관(CMA) 원본 소스 레코드 (`data/evaluation/cma_real_v1/sources/*.json`)
- 분석 목적: 사람 정량 검수 착수 전, 생성 카피의 사실 근거성 검증 및 `src/detail_page_ai/prompts.py` 귀책 결함/개선 후보 도출
- 주의: 본 문서는 정량 점수(1~5점 등)를 매기지 않으며, 모든 평가는 원문 그대로의 인용에 기반합니다.

---

## 1. Case별 상세 카피 분석

각 케이스별로 (A) 이미지 관찰 가능 사실, (B) 소스 레코드로만 확인 가능한 사실의 단언 여부, (C) 근거 없는 주장(지어냄)을 원문 인용과 함께 분석합니다.

---

### Case 1. 직물 (`textile` / `analysis-cma-102980` / `cma-102980`)

#### [실제 사실 대조 (CMA 소스 레코드)]
- **소장품명**: Fragment (직물 조각)
- **제작자/시기/문화권**: Gunta Stölzl (독일, 1897–1983), c. 1928, 독일 바우하우스(Bauhaus)
- **재질/기법**: Cotton and rayon; 4-ply jacquard (면, 레이온, 4겹 자카드 직조)
- **규격**: 14.6 x 14.6 cm

#### [생성 카피 주요 원문]
- `display_name`: `"흑백 기하학적 무늬 직물"`
- `classification_reason`: `"이미지에서 직물의 조직, 반복되는 기하학적 문양, 그리고 가장자리와 하단의 실밥이 명확하게 관찰되어 직물류로 분류합니다. 전통 직조 기법일 가능성이 있으나, 구체적인 기법명은 확인이 필요합니다."`
- `hero.body`: `"회색과 검은색이 어우러진 기하학적 무늬가 반복되는 직물입니다. 붉은 실선이 세로로 지나가며 전체적인 균형을 잡아줍니다."`
- `feature_grid.items`:
  - 1: `"정사각형 격자 패턴"` / `"표면 전체에 걸쳐 규칙적으로 반복되는 회색과 검은색의 작은 사각형 무늬입니다."`
  - 2: `"검은색과 붉은색 라인"` / `"직물의 폭을 따라 세로로 배치된 검은색 띠와 붉은색 실선이 대비를 이룹니다."`
  - 3: `"거친 실밥"` / `"하단과 측면 가장자리에서 직조된 실의 끝이 드러나 있는 상태입니다."`
- `usage_scene.body`: `"정제된 흑백 무늬와 붉은 실선의 대비는 공간의 포인트로 활용하기에 적합합니다. 벽걸이 소품이나 테이블 위 장식 등 다양한 인테리어 컨셉에 어울릴 수 있습니다."`
- `info_table.items`: `색상: 회색, 검은색, 붉은색`, `무늬: 기하학적 격자`, `소재: 확인 필요`, `크기: 확인 필요`
- `notice.body`: `"관리 안내는 제공되지 않아 확인 필요합니다."`

#### [평가 및 분류]
- **(A) 이미지 관찰 사실 (우수)**:
  - 색상(회색, 검은색, 붉은 실선), 무늬(정사각형/직사각형 격자), 구조(하단 및 측면 실밥 노출) 등 시각적 사실 묘사가 매우 정확함.
  - `info_table`에서 소재와 크기를 단정하지 않고 `"확인 필요"`로 처리한 점이 뛰어남.
- **(B) 소스 레코드 관련 사실 단언 여부 (우수)**:
  - 바우하우스, 군타 슈퇼츨, 면/레이온 자카드 등 외부 지식을 시각 관찰로 거짓 주장하지 않음.
- **(C) 근거 없는 주장 (환각 / 프롬프트 지침 위반)**:
  - `usage_scene.body`에서 `"공간의 포인트로 활용하기에 적합합니다. 벽걸이 소품이나 테이블 위 장식 등 다양한 인테리어 컨셉에 어울릴 수 있습니다."`라고 서술함.
  - 실제 원본은 14.6cm 크기의 바우하우스 직물 단편(Fragment)인데, 벽걸이 소품이나 테이블 위 장식으로 임의 단정함.
  - 특히 프롬프트 금지어인 `"공간의 포인트"`가 그대로 노출됨.
  - 또한 모델 내부 `warnings` 필드에 `"검증되지 않은 AI 추정 문구 제외: 공간 소품으로의 활용"`이라고 스스로 경고를 생성했음에도, 고객 노출 `page_plan`에 해당 문구를 그대로 삽입하는 모순이 발생함.

---

### Case 2. 상자 (`box` / `analysis-cma-101636` / `cma-101636`)

#### [실제 사실 대조 (CMA 소스 레코드)]
- **소장품명**: Box with Painted Oxhorn (화각 상자)
- **시기/문화권**: 1800s, 한국 조선시대 (Joseon dynasty, 1392–1910)
- **재질/기법**: painted wood with flattened ox-horn inlay (목재에 쇠뿔을 얇게 펴서 채색한 화각 상자)
- **규격**: 16.5 x 28.6 cm

#### [생성 카피 주요 원문]
- `display_name`: `"황색 바탕 문양 칠기 상자"`
- `product_type`: `"전통 칠기 상자"`
- `craft_type`: `"칠기"` (confidence: 0.88)
- `classification_reason`: `"직사각형 상자의 형태, 뚜껑과 몸체를 나누는 구조, 그리고 표면의 황색·적색 바탕에 동식물 문양을 채색한 칠기 특유의 광택과 결이 이미지에서 명확하게 확인됩니다. 중앙의 금속 자물쇠와 문양 구성은 전통 칠기 상자의 특징과 일치합니다."`
- `hero.body`: `"직사각형의 단정한 형태 위에 황색과 적색을 바탕으로 한 화려한 문양이 채색된 전통 칠기 상자입니다. 뚜껑과 몸체를 나누는 구조와 중앙의 금속 자물쇠가 시각적 중심을 이룹니다."`
- `statement.body`: `"상자의 표면은 황색을 주조로 하고, 적색 띠를 따라 다양한 동식물 문양이 배치되어 있습니다. 칠기 특유의 매끄러운 표면 위를 따라 흐르는 색의 대비가 이 제품의 가장 큰 특징입니다."`
- `feature_grid.items`:
  - 1: `"직사각형 형태"` / `"뚜껑과 몸체가 명확히 구분되는 직사각형 형태를 갖추고 있습니다."`
  - 2: `"황색·적색 바탕"` / `"황색 바탕과 적색 띠가 교차하며 시각적 리듬을 만듭니다."`
  - 3: `"동식물 문양"` / `"호랑이, 사슴, 연꽃, 새 등 다양한 동식물 문양이 채색되어 있습니다."`
- `info_table.items`: `재질: 확인 필요 (칠기 특유의 광택이 보이나 정확한 재질은 확인 필요)`, `크기: 확인 필요`

#### [평가 및 분류]
- **(A) 이미지 관찰 사실 (우수)**:
  - 문양에 등장하는 구체적 동식물(`"호랑이, 사슴, 연꽃, 새"`)을 사진에서 정확히 식별하여 서술함.
  - 직사각형 상자 구조와 구리색 금속 자물쇠의 형태 묘사가 정확함.
- **(B) 소스 레코드 관련 사실 단언 여부 (치명적 결함: 공예 기법 오판 및 날조)**:
  - 본 제품의 실제 공예 기법은 **화각(Oxhorn inlay)**이나, 모델은 표면 광택만 보고 **"칠기(Lacquerware)"**로 단정함.
  - `"칠기 특유의 광택과 결이 이미지에서 명확하게 확인됩니다"`, `"칠기 특유의 매끄러운 표면"`이라고 시각적으로 확인할 수 없는 제작 기법을 시각 관찰로 거짓 주장함 (`source_facts_not_claimed_as_visually_observed` 위반).
- **(C) 근거 없는 주장 및 카피 간 내부 모순**:
  - `info_table`에서는 `"재질: 확인 필요 (칠기 특유의 광택이 보이나 정확한 재질은 확인 필요)"`라고 적었음에도, `display_name`, `product_type`, `hero`, `statement`, `closing` 전체에서 일관되게 `"전통 칠기 상자"`라고 확정적 단언을 내림.
  - 이는 프롬프트의 지시(L196-198: "If material is unknown in info_table, do not assert ... Use a neutral product noun")를 정면 위반한 내부 모순임.

---

### Case 3. 금속기 (`metalware` / `analysis-cma-114971` / `cma-114971`)

#### [실제 사실 대조 (CMA 소스 레코드)]
- **소장품명**: Covered Cup (뚜껑 달린 잔)
- **시기/문화권**: c. 1820, 프랑스 파리, 왕정복고기 (France, Paris, Restoration period)
- **재질/기법**: Silver gilt (은에 금도금)
- **규격**: 29.8 x 20.3 x 15.2 cm

#### [생성 카피 주요 원문]
- `display_name`: `"금색 양각 문양 뚜껑 달린 용기"`
- `product_type`: `"뚜껑 달린 금속 용기"`
- `craft_type`: `"금속 공예"` (confidence: 0.85)
- `classification_reason`: `"이미지에서 정교한 양각 문양, 양쪽 손잡이의 소용돌이 장식, 그리고 뚜껑 꼭대기의 잎사귀 모양 장식이 명확하게 관찰됩니다. 금색 금속 소재의 표면 질감과 전통적인 주조/단조 기법의 특징이 드러나 있어 전통 금속 공예품으로 분류합니다."`
- `hero.body`: `"정교한 양각 문양과 금색 금속의 광택이 조화를 이루는 뚜껑 달린 용기입니다. 대칭적인 형태와 장식적인 손잡이가 시각적 안정감을 주며, 공예적 정교함을 드러냅니다."`
- `feature_grid.items`:
  - 1: `"양각 문양"` / `"날개 달린 인물과 왕관, 화환"` / `"몸체 중앙에 정교하게 새겨진 양각 장식"`
  - 2: `"손잡이"` / `"소용돌이 장식"` / `"양쪽 손잡이 끝단에 곡선 소용돌이 형태"`
  - 3: `"뚜껑 장식"` / `"잎사귀 모양"` / `"뚜껑 꼭대기에 자리한 입체 장식"`
- `detail_split.body`: `"몸체 표면은 부드러운 광택을 띠며, 양각 문양 주변의 미세한 질감이 빛을 받아 드러납니다. 뚜껑 표면에는 손으로 다듬은 듯한 흔적이 보이며, 금속의 자연스러운 결을 보여줍니다."`
- `info_table.items`: `형태: 원통형 몸체, 뚜껑, 양쪽 손잡이`, `장식: 양각 문양, 잎사귀 장식`, `색상: 금색 금속`, `소재: 확인 필요`, `크기: 확인 필요`
- `closing.body`: `"금속의 광택과 정교한 양각 문양, 그리고 균형 잡힌 형태가 어우러진 이 용기는 시각적 중심을 이루는 공예품입니다."`

#### [평가 및 분류]
- **(A) 이미지 관찰 사실 (매우 우수)**:
  - 문양 세부 요소인 `"날개 달린 인물과 왕관, 화환"`, 손잡이의 `"소용돌이 장식"`, 뚜껑의 `"잎사귀 모양"`을 완벽하게 시각적으로 포착함.
  - 순금인지 도금인지 모르는 상태에서 `"금색 금속"`으로 안전하게 절제하여 표현함.
- **(B) 소스 레코드 관련 사실 단언 여부 (우수)**:
  - 1820년대 프랑스 왕정복고기 유물이라는 비시각적 배경을 사진에서 보았다고 날조하지 않음.
- **(C) 근거 없는 주장 / 상투적 표현**:
  - `classification_reason`에서 `"전통적인 주조/단조 기법의 특징이 드러나 있어"`라고 사진만으로 주조/단조 공법을 추정 단언함.
  - `closing.body`에서 금지 표현인 `"시각적 중심"`(`prompts.py` L203 금지어)을 사용함.

---

### Case 4. 도자기 (`ceramic` / `analysis-cma-122443` / `cma-122443`)

#### [실제 사실 대조 (CMA 소스 레코드)]
- **소장품명**: Prunus Vase (Meiping) with Blossoming Lotus (연화문 매병)
- **시기/문화권**: late 1400s, **중국 명나라 경덕진요 (China, Jiangxi Province, Jingdezhen kilns, Ming dynasty)**
- **재질/기법**: Porcelain with polychrome glazes, **Fahua ware (법화, 法華)**
- **규격**: 지름 19 cm, 높이 37.5 cm

#### [생성 카피 주요 원문]
- `display_name`: `"청자 연화문 병"`
- `product_type`: `"도자기"`
- `craft_type`: `"청자"` (confidence: 0.90)
- `classification_reason`: `"이미지에서 확인되는 청색 유약, 부각된 연꽃 문양, 그리고 병의 형태는 한국 전통 도자기, 특히 청자 계열의 특징을 명확히 보여줍니다."`
- `hero.title`: `"청자 연화문 병"`
- `hero.body`: `"깊은 청색의 유약 위에 부각된 연꽃 문양이 조화를 이루는 전통 도자기 병입니다. 고요한 색감과 정교한 장식은 시간의 흐름을 담은 듯한 인상을 줍니다."`
- `statement.body`: `"이 병은 청색 유약의 깊은 색감과 부각된 연꽃 문양의 대비를 통해 시각적 깊이를 더합니다. 표면의 질감과 문양의 입체감은 전통 도자기 공예의 정수를 보여줍니다."`
- `feature_grid.items`:
  - 1: `"청색 유약"` / `"유약의 색상은 청자 계열의 특징을 보여줍니다."`
  - 2: `"부각된 연꽃 문양"` / `"문양의 부각은 전통 도자기 장식 기법의 하나입니다."`
- `info_table.items`: `제품명: 청자 연화문 병`, `재질: 도자기`, `색상: 청색`, `문양: 연화문` (확인 필요 항목 없음)
- `closing.body`: `"이 청자 연화문 병은 깊은 색감과 정교한 문양을 통해 시간의 흐름을 담은 아름다움을 보여줍니다. 전통 도자기 공예의 정수를 담은 이 병은 공간에 고요한 아름다움을 더할 것입니다."`

#### [평가 및 분류]
- **(A) 이미지 관찰 사실 (부분 양호)**:
  - 연꽃 문양의 부각(입체적 선), 좁은 목과 둥근 몸통 형태는 관찰에 부합함.
- **(B) 소스 레코드와 정면 충돌 (파일럿 최악의 결함: 국가·문화권 및 공예사적 왜곡)**:
  - 실제 유물은 **중국 명나라 경덕진의 대표적 다채 유약 도기인 법화(Fahua ware)**임.
  - 그러나 모델은 코발트 블루/터콰이즈 빛 유약 색상만 보고 **"한국 전통 도자기, 특히 청자 계열의 특징을 명확히 보여줍니다"**라고 단정함.
  - 제품명을 `"청자 연화문 병"`으로 명명하고, `craft_type`을 `"청자"`, 확신도를 0.90으로 극단적으로 높게 설정함.
  - 명나라 법화기는 고려/조선의 비색 청자(Celadon)와 소성 온도, 태토, 안료 기법이 완전히 다름에도 불구하고, 청(靑)색이라는 단어에 갇혀 한국 청자로 둔갑시킴 (`source_facts_not_claimed_as_visually_observed` 및 P0 안전 정책 정면 위반).
- **(C) 근거 없는 주장 및 검증 회피**:
  - 다른 5개 케이스와 달리 `info_table`에서 `"확인 필요"` 항목을 단 하나도 두지 않고 모두 확정 사실로 채워 넣음.

---

### Case 5. 장신구 (`jewelry` / `analysis-cma-109609` / `cma-109609`)

#### [실제 사실 대조 (CMA 소스 레코드)]
- **소장품명**: Necklace (목걸이)
- **시기/문화권**: 6th century, 비잔틴 제국 (Byzantine, 6세기)
- **재질/기법**: Gold, pearls, glass, emerald, sapphire, amethyst (금, 진주, 유리, 에메랄드, 사파이어, 자수정)
- **규격**: 길이 33.7 cm

#### [생성 카피 주요 원문]
- `display_name`: `"금·보석 목걸이"`
- `product_type`: `"목걸이"`
- `is_traditional_craft`: `False` (confidence: 0.40)
- `craft_type`: `None`
- `classification_reason`: `"이미지에서 금색 금속 체인, 중앙의 타원형 보석 세 개, 그리고 다채로운 색상의 구슬이 명확하게 관찰되어 목걸이류로 분류합니다. 전통 공예품으로 단정하기에는 제작 맥락과 기법 정보가 부족합니다."`
- `hero.body`: `"다채로운 색상의 구슬과 보석이 조화를 이루는 목걸이입니다. 중앙의 타원형 보석 세 개가 시선을 끄며, 금색 금속 체인이 전체를 부드럽게 연결합니다."`
- `feature_grid.items`:
  - 1: `"중앙 보석"` / `"중앙에 붉은색 보석 두 개와 은백색 보석 한 개가 배치되어 있습니다."`
  - 2: `"구슬 조합"` / `"녹색, 흰색, 흑백 무늬 구슬이 번갈아 배치되어 리듬감을 줍니다."`
  - 3: `"금색 체인"` / `"구슬과 보석을 연결하는 금색 금속 체인이 전체 구조를 지탱합니다."`
- `usage_scene.body`: `"정장이나 드레스와 함께 착용하여 격식을 더하거나, 캐주얼한 옷차림에 포인트로 활용하는 것을 제안합니다."`
- `info_table.items`:
  - `제품 유형: 목걸이` / `목에 걸erek 착용하는 장신구`
  - `주요 소재: 금색 금속, 보석, 구슬`
- `closing.body`: `"금색 금속과 다양한 색상의 보석, 구슬이 어우러져 독창적인 매력을 선사하는 목걸이입니다."`

#### [평가 및 분류]
- **(A) 이미지 관찰 사실 (매우 우수)**:
  - 타원형 보석의 배치(붉은색 2개, 은백색 1개), 구슬 색상 조합(녹색, 흰색, 흑백 무늬)이 사진과 정확히 일치함.
  - `is_traditional_craft`를 `False`로 판정하고, `"전통 공예품으로 단정하기에는 제작 맥락과 기법 정보가 부족합니다"`라고 서술한 점은 전체 파일럿 중 가장 이상적인 보수적 판정 사례임.
- **(B) 소스 레코드 관련 사실 단언 여부 (우수)**:
  - 비잔틴 6세기 유물임을 알 수 없는 상태에서 임의로 시기나 지역을 날조하지 않음.
- **(C) 근거 없는 주장 및 텍스트 결함**:
  - **오타 누출**: `info_table` 설명에 `"목에 걸erek 착용하는 장신구"`라는 오타가 발생함 ("걸어서"의 토크나이저 오류 추정).
  - 6세기 비잔틴 고대 유물임에도 `usage_scene`에서 `"정장이나 드레스... 캐주얼한 옷차림에 포인트로 활용"`과 같이 현대 패션 이커머스 카피로 과도하게 일반화함.

---

### Case 6. 가구/목공 (`furniture` / `analysis-cma-110793` / `cma-110793`)

#### [실제 사실 대조 (CMA 소스 레코드)]
- **소장품명**: Part of a chair (의자 부품/다리)
- **시기/문화권**: 1900s, 아프리카 콩고민주공화국 망베투 양식 (Democratic Republic of Congo, Mangbetu style)
- **재질/기법**: Wood (나무 조각)
- **규격**: 49.9 x 2.6 x 4.6 cm

#### [생성 카피 주요 원문]
- `display_name`: `"곡선 목제 도구"`
- `product_type`: `"목제 생활 도구"`
- `is_traditional_craft`: `False` (confidence: 0.30)
- `craft_type`: `None`
- `classification_reason`: `"이미지상 나무 소재로 제작된 긴 막대형 도구로, 한쪽 끝이 넓고 다른 쪽은 좁은 형태를 띱니다. 표면의 나무 결과 뚫린 구멍이 관찰되며, 전통 공예품으로 단정하기에는 제작 맥락이 부족합니다."`
- `hero.body`: `"자연스러운 곡선을 가진 나무 도구입니다. 한쪽 끝이 넓고 다른 쪽은 좁아지는 형태와 표면의 나무 결이 특징입니다."`
- `feature_grid.items`:
  - 1: `"곡선 형태"` / `"도구의 전체적인 형태가 자연스러운 곡선을 이루고 있습니다."`
  - 2: `"나무 결"` / `"표면에 나무의 결이 선명하게 드러나 소재의 특징을 보여줍니다."`
  - 3: `"구멍 구조"` / `"본체와 끝단에 뚫린 구멍이 관찰되며, 특정 기능을 위한 것으로 보입니다."`
- `usage_scene.body`: `"이 도구는 전통적인 생활 공간이나 작업 환경에서 활용될 수 있는 형태를 가지고 있습니다. (활용 방식은 추측입니다)"`
- `info_table.items`: `소재: 나무`, `형태: 곡선 막대형`, `크기: 확인 필요`, `용도: 확인 필요`
- `closing.body`: `"나무의 결과 형태가 어우러진 이 도구는, 사용의 흔적이 담긴 생활의 도구로 다가옵니다."`

#### [평가 및 분류]
- **(A) 이미지 관찰 사실 (우수)**:
  - 실제 유물이 의자의 한 부품(Part of a chair)이지만, 단일 막대 사진만으로는 의자임을 알 수 없으므로 무리하게 의자로 단정하지 않고 `"곡선 목제 도구"`로 보수적 접근을 취함.
  - 나무 결, 한쪽이 넓은 비대칭 형태, 뚫린 구멍 등 시각적 요소를 매우 정직하게 서술함.
  - `is_traditional_craft: False`로 적절히 제어함.
- **(B) 소스 레코드 관련 사실 단언 여부 (우수)**:
  - 콩고 망베투 부족 목공예라는 출처 사실을 자의적으로 창작하지 않음.
- **(C) 고객 노출 문장 내 메타 괄호 노출**:
  - `usage_scene.body` 끝에 `"(활용 방식은 추측입니다)"`라는 AI 프롬프트 준수용 자가 해명 문구가 고객 노출 카피에 괄호째 그대로 출력됨.

---

## 2. 6건 공통 반복 패턴 (Cross-Cutting Patterns)

프롬프트 귀책으로 판단되는 공통 패턴과 발생 건수입니다.

| 번호 | 공통 패턴 | 발생 건수 | 대표 사례 및 현상 |
|:---:|---|:---:|---|
| **패턴 1** | **`recommended-scenes` 100% 동일 문구 복제** | **6 / 6건 (100%)** | 6건 전건에서 `01: 여백 있는 테이블`, `02: 부드러운 자연광`, `03: 차분한 배경색` 항목이 글자 하나 안 틀리고 동일하게 출력됨. |
| **패턴 2** | **Hero 첫 문장 템플릿 고착화** | **5 / 6건 (83%)** | `"[A]와 [B]가 조화를 이루는 [명사]입니다"` (Case 3, 4, 5)<br>`"[A] 위에 [B]가 채색된 [명사]입니다"` (Case 2)<br>`"[A]가 어우러진 [B]가 반복되는 [명사]입니다"` (Case 1) |
| **패턴 3** | **한국 전통 공예 및 기법 과잉 단정** | **2 / 6건 (33%)** | 중국 명나라 자기를 `"한국 전통 도자기, 특히 청자"`로 왜곡(Case 4). 화각 유물을 `"칠기"`로 왜곡(Case 2). |
| **패턴 4** | **`info_table`의 "확인 필요"와 상단 카피 간 모순** | **2 / 6건 (33%)** | 표에서는 `재질: 확인 필요`라 쓰면서 제목과 본문에는 `전통 칠기 상자`로 단정(Case 2). Case 4는 확인 필요를 아예 누락. |
| **패턴 5** | **프롬프트 금지 어휘의 반복 노출** | **4 / 6건 (67%)** | 금지어인 `"공간의 포인트"`(Case 1), `"시각적 중심"`(Case 2, 3), `"매력을 선사하는"`(Case 5)이 그대로 노출됨. |
| **패턴 6** | **고객 노출 카피 내 AI 추측 괄호/메타 발언 노출** | **2 / 6건 (33%)** | `"(활용 방식은 추측입니다)"` 괄호 노출(Case 6), 내부 `warnings`에 제외하라고 쓴 문구를 그대로 본문에 채택(Case 1). |
| **패턴 7** | **관리 안내(Notice)의 100% 완벽한 제어 성공** | **6 / 6건 (100%)** | `care_guide` 부재 시 `"관리 안내는 제공되지 않아 확인 필요합니다."` 100% 일치 준수 (성공 패턴). |

---

## 3. 프롬프트 개선 후보 (`src/detail_page_ai/prompts.py` 분석)

현재 적용된 분석 프롬프트 버전은 `ANALYSIS_PROMPT_VERSION = "analysis-v11-product-intro-copy-brief-care-gate"` 이며, `build_analysis_prompt` 함수와 `reference_guide.py`의 결합으로 프롬프트가 구성됩니다. 각 공통 결함의 원인 문구와 개정 후보를 제안합니다.

---

### 개선 후보 1. 한국 전통성 편향 억제 및 문화권 자의적 단정 금지 (패턴 3 해결)

- **문제점**: 동양풍 유물에 대해 출처 없이 `"한국 전통 도자기, 특히 청자"`(Case 4), `"전통 칠기 상자"`(Case 2)로 임의 귀속시킴.
- **원인 프롬프트 문구**:
  - `prompts.py` L30: `The output language is ko-KR.`
  - `prompts.py` L188: `Set is_traditional_craft to true only when image-visible evidence strongly supports it. Never claim authenticity, maker, provenance, or heritage status.`
  - `reference_guide.py` L112: `The attached reference materials describe a calm, product-first Korean craft-commerce detail page.`
- **분석 (원인 규명)**:
  - 프롬프트 전반이 "한국 공예 상세페이지"로 브리프되어 있어, LLM이 시각적 특징만 보고 한국 전통 공예의 특정 카테고리(청자, 칠기)로 무리하게 매핑함.
  - "진품성/제작자/원산지 주장 금지" 지침은 있으나, **"제공된 데이터에 없는 국가, 문화권, 특정 공예사적 계보(예: 한국 전통, 청자, 분청 등)를 이미지 색상만으로 단정하지 말 것"**이라는 명시적 규칙이 없음.
- **프롬프트 개정 제안 (안)**:
  ```text
  - DO NOT infer a specific country, culture, dynasty, or named craft lineage (e.g. "한국 전통", "조선", "청자", "백자", "칠기") unless explicitly provided in the creator product data.
  - Deep blue, turquoise, or celadon-like glaze is a visual color, NOT proof of Korean celadon ("청자"). When cultural origin is unverified, describe only visible color and form (e.g., "청색 유약 도자기", "채색 장식 상자").
  ```

---

### 개선 후보 2. `info_table`의 "확인 필요"와 전체 카피 간 정합성 강제 (패턴 4 해결)

- **문제점**: `info_table`에 `재질: 확인 필요`라고 표기하면서도 `display_name`, `hero`, `statement`에는 `칠기 상자`라고 단정함.
- **원인 프롬프트 문구**:
  - `prompts.py` L196-198:
    `Apply the same evidence standard to display_name, titles, summary, keywords, features, page_plan and care copy. If material is unknown in info_table, do not assert glass, ceramic, wood, or metal as a fact elsewhere. Use a neutral product noun and describe visible finish.`
- **분석 (원인 규명)**:
  - L197의 금지 예시가 `glass, ceramic, wood, or metal` 4대 기초 소재로만 한정되어 있어, `칠기`, `도자기`, `유리` 등의 가공 공예 명칭이나 `display_name`의 복합 명사에는 적용되지 않는다고 모델이 오판함.
  - 또한 JSON 생성 순서상 `display_name`이 `page_plan`(및 `info_table`)보다 앞에 위치하여, 상단에서 먼저 단정한 단어가 전체 페이지로 전파됨.
- **프롬프트 개정 제안 (안)**:
  ```text
  - Noun Consistency Enforcement: If a specific craft material or technique (e.g., lacquerware/칠기, celadon/청자, brass/유기, oxhorn/화각) cannot be verified with 100% visual certainty, you MUST use a generic functional noun (상자, 보관함, 병, 용기) in display_name, product_type, and hero title.
  - Never allow display_name to assert a material/technique that is labeled "확인 필요" in info_table.
  ```

---

### 개선 후보 3. `recommendation` 블록의 모델 생성 유도 및 하드코딩 폴백 의존 탈피 (패턴 1 해결)

- **문제점**: 6건 전건에서 목걸이, 직물 조각, 도자기 가릴 것 없이 `"01: 여백 있는 테이블 / 02: 부드러운 자연광 / 03: 차분한 배경색"`이 100% 동일하게 출력됨.
- **원인 프롬프트 및 코드 분석**:
  - `prompts.py` L146: `recommendation` 블록을 옵션으로만 명시하고 구체적인 생성 스키마 예시를 제공하지 않음.
  - 이로 인해 모델이 `page_plan` 작성 시 `recommendation` 블록을 누락시킴.
  - 그 결과 `src/detail_page_ai/validation.py` L180-211의 시스템 방어 코드가 작동하여 하드코딩된 정적 템플릿(테이블/자연광/배경색)을 전건에 삽입함.
- **개선 제안 (안)**:
  - **프롬프트 측면**: `prompts.py`에 `recommendation` 블록의 아이템 생성 지침을 명확히 주어, 제품 유형별 맞춤 연출(예: 목걸이라면 '단색 셔츠나 깃이 있는 상의', 도자기라면 '낮은 다도 테이블이나 서가')을 모델이 직접 동적으로 작성하도록 유도.
  - **추정/보완**: 모델이 누락하더라도 코드 단(`validation.py`)에서 제품 카테고리(`jewelry`, `ceramic` 등)에 따라 fallback 아이템을 분기하도록 후속 코드 과제로 전달 필요.

---

### 개선 후보 4. 본문 문장 내 상투적 표현(클리셰) 금지 범위 확대 (패턴 2, 패턴 5 해결)

- **문제점**: 
  - `reference_guide.py`에 금지된 `"공간의 포인트"`, `"시각적 중심"`, `"매력을 더하다/선사하다"`가 본문 곳곳에 여전히 출현함.
  - Hero 첫 문장이 `"...조화를 이루는 [제품명]입니다"`로 획일화됨.
- **원인 프롬프트 문구**:
  - `reference_guide.py` L94: `Do not use stock headings such as 일상 속 작은 예술, 조용한 변화, 잔잔한 조화, 공간의 포인트, or 매력을 더하다.`
  - `prompts.py` L203: `do not repeat "시각적 중심", "흐름", or the same claim throughout hero, statement, detail and closing.`
- **분석 (원인 규명)**:
  - L94의 규칙이 **"stock headings (제목/헤드라인)"**으로 한정되어 있어, 모델이 본문(`body`)에는 써도 된다고 해석함.
  - L203의 규칙은 산문형 문장 속에 녹아 있어 LLM의 네거티브 제약 준수율이 떨어짐.
- **프롬프트 개정 제안 (안)**:
  ```text
  - Banned Clichés in BOTH titles and body text:
    * Do NOT use: "공간의 포인트", "시각적 중심", "조화를 이루는", "매력을 더하다/선사하다", "일상 속", "시간의 흐름을 담은", "정수를 보여주는".
    * Hero Opening Variation: Never open hero body with "[A]와 [B]가 조화를 이루는...". Open directly with an observable structural feature or concrete physical proportion (e.g. "원통형 몸체 양옆으로 곡선 손잡이가 대칭을 이루는 용기입니다.").
  ```

---

### 개선 후보 5. 고객 노출 카피 내 AI 추측 괄호/메타 발언 금지 (패턴 6 해결)

- **문제점**: Case 6에서 `"(활용 방식은 추측입니다)"` 괄호가 본문 카피에 노출됨.
- **원인 프롬프트 문구**:
  - `prompts.py` L165-166: `The copy must describe a plausible setting as a styling suggestion, never as proof of actual performance.`
  - `prompts.py` L74-76: `do not expose the copy brief, search process, or source URLs in customer-facing copy.`
- **분석 (원인 규명)**:
  - 모델이 "추측/제안임을 고객이 알게 하라"는 규칙을 준수하려다 보니 괄호 주석 형태로 출력함.
- **프롬프트 개정 제안 (안)**:
  ```text
  - Never include meta-commentary, reasoning disclaimers, or parenthetical self-corrections (e.g., "(활용 방식은 추측입니다)") in customer-facing body text. Express uncertainty naturally through soft suggestion verb endings (e.g., "~로 활용해 볼 수 있습니다", "~에 연출하기에 자연스럽습니다").
  ```

---

### 개선 후보 6. 다국어 토크나이저 오타 방지 규칙 추가

- **문제점**: Case 5에서 `"목에 걸erek 착용하는 장신구"`와 같은 한글-영문 결합 오타 발생.
- **프롬프트 개정 제안 (안)**:
  ```text
  - Strict Korean Token Hygiene: Ensure every Korean syllable and particle is grammatically complete. Never mix random English letters (e.g. "걸erek") into Korean words.
  ```

---

## 4. 요약 및 권고 사항

1. **카피 생성의 강점**:
   - 6건 모두 원본 이미지의 외형(색상, 형태, 세부 부속물)을 포착하는 시각적 묘사력은 대단히 탁월함 (금속 용기의 날개 달린 인물/왕관 양각, 화각 상자의 호랑이/사슴 문양, 직물의 격자 및 실밥 등).
   - `notice`(관리 안내)는 프롬프트의 엄격한 가드레일 덕분에 환각 없이 100% 완벽하게 제어됨.
2. **카피 생성의 취약점**:
   - 한국 공예 이커머스라는 시스템 설정으로 인해 **문화권/공예 기법을 '한국 전통'으로 과잉 단정하는 심각한 왜곡(중국 명나라 법화기 -> 한국 청자)**이 발생함.
   - 템플릿화된 문장 구조("조화를 이루는", "시각적 중심")와 `recommendation` 블록의 코드 폴백 복제 현상이 발견됨.
3. **다음 단계 권고**:
   - 현재 진행 중인 마스크 로직(`source_photos.py`) 수정 및 파일럿 재생성 이후, 프롬프트 개정 시 본 문서에서 도출된 **개선 후보 1~5**를 `prompts.py`의 `build_analysis_prompt`에 반영할 것을 권고함.
