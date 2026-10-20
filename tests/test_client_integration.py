from __future__ import annotations

from app.schemas import CorrectionRequest
from app.services import AppServices


async def test_weather_currency_chain(services: AppServices) -> None:
    result = await services.client.run(
        "What is the temperature in Lahore tomorrow, and what is 200 USD in PKR?"
    )
    assert result.status == "completed"
    assert result.plan is not None
    capabilities = [step.capability for step in result.plan.steps]
    assert capabilities == ["GeocodeLocation", "GetWeatherForecast", "ConvertCurrency"]
    assert all(step.status == "completed" for step in result.plan.steps)
    assert "Weather for Lahore" in result.answer
    assert "PKR" in result.answer
    assert len(result.candidate_lists) == 3
    event_types = {event.event_type for event in result.trace}
    assert {"task_started", "graphrag_shortlist", "chain_composed", "task_completed"} <= event_types
    assert services.trust.all()


async def test_sql_and_holiday_tasks(services: AppServices) -> None:
    sql_result = await services.client.run(
        "How many students are enrolled in the BS Artificial Intelligence program?"
    )
    assert sql_result.status == "completed"
    assert "students = 8" in sql_result.answer

    holiday_result = await services.client.run("Which public holidays does Pakistan have in 2026?")
    assert holiday_result.status == "completed"
    assert "Independence Day" in holiday_result.answer


async def test_document_task_uses_seeded_brief(services: AppServices) -> None:
    result = await services.client.run(
        "According to the uploaded document, what is the main goal of the project?"
    )
    assert result.status == "completed"
    assert "self-healing" in result.answer
    assert "agent_bazaar_project_brief.txt" in result.answer


async def test_substitution_after_injected_failure(services: AppServices) -> None:
    assert services.providers.force_failure("open-meteo-forecast", times=1) is True
    result = await services.client.run("What is the temperature in Lahore tomorrow?")
    assert result.status == "completed"
    assert result.plan is not None
    weather_step = next(step for step in result.plan.steps if step.capability == "GetWeatherForecast")
    assert weather_step.tool_id == "open-meteo-forecast-backup"
    assert weather_step.substituted_from == "open-meteo-forecast"
    assert any(event.event_type == "substitution_succeeded" for event in result.trace)
    assert "substitute" in result.answer.lower()


async def test_open_breaker_routes_to_backup(services: AppServices) -> None:
    key = services.breakers.link_key("client", "open-meteo")
    services.breakers.trip(key, "test outage")
    result = await services.client.run("What is the temperature in Lahore tomorrow?")
    assert result.status == "completed"
    assert result.plan is not None
    weather_step = next(step for step in result.plan.steps if step.capability == "GetWeatherForecast")
    assert weather_step.tool_id == "open-meteo-forecast-backup"
    assert weather_step.substituted_from is None


async def test_mapper_accepts_valid_correction(services: AppServices) -> None:
    correction = services.mapper.submit_correction(
        CorrectionRequest(
            tool_id="mock-weather-fahrenheit",
            field_name="forecast",
            original_concept="Temperature",
            corrected_concept="Temperature",
            corrected_unit="C",
            note="Normalize the adversarial Fahrenheit mock.",
        ),
        correlation_id="test-correction",
    )
    assert correction.accepted is True
    assert correction.staged is True
    assert services.mapper.staged()["corrections"][0]["tool_id"] == "mock-weather-fahrenheit"


async def test_baselines_run_in_offline_mode(services: AppServices) -> None:
    task = "How many students are enrolled in the BS Artificial Intelligence program?"
    for baseline in (services.b1, services.b2):
        result = await baseline.run(task)
        assert result.status == "completed"
        assert result.rankings
        assert "students" in result.answer
