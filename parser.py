import json
from pathlib import Path

class Parser:
    def __init__(self, output_dir: str = "parsed_command") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    def parse(self, text: str) -> int:
        decoder = json.JSONDecoder(); pos = 0; count = 0
        while pos < len(text):
            while pos < len(text) and text[pos].isspace():
                pos += 1
            if pos >= len(text): break
            try:
                obj, end = decoder.raw_decode(text, pos)
                count += 1
                with (self.output_dir / f"command_{count}.json").open("w", encoding="utf-8") as file:
                    json.dump(obj, file, ensure_ascii=False, indent=4)
                pos = end
            except json.JSONDecodeError:
                pos += 1
        return count
