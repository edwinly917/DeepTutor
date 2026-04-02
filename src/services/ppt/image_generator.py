from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Optional

import requests

from src.logging import get_logger
from src.services.config import BananaPptImageConfig, get_banana_ppt_config
from src.services.ppt.prompts import PptPromptManager

logger = get_logger("PPTImageGenerator")

_PROMPT_CACHE_VERSION = "pptimg-v2-nonabstract"


class ImageGenerator:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config = get_banana_ppt_config(project_root)
        self.cache_dir = project_root / "data" / "user" / "ppt_images"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def generate_image(
        self,
        *,
        description_content: dict | None = None,
        slide_title: str | None = None,
        prompt_override: str | None = None,
        style_prompt: str | None = None,
        style_context=None,
        page_index: int = 1,
        language: str = "zh",
    ) -> str:
        description_content = description_content or {}
        override_prompt = (prompt_override or "").strip()
        if (
            not override_prompt
            and not description_content.get("text")
            and not description_content.get("page_title")
        ):
            return ""

        img_cfg = self.config.image
        if not img_cfg.model or not img_cfg.base_url:
            logger.warning("PPT image config missing model/base_url")
            return ""

        primary_prompt = override_prompt or self.build_image_prompt(
            description_content=description_content,
            slide_title=slide_title,
            style_prompt=style_prompt,
            style_context=style_context,
            page_index=page_index,
            simplified=False,
            language=language,
        )
        image_data = self._generate_image_with_cache(primary_prompt, img_cfg)
        if image_data:
            return image_data

        fallback_prompt = override_prompt or self.build_image_prompt(
            description_content=description_content,
            slide_title=slide_title,
            style_prompt=style_prompt,
            style_context=style_context,
            page_index=page_index,
            simplified=True,
            language=language,
        )
        if fallback_prompt != primary_prompt:
            logger.info("Retrying PPT image generation with simplified prompt")
            image_data = self._generate_image_with_cache(fallback_prompt, img_cfg)
            if image_data:
                return image_data

        return ""

    def build_image_prompt(
        self,
        *,
        description_content: dict | None = None,
        slide_title: str | None = None,
        style_prompt: str | None = None,
        style_context=None,
        page_index: int = 1,
        simplified: bool = False,
        language: str = "zh",
    ) -> str:
        resolved_style_context = style_context or PptPromptManager.resolve_style_context(
            style_custom_text=style_prompt
        )
        return PptPromptManager.image_generation(
            description_content=description_content or {},
            slide_title=slide_title,
            style_context=resolved_style_context,
            page_index=page_index,
            simplified=simplified,
            language=language,
        )

    def _generate_image_with_cache(
        self, effective_prompt: str, cfg: BananaPptImageConfig
    ) -> Optional[str]:
        cache_key = self._hash_prompt(effective_prompt, cfg)
        cached = self._read_cached_image(cache_key)
        if cached:
            return cached

        image_data = self._run_image_provider(effective_prompt, cfg)
        if not image_data:
            return None

        self._write_cached_image(cache_key, image_data)
        return image_data

    def _run_image_provider(self, prompt: str, cfg: BananaPptImageConfig) -> Optional[str]:
        if cfg.binding == "gemini":
            return self._generate_gemini_image(prompt, cfg)
        if cfg.binding == "openai":
            return self._generate_openai_image(prompt, cfg)
        if cfg.binding == "doubao":
            return self._generate_doubao_image(prompt, cfg)
        logger.warning(f"Unsupported image binding: {cfg.binding}")
        return None

    def _generate_doubao_image(self, prompt: str, cfg: BananaPptImageConfig) -> Optional[str]:
        base = cfg.base_url.rstrip("/")
        if "/api/v3" not in base and "/api/v1" not in base:
            url = f"{base}/api/v3/images/generations"
        else:
            url = f"{base}/images/generations" if not base.endswith("/images/generations") else base

        headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
        size = cfg.aspect_ratio
        if size == "16:9":
            size = "1280x720"
        elif size == "1:1":
            size = "1024x1024"

        payload = {
            "model": cfg.model,
            "prompt": prompt,
            "response_format": "b64_json",
            "size": size,
            "sequential_image_generation": "disabled",
            "watermark": False,
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code != 200:
                logger.warning(f"Doubao image request failed (b64): {resp.status_code} {resp.text}")
                payload["response_format"] = "url"
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code != 200:
                    logger.warning(
                        f"Doubao image request failed (url): {resp.status_code} {resp.text}"
                    )

            resp.raise_for_status()
            data = resp.json()
            items = data.get("data") or []
            if not items:
                logger.warning(f"Doubao image response empty: {data}")
                return None

            item = items[0]
            if "b64_json" in item:
                return f"data:image/png;base64,{item['b64_json']}"
            if "url" in item:
                img_resp = requests.get(item["url"], timeout=30)
                img_resp.raise_for_status()
                b64 = base64.b64encode(img_resp.content).decode("utf-8")
                return f"data:image/png;base64,{b64}"

            logger.warning(f"Doubao image response missing recognized data: {item}")
            return None
        except Exception as exc:
            logger.warning(f"Doubao image request failed: {exc}")
            return None

    def _generate_gemini_image(self, prompt: str, cfg: BananaPptImageConfig) -> Optional[str]:
        url = cfg.base_url.rstrip("/")
        url = f"{url}/models/{cfg.model}:generateContent"
        params = {"key": cfg.api_key} if cfg.api_key else None

        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        try:
            resp = requests.post(url, params=params, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning(f"Gemini image request failed: {exc}")
            return None

        image = self._extract_inline_image(data)
        if not image:
            logger.warning(
                f"Gemini image response missing inline data. Response preview: {json.dumps(data)[:500]}..."
            )
            return None
        mime, b64 = image
        return f"data:{mime};base64,{b64}"

    def _generate_openai_image(self, prompt: str, cfg: BananaPptImageConfig) -> Optional[str]:
        base = cfg.base_url.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        url = f"{base}/images/generations"
        size = "1792x1024" if cfg.aspect_ratio == "16:9" else "1024x1024"
        headers = {"Authorization": f"Bearer {cfg.api_key}"}
        payload = {
            "model": cfg.model,
            "prompt": prompt,
            "size": size,
            "response_format": "b64_json",
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning(f"OpenAI image request failed: {exc}")
            return None

        items = data.get("data") or [] if isinstance(data, dict) else []
        b64 = items[0].get("b64_json") if items and isinstance(items[0], dict) else None
        if not b64:
            logger.warning("OpenAI image response missing b64_json")
            return None
        return f"data:image/png;base64,{b64}"

    def _extract_inline_image(self, data: dict) -> Optional[tuple[str, str]]:
        candidates = data.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            for part in parts:
                inline = part.get("inlineData") or part.get("inline_data")
                if not inline:
                    continue
                b64 = inline.get("data")
                if not b64:
                    continue
                mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                return mime, b64
        return None

    def _hash_prompt(self, prompt: str, cfg: BananaPptImageConfig) -> str:
        hasher = hashlib.sha256()
        hasher.update(_PROMPT_CACHE_VERSION.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(cfg.model.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(cfg.binding.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(cfg.aspect_ratio.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(prompt.encode("utf-8"))
        return hasher.hexdigest()

    def _read_cached_image(self, cache_key: str) -> Optional[str]:
        path = self.cache_dir / f"{cache_key}.png"
        if not path.exists():
            return None
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    def _write_cached_image(self, cache_key: str, data_url: str) -> None:
        try:
            header, b64_data = data_url.split(",", 1)
            if "base64" not in header:
                return
            path = self.cache_dir / f"{cache_key}.png"
            path.write_bytes(base64.b64decode(b64_data))
        except Exception as exc:
            logger.warning(f"Failed to cache image: {exc}")
