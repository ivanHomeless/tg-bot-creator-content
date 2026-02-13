import pytest
from datetime import datetime, timedelta

from db.models import Post, PostStatus
from db.repo import Repository


@pytest.fixture
def repo(db_session):
    return Repository(db_session)


class TestAllowedChat:
    async def test_is_chat_allowed_true(self, repo):
        await repo.add_allowed_chat(123456)
        assert await repo.is_chat_allowed(123456) is True

    async def test_is_chat_allowed_false(self, repo):
        assert await repo.is_chat_allowed(999999) is False

    async def test_add_and_remove_allowed_chat(self, repo):
        await repo.add_allowed_chat(111, description="Test")
        assert await repo.is_chat_allowed(111) is True

        await repo.remove_allowed_chat(111)
        assert await repo.is_chat_allowed(111) is False


class TestSettings:
    async def test_get_setting_returns_none_for_missing_key(self, repo):
        result = await repo.get_setting("nonexistent")
        assert result is None

    async def test_set_and_get_setting(self, repo):
        await repo.set_setting("system_prompt", "You are an expert.")
        result = await repo.get_setting("system_prompt")
        assert result == "You are an expert."

    async def test_set_setting_overwrites(self, repo):
        await repo.set_setting("key1", "value1")
        await repo.set_setting("key1", "value2")
        result = await repo.get_setting("key1")
        assert result == "value2"


class TestPosts:
    async def test_create_post_returns_pending(self, repo):
        post = await repo.create_post(
            original_text="iPhone 15",
            generated_text="Great phone",
        )
        assert post.status == PostStatus.pending.value
        assert post.id is not None

    async def test_get_post_by_id(self, repo):
        post = await repo.create_post("query", "text")
        result = await repo.get_post(post.id)
        assert result is not None
        assert result.original_text == "query"

    async def test_update_post_status(self, repo):
        post = await repo.create_post("q", "t")
        updated = await repo.update_post_status(post.id, PostStatus.approved)
        assert updated is not None
        assert updated.status == PostStatus.approved.value

    async def test_update_post_text(self, repo):
        post = await repo.create_post("q", "old text")
        updated = await repo.update_post_text(post.id, "new text")
        assert updated is not None
        assert updated.generated_text == "new text"

    async def test_delete_post(self, repo):
        post = await repo.create_post("q", "t")
        post_id = post.id
        await repo.delete_post(post_id)
        result = await repo.get_post(post_id)
        assert result is None

    async def test_get_approved_posts_pagination(self, repo, db_session):
        # Create 7 approved posts
        for i in range(7):
            p = Post(
                original_text=f"product {i}",
                generated_text=f"text {i}",
                status=PostStatus.approved.value,
                created_at=datetime(2025, 1, 1) + timedelta(hours=i),
            )
            db_session.add(p)
        await db_session.commit()

        page1 = await repo.get_approved_posts(page=1, per_page=5)
        page2 = await repo.get_approved_posts(page=2, per_page=5)

        assert len(page1) == 5
        assert len(page2) == 2
        # Ordered by created_at asc
        assert page1[0].original_text == "product 0"
        assert page2[0].original_text == "product 5"

    async def test_count_approved_posts(self, repo, db_session):
        # 3 approved, 2 pending, 1 published
        for status, count in [
            (PostStatus.approved, 3),
            (PostStatus.pending, 2),
            (PostStatus.published, 1),
        ]:
            for i in range(count):
                db_session.add(
                    Post(
                        original_text=f"{status.value} {i}",
                        generated_text="t",
                        status=status.value,
                    )
                )
        await db_session.commit()

        count = await repo.count_approved_posts()
        assert count == 3

    async def test_get_oldest_approved_post(self, repo, db_session):
        for i in range(3):
            db_session.add(
                Post(
                    original_text=f"post {i}",
                    generated_text="t",
                    status=PostStatus.approved.value,
                    created_at=datetime(2025, 1, 1) + timedelta(days=i),
                )
            )
        await db_session.commit()

        oldest = await repo.get_oldest_approved_post()
        assert oldest is not None
        assert oldest.original_text == "post 0"

    async def test_get_oldest_approved_post_empty(self, repo):
        result = await repo.get_oldest_approved_post()
        assert result is None
