"""
Tests for restocking API endpoints and the restock fields on demand forecasts.
"""
from datetime import datetime, timedelta

import pytest

import mock_data


@pytest.fixture(autouse=True)
def clear_restock_orders():
    """Reset the in-memory restock order store around every test."""
    mock_data.restock_orders.clear()
    yield
    mock_data.restock_orders.clear()


@pytest.fixture
def demand_by_sku(client):
    """Demand forecasts keyed by SKU."""
    response = client.get("/api/demand")
    return {f["item_sku"]: f for f in response.json()}


class TestDemandRestockFields:
    """Test suite for unit cost and lead time on demand forecasts."""

    def test_demand_forecast_restock_fields_types(self, client):
        """Test that every forecast has a positive unit cost and lead time."""
        response = client.get("/api/demand")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0

        for forecast in data:
            assert isinstance(forecast["unit_cost"], (int, float))
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["unit_cost"] > 0
            assert forecast["lead_time_days"] > 0

    def test_demand_forecast_cost_matches_inventory(self, client, demand_by_sku):
        """Test that forecast unit cost matches inventory for shared SKUs."""
        inventory = client.get("/api/inventory").json()

        for item in inventory:
            if item["sku"] in demand_by_sku:
                assert abs(demand_by_sku[item["sku"]]["unit_cost"] - item["unit_cost"]) < 0.01


class TestRestockOrdersEndpoints:
    """Test suite for restock order endpoints."""

    def test_get_restock_orders_empty(self, client):
        """Test that no restock orders exist before any are submitted."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restock_order(self, client, demand_by_sku):
        """Test submitting a valid restock order."""
        payload = {
            "items": [
                {"sku": "GSK-203", "quantity": 100},
                {"sku": "MTR-304", "quantity": 5},
            ],
            "budget": 50000,
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("RST-")
        assert order["budget"] == 50000
        assert len(order["items"]) == 2

        for item in order["items"]:
            forecast = demand_by_sku[item["sku"]]
            assert item["name"] == forecast["item_name"]
            assert item["unit_cost"] == forecast["unit_cost"]
            assert item["lead_time_days"] == forecast["lead_time_days"]

    def test_restock_order_total_value_calculation(self, client, demand_by_sku):
        """Test that the total is computed from server-side unit costs."""
        payload = {"items": [{"sku": "GSK-203", "quantity": 100}, {"sku": "FLT-405", "quantity": 10}], "budget": 5000}
        order = client.post("/api/restock-orders", json=payload).json()

        expected = (
            100 * demand_by_sku["GSK-203"]["unit_cost"]
            + 10 * demand_by_sku["FLT-405"]["unit_cost"]
        )
        assert abs(order["total_value"] - expected) < 0.01

    def test_restock_order_lead_time_calculation(self, client, demand_by_sku):
        """Test that order lead time is the slowest item's lead time."""
        payload = {"items": [{"sku": "GSK-203", "quantity": 1}, {"sku": "MTR-304", "quantity": 1}], "budget": 5000}
        order = client.post("/api/restock-orders", json=payload).json()

        expected_lead = max(
            demand_by_sku["GSK-203"]["lead_time_days"],
            demand_by_sku["MTR-304"]["lead_time_days"],
        )
        assert order["lead_time_days"] == expected_lead

        order_date = datetime.fromisoformat(order["order_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        assert expected_delivery - order_date == timedelta(days=expected_lead)

    def test_get_restock_orders_newest_first(self, client):
        """Test that submitted orders are listed newest first."""
        first = client.post("/api/restock-orders", json={"items": [{"sku": "GSK-203", "quantity": 1}], "budget": 100}).json()
        second = client.post("/api/restock-orders", json={"items": [{"sku": "FLT-405", "quantity": 1}], "budget": 100}).json()

        response = client.get("/api/restock-orders")
        assert response.status_code == 200

        data = response.json()
        assert [o["id"] for o in data] == [second["id"], first["id"]]
        assert first["order_number"] != second["order_number"]

    def test_create_restock_order_unknown_sku(self, client):
        """Test that an unknown SKU is rejected and nothing is stored."""
        response = client.post("/api/restock-orders", json={"items": [{"sku": "NOPE-999", "quantity": 1}], "budget": 100})
        assert response.status_code == 400
        assert "NOPE-999" in response.json()["detail"]
        assert client.get("/api/restock-orders").json() == []

    def test_create_restock_order_over_budget(self, client):
        """Test that an order above the stated budget is rejected."""
        payload = {"items": [{"sku": "MTR-304", "quantity": 10}], "budget": 100}
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()
        assert client.get("/api/restock-orders").json() == []

    def test_create_restock_order_zero_quantity(self, client):
        """Test that a zero quantity fails validation."""
        response = client.post("/api/restock-orders", json={"items": [{"sku": "GSK-203", "quantity": 0}], "budget": 100})
        assert response.status_code == 422

    def test_create_restock_order_empty_items(self, client):
        """Test that an order with no items fails validation."""
        response = client.post("/api/restock-orders", json={"items": [], "budget": 100})
        assert response.status_code == 422

    def test_create_restock_order_exactly_at_budget(self, client, demand_by_sku):
        """Test that an order whose total equals the budget is accepted."""
        unit_cost = demand_by_sku["MTR-304"]["unit_cost"]
        payload = {"items": [{"sku": "MTR-304", "quantity": 2}], "budget": 2 * unit_cost}
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 201
        assert abs(response.json()["total_value"] - 2 * unit_cost) < 0.01

    def test_create_restock_order_missing_budget(self, client):
        """Test that the budget is required."""
        response = client.post("/api/restock-orders", json={"items": [{"sku": "GSK-203", "quantity": 1}]})
        assert response.status_code == 422

    def test_create_restock_order_duplicate_skus(self, client):
        """Test that the same SKU on two lines is rejected and nothing is stored."""
        payload = {
            "items": [{"sku": "GSK-203", "quantity": 1}, {"sku": "GSK-203", "quantity": 2}],
            "budget": 1000,
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 400
        assert "GSK-203" in response.json()["detail"]
        assert client.get("/api/restock-orders").json() == []
