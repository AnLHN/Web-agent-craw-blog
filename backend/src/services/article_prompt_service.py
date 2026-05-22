from dataclasses import dataclass


@dataclass(frozen=True)
class ArticlePrompt:
    prompt_key: str
    version: str
    content: str
    max_output_tokens: int
    temperature: float


class ArticlePromptService:
    def active_prompts(self) -> list[ArticlePrompt]:
        return [
            ArticlePrompt(
                prompt_key="article.translate",
                version="v1",
                content=(
                    "Translate article text blocks into natural Vietnamese. Preserve technical meaning, "
                    "do not invent claims, and keep code/API/package/model names unchanged."
                ),
                max_output_tokens=4096,
                temperature=0.2,
            ),
            ArticlePrompt(
                prompt_key="article.metadata",
                version="v1",
                content=(
                    "Create Vietnamese blog metadata from the source article: title, excerpt, slug, tags, "
                    "and categories. Keep it faithful to the source."
                ),
                max_output_tokens=1024,
                temperature=0.2,
            ),
            ArticlePrompt(
                prompt_key="article.term_review",
                version="v1",
                content=(
                    "Review specialized terminology consistency. Return warnings when a term may be wrong "
                    "or inconsistent."
                ),
                max_output_tokens=1024,
                temperature=0.0,
            ),
        ]

    def system_prompt(self) -> str:
        return "\n\n".join(f"[{prompt.prompt_key}@{prompt.version}]\n{prompt.content}" for prompt in self.active_prompts())
