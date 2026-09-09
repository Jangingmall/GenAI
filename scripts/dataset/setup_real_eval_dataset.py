"""Download CC0 craft objects; never call a model or modify legacy fixtures."""
import argparse
import hashlib
import io
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/evaluation/cma_real_v1'
API = 'https://openaccess-api.clevelandart.org/api/artworks/'
POLICY = 'https://www.clevelandart.org/open-access'
CATEGORIES = {'textile': 'textile', 'box': 'box', 'metalware': 'silver',
              'ceramic': 'vase', 'jewelry': 'necklace', 'furniture': 'chair'}
EXCLUDED_TYPES = {'Painting', 'Drawing', 'Print', 'Photograph'}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def rows(path, values):
    path.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in values))


def fetch(client, url, **kwargs):
    for attempt in range(4):
        try:
            response = client.get(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError:
            if attempt == 3:
                raise
            time.sleep(attempt + 1)


def download():
    if (OUT / 'manifest.json').exists():
        raise SystemExit('Existing snapshot retained. Run --validate; use a new version for recollection.')
    OUT.mkdir(parents=True, exist_ok=True)
    seen, hashes, records = set(), set(), []
    acquired = datetime.now(timezone.utc).isoformat()
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        policy = fetch(client, POLICY).content
        (OUT / 'license-policy.html').write_bytes(policy)
        for category, query in CATEGORIES.items():
            response = fetch(client, API, params={'cc0': 1, 'has_image': 1, 'q': query, 'limit': 100})
            payload = response.json()
            dump(OUT / 'sources' / f'{category}-search.json', payload)
            count = 0
            for obj in payload['data']:
                # Full text search can match citations rather than object identity.
                identity = (obj['title'] + ' ' + str(obj.get('type')) + ' ' + str(obj.get('technique'))).lower()
                if query not in identity or obj['id'] in seen or obj.get('share_license_status') != 'CC0' or obj.get('type') in EXCLUDED_TYPES:
                    continue
                image = (obj.get('images') or {}).get('web')
                if not image or not image.get('url'):
                    continue
                content = fetch(client, image['url']).content
                digest = hashlib.sha256(content).hexdigest()
                if digest in hashes:
                    continue
                with Image.open(io.BytesIO(content)) as picture:
                    picture.load()
                    width, height = picture.size
                    if min(width, height) < 224:
                        continue
                asset_id = f'cma-{obj["id"]}'
                relative = f'images/{asset_id}.jpg'
                (OUT / 'images').mkdir(exist_ok=True)
                (OUT / relative).write_bytes(content)
                dump(OUT / 'sources' / f'{asset_id}.json', obj)
                records.append({'asset_id': asset_id, 'product_group_id': asset_id,
                    'category': category, 'split': 'heldout', 'image_path': relative,
                    'sha256': digest, 'width': width, 'height': height,
                    'source_url': obj['url'], 'image_url': image['url'],
                    'source_record': f'sources/{asset_id}.json', 'acquired_at': acquired,
                    'license': 'CC0-1.0', 'license_status_evidence': obj['share_license_status'],
                    'license_policy_url': POLICY, 'title': obj['title'],
                    'reference_facts': {key: obj.get(key) for key in
                        ['type', 'technique', 'measurements', 'creation_date', 'culture']},
                    'label_status': 'source_metadata_not_human_reviewed'})
                seen.add(obj['id'])
                hashes.add(digest)
                count += 1
                print(f'{category}: {count}/10 {asset_id}', flush=True)
                if count == 10:
                    break
            if count != 10:
                raise RuntimeError(f'Insufficient eligible records: {category}: {count}')
    dump(OUT / 'manifest.json', {'version': 'cma_real_v1', 'acquired_at': acquired,
        'license_policy_sha256': hashlib.sha256(policy).hexdigest(), 'assets': records})
    for domain in ['analysis', 'rendering']:
        cases = []
        for record in records:
            ident = record['asset_id']
            cases.append({'case_id': f'{domain}-{ident}', 'domain': domain,
                'asset_id': ident, 'image_path': record['image_path'],
                'metadata': {'product_id': ident, 'idempotency_key': f'eval-v1-{domain}-{ident}',
                    'locale': 'ko-KR', 'user_hints': {},
                    'options': {'aspect_ratio': '1:4', 'image_size': '1K', 'output_mime_type': 'image/png'}},
                'reference_record': record['source_record'],
                'checks': (['schema_valid', 'visible_features_grounded', 'no_invented_price_shipping_care',
                            'source_facts_not_claimed_as_visually_observed'] if domain == 'analysis' else
                           ['human_approved_draft_required', 'source_object_preserved', 'text_not_clipped',
                            'png_decodes', 'no_unrequested_object_changes']),
                'score': None, 'review_status': 'pending'})
        rows(OUT / f'{domain}_60.jsonl', cases)
    validate()


def validate():
    manifest = json.loads((OUT / 'manifest.json').read_text())
    records = manifest['assets']
    assert len(records) == 60
    assert Counter(x['category'] for x in records) == {x: 10 for x in CATEGORIES}
    assert len({x['asset_id'] for x in records}) == 60
    assert len({x['sha256'] for x in records}) == 60
    legacy_hashes = {hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (ROOT / 'assets/samples').rglob('*') if p.is_file()}
    for record in records:
        path = OUT / record['image_path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
        assert record['sha256'] not in legacy_hashes
        assert record['license_status_evidence'] == 'CC0'
        obj = json.loads((OUT / record['source_record']).read_text())
        assert obj['share_license_status'] == 'CC0'
        assert obj['type'] not in EXCLUDED_TYPES
        assert f'cma-{obj["id"]}' == record['asset_id']
        with Image.open(path) as image:
            image.load()
            assert image.size == (record['width'], record['height'])
    assert hashlib.sha256((OUT / 'license-policy.html').read_bytes()).hexdigest() == manifest['license_policy_sha256']
    from detail_page_ai.ai_dto import ProductBeToAiCreateJobRequestDto
    for domain in ['analysis', 'rendering']:
        cases = [json.loads(line) for line in (OUT / f'{domain}_60.jsonl').read_text().splitlines()]
        assert len(cases) == len({case['case_id'] for case in cases}) == 60
        assert {case['asset_id'] for case in cases} == {record['asset_id'] for record in records}
        for case in cases:
            ProductBeToAiCreateJobRequestDto.model_validate(case['metadata'])
    report = {'assets': 60, 'categories': dict(Counter(x['category'] for x in records)),
              'analysis_cases': 60, 'rendering_cases': 60, 'unique_objects_across_domains': 60,
              'legacy_exact_image_overlap': 0, 'image_decode_hash_license_dto_checks': 'passed',
              'model_evaluation_run': False, 'human_label_review': 'pending'}
    dump(OUT / 'validation-report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def repair_selection():
    """Replace search false positives, retaining rejected provenance separately."""
    manifest = json.loads((OUT / 'manifest.json').read_text())
    records = manifest['assets']
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for record in records:
            if record['reference_facts']['type'] not in EXCLUDED_TYPES:
                continue
            old = record.copy()
            candidates = json.loads((OUT / 'sources' / f'{record["category"]}-search.json').read_text())['data']
            for obj in candidates:
                if obj.get('type') != 'Silver' or obj.get('share_license_status') != 'CC0':
                    continue
                ident = f'cma-{obj["id"]}'
                if ident in {r['asset_id'] for r in records}:
                    continue
                url = obj['images']['web']['url']
                content = fetch(client, url).content
                digest = hashlib.sha256(content).hexdigest()
                if digest in {r['sha256'] for r in records}:
                    continue
                with Image.open(io.BytesIO(content)) as image:
                    image.load()
                    width, height = image.size
                if min(width, height) < 224:
                    continue
                record.update(asset_id=ident, product_group_id=ident, image_path=f'images/{ident}.jpg',
                    sha256=digest, width=width, height=height, source_url=obj['url'], image_url=url,
                    source_record=f'sources/{ident}.json', title=obj['title'],
                    reference_facts={k: obj.get(k) for k in record['reference_facts']},
                    acquired_at=datetime.now(timezone.utc).isoformat())
                (OUT / record['image_path']).write_bytes(content)
                dump(OUT / record['source_record'], obj)
                rejected = OUT / 'excluded'
                rejected.mkdir(exist_ok=True)
                (OUT / old['image_path']).rename(rejected / Path(old['image_path']).name)
                dump(rejected / f'{old["asset_id"]}.json', {'reason': 'Painting rather than physical craft object', 'record': old})
                for domain in ['analysis', 'rendering']:
                    path = OUT / f'{domain}_60.jsonl'
                    cases = [json.loads(line) for line in path.read_text().splitlines()]
                    for case in cases:
                        if case['asset_id'] == old['asset_id']:
                            case.update(case_id=f'{domain}-{ident}', asset_id=ident,
                                image_path=record['image_path'], reference_record=record['source_record'])
                            case['metadata'].update(product_id=ident, idempotency_key=f'eval-v1-{domain}-{ident}')
                    rows(path, cases)
                break
            else:
                raise RuntimeError('No eligible replacement')
    dump(OUT / 'manifest.json', manifest)
    validate()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--repair-selection', action='store_true')
    args = parser.parse_args()
    repair_selection() if args.repair_selection else validate() if args.validate else download()
