from __future__ import annotations

from app.baselines.common import TfidfBaseline
from app.schemas import SubGoal, ToolSpec


class B1ToolCalling(TfidfBaseline):
    name = "B1 plain LLM tool-calling"
    use_keywords = True

    async def rank_subgoal(self, subgoal: SubGoal) -> list[ToolSpec]:
        ranked = await self._retrieval_rank(subgoal)
        if not self.llm.enabled or not ranked:
            return ranked
        tool_text = "\n".join(
            f"- {tool.id}: {tool.name}. {tool.description}"
            for tool in ranked
        )
        prompt = (
            f"Sub-goal: {subgoal.description}\n\nAvailable tools:\n{tool_text}\n\n"
            "Choose the single best tool. Return JSON {\"tool_id\": \"...\"}."
        )
        result = await self.llm.complete(prompt, json_mode=True, max_tokens=200)
        if not result.ok:
            return ranked
        payload = self.llm.parse_json_object(result.text)
        if not payload:
            return ranked
        chosen = str(payload.get("tool_id", ""))
        ordered = [tool for tool in ranked if tool.id == chosen]
        ordered.extend(tool for tool in ranked if tool.id != chosen)
        return ordered
