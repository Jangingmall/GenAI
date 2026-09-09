import argparse
import mimetypes
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from detail_page_ai.dto import ProductProfileDto
from detail_page_ai.html_renderer import build_detail_page_html


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a self-contained HTML detail page from a product profile."
    )
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    image = args.image.read_bytes()
    profile = ProductProfileDto.model_validate_json(
        args.profile.read_text(encoding="utf-8")
    )
    mime_type = mimetypes.guess_type(args.image.name)[0] or "image/jpeg"
    html = build_detail_page_html(profile, image, mime_type=mime_type)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
