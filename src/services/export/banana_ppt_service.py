import base64
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, Optional, Tuple

import requests

from src.logging import get_logger
from src.services.config import BananaPptImageConfig, get_banana_ppt_config
from src.services.llm import complete as llm_complete
from src.services.llm import get_llm_config, get_token_limit_kwargs

logger = get_logger("BananaPPTService")

_LAYOUTS = {
    "SECTION_HEADER",
    "OVERVIEW",
    "SPLIT_IMAGE_LEFT",
    "SPLIT_IMAGE_RIGHT",
    "TOP_IMAGE",
    "TYPOGRAPHIC_WITH_IMAGE",
    "QUOTE",
    "TYPOGRAPHIC",
    "SPLIT_LEFT",
    "SPLIT_RIGHT",
}
_PROMPT_CACHE_VERSION = "pptimg-v2-nonabstract"


class BananaPptService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config = get_banana_ppt_config(project_root)
        self.cache_dir = project_root / "data" / "user" / "ppt_images"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def generate_outline(
        self,
        source_content: str,
        style_prompt: Optional[str] = None,
        max_slides: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not source_content:
            raise ValueError("source_content is empty")

        max_slides = max(1, int(max_slides or self.config.max_slides))
        trimmed_content = self._trim_source(source_content)
        style_prompt = (style_prompt or "").strip()

        system_prompt = (
            "You are an elite presentation information architect.\n\n"
            "Return ONLY valid JSON with this schema:\n"
            "{\n"
            '  "title": string,\n'
            '  "subtitle": string,\n'
            '  "themeColor": string,\n'
            '  "accentColor": string,\n'
            '  "slides": [\n'
            "    {\n"
            '      "title": string,\n'
            '      "points": [string],\n'
            '      "layout": string,\n'
            '      "imagePrompt": string\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules for output:\n"
            "- Output ONLY JSON, with no markdown or commentary.\n"
            '- themeColor and accentColor must be valid hex colors like "#3b82f6".\n'
            '- subtitle should be concise; if unnecessary, return "".\n'
            "- Use the requested language consistently."
        )
        user_prompt = (
            "Build a PPT outline from the report below.\n\n"
            "Business goal:\n"
            "- Audience: business / research readers\n"
            "- Language: zh\n"
            f"- Max slides: {max_slides}\n"
            "- Preserve the report's real argument order\n"
            "- Prefer synthesis over copying section headers\n"
            "- Compress lower-priority details when needed to fit slide limits\n\n"
            f"Visual planning brief:\n{style_prompt or 'default'}\n\n"
            "Rules:\n"
            "- Style affects only tone, density, pacing, palette, image treatment, and layout preference.\n"
            "- Style must not distort the report's substance, priorities, or conclusions.\n"
            "- Output must be presentation-ready, concise, and executive-readable.\n"
            "- Create a balanced narrative arc: opening / core insights / implications / close.\n"
            "- The first slide should introduce the topic, context, and stakes.\n"
            "- The last slide should summarize implications, decisions, or takeaways.\n"
            "- Each slide must communicate one clear message.\n"
            "- Each slide title must be presentation-ready, not a raw report heading.\n"
            "- Each slide must contain 3-5 concise points.\n"
            "- Each point should be short, non-redundant, and insight-oriented.\n"
            "- Avoid copying long phrases from the report unless necessary.\n"
            f"- Ensure the total number of slides does not exceed {max_slides}.\n\n"
            "Use only these layout values:\n"
            '["SECTION_HEADER", "OVERVIEW", "SPLIT_IMAGE_LEFT", "SPLIT_IMAGE_RIGHT", '
            '"TOP_IMAGE", "TYPOGRAPHIC_WITH_IMAGE", "QUOTE", "TYPOGRAPHIC", '
            '"SPLIT_LEFT", "SPLIT_RIGHT"]\n\n'
            "Layout guidance:\n"
            "- Vary layouts naturally across the deck.\n"
            "- Do not repeat the same layout more than twice in a row.\n"
            "- Choose layout based on slide function, not decoration.\n\n"
            "imagePrompt guidance:\n"
            "- imagePrompt must directly support the slide's message.\n"
            "- imagePrompt must describe one professional 16:9 presentation visual concept.\n"
            "- Include subject, setting, composition, and mood.\n"
            "- Prefer realistic, editorial, analytical, or conceptual business visuals.\n"
            "- Avoid fantasy, cinematic spectacle, decorative-only imagery, logos, watermarks, readable text, UI screenshots, or literal chart screenshots.\n"
            "- If the slide is data-heavy, describe a business/editorial visual metaphor instead of a chart screenshot.\n\n"
            f"Report:\n{trimmed_content}"
        )

        outline_cfg = self.config.outline
        llm_cfg = get_llm_config()
        model = outline_cfg.model or llm_cfg.model
        api_key = outline_cfg.api_key or llm_cfg.api_key
        base_url = outline_cfg.base_url or llm_cfg.base_url
        binding = outline_cfg.binding or llm_cfg.binding

        if not model:
            raise ValueError("No LLM model configured for outline generation")

        kwargs = {"temperature": outline_cfg.temperature}
        kwargs.update(get_token_limit_kwargs(model, outline_cfg.max_tokens))

        raw = await llm_complete(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=model,
            api_key=api_key,
            base_url=base_url,
            binding=binding,
            **kwargs,
        )

        data = self._extract_json(raw)
        if not data:
            raise ValueError("Failed to parse outline JSON")

        return self._normalize_outline(data, max_slides)

    async def generate_image(
        self,
        prompt: str,
        slide_title: Optional[str] = None,
        slide_points: Optional[list[str]] = None,
        layout: Optional[str] = None,
        deck_title: Optional[str] = None,
        style_prompt: Optional[str] = None,
    ) -> str:
        prompt = (prompt or "").strip()
        if not prompt:
            return ""

        img_cfg = self.config.image
        if not img_cfg.model or not img_cfg.base_url:
            logger.warning("BananaPPT image config missing model/base_url")
            return ""

        primary_prompt = self._build_image_generation_prompt(
            prompt=prompt,
            slide_title=slide_title,
            slide_points=slide_points,
            layout=layout,
            deck_title=deck_title,
            style_prompt=style_prompt,
            simplified=False,
        )
        image_data = self._generate_image_with_cache(primary_prompt, img_cfg)
        if image_data:
            return image_data

        # Retry once with a simpler prompt when providers reject richer prompts.
        fallback_prompt = self._build_image_generation_prompt(
            prompt=prompt,
            slide_title=slide_title,
            slide_points=slide_points,
            layout=layout,
            deck_title=deck_title,
            style_prompt=style_prompt,
            simplified=True,
        )
        if fallback_prompt != primary_prompt:
            logger.info("Retrying PPT image generation with simplified prompt")
            image_data = self._generate_image_with_cache(fallback_prompt, img_cfg)
            if image_data:
                return image_data

        return ""

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

    def _build_image_generation_prompt(
        self,
        prompt: str,
        slide_title: Optional[str],
        slide_points: Optional[list[str]],
        layout: Optional[str],
        deck_title: Optional[str],
        style_prompt: Optional[str],
        simplified: bool = False,
    ) -> str:
        clean_points = [str(p).strip() for p in (slide_points or []) if str(p).strip()]
        lines = []
        if simplified:
            lines.append(
                "Create a professional presentation illustration that matches the topic below."
            )
        else:
            lines.append(
                "Create a professional presentation illustration that directly matches this slide."
            )

        if deck_title:
            lines.append(f"Deck title: {deck_title}")
        if slide_title:
            lines.append(f"Slide title: {slide_title}")
        if clean_points and not simplified:
            lines.append("Slide key points:")
            for point in clean_points[:5]:
                lines.append(f"- {point}")
        if layout and not simplified:
            lines.append(f"Target layout: {layout}")
        if style_prompt and not simplified:
            lines.append(f"Visual style guidance: {style_prompt}")

        lines.extend(
            [
                "Hard constraints:",
                "- Avoid logos, brand marks, and watermarks.",
                "- Avoid long readable text overlays and dense numeric labels.",
                "- Keep composition clear and suitable for a 16:9 slide.",
                f"Image brief: {prompt}",
            ]
        )
        return "\n".join(lines)

    def _generate_doubao_image(self, prompt: str, cfg: BananaPptImageConfig) -> Optional[str]:
        """
        Generate image using Doubao (Volcano Engine Ark) API.
        Reference curl example:
        {
          "model": "doubao-seedream-4-5-251128",
          "prompt": "...",
          "sequential_image_generation": "disabled",
          "response_format": "url",
          "size": "2K",
          "stream": false,
          "watermark": true
        }
        """
        base = cfg.base_url.rstrip("/")
        if "/api/v3" not in base and "/api/v1" not in base:
            url = f"{base}/api/v3/images/generations"
        else:
            url = f"{base}/images/generations" if not base.endswith("/images/generations") else base

        headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}

        # Use User's suggested size or fallback to aspect ratio mapping
        size = cfg.aspect_ratio
        if size == "16:9":
            size = "1280x720"
        elif size == "1:1":
            size = "1024x1024"
        # If the user enters a specific string like "2K", "512x512", use it directly.

        payload = {
            "model": cfg.model,
            "prompt": prompt,
            "response_format": "b64_json",  # Prefer b64 for local caching
            "size": size,
            "sequential_image_generation": "disabled",
            "watermark": True,
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code != 200:
                logger.warning(f"Doubao image request failed (b64): {resp.status_code} {resp.text}")
                # If b64_json failed, try with 'url' as in user's example
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
            elif "url" in item:
                # Download image from URL
                img_url = item["url"]
                img_resp = requests.get(img_url, timeout=30)
                img_resp.raise_for_status()
                b64 = base64.b64encode(img_resp.content).decode("utf-8")
                return f"data:image/png;base64,{b64}"

            logger.warning(f"Doubao image response missing recognized data: {item}")
            return None
        except Exception as exc:
            logger.warning(f"Doubao image request failed: {exc}")
            return None

    def _trim_source(self, source: str, max_chars: int = 16000) -> str:
        cleaned = (source or "").strip()
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[:max_chars]

    def _normalize_outline(self, outline: Dict[str, Any], max_slides: int) -> Dict[str, Any]:
        title = str(outline.get("title") or "Presentation")
        subtitle = str(outline.get("subtitle") or "")
        theme_color = self._normalize_hex(outline.get("themeColor"), "#3b82f6")
        accent_color = self._normalize_hex(outline.get("accentColor"), "#f59e0b")

        slides = []
        for slide in outline.get("slides") or []:
            if not isinstance(slide, dict):
                continue
            slide_title = str(slide.get("title") or "Slide")
            points = [str(p) for p in (slide.get("points") or []) if str(p).strip()]
            layout = str(slide.get("layout") or "TYPOGRAPHIC")
            if layout not in _LAYOUTS:
                layout = "TYPOGRAPHIC"
            image_prompt = slide.get("imagePrompt")
            if image_prompt is not None:
                image_prompt = str(image_prompt).strip() or None

            # If slide has imagePrompt but layout doesn't support images, upgrade it
            if image_prompt and layout == "TYPOGRAPHIC":
                layout = "TYPOGRAPHIC_WITH_IMAGE"

            slides.append(
                {
                    "title": slide_title,
                    "points": points,
                    "layout": layout,
                    "imagePrompt": image_prompt,
                }
            )
            if len(slides) >= max_slides:
                break

        if not slides:
            slides = [{"title": "Overview", "points": [], "layout": "TYPOGRAPHIC"}]

        return {
            "title": title,
            "subtitle": subtitle,
            "themeColor": theme_color,
            "accentColor": accent_color,
            "slides": slides,
        }

    def _normalize_hex(self, value: Any, fallback: str) -> str:
        if not value:
            return fallback
        text = str(value).strip()
        if not text.startswith("#"):
            text = f"#{text}"
        if re.match(r"^#[0-9a-fA-F]{6}$", text):
            return text.lower()
        return fallback

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r"```json\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except Exception:
                pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
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
            data = base64.b64decode(b64_data)
            path = self.cache_dir / f"{cache_key}.png"
            path.write_bytes(data)
        except Exception as exc:
            logger.warning(f"Failed to cache image: {exc}")

    def _generate_gemini_image(self, prompt: str, cfg: BananaPptImageConfig) -> Optional[str]:
        url = cfg.base_url.rstrip("/")
        url = f"{url}/models/{cfg.model}:generateContent"
        params = {"key": cfg.api_key} if cfg.api_key else None

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
        }
        try:
            # Increase timeout to 120s for large image generation
            resp = requests.post(url, params=params, json=payload, timeout=120)
            resp.raise_for_status()
            # Log response size for debugging
            resp_size = len(resp.content)
            logger.info(f"Gemini image response received: {resp_size} bytes")
            data = resp.json()
        except Exception as exc:
            error_msg = f"Gemini image request failed: {exc}"
            if "resp" in locals():
                try:
                    error_msg += f" | Response size: {len(resp.content)} bytes"
                except:
                    pass
            logger.warning(error_msg)
            return None

        image = self._extract_inline_image(data)
        if not image:
            # Log truncated response for debugging (first 500 chars)
            resp_preview = json.dumps(data)[:500]
            logger.warning(
                f"Gemini image response missing inline data. Response preview: {resp_preview}..."
            )
            return None
        mime, b64 = image
        logger.info(f"Gemini image extracted: mime={mime}, data_length={len(b64)} chars")
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

        b64 = None
        if isinstance(data, dict):
            items = data.get("data") or []
            if items and isinstance(items[0], dict):
                b64 = items[0].get("b64_json")
        if not b64:
            logger.warning("OpenAI image response missing b64_json")
            return None
        return f"data:image/png;base64,{b64}"

    def _extract_inline_image(self, data: Dict[str, Any]) -> Optional[Tuple[str, str]]:
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
