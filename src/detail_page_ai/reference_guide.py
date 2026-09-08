"""Design rules distilled from ``assets/references/detail-page-guide``.

The source PDFs are design references, not runtime instructions. Keeping the distilled
rules here gives the analyzer and renderer one versioned contract to follow without
shipping reference artwork or copying its sample content into generated pages.
"""

REFERENCE_GUIDE_VERSION = "detail-page-guide-v2-premium-editorial"

REFERENCE_GUIDE_COLORS = {
    "black": "#101010",
    "white": "#FFFFFF",
    "cool_grey_50": "#F0F0F0",
    "cool_grey_100": "#C4C7CA",
    "cool_grey_200": "#A8ABB0",
    "cool_grey_300": "#80858C",
    "cool_grey_400": "#676D76",
    "cool_grey_500": "#414954",
    "cool_grey_900": "#121B29",
    "jade_blue_50": "#FAFBFC",
    "jade_blue_100": "#EEF3F4",
    "jade_blue_200": "#E6EEEF",
    "jade_blue_300": "#DAE6E8",
    "jade_blue_400": "#D3E1E3",
    "jade_blue_500": "#C8D9DC",
    "yellow_500": "#FFC14C",
    "red_500": "#E84610",
}

REFERENCE_GUIDE_TYPE_SCALE = {
    "display": "28px / bold / 130%",
    "title": "17px / bold / 130%",
    "body": "16px / regular / 140%",
    "body_small": "13px / bold or regular / 140%",
    "caption": "10px / regular / 140%",
}


def build_image_mood_prompt() -> str:
    """Return the image-direction rules from the guide's Image-2 page."""
    return """Image mood contract (detail-page-guide / Image-2):

Do / Don't image mood - premium product-photography direction:
- Use white, light-grey, or deep single-color backgrounds: either a high-key white/light-grey
  treatment or a low-key deep neutral treatment.
  Keep the tone quiet, coherent, and product-first; never use a decorative backdrop as the subject.
- Use natural-looking soft light from one single dominant light source that feels like a diffused
  window. Shape it from the side
  or rear-side, retain believable contact shadows, and use only restrained fill. Preserve highlight
  roll-off on lacquer, metal, glass, glaze, shell, paper, wood, and textile.
- Preserve material micro-contrast: weave, grain, brush trace, inlay edge, joinery, glaze variation,
  hammered marks, and other source-visible details must remain legible without artificial sharpening.
- Use a normal 50-70mm camera for contextual scenes and an 85mm-equivalent view for detail cuts.
  Keep verticals natural, perspective believable, and depth of field sufficient to read the product.
- Compose with deliberate negative space and one clear focal hierarchy. The product remains the visual anchor.
  Every prop must have a clear relationship to scale, use, material, or making; props
  are optional and should be removed when they do not add evidence.
- Show close details of material, pattern, texture, construction, and the maker's process when real
  source images are supplied. Process scenes must prioritize hands, tools, and the making action,
  never a posed portrait or invented technique.
- When it fits the product, use a believable Korean/traditional architectural detail, quiet workshop,
  or lived-in context. Keep that context subordinate and avoid costume-like or theme-park styling.

Don't:
- No mid-tone grey or color gradients; no gradients in any image treatment; avoid excessive artificial lighting, harsh shadows, or glossy CGI;
- No modern gadgets, unrelated props, showroom staging, or overly posed studio scenes;
- let the background, person, prop, or decorative effect become more prominent than the product;
- redraw, recolor, duplicate, remove, merge, or distort any product, pattern, texture, or component;
- add text, logo, watermark, packaging, infographic, or placeholder content to the image.
"""


