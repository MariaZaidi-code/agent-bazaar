from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from app.agents.planner import TaskPlanner
from app.config import Settings
from app.core.llm import LLMClient
from app.knowledge.graph import ToolKnowledgeGraph
from app.knowledge.retrieval import TfidfIndex
from app.providers.registry import ProviderRegistry
from app.schemas import SubGoal, ToolSpec


@dataclass
class BaselineStep:
    subgoal_id: str
    capability: str
    tool_id: str
    tool_name: str
    status: str = "pending"
    data: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: float = 0.0
    cached: bool = False
    source: str = ""


@dataclass
class BaselineResult:
    baseline: str
    task: str
    subgoals: list[SubGoal] = field(default_factory=list)
    rankings: dict[str, list[str]] = field(default_factory=dict)
    steps: list[BaselineStep] = field(default_factory=list)
    status: str = "failed"
    answer: str = ""
    error: str | None = None
    duration_ms: float = 0.0
    mode: str = "live"


class BaselineRunner:
    name = "baseline"

    def __init__(
        self,
        settings: Settings,
        graph: ToolKnowledgeGraph,
        providers: ProviderRegistry,
        planner: TaskPlanner,
        llm: LLMClient,
    ) -> None:
        self.settings = settings
        self.graph = graph
        self.providers = providers
        self.planner = planner
        self.llm = llm

    async def rank(self, task: str) -> tuple[list[SubGoal], dict[str, list[str]]]:
        subgoals, _ = await self.planner.decompose(task)
        rankings: dict[str, list[str]] = {}
        for subgoal in subgoals:
            ranked = await self.rank_subgoal(subgoal)
            rankings[subgoal.id] = [tool.id for tool in ranked]
        return subgoals, rankings

    async def rank_subgoal(self, subgoal: SubGoal) -> list[ToolSpec]:
        raise NotImplementedError

    async def run(self, task: str) -> BaselineResult:
        started = time.perf_counter()
        result = BaselineResult(baseline=self.name, task=task)
        try:
            subgoals, rankings = await self.rank(task)
        except Exception as exc:
            result.error = str(exc)
            result.answer = f"Baseline could not plan the task: {exc}"
            result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
            return result
        result.subgoals = subgoals
        result.rankings = rankings
        tools_by_subgoal = {
            subgoal.id: self.graph.get(rankings[subgoal.id][0]) if rankings[subgoal.id] else None
            for subgoal in subgoals
        }
        ordered = self._topological_order(subgoals)
        outputs: dict[str, dict[str, Any]] = {}
        stopped = False
        for subgoal in ordered:
            if stopped:
                result.steps.append(
                    BaselineStep(
                        subgoal_id=subgoal.id,
                        capability=subgoal.capability,
                        tool_id="",
                        tool_name="",
                        status="skipped",
                        error="earlier step failed",
                    )
                )
                continue
            tool = tools_by_subgoal.get(subgoal.id)
            if tool is None:
                result.steps.append(
                    BaselineStep(
                        subgoal_id=subgoal.id,
                        capability=subgoal.capability,
                        tool_id="",
                        tool_name="",
                        status="failed",
                        error="no candidate returned",
                    )
                )
                stopped = True
                continue
            bindings, binding_errors = self._bindings(tool, subgoal, ordered, tools_by_subgoal)
            if binding_errors:
                result.steps.append(
                    BaselineStep(
                        subgoal_id=subgoal.id,
                        capability=subgoal.capability,
                        tool_id=tool.id,
                        tool_name=tool.name,
                        status="failed",
                        error="; ".join(binding_errors),
                    )
                )
                stopped = True
                continue
            try:
                params = self._resolve(bindings, subgoal, outputs)
            except Exception as exc:
                result.steps.append(
                    BaselineStep(
                        subgoal_id=subgoal.id,
                        capability=subgoal.capability,
                        tool_id=tool.id,
                        tool_name=tool.name,
                        status="failed",
                        error=str(exc),
                    )
                )
                stopped = True
                continue
            provider = self.providers.by_tool(tool.id)
            if provider is None:
                result.steps.append(
                    BaselineStep(
                        subgoal_id=subgoal.id,
                        capability=subgoal.capability,
                        tool_id=tool.id,
                        tool_name=tool.name,
                        status="failed",
                        error="provider unavailable",
                    )
                )
                stopped = True
                continue
            response = await provider.call(params)
            step = BaselineStep(
                subgoal_id=subgoal.id,
                capability=subgoal.capability,
                tool_id=tool.id,
                tool_name=tool.name,
                status="completed" if response.status == "success" else "failed",
                data=response.data,
                error=response.error,
                latency_ms=response.latency_ms,
                cached=response.cached,
                source=response.source,
            )
            result.steps.append(step)
            if response.status == "success":
                outputs[subgoal.id] = response.data
            else:
                stopped = True
        completed = [step for step in result.steps if step.status == "completed"]
        if completed and len(completed) == len(result.steps):
            result.status = "completed"
        elif completed:
            result.status = "partial"
        else:
            result.status = "failed"
        errors = [step.error for step in result.steps if step.error]
        result.error = "; ".join(errors) if errors else None
        result.answer = self._answer(result)
        result.mode = "offline" if self.settings.offline_mode else "live"
        result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        return result

    def _bindings(
        self,
        tool: ToolSpec,
        subgoal: SubGoal,
        ordered: list[SubGoal],
        tools_by_subgoal: dict[str, ToolSpec | None],
    ) -> tuple[dict[str, str], list[str]]:
        bindings: dict[str, str] = {}
        errors: list[str] = []
        for item in tool.inputs:
            if item.name in subgoal.slots:
                bindings[item.name] = f"$task.{item.name}"
                continue
            found = False
            for dep_id in subgoal.depends_on:
                dep_tool = tools_by_subgoal.get(dep_id)
                if dep_tool is None:
                    continue
                for output in dep_tool.outputs:
                    if output.name == item.name:
                        bindings[item.name] = f"${dep_id}.{output.name}"
                        found = True
                        break
                    if item.name in output.fields:
                        bindings[item.name] = f"${dep_id}.{output.name}.{item.name}"
                        found = True
                        break
                if found:
                    break
            if not found and item.required:
                errors.append(f"no source for required input {item.name}")
        return bindings, errors

    @staticmethod
    def _resolve(
        bindings: dict[str, str],
        subgoal: SubGoal,
        outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for name, reference in bindings.items():
            if reference.startswith("$task."):
                key = reference[len("$task.") :]
                resolved[name] = subgoal.slots[key]
                continue
            path = reference[1:].split(".")
            value: Any = outputs.get(path[0])
            if value is None:
                raise ValueError(f"missing output {path[0]}")
            for key in path[1:]:
                if not isinstance(value, dict) or key not in value:
                    raise ValueError(f"missing upstream value {reference}")
                value = value[key]
            resolved[name] = value
        return resolved

    @staticmethod
    def _topological_order(subgoals: list[SubGoal]) -> list[SubGoal]:
        remaining = {item.id: item for item in subgoals}
        ordered: list[SubGoal] = []
        while remaining:
            progressed = False
            for item in list(remaining.values()):
                if all(dep not in remaining for dep in item.depends_on):
                    ordered.append(item)
                    remaining.pop(item.id)
                    progressed = True
                    break
            if not progressed:
                ordered.extend(remaining.values())
                break
        return ordered

    @staticmethod
    def _answer(result: BaselineResult) -> str:
        pieces = []
        for step in result.steps:
            if step.status == "completed" and step.data is not None:
                pieces.append(f"{step.tool_name}: {json.dumps(step.data, default=str)}")
        if result.error:
            pieces.append(f"Errors: {result.error}")
        return " ".join(pieces) if pieces else "Baseline produced no answer."


class TfidfBaseline(BaselineRunner):
    use_keywords = False

    def _documents(self) -> dict[str, str]:
        documents = {}
        for tool in self.graph.all():
            pieces = [tool.name, tool.description, tool.capability]
            if self.use_keywords:
                pieces.append(" ".join(tool.keywords))
            documents[tool.id] = " ".join(pieces)
        return documents

    async def _retrieval_rank(self, subgoal: SubGoal) -> list[ToolSpec]:
        query = " ".join(
            [subgoal.description, *[str(value) for value in subgoal.slots.values()]]
        )
        index = TfidfIndex(self._documents())
        ranked = index.search(query, top_k=len(self.graph.all()))
        tools = []
        for tool_id, _ in ranked:
            tool = self.graph.get(tool_id)
            if tool is not None:
                tools.append(tool)
        return tools
