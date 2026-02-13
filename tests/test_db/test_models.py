import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db.models import AllowedChat, Post, PostStatus, Setting


class TestAllowedChat:
    async def test_create_allowed_chat(self, db_session):
        chat = AllowedChat(telegram_id=123456789, description="Test chat")
        db_session.add(chat)
        await db_session.commit()

        result = await db_session.get(AllowedChat, chat.id)
        assert result is not None
        assert result.telegram_id == 123456789
        assert result.description == "Test chat"

    async def test_allowed_chat_unique_telegram_id(self, db_session):
        chat1 = AllowedChat(telegram_id=111, description="First")
        db_session.add(chat1)
        await db_session.commit()

        chat2 = AllowedChat(telegram_id=111, description="Duplicate")
        db_session.add(chat2)
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestSetting:
    async def test_create_setting(self, db_session):
        setting = Setting(key="system_prompt", value="You are an expert.")
        db_session.add(setting)
        await db_session.commit()

        result = await db_session.get(Setting, "system_prompt")
        assert result is not None
        assert result.value == "You are an expert."


class TestPost:
    async def test_create_post_default_status(self, db_session):
        post = Post(original_text="iPhone 15", generated_text="Great phone")
        db_session.add(post)
        await db_session.commit()

        result = await db_session.get(Post, post.id)
        assert result is not None
        assert result.status == PostStatus.pending.value
        assert result.published_at is None

    async def test_post_status_enum_values(self, db_session):
        statuses = [s.value for s in PostStatus]
        assert statuses == ["pending", "approved", "published", "editing", "deleted"]

        for status in statuses:
            post = Post(
                original_text=f"test {status}",
                generated_text="text",
                status=status,
            )
            db_session.add(post)

        await db_session.commit()

        result = await db_session.execute(select(Post))
        posts = result.scalars().all()
        assert len(posts) == 5

    async def test_post_media_ids_json(self, db_session):
        media = [
            {"type": "photo", "file_id": "abc123"},
            {"type": "video", "file_id": "def456"},
        ]
        post = Post(
            original_text="Product",
            generated_text="Text",
            media_ids=media,
        )
        db_session.add(post)
        await db_session.commit()

        # Re-fetch to ensure JSON round-trip works
        post_id = post.id
        await db_session.reset()
        result = await db_session.get(Post, post_id)
        assert result is not None
        assert result.media_ids == media
        assert result.media_ids[0]["type"] == "photo"
        assert result.media_ids[1]["file_id"] == "def456"
