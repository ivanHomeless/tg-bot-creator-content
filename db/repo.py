from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AllowedChat, Post, PostStatus, Setting


class Repository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # --- AllowedChat ---

    async def is_chat_allowed(self, telegram_id: int) -> bool:
        stmt = select(AllowedChat).where(AllowedChat.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def add_allowed_chat(
        self, telegram_id: int, description: str = ""
    ) -> AllowedChat:
        chat = AllowedChat(telegram_id=telegram_id, description=description)
        self.session.add(chat)
        await self.session.commit()
        return chat

    async def remove_allowed_chat(self, telegram_id: int) -> None:
        stmt = delete(AllowedChat).where(AllowedChat.telegram_id == telegram_id)
        await self.session.execute(stmt)
        await self.session.commit()

    # --- Settings ---

    async def get_setting(self, key: str) -> str | None:
        result = await self.session.get(Setting, key)
        return result.value if result else None

    async def set_setting(self, key: str, value: str) -> None:
        existing = await self.session.get(Setting, key)
        if existing:
            existing.value = value
        else:
            self.session.add(Setting(key=key, value=value))
        await self.session.commit()

    # --- Posts ---

    async def create_post(
        self,
        original_text: str,
        generated_text: str,
        media_ids: list[dict] | None = None,
    ) -> Post:
        post = Post(
            original_text=original_text,
            generated_text=generated_text,
            media_ids=media_ids,
        )
        self.session.add(post)
        await self.session.commit()
        return post

    async def get_post(self, post_id: int) -> Post | None:
        return await self.session.get(Post, post_id)

    async def update_post_status(
        self, post_id: int, status: PostStatus
    ) -> Post | None:
        post = await self.session.get(Post, post_id)
        if post is None:
            return None
        post.status = status.value
        await self.session.commit()
        return post

    async def update_post_text(
        self, post_id: int, generated_text: str
    ) -> Post | None:
        post = await self.session.get(Post, post_id)
        if post is None:
            return None
        post.generated_text = generated_text
        await self.session.commit()
        return post

    async def delete_post(self, post_id: int) -> None:
        stmt = delete(Post).where(Post.id == post_id)
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_approved_posts(
        self, page: int = 1, per_page: int = 5
    ) -> list[Post]:
        offset = (page - 1) * per_page
        stmt = (
            select(Post)
            .where(Post.status == PostStatus.approved.value)
            .order_by(Post.created_at.asc())
            .offset(offset)
            .limit(per_page)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_approved_posts(self) -> int:
        stmt = select(func.count()).select_from(Post).where(
            Post.status == PostStatus.approved.value
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_oldest_approved_post(self) -> Post | None:
        stmt = (
            select(Post)
            .where(Post.status == PostStatus.approved.value)
            .order_by(Post.created_at.asc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
