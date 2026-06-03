from typing import Any, Dict


class AnalystAgent:
    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        task = payload.get("task") or payload.get("prompt") or ""
        context = payload.get("context", {})

        return {
            "agent": "AnalystAgent",
            "status": "ok",
            "result": {
                "summary": f"Analysis completed for task: {task}",
                "context_keys": list(context.keys()) if isinstance(context, dict) else []
            }
        }
