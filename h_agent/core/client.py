import os
import functools
from openai import OpenAI
from dotenv import load_dotenv


@functools.lru_cache(maxsize=1)
def get_client() -> OpenAI:
    load_dotenv(override=True)
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY", "sk-dummy"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
