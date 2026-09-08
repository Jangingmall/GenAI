import argparse
import mimetypes
import sys
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from detail_page_ai.dto import GenerationOptions, UserHintsDto
from local_detail_page_ai.runner import build_local_pipeline, save_pipeline_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the detail-page pipeline with local text and image models."
    )
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--product-name")
    parser.add_argument("--making-method")
    parser.add_argument("--care-guide")
    parser.add_argument("--output-dir", default="generated/runs/local_detail_page", type=Path)
    parser.add_argument("--text-url", default="http://127.0.0.1:11234")
    parser.add_argument(
        "--text-model", default="mlx-community/gemma-4-12b-it-4bit"
    )
    parser.add_argument("--text-timeout", type=float, default=300.0)
    parser.add_argument("--text-provider", choices=("ollama", "mlx"), default="mlx")
    parser.add_argument("--image-provider", choices=("none", "mlx"), default="mlx")
    parser.add_argument("--image-url", default="http://127.0.0.1:11234")
    parser.add_argument("--image-model", default="mlx-community/flux2-klein-9b-4bit")
    parser.add_argument("--image-timeout", type=float, default=300.0)
    parser.add_argument(
        "--no-product-photos",
        action="store_true",
        help="Use the primary source image without generating source-preserving role cuts.",
    )
    args = parser.parse_args()

    source_image = args.image.read_bytes()
    mime_type = mimetypes.guess_type(args.image.name)[0] or "image/jpeg"
    pipeline = build_local_pipeline(
        text_url=args.text_url,
        text_model=args.text_model,
        text_timeout=args.text_timeout,
        generate_product_photos=not args.no_product_photos,
        text_provider=args.text_provider,
        image_provider=args.image_provider,
        image_url=args.image_url,
        image_model=args.image_model,
        image_timeout=args.image_timeout,
    )
    result = pipeline.run(
        job_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        source_image=source_image,
        source_mime_type=mime_type,
        options=GenerationOptions(),
        user_hints=UserHintsDto(
            product_name=args.product_name,
            making_method=args.making_method,
            care_guide=args.care_guide,
        ),
    )
    output = save_pipeline_result(result, args.output_dir)
    print(output)


if __name__ == "__main__":
    main()
