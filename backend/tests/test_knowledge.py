import unittest
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import AuthenticatedUser, get_current_user
from app.database import Base, get_db
from app.main import app
from app.models import KnowledgeArticle, Meeting


class KnowledgeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.current_user_id = "clerk_user_1"
        app.dependency_overrides[get_db] = self.get_db
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            self.current_user_id
        )
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

    def create_article(self, **overrides) -> int:
        payload = {
            "title": "Deployment checklist",
            "content": "Verify backups before every release.",
            "category": "Operations",
            "tags": ["Release", "checklist"],
            "visibility": "private",
        }
        payload.update(overrides)
        response = self.client.post("/api/knowledge", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def test_create_and_retrieve_article_with_verified_creator(self) -> None:
        response = self.client.post(
            "/api/knowledge",
            json={
                "title": "  Incident response  ",
                "content": "Document the recovery steps.",
                "tags": ["Recovery", " recovery "],
            },
        )

        self.assertEqual(response.status_code, 201)
        article = response.json()
        self.assertEqual(article["title"], "Incident response")
        self.assertEqual(article["category"], "General")
        self.assertEqual(article["tags"], ["recovery"])
        self.assertEqual(article["creator_clerk_id"], "clerk_user_1")
        retrieved = self.client.get(f"/api/knowledge/{article['id']}")
        self.assertEqual(retrieved.status_code, 200)
        self.assertEqual(retrieved.json(), article)

    def test_update_delete_and_persist_article(self) -> None:
        article_id = self.create_article()

        updated = self.client.patch(
            f"/api/knowledge/{article_id}",
            json={"title": "Updated checklist", "tags": ["launch"]},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["title"], "Updated checklist")
        self.assertEqual(updated.json()["tags"], ["launch"])

        with self.sessions() as db:
            stored = db.get(KnowledgeArticle, article_id)
            self.assertEqual(stored.title, "Updated checklist")
            self.assertEqual([tag.tag for tag in stored.tags], ["launch"])

        deleted = self.client.delete(f"/api/knowledge/{article_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get(f"/api/knowledge/{article_id}").status_code, 404)

    def test_search_filters_by_title_content_category_and_tag(self) -> None:
        self.create_article()
        self.create_article(
            title="On-call guide",
            content="Steps for service recovery.",
            category="Engineering",
            tags=["operations"],
        )

        title_results = self.client.get("/api/knowledge/search?q=deployment")
        content_results = self.client.get("/api/knowledge/search?q=service%20recovery")
        category_results = self.client.get("/api/knowledge?category=Engineering")
        tag_results = self.client.get("/api/knowledge?tag=operations")
        self.assertEqual([item["title"] for item in title_results.json()], ["Deployment checklist"])
        self.assertEqual([item["title"] for item in content_results.json()], ["On-call guide"])
        self.assertEqual([item["title"] for item in category_results.json()], ["On-call guide"])
        self.assertEqual([item["title"] for item in tag_results.json()], ["On-call guide"])

    def test_private_article_is_hidden_from_another_authenticated_user(self) -> None:
        article_id = self.create_article()
        self.current_user_id = "clerk_user_2"

        listed = self.client.get("/api/knowledge")
        retrieved = self.client.get(f"/api/knowledge/{article_id}")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json(), [])
        self.assertEqual(retrieved.status_code, 404)

    def test_shared_article_is_readable_but_not_editable_or_deletable_by_others(self) -> None:
        article_id = self.create_article(visibility="shared")
        self.current_user_id = "clerk_user_2"

        self.assertEqual(self.client.get(f"/api/knowledge/{article_id}").status_code, 200)
        self.assertEqual(
            self.client.patch(f"/api/knowledge/{article_id}", json={"title": "Changed"}).status_code,
            403,
        )
        self.assertEqual(self.client.delete(f"/api/knowledge/{article_id}").status_code, 403)

    def test_meeting_link_requires_an_existing_meeting_and_is_persisted(self) -> None:
        invalid = self.client.post(
            "/api/knowledge",
            json={
                "title": "Meeting notes",
                "content": "Reviewed.",
                "related_meeting_id": 404,
            },
        )
        self.assertEqual(invalid.status_code, 404)

        with self.sessions() as db:
            meeting = Meeting(
                title="Planning",
                meeting_type="Planning",
                meeting_date=date(2026, 10, 30),
                agenda="Review milestones",
                participants="[]",
                raw_notes="The team reviewed milestones.",
            )
            db.add(meeting)
            db.commit()
            meeting_id = meeting.id

        article_id = self.create_article(related_meeting_id=meeting_id)
        self.assertEqual(self.client.get(f"/api/knowledge/{article_id}").json()["related_meeting_id"], meeting_id)

    def test_client_cannot_supply_creator_identity(self) -> None:
        response = self.client.post(
            "/api/knowledge",
            json={
                "title": "Spoofed",
                "content": "The creator must come from the token.",
                "creator_clerk_id": "victim",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_patch_rejects_null_required_fields(self) -> None:
        article_id = self.create_article()
        response = self.client.patch(
            f"/api/knowledge/{article_id}",
            json={"title": None},
        )
        self.assertEqual(response.status_code, 422)
        with self.sessions() as db:
            self.assertEqual(db.get(KnowledgeArticle, article_id).title, "Deployment checklist")

    def test_knowledge_requires_authentication(self) -> None:
        app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.get("/api/knowledge").status_code, 401)
        self.assertEqual(
            self.client.post(
                "/api/knowledge",
                json={"title": "Private", "content": "Protected article."},
            ).status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()
