import re


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


def normalize_name(value: str | None) -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9 ]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_docket(value: str | None) -> str:
    return normalize_text(value).replace(" ", "")

