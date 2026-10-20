from __future__ import annotations

from app.baselines.common import TfidfBaseline
from app.schemas import SubGoal, ToolSpec


class B2RagOnly(TfidfBaseline):
    name = "B2 RAG without graph or ontology"
    use_keywords = False

    async def rank_subgoal(self, subgoal: SubGoal) -> list[ToolSpec]:
        return await self._retrieval_rank(subgoal)
