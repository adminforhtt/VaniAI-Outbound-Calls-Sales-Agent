import httpx
from typing import List, Dict, AsyncGenerator
import logging
import json
import time
from app.config.settings import settings

logger = logging.getLogger(__name__)

# Persistent connection pool for lower latency
_http_client = httpx.AsyncClient()

class LLMService:
    @staticmethod
    async def generate_response_stream(messages: List[Dict[str, str]], provider: str = "groq", model: str = None) -> AsyncGenerator[str, None]:
        if provider.lower() == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            selected_model = model if model else "llama-3.3-70b-versatile"
        else:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "HTTP-Referer": settings.BASE_URL,
                "X-Title": settings.PROJECT_NAME,
                "Content-Type": "application/json"
            }
            selected_model = model if model else "meta-llama/llama-3.3-70b-instruct"

        payload = {
            "model": selected_model,
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": 300,
            "stream": True,
            "stop": ["User:", "Agent:", "\n\n"]
        }
        
        t0 = time.time()
        first_token_logged = False
        
        try:
            async with _http_client.stream("POST", url, headers=headers, json=payload, timeout=15.0) as response:
                response.raise_for_status()
                
                in_think = False
                buffer = ""
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            total_ms = int((time.time() - t0) * 1000)
                            logger.info(f"⏱ LLM_TOTAL_MS={total_ms}")
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            
                            if content:
                                buffer += content
                                while buffer:
                                    if not in_think:
                                        think_start = buffer.find("<think>")
                                        if think_start != -1:
                                            if think_start > 0:
                                                if not first_token_logged:
                                                    first_token_ms = int((time.time() - t0) * 1000)
                                                    logger.info(f"⏱ LLM_FIRST_TOKEN_MS={first_token_ms}")
                                                    first_token_logged = True
                                                yield buffer[:think_start]
                                            buffer = buffer[think_start + len("<think>"):]
                                            in_think = True
                                        else:
                                            potential_tag = buffer.rfind("<")
                                            if potential_tag != -1 and "<think>".startswith(buffer[potential_tag:]):
                                                if potential_tag > 0:
                                                    if not first_token_logged:
                                                        first_token_ms = int((time.time() - t0) * 1000)
                                                        logger.info(f"⏱ LLM_FIRST_TOKEN_MS={first_token_ms}")
                                                        first_token_logged = True
                                                    yield buffer[:potential_tag]
                                                buffer = buffer[potential_tag:]
                                                break
                                            else:
                                                if not first_token_logged:
                                                    first_token_ms = int((time.time() - t0) * 1000)
                                                    logger.info(f"⏱ LLM_FIRST_TOKEN_MS={first_token_ms}")
                                                    first_token_logged = True
                                                yield buffer
                                                buffer = ""
                                                break
                                    else:
                                        think_end = buffer.find("</think>")
                                        if think_end != -1:
                                            buffer = buffer[think_end + len("</think>"):]
                                            in_think = False
                                        else:
                                            potential_tag = buffer.rfind("<")
                                            if potential_tag != -1 and "</think>".startswith(buffer[potential_tag:]):
                                                buffer = buffer[potential_tag:]
                                                break
                                            else:
                                                buffer = ""
                                                break
                        except Exception:
                            continue
        except Exception as e:
            logger.error(f"Error in LLM streaming using {selected_model} ({provider}): {e}")
            yield ""

    @staticmethod
    async def generate_response(messages: List[Dict[str, str]], provider: str = "groq", model: str = None) -> str:
        if provider.lower() == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            selected_model = model if model else "llama-3.3-70b-versatile"
        else:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "HTTP-Referer": settings.BASE_URL,
                "X-Title": settings.PROJECT_NAME,
                "Content-Type": "application/json"
            }
            selected_model = model if model else "meta-llama/llama-3.3-70b-instruct"

        payload = {
            "model": selected_model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 300,
            "stop": ["User:", "Agent:", "\n\n"]
        }
        
        try:
            response = await _http_client.post(url, headers=headers, json=payload, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            raw_content = data["choices"][0]["message"]["content"]
            import re
            clean_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()
            return clean_content
        except Exception as e:
            logger.error(f"Error in LLM generation using {selected_model} ({provider}): {e}")
            return "Haan ji, ek second."
