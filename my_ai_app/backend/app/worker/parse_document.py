"""Isolated parser subprocess. Only JSON leaves stdout."""

import io
import json
import sys


def main():
    data = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise ValueError("Too large")
    if sys.argv[1] == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted or len(reader.pages) > 200:
            raise ValueError("Unsupported PDF")
        pages = []
        for page in reader.pages:
            if page.get("/AA") or reader.trailer["/Root"].get("/OpenAction"):
                raise ValueError("Active PDF content rejected")
            text = page.extract_text() or ""
            pages.append(text)
            if sum(map(len, pages)) > 500_000:
                raise ValueError("Too much text")
    else:
        pages = [data.decode("utf-8-sig")]
    if sum(map(len, pages)) > 500_000 or not any(t.strip() for t in pages):
        raise ValueError("No usable text or document too large")
    sys.stdout.write(json.dumps(pages))


if __name__ == "__main__":
    main()
