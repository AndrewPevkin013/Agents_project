from __future__ import annotations
from typing import Any, Dict, List
from uuid import uuid4

class MockAgent:
    def __init__(self, metadata: Dict[str, Any]) -> None:
        self.name = metadata["name"]
        self.description = metadata.get("description", "")
        self.system_prompt = metadata.get("system_prompt", "")
        self.tags: List[str] = list(metadata.get("tags", []))
        self.memory: Dict[str, Any] = {}

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        prompt = payload.get("prompt") or payload.get("task") or payload.get("query") or ""
        return {
            "agent": self.name,
            "status": "ok",
            "type": "mock",
            "role": self.system_prompt,
            "received_prompt": prompt,
            "memory_items": len(self.memory),
            "result": f"[{self.name}] обработал задачу как mock-агент: {prompt}",
        }

    def add_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        record_id = data.get("id") or f"rec_{uuid4().hex[:8]}"
        self.memory[record_id] = data
        return {"status": "ok", "agent": self.name, "added_id": record_id}

    def delete_data(self, target: str) -> Dict[str, Any]:
        existed = target in self.memory
        if existed:
            del self.memory[target]
        return {"status": "ok", "agent": self.name, "deleted": target, "existed": existed}

    def edit_data(self, target: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if target not in self.memory:
            self.memory[target] = {}
        if isinstance(self.memory[target], dict):
            self.memory[target].update(data)
        else:
            self.memory[target] = data
        return {"status": "ok", "agent": self.name, "updated": target}

    def load_file(self, file_path: str) -> Dict[str, Any]:
        record_id = f"file_{uuid4().hex[:8]}"
        self.memory[record_id] = {"type": "file", "path": file_path}
        return {"status": "ok", "agent": self.name, "file_path": file_path, "record_id": record_id, "chunks_loaded": 1}

class LLMAgent:
    def __init__(self, metadata: Dict[str, Any]) -> None:
        self.name = metadata["name"]
        self.description = metadata.get("description", "")
        self.system_prompt = metadata.get("system_prompt", "")
        self.tags: List[str] = list(metadata.get("tags", []))
        self.model_path = metadata["model_path"]
        generation = metadata.get("generation", {})
        self.max_new_tokens = generation.get("max_new_tokens", 256)
        self.temperature = generation.get("temperature", 0.7)
        self.do_sample = generation.get("do_sample", True)
        self.device = metadata.get("device", "auto")
        self.torch_dtype_name = metadata.get("torch_dtype", "float16")
        self.tokenizer = None
        self.model = None

    def _ensure_loaded(self) -> None:
        if self.tokenizer is not None and self.model is not None:
            return
        from transformers import AutoTokenizer, AutoModelForCausalLM
        import torch
        dtype_map = {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}
        torch_dtype = dtype_map.get(self.torch_dtype_name, torch.float16)
        print(f"Loading LLM agent {self.name}: {self.model_path}")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, local_files_only=True, trust_remote_code=True)
        if self.device == "auto":
            self.model = AutoModelForCausalLM.from_pretrained(self.model_path, local_files_only=True, device_map="auto", torch_dtype=torch_dtype, trust_remote_code=True)
        else:
            self.model = AutoModelForCausalLM.from_pretrained(self.model_path, local_files_only=True, torch_dtype=torch_dtype, trust_remote_code=True)
            self.model.to(self.device)
        self.model.eval()

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_loaded()
        prompt = payload.get("prompt") or payload.get("task") or payload.get("query") or ""
        messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": prompt}]
        if hasattr(self.tokenizer, "apply_chat_template"):
            text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        else:
            text = f"{self.system_prompt}\n\nUser: {prompt}\nAssistant:"
        inputs = self.tokenizer(text, return_tensors="pt")
        inputs = inputs.to(self.model.device if self.device == "auto" else self.device)
        outputs = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, temperature=self.temperature, do_sample=self.do_sample, pad_token_id=self.tokenizer.eos_token_id)
        answer = self.tokenizer.decode(outputs[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True).strip()
        return {"agent": self.name, "status": "ok", "type": "llm", "role": self.system_prompt, "received_prompt": prompt, "result": answer}

    def add_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "agent": self.name, "note": "LLM memory is not implemented yet", "data": data}
    def delete_data(self, target: str) -> Dict[str, Any]:
        return {"status": "ok", "agent": self.name, "note": "LLM memory is not implemented yet", "target": target}
    def edit_data(self, target: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "agent": self.name, "note": "LLM memory is not implemented yet", "target": target, "data": data}
    def load_file(self, file_path: str) -> Dict[str, Any]:
        return {"status": "ok", "agent": self.name, "note": "RAG loading is not implemented yet", "file_path": file_path}
