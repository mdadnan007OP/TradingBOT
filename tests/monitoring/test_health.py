"""Phase 10 — Health monitoring tests."""

from datetime import datetime, timezone

import pytest

from src.monitoring.health import (
    BrokerHealthChecker,
    ExecutionEngineHealthChecker,
    HealthService,
    HealthStatus,
    MarketDataHealthChecker,
    NewsEngineHealthChecker,
    RiskEngineHealthChecker,
    StrategyEngineHealthChecker,
    SubsystemHealth,
)


class MockConnection:
    def check_connection(self):
        return True

    def get_account_info(self):
        class AI:
            trade_mode = "demo"
            trade_allowed = True
            server = "PUPrime-Demo"
            currency = "USD"

        return AI()


def test_health_service_initial_state():
    service = HealthService()
    assert service.overall_status() == HealthStatus.UNKNOWN


def test_register_and_check():
    service = HealthService()
    checker = BrokerHealthChecker(lambda: MockConnection())
    service.register(checker)
    results = service.check_all()
    assert "broker" in results
    assert results["broker"].status == HealthStatus.HEALTHY


def test_broker_disconnected():
    class BadConn:
        def check_connection(self):
            return False

        def get_account_info(self):
            return None

    checker = BrokerHealthChecker(lambda: BadConn())
    health = checker.check()
    assert health.status == HealthStatus.UNHEALTHY


def test_market_data_fresh():
    class MD:
        def get_tick(self, symbol):
            class Tick:
                bid = 1.1
                ask = 1.1002
                timestamp = datetime.now(timezone.utc)
                spread = 0.0002

            return Tick()

    checker = MarketDataHealthChecker(MD())
    health = checker.check()
    assert health.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)


def test_strategy_engine_healthy():
    class SE:
        strategies = {"s1": type("S", (), {"enabled": True})()}

    checker = StrategyEngineHealthChecker(SE())
    health = checker.check()
    assert health.status == HealthStatus.HEALTHY


def test_risk_engine_healthy():
    class RE:
        circuit_breaker = type("CB", (), {"is_locked": lambda self: False})()
        daily_loss_limit_reached = lambda self: False

    checker = RiskEngineHealthChecker(RE())
    health = checker.check()
    assert health.status == HealthStatus.HEALTHY


def test_risk_engine_circuit_breaker_locked():
    class RE:
        circuit_breaker = type("CB", (), {"is_locked": lambda self: True})()
        daily_loss_limit_reached = lambda self: False

    checker = RiskEngineHealthChecker(RE())
    health = checker.check()
    assert health.status == HealthStatus.UNHEALTHY


def test_execution_engine_healthy():
    class EE:
        config = type("C", (), {"mode": "PAPER"})()
        journal = type("J", (), {"load_all": lambda self: []})()

    checker = ExecutionEngineHealthChecker(EE())
    health = checker.check()
    assert health.status == HealthStatus.HEALTHY


def test_overall_status_unhealthy_when_one_unhealthy():
    service = HealthService()
    service.register(BrokerHealthChecker(lambda: MockConnection()))
    # Force an unhealthy checker
    class Bad:
        name = "bad"

        def check(self):
            return SubsystemHealth(name="bad", status=HealthStatus.UNHEALTHY, detail="fail")

    service.register(Bad())
    service.check_all()
    assert service.overall_status() == HealthStatus.UNHEALTHY


def test_subsystem_health_to_dict():
    h = SubsystemHealth(name="test", status=HealthStatus.HEALTHY, detail="ok", latency_ms=1.5)
    d = h.to_dict()
    assert d["name"] == "test"
    assert d["status"] == "healthy"
    assert d["detail"] == "ok"
    assert d["latency_ms"] == 1.5