def build_editorial_story_prompt() -> str:
    """Return the guide-derived editorial reasoning and copy contract."""
    return """Editorial decision protocol:
- First identify the product's strongest source-visible anchor: silhouette, material/texture,
  repeated set or color system, or a creator-provided making process.
- Choose one primary story archetype and let it control the middle-page rhythm:
  * silhouette-led: hero scale → form proof → proportion/edge detail → use context;
  * texture-led: quiet hero → material macro → craft/finish proof → tactile use context;
  * set-led: complete lineup → component grouping → comparison/gallery → shared use context;
  * process-led: finished object → creator-provided process → detail proof → care and use.
  Process-led is allowed only when howMade or real process imagery exists.
- Build the narrative arc as hook → proof → context → use → information → close. The opening
  creates interest, the middle earns trust with visible evidence, and the ending resolves practical
  questions without turning into a generic catalog dump.
- Give each section one concrete visual truth and place its supporting image next to it.
  Do not repeat the same claim, crop purpose, or sentence idea in adjacent sections.

Premium Korean copy direction:
- Prefer precise product nouns and observable verbs over generic luxury adjectives. Avoid empty
  expressions such as 프리미엄, 고급스러운, 특별한, 완벽한, 품격을 더하다, and 소장 가치 unless
  creator-provided facts supply a concrete reason.
- Do not use stock headings such as 일상 속 작은 예술, 조용한 변화, 잔잔한 조화, 공간의 포인트,
  or 매력을 더하다. Replace them with a product-specific form, pattern, surface, or use detail.
- Headlines should be short, specific, and image-answerable. A headline promises one idea; its body
  explains the visible evidence in one to three compact sentences.
- Sensory language is allowed only when tied to visible evidence: reflected light, edge line, surface
  grain, color contrast, repeated motif, or form. Never convert mood into an unverified material,
  technique, origin, function, or performance claim.
- Separate creator-provided making/care information from image observations and label styling or use
  ideas as suggestions. Unknown specifications stay 확인 필요.
"""


def build_reference_guide_prompt() -> str:
    """Return the reusable visual contract for AI-authored page plans."""
    colors = REFERENCE_GUIDE_COLORS
    type_scale = REFERENCE_GUIDE_TYPE_SCALE
    return f"""Reference guide contract ({REFERENCE_GUIDE_VERSION}):

The attached reference materials describe a calm, product-first Korean craft-commerce detail page.
Use these rules as a direction, never as a fixed template:

Typography:
- Use Pretendard or a comparable clean Korean sans-serif throughout the page.
- Keep a clear hierarchy: display {type_scale['display']}, title {type_scale['title']},
  body {type_scale['body']}, small body {type_scale['body_small']}, caption {type_scale['caption']}.
- Use short readable paragraphs, strong alignment, and generous whitespace.

Color system:
- Use a black and white foundation ({colors['black']} / {colors['white']}), cool grey
  {colors['cool_grey_50']}–{colors['cool_grey_500']}, and jade blue
  {colors['jade_blue_50']}–{colors['jade_blue_500']} as the main system. Use the light jade
  surface {colors['jade_blue_300']} for calm section washes.
- Use yellow {colors['yellow_500']} or red {colors['red_500']} only for small emphasis rules,
  labels, or status accents. Do not let accents compete with the product.

Layout and image rhythm:
- Start with a product-first introduction: a clear primary image with concise product copy.
- Alternate image and text sections so each claim is adjacent to its visual evidence.
- Prefer a square image-and-copy unit around 387x387px, a wide image block around 774x520px,
  and a 3-up then 2-up gallery when enough source images or crops exist.
- Finish with compact basic information, creator-provided care/notice content, and recommendations.
  Reviews, artisan profiles, videos, and other modules may appear only when BE supplies real data;
  never invent them.
- For traditional crafts, a natural workshop, Korean/traditional architectural detail, or quiet
  lived-in space is preferred when it fits the product. The product must remain the visual anchor.

{build_editorial_story_prompt()}

{build_image_mood_prompt()}

Do not copy sample text, product names, claims, or exact layouts from the reference materials.

Content safety:
- Ground every product statement in the source image or creator-provided text.
- Clearly label inferred styling suggestions and leave unverifiable specifications as 확인 필요.
"""
