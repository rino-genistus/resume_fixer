"""Turn a job description into structured JobRequirements, via LiteLLM JSON
mode at temperature 0 (schema documented in prompts/extract_jd.md)."""
from backend.llm import complete_json, load_prompt
from backend.schemas import JobRequirements

PROMPT_FILE = "extract_jd.md"


def extract_requirements(jd_text: str) -> JobRequirements:
    prompt = load_prompt(PROMPT_FILE).replace("{jd_text}", jd_text)
    data = complete_json(prompt, temperature=0.0)
    return JobRequirements.model_validate(data)
