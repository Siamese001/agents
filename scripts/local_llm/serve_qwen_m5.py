#!/usr/bin/env python3
"""OpenAI-compatible local inference server for Qwen 27B on Apple Silicon (M5 Pro).

Exposes:
- GET  /v1/models
- POST /v1/chat/completions
- GET  /healthz
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn


def _load_local_catalog_section() -> dict[str, Any]:
    catalog_path = Path(__file__).resolve().parents[2] / "config" / "model_catalog.json"
    if catalog_path.is_file():
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            for section in catalog.values():
                if isinstance(section, dict) and "local_model_id" in section:
                    return section
        except (OSError, ValueError, TypeError):
            pass
    return {}


_LOCAL_CATALOG = _load_local_catalog_section()
DEFAULT_LOCAL_MODEL_ID = str(_LOCAL_CATALOG.get("local_model_id") or "local-default-27b")
DEFAULT_LOCAL_MLX_REPO = str(_LOCAL_CATALOG.get("local_27b_mlx") or "mlx-community/local-27b-4bit")

app = FastAPI(title="Local 27B OpenAI-Compatible Server", version="1.0.0")

# Global engine state
_LOADED_MODEL = None
_LOADED_TOKENIZER = None
_MODEL_PATH: Optional[str] = None
_ENGINE_TYPE: str = "mock"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = DEFAULT_LOCAL_MODEL_ID
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.3
    max_tokens: Optional[int] = 4096
    stream: Optional[bool] = False


class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str = "stop"


class UsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatChoice]
    usage: UsageInfo


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {
        "status": "healthy",
        "engine": _ENGINE_TYPE,
        "model_path": _MODEL_PATH,
        "context_window": 32768,
    }


@app.get("/v1/models")
def list_models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": DEFAULT_LOCAL_MODEL_ID,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local-m5",
                "permission": [],
                "root": DEFAULT_LOCAL_MODEL_ID,
                "parent": None,
            },
        ]
    }


def _generate_response(prompt: str, max_tokens: int = 4096, temperature: float = 0.3) -> str:
    global _LOADED_MODEL, _LOADED_TOKENIZER, _ENGINE_TYPE
    
    if _ENGINE_TYPE == "mlx" and _LOADED_MODEL is not None:
        import mlx_lm
        return mlx_lm.generate(
            _LOADED_MODEL,
            _LOADED_TOKENIZER,
            prompt=prompt,
            max_tokens=max_tokens,
            temp=temperature,
        )
    elif _ENGINE_TYPE == "transformers" and _LOADED_MODEL is not None:
        import torch
        inputs = _LOADED_TOKENIZER(prompt, return_tensors="pt").to(_LOADED_MODEL.device)
        with torch.no_grad():
            outputs = _LOADED_MODEL.generate(**inputs, max_new_tokens=max_tokens, temperature=temperature)
        return _LOADED_TOKENIZER.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    else:
        # Fallback / mock mode for testing environments
        return (
            "Scaled enterprise agentic AI architectures and governed multi-agent orchestration "
            "platforms across complex business workflows with deterministic verification."
        )


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def create_chat_completion(request: ChatCompletionRequest) -> ChatCompletionResponse:
    created_ts = int(time.time())
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    
    # Format messages into prompt
    formatted_prompt = ""
    for m in request.messages:
        formatted_prompt += f"<|im_start|>{m.role}\n{m.content}<|im_end|>\n"
    formatted_prompt += "<|im_start|>assistant\n"
    
    prompt_tokens = max(1, len(formatted_prompt.split()))
    
    generated_text = _generate_response(
        formatted_prompt,
        max_tokens=request.max_tokens or 4096,
        temperature=request.temperature or 0.3,
    )
    completion_tokens = max(1, len(generated_text.split()))

    return ChatCompletionResponse(
        id=completion_id,
        created=created_ts,
        model=request.model,
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content=generated_text),
                finish_reason="stop",
            )
        ],
        usage=UsageInfo(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
    )


def init_engine(model_path: Optional[str] = None) -> None:
    global _LOADED_MODEL, _LOADED_TOKENIZER, _MODEL_PATH, _ENGINE_TYPE
    _MODEL_PATH = model_path
    
    if model_path and os.path.exists(model_path):
        try:
            import mlx_lm
            print(f"Loading MLX model from {model_path}...")
            _LOADED_MODEL, _LOADED_TOKENIZER = mlx_lm.load(model_path)
            _ENGINE_TYPE = "mlx"
            print("Successfully initialized MLX engine on Apple Silicon Metal!")
            return
        except Exception as e:
            print(f"MLX load skipped/failed ({e}), checking PyTorch/Transformers...")
        
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            print(f"Loading model via Transformers onto {device}...")
            _LOADED_TOKENIZER = AutoTokenizer.from_pretrained(model_path)
            _LOADED_MODEL = AutoModelForCausalLM.from_pretrained(
                model_path,
                torch_dtype=torch.float16 if device == "mps" else torch.float32,
                device_map=device,
            )
            _ENGINE_TYPE = "transformers"
            print(f"Successfully initialized Transformers engine on {device}!")
            return
        except Exception as e:
            print(f"Transformers load failed: {e}")

    print("Running in fast testing/mock mode (32K context simulated).")
    _ENGINE_TYPE = "mock"


_HUB_SLUG = DEFAULT_LOCAL_MLX_REPO.replace("/", "--")
DEFAULT_LOCAL_MODEL_PATH = (
    os.getenv("LOCAL_M5_MODEL_PATH")
    or str(
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / f"models--{_HUB_SLUG}"
        / "snapshots"
        / "3e6447f082e89cc7f0bc6e5441afd38dfce760ff"
    )
)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start local 27B inference server.")
    parser.add_argument("--model-path", default=DEFAULT_LOCAL_MODEL_PATH, help="Path to local model weights")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    args = parser.parse_args()

    init_engine(args.model_path)
    uvicorn.run(app, host=args.host, port=args.port)
