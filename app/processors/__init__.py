"""The processor registry: category → the processor that converts it to PDF.

Registering a processor here is the ONLY code change needed to enable a
format category (its magic signatures already live in app/detection.py).
A category without a registration is detected but refused at upload time;
a REGISTERED processor can still be per-machine unavailable (the office
kill switch, LibreOffice missing) — that's what Processor.available() is
for (docs/MULTI_FORMAT_PLAN.md §10).
"""

from app.processors.base import ConversionError, Processor
from app.processors.images import IMAGE_PROCESSOR
from app.processors.office import OFFICE_PROCESSOR
from app.processors.pdf import PDF_PROCESSOR

__all__ = [
    "ConversionError",
    "Processor",
    "for_category",
    "supported_categories",
]

_REGISTRY: dict[str, Processor] = {
    "image": IMAGE_PROCESSOR,
    "office": OFFICE_PROCESSOR,
    "pdf": PDF_PROCESSOR,
}


def for_category(category: str) -> Processor | None:
    """The processor for a category, or None while that format is
    unregistered ("not enabled yet" — the upload gate and the pipeline
    both treat None as "cannot convert")."""
    return _REGISTRY.get(category)


def supported_categories() -> tuple[str, ...]:
    """Categories that can currently be printed (sorted for stable display)."""
    return tuple(sorted(_REGISTRY))
