import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import AuthenticatedUser, get_current_user
from app.database import Base, get_db
from app.main import app
from app.models import Task, TaskHistory


class TaskAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        app.dependency_overrides[get_db] = self.get_db
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser("clerk_user_1")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def get_db(self):
        db = self.sessions()
        try:
            yield db
        finally:
            db.close()

    def create_task(self, assignee_clerk_id: str | None = "clerk_user_1") -> int:
        with self.sessions() as db:
            task = Task(
                title="Review handover",
                status="Open",
                assignee_clerk_id=assignee_clerk_id,
            )
            db.add(task)
            db.commit()
            return task.id

    def test_assigned_user_updates_and_persists_status(self) -> None:
        task_id = self.create_task()

        response = self.client.patch(
            f"/api/tasks/{task_id}/status",
            json={"status": "In Progress"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "In Progress")
        with self.sessions() as db:
            self.assertEqual(db.get(Task, task_id).status, "In Progress")
            history = db.scalars(
                select(TaskHistory).where(TaskHistory.task_id == task_id)
            ).all()
            self.assertEqual([item.event_type for item in history], ["status_changed"])

    def test_unrelated_authenticated_user_is_forbidden(self) -> None:
        task_id = self.create_task()
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser("clerk_user_2")

        response = self.client.patch(
            f"/api/tasks/{task_id}/status",
            json={"status": "Completed"},
        )

        self.assertEqual(response.status_code, 403)
        with self.sessions() as db:
            self.assertEqual(db.get(Task, task_id).status, "Open")

    def test_missing_authentication_is_unauthorized(self) -> None:
        task_id = self.create_task()
        app.dependency_overrides.pop(get_current_user)

        response = self.client.patch(
            f"/api/tasks/{task_id}/status",
            json={"status": "In Progress"},
        )

        self.assertEqual(response.status_code, 401)

    def test_invalid_status_is_rejected(self) -> None:
        task_id = self.create_task()

        response = self.client.patch(
            f"/api/tasks/{task_id}/status",
            json={"status": "Waiting"},
        )

        self.assertEqual(response.status_code, 422)

    def test_request_cannot_supply_or_impersonate_assignee(self) -> None:
        task_id = self.create_task(assignee_clerk_id=None)

        response = self.client.patch(
            f"/api/tasks/{task_id}/status",
            json={"status": "Completed", "assignee_clerk_id": "clerk_user_1"},
        )
        generic_patch = self.client.patch(
            f"/api/tasks/{task_id}",
            json={"status": "Completed"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(generic_patch.status_code, 422)
        with self.sessions() as db:
            self.assertIsNone(db.get(Task, task_id).assignee_clerk_id)
            self.assertEqual(db.get(Task, task_id).status, "Open")

    def test_nonexistent_task_returns_404(self) -> None:
        response = self.client.patch(
            "/api/tasks/999/status",
            json={"status": "Completed"},
        )

        self.assertEqual(response.status_code, 404)

    def test_unassigned_task_can_be_claimed_but_not_taken_over(self) -> None:
        task_id = self.create_task(assignee_clerk_id=None)

        response = self.client.post(f"/api/tasks/{task_id}/claim")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["assignee_clerk_id"], "clerk_user_1")

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser("clerk_user_2")
        conflict = self.client.post(f"/api/tasks/{task_id}/claim")
        self.assertEqual(conflict.status_code, 409)

    def test_startup_migration_adds_assignee_column_without_changing_legacy_owner(self) -> None:
        legacy_engine = create_engine("sqlite://")
        with legacy_engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE tasks (id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, "
                    "owner VARCHAR(120), status VARCHAR(20) NOT NULL)"
                )
            )
            connection.execute(
                text("INSERT INTO tasks (id, title, owner, status) VALUES (1, 'Legacy task', 'Sam', 'Open')")
            )

        with patch("app.database.engine", legacy_engine):
            from app.database import ensure_task_assignee_column

            ensure_task_assignee_column()

        columns = {column["name"] for column in inspect(legacy_engine).get_columns("tasks")}
        with legacy_engine.connect() as connection:
            legacy_owner = connection.scalar(text("SELECT owner FROM tasks WHERE id = 1"))

        self.assertIn("assignee_clerk_id", columns)
        self.assertEqual(legacy_owner, "Sam")
        legacy_engine.dispose()


if __name__ == "__main__":
    unittest.main()
