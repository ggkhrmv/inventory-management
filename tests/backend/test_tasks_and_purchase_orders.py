"""
Tests for task and purchase order API endpoints.
"""
import pytest

import mock_data


@pytest.fixture(autouse=True)
def clear_in_memory_stores():
    """Reset the in-memory task and purchase order stores around every test."""
    original_pos = list(mock_data.purchase_orders)
    mock_data.tasks.clear()
    mock_data.purchase_orders.clear()
    yield
    mock_data.tasks.clear()
    mock_data.purchase_orders[:] = original_pos


@pytest.fixture
def task_payload():
    return {"title": "Review Q4 stock", "priority": "high", "dueDate": "2025-10-08"}


@pytest.fixture
def po_payload():
    return {
        "backlog_item_id": "1",
        "supplier_name": "Acme Parts",
        "quantity": 350,
        "unit_cost": 12.5,
        "expected_delivery_date": "2025-11-10",
        "notes": "Rush order",
    }


class TestTasksEndpoints:
    """Test suite for task endpoints."""

    def test_get_tasks_empty(self, client):
        """Test that the task list starts empty."""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_task(self, client, task_payload):
        """Test creating a task returns it as pending with a string ID."""
        response = client.post("/api/tasks", json=task_payload)
        assert response.status_code == 201

        task = response.json()
        assert isinstance(task["id"], str)
        assert task["title"] == "Review Q4 stock"
        assert task["priority"] == "high"
        assert task["dueDate"] == "2025-10-08"
        assert task["status"] == "pending"

    def test_create_task_trims_title(self, client, task_payload):
        """Test that surrounding whitespace is stripped from the title."""
        response = client.post("/api/tasks", json={**task_payload, "title": "  Call supplier  "})
        assert response.status_code == 201
        assert response.json()["title"] == "Call supplier"

    def test_create_task_default_priority(self, client):
        """Test that priority defaults to medium."""
        response = client.post("/api/tasks", json={"title": "Audit", "dueDate": "2025-10-08"})
        assert response.status_code == 201
        assert response.json()["priority"] == "medium"

    def test_get_tasks_newest_first(self, client, task_payload):
        """Test that tasks are listed newest first."""
        first = client.post("/api/tasks", json={**task_payload, "title": "First"}).json()
        second = client.post("/api/tasks", json={**task_payload, "title": "Second"}).json()

        data = client.get("/api/tasks").json()
        assert [t["id"] for t in data] == [second["id"], first["id"]]

    def test_task_ids_not_reused_after_delete(self, client, task_payload):
        """Test that deleting a task never lets its ID be handed out again."""
        first = client.post("/api/tasks", json=task_payload).json()
        client.delete(f"/api/tasks/{first['id']}")
        second = client.post("/api/tasks", json=task_payload).json()
        assert second["id"] != first["id"]

    @pytest.mark.parametrize("field, value", [
        ("title", ""),
        ("priority", "urgent"),
        ("dueDate", "not-a-date"),
    ])
    def test_create_task_invalid_fields(self, client, task_payload, field, value):
        """Test that invalid task fields are rejected."""
        response = client.post("/api/tasks", json={**task_payload, field: value})
        assert response.status_code == 422

    def test_create_task_blank_title(self, client, task_payload):
        """Test that a whitespace-only title is rejected."""
        response = client.post("/api/tasks", json={**task_payload, "title": "   "})
        assert response.status_code == 400

    def test_toggle_task(self, client, task_payload):
        """Test that PATCH toggles pending -> completed -> pending."""
        task = client.post("/api/tasks", json=task_payload).json()

        response = client.patch(f"/api/tasks/{task['id']}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.patch(f"/api/tasks/{task['id']}")
        assert response.json()["status"] == "pending"

    def test_delete_task(self, client, task_payload):
        """Test deleting a task removes it from the list."""
        task = client.post("/api/tasks", json=task_payload).json()

        response = client.delete(f"/api/tasks/{task['id']}")
        assert response.status_code == 204
        assert client.get("/api/tasks").json() == []

    @pytest.mark.parametrize("method", ["patch", "delete"])
    def test_nonexistent_task(self, client, method):
        """Test toggling or deleting a missing task returns 404."""
        response = getattr(client, method)("/api/tasks/task-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestPurchaseOrderEndpoints:
    """Test suite for purchase order endpoints."""

    def test_create_purchase_order(self, client, po_payload):
        """Test creating a purchase order for a backlog item."""
        response = client.post("/api/purchase-orders", json=po_payload)
        assert response.status_code == 201

        po = response.json()
        assert po["id"].startswith("PO-")
        assert po["backlog_item_id"] == "1"
        assert po["supplier_name"] == "Acme Parts"
        assert po["quantity"] == 350
        assert abs(po["unit_cost"] - 12.5) < 0.01
        assert po["expected_delivery_date"] == "2025-11-10"
        assert po["status"] == "Pending"
        assert "T" in po["created_date"]
        assert po["notes"] == "Rush order"

    def test_get_purchase_order_by_backlog_item(self, client, po_payload):
        """Test fetching the purchase order for a backlog item."""
        created = client.post("/api/purchase-orders", json=po_payload).json()

        response = client.get("/api/purchase-orders/1")
        assert response.status_code == 200
        assert response.json() == created

    def test_get_nonexistent_purchase_order(self, client):
        """Test that a backlog item without a PO returns 404."""
        response = client.get("/api/purchase-orders/1")
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_create_purchase_order_unknown_backlog_item(self, client, po_payload):
        """Test that a PO for an unknown backlog item returns 404."""
        response = client.post("/api/purchase-orders", json={**po_payload, "backlog_item_id": "999"})
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_duplicate_purchase_order(self, client, po_payload):
        """Test that a second PO for the same backlog item is rejected."""
        client.post("/api/purchase-orders", json=po_payload)
        response = client.post("/api/purchase-orders", json=po_payload)
        assert response.status_code == 409

    @pytest.mark.parametrize("field, value", [
        ("quantity", 0),
        ("unit_cost", -1),
        ("supplier_name", ""),
        ("expected_delivery_date", "next week"),
    ])
    def test_create_purchase_order_invalid_fields(self, client, po_payload, field, value):
        """Test that invalid purchase order fields are rejected."""
        response = client.post("/api/purchase-orders", json={**po_payload, field: value})
        assert response.status_code == 422

    def test_create_purchase_order_blank_supplier(self, client, po_payload):
        """Test that a whitespace-only supplier name is rejected."""
        response = client.post("/api/purchase-orders", json={**po_payload, "supplier_name": "   "})
        assert response.status_code == 400

    def test_backlog_reflects_purchase_order(self, client, po_payload):
        """Test that the backlog reports the PO ID once a PO exists."""
        before = {b["id"]: b for b in client.get("/api/backlog").json()}
        assert before["1"]["has_purchase_order"] is False
        assert before["1"]["purchase_order_id"] is None

        po = client.post("/api/purchase-orders", json=po_payload).json()

        after = {b["id"]: b for b in client.get("/api/backlog").json()}
        assert after["1"]["has_purchase_order"] is True
        assert after["1"]["purchase_order_id"] == po["id"]
        assert after["2"]["purchase_order_id"] is None
