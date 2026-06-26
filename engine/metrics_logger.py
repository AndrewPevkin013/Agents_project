from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


class MetricsLogger:
    def __init__(self, logs_dir: str | Path = "logs") -> None:
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(exist_ok=True)

        self.events_path = self.logs_dir / "agent_events.jsonl"
        self.summary_path = self.logs_dir / "metrics_summary.txt"

    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, len(text.split()))

    def log_request(
        self,
        agent_name: str,
        prompt: str,
        response: Dict[str, Any],
        elapsed_seconds: float,
    ) -> None:
        result_text = json.dumps(response, ensure_ascii=False)

        event = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "agent": agent_name,
            "prompt_length": len(prompt),
            "prompt_tokens_est": self.estimate_tokens(prompt),
            "response_tokens_est": self.estimate_tokens(result_text),
            "total_tokens_est": self.estimate_tokens(prompt) + self.estimate_tokens(result_text),
            "elapsed_seconds": elapsed_seconds,
            "status": response.get("status", "unknown"),
        }

        with self.events_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

        self.save_summary()

    def read_events(self) -> List[Dict[str, Any]]:
        if not self.events_path.exists():
            return []

        events = []
        with self.events_path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line:
                    events.append(json.loads(line))

        return events

    def build_summary(self) -> Dict[str, Any]:
        events = self.read_events()

        if not events:
            return {
                "requests_count": 0,
                "total_tokens_est": 0,
                "avg_tokens_per_request": 0,
                "avg_response_time": 0,
                "avg_prompt_length": 0,
                "by_agent": {},
            }

        total_tokens = sum(e["total_tokens_est"] for e in events)
        total_time = sum(e["elapsed_seconds"] for e in events)
        total_prompt_length = sum(e["prompt_length"] for e in events)

        by_agent: Dict[str, Dict[str, Any]] = {}

        for event in events:
            name = event["agent"]
            if name not in by_agent:
                by_agent[name] = {
                    "requests_count": 0,
                    "total_tokens_est": 0,
                    "total_elapsed_seconds": 0,
                }

            by_agent[name]["requests_count"] += 1
            by_agent[name]["total_tokens_est"] += event["total_tokens_est"]
            by_agent[name]["total_elapsed_seconds"] += event["elapsed_seconds"]

        for name, item in by_agent.items():
            count = item["requests_count"]
            item["avg_tokens_per_request"] = item["total_tokens_est"] / count
            item["avg_response_time"] = item["total_elapsed_seconds"] / count

        return {
            "requests_count": len(events),
            "total_tokens_est": total_tokens,
            "avg_tokens_per_request": total_tokens / len(events),
            "avg_response_time": total_time / len(events),
            "avg_prompt_length": total_prompt_length / len(events),
            "by_agent": by_agent,
        }

    def save_summary(self) -> None:
        summary = self.build_summary()

        lines = [
            "AGENT METRICS SUMMARY",
            "",
            f"Requests count: {summary['requests_count']}",
            f"Total tokens estimated: {summary['total_tokens_est']}",
            f"Average tokens per request: {summary['avg_tokens_per_request']}",
            f"Average response time: {summary['avg_response_time']}",
            f"Average prompt length: {summary['avg_prompt_length']}",
            "",
            "BY AGENT:",
        ]

        for name, data in summary["by_agent"].items():
            lines.append(f"- {name}:")
            lines.append(f"  requests: {data['requests_count']}")
            lines.append(f"  total_tokens_est: {data['total_tokens_est']}")
            lines.append(f"  avg_tokens_per_request: {data['avg_tokens_per_request']}")
            lines.append(f"  avg_response_time: {data['avg_response_time']}")

        self.summary_path.write_text("\n".join(lines), encoding="utf-8")