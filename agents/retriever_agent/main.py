from typing import Any, Dict


class RetrieverAgent:
    def __init__(self) -> None:
        self.knowledge_base = {
            "parser": "Parser extracts JSON commands from raw LLM output.",
            "engine": "Engine loads agents, routes commands, and executes selected agents.",
            "agent": "Agent is a plug-in with agent.json metadata and a run(payload) method."
        }

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        query = str(payload.get("query") or payload.get("task") or payload.get("prompt") or "").lower()

        matches = {
            key: value
            for key, value in self.knowledge_base.items()
            if key in query or query in key
        }

        return {
            "agent": "RetrieverAgent",
            "status": "ok",
            "result": matches or {"message": "No exact match found."}
        }
