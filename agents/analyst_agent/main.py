# from typing import Any, Dict
#
#
# class AnalystAgent:
#     def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
#         task = payload.get("task") or payload.get("prompt") or ""
#         context = payload.get("context", {})
#
#         return {
#             "agent": "AnalystAgent",
#             "status": "ok",
#             "result": {
#                 "summary": f"Analysis completed for task: {task}",
#                 "context_keys": list(context.keys()) if isinstance(context, dict) else []
#             }
#         }

from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

class AnalystAgent:
    def __init__(self):
        self.model_path = r"D:/Programming/PycharmProjects/Agents_project/agents/analyst_agent"

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path,
            local_files_only=True
        )

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            local_files_only=True,
            torch_dtype=torch.float16,
            device_map="auto"
        )

    def run(self, payload):
        prompt = payload.get("prompt") or payload.get("task") or ""

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.7,
            do_sample=True
        )

        text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        return {
            "agent": "AnalystAgent",
            "status": "ok",
            "result": text
        }