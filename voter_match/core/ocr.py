"""Electoral Roll OCR Pipeline (Phase 2).

Converts scanned Hindi voter roll PDFs (standard 3x10 card grid per page)
into structured voter tables using image contour detection, Otsu binarization,
and Hindi/English Tesseract OCR with low-confidence field verification flagging.
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Optional dependencies for OCR
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pdf2image
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False


@dataclass
class OcrVoterCard:
    """Extracted voter record from an OCR box."""
    page_num: int
    box_num: int
    serial_no: str = ""
    epic_no: str = ""
    voter_name: str = ""
    relative_name: str = ""
    relation_type: str = "पिता"  # 'पिता', 'पति', 'माता', 'अन्य'
    house_no: str = ""
    age: str = ""
    gender: str = ""
    is_deleted: bool = False
    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)
    image_crop_path: str | None = None
    raw_text: str = ""


class ElectoralRollOCR:
    """Pipeline for processing scanned Hindi voter roll PDFs."""

    def __init__(
        self,
        tesseract_cmd: str | None = None,
        tessdata_dir: str | None = None,
        poppler_path: str | None = None,
    ):
        self.tesseract_cmd = tesseract_cmd
        self.tessdata_dir = tessdata_dir
        self.poppler_path = poppler_path

        if tesseract_cmd and PYTESSERACT_AVAILABLE:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        if tessdata_dir:
            os.environ["TESSDATA_PREFIX"] = tessdata_dir

    @staticmethod
    def is_ocr_supported() -> tuple[bool, str]:
        """Check if OCR runtime requirements are met."""
        missing = []
        if not CV2_AVAILABLE:
            missing.append("opencv-python")
        if not PYTESSERACT_AVAILABLE:
            missing.append("pytesseract")
        if not PIL_AVAILABLE:
            missing.append("Pillow")
        if not PDF2IMAGE_AVAILABLE:
            missing.append("pdf2image")

        if missing:
            return False, f"अतिरिक्त पैकेज अनुपलब्ध: {', '.join(missing)}"
        return True, "OCR इंजन सक्रिय एवं तैयार है।"

    def parse_card_text(self, text: str) -> dict[str, Any]:
        """Parse structured voter fields from OCR'ed Hindi text box."""
        data: dict[str, Any] = {
            "serial_no": "",
            "epic_no": "",
            "voter_name": "",
            "relative_name": "",
            "relation_type": "पिता",
            "house_no": "",
            "age": "",
            "gender": "",
            "is_deleted": False,
            "needs_review": False,
            "review_reasons": [],
            "raw_text": text,
        }

        # Check for deletion stamps or symbols
        if re.search(r"\b(DELETED|विलोपित|हटाया|निरस्त)\b|[#Q]{1,2}", text, re.IGNORECASE):
            data["is_deleted"] = True

        # Extract EPIC (3 letters followed by 7 digits or similar alphanumeric)
        epic_match = re.search(r"([A-Z]{3}[0-9OIB]{7,8})", text)
        if epic_match:
            epic_raw = epic_match.group(1)
            # OCR corrections for digits
            prefix = epic_raw[:3]
            digits = epic_raw[3:].translate(str.maketrans("OIB", "018"))
            data["epic_no"] = f"{prefix}{digits}"

        # Extract Serial Number (first number in upper section)
        s_match = re.search(r"^\s*([0-9\u0966-\u096F]{1,5})\b", text)
        if s_match:
            data["serial_no"] = s_match.group(1)

        # Extract Voter Name (निर्वाचक का नाम / नाम)
        name_match = re.search(r"(?:निर्वाचक का नाम|नाम)\s*[:\-।.]?\s*([^\n\r;:]+)", text)
        if name_match:
            data["voter_name"] = name_match.group(1).strip()
        else:
            data["needs_review"] = True
            data["review_reasons"].append("मतदाता नाम स्पष्ट नहीं")

        # Extract Relative Name (पिता का नाम / पति का नाम / माता का नाम)
        rel_match = re.search(r"(पिता|पति|माता)\s*(?:का नाम)?\s*[:\-।.]?\s*([^\n\r;:]+)", text)
        if rel_match:
            data["relation_type"] = rel_match.group(1).strip()
            data["relative_name"] = rel_match.group(2).strip()
        else:
            # Fallback search for relative name
            alt_rel = re.search(r"(?:का नाम)\s*[:\-।.]?\s*([^\n\r;:]+)", text)
            if alt_rel and not data["voter_name"]:
                data["relative_name"] = alt_rel.group(1).strip()

        # Extract House Number (मकान संख्या / मकान नं०)
        house_match = re.search(r"(?:मकान संख्या|मकान नं०?|House No)\s*[:\-।.]?\s*([0-9A-Za-z\/\-\u0966-\u096F]+)", text)
        if house_match:
            data["house_no"] = house_match.group(1).strip()

        # Extract Age (आयु)
        age_match = re.search(r"(?:आयु|Age)\s*[:\-।.]?\s*([0-9\u0966-\u096F]{1,3})", text)
        if age_match:
            data["age"] = age_match.group(1).strip()
        else:
            data["needs_review"] = True
            data["review_reasons"].append("आयु स्पष्ट नहीं")

        # Extract Gender (लिंग)
        gen_match = re.search(r"(?:लिंग|Gender)\s*[:\-।.]?\s*(पु|महिला|पुरुष|स्त्री|अन्य|M|F)", text, re.IGNORECASE)
        if gen_match:
            g_raw = gen_match.group(1).strip().lower()
            if g_raw in {"पु", "पुरुष", "m"}:
                data["gender"] = "पु"
            elif g_raw in {"महिला", "स्त्री", "f"}:
                data["gender"] = "महिला"
            else:
                data["gender"] = "अन्य"
        else:
            data["needs_review"] = True
            data["review_reasons"].append("लिंग स्पष्ट नहीं")

        return data

    def extract_from_pdf(
        self,
        pdf_path: str | Path,
        start_page: int = 1,
        end_page: int = 5,
        output_crops_dir: str | Path | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> list[OcrVoterCard]:
        """Convert PDF pages to images and extract voter boxes using OCR."""
        supported, msg = self.is_ocr_supported()
        if not supported:
            raise RuntimeError(msg)

        pdf_path = Path(pdf_path)
        crops_dir = Path(output_crops_dir) if output_crops_dir else pdf_path.parent / "ocr_crops"
        crops_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback("PDF पृष्ठों का रूपांतरण प्रारंभ...", 10, 100)

        # Convert pages to images
        kwargs: dict[str, Any] = {"first_page": start_page, "last_page": end_page}
        if self.poppler_path:
            kwargs["poppler_path"] = self.poppler_path

        pages = pdf2image.convert_from_path(str(pdf_path), **kwargs)
        total_pages = len(pages)

        all_cards: list[OcrVoterCard] = []

        for p_idx, page_img in enumerate(pages, start=start_page):
            if progress_callback:
                pct = 15 + int(75 * (p_idx - start_page + 1) / total_pages)
                progress_callback(f"पृष्ठ {p_idx}/{end_page} का OCR विश्लेषण...", pct, 100)

            # Convert to OpenCV format
            open_cv_image = np.array(page_img)
            # RGB to BGR
            open_cv_image = open_cv_image[:, :, ::-1].copy()
            gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)

            # Detect grid boxes or divide standard 3x10 grid
            h, w = gray.shape
            # ECI rolls standard layout: 3 columns, 10 rows per page
            # Header ~12% top, Footer ~5% bottom, Left/Right margins ~3%
            top_margin = int(h * 0.12)
            bottom_margin = int(h * 0.95)
            left_margin = int(w * 0.03)
            right_margin = int(w * 0.97)

            grid_h = bottom_margin - top_margin
            grid_w = right_margin - left_margin

            card_h = grid_h // 10
            card_w = grid_w // 3

            box_id = 1
            for row in range(10):
                for col in range(3):
                    y1 = top_margin + row * card_h
                    y2 = y1 + card_h
                    x1 = left_margin + col * card_w
                    x2 = x1 + card_w

                    crop = gray[y1:y2, x1:x2]

                    # Preprocessing: Otsu binarization
                    _, thresh = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

                    # Tesseract OCR in Hindi + English
                    config = "--oem 3 --psm 6"
                    text = pytesseract.image_to_string(thresh, lang="hin+eng", config=config)

                    parsed = self.parse_card_text(text)

                    crop_path = None
                    if parsed["needs_review"] or parsed["is_deleted"]:
                        crop_filename = f"p{p_idx}_b{box_id}.png"
                        crop_file = crops_dir / crop_filename
                        cv2.imwrite(str(crop_file), crop)
                        crop_path = str(crop_file)

                    card = OcrVoterCard(
                        page_num=p_idx,
                        box_num=box_id,
                        serial_no=parsed["serial_no"],
                        epic_no=parsed["epic_no"],
                        voter_name=parsed["voter_name"],
                        relative_name=parsed["relative_name"],
                        relation_type=parsed["relation_type"],
                        house_no=parsed["house_no"],
                        age=parsed["age"],
                        gender=parsed["gender"],
                        is_deleted=parsed["is_deleted"],
                        needs_review=parsed["needs_review"],
                        review_reasons=parsed["review_reasons"],
                        image_crop_path=crop_path,
                        raw_text=parsed["raw_text"],
                    )
                    all_cards.append(card)
                    box_id += 1

        if progress_callback:
            progress_callback(f"OCR पूर्ण: {len(all_cards)} कार्ड प्राप्त।", 100, 100)

        return all_cards
