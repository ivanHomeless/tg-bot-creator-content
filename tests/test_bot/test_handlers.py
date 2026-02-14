import io
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot.handlers.start import cmd_start
from bot.handlers.create_post import start_create_post, process_create_post, group_create_post
from bot.handlers.post_actions import on_post_action, on_edit_text, on_rewrite_prompt
from bot.handlers.queue import cmd_queue, on_queue_page, on_queue_post_detail
from bot.handlers.settings import (
    on_edit_prompt_start,
    on_prompt_document,
    on_prompt_not_a_file,
    on_schedule_input,
    on_edit_providers_start,
    on_providers_json_file,
    on_chats_start,
    on_chat_add_input,
    on_chat_add_description,
    on_chat_remove,
)
from bot.states.fsm import CreatePost, EditPost, EditPrompt, EditSchedule, RewritePost
from db.models import PostStatus
from services.llm.base import LLMResponse


def _make_message(chat_type: str = "private") -> MagicMock:
    """Create a mock Message with the given chat type."""
    msg = AsyncMock()
    msg.chat = MagicMock()
    msg.chat.type = chat_type
    msg.answer = AsyncMock()
    return msg


class TestStartHandler:
    async def test_start_private_sends_menu(self):
        """/start in private chat → answer with ReplyKeyboardMarkup."""
        msg = _make_message("private")

        await cmd_start(msg)

        msg.answer.assert_called_once()
        kwargs = msg.answer.call_args
        reply_markup = kwargs.kwargs.get("reply_markup") or kwargs[1].get("reply_markup")
        assert isinstance(reply_markup, ReplyKeyboardMarkup)

    async def test_start_group_no_reply_keyboard(self):
        """/start in group → answer without ReplyKeyboardMarkup."""
        msg = _make_message("group")

        await cmd_start(msg)

        msg.answer.assert_called_once()
        kwargs = msg.answer.call_args
        reply_markup = kwargs.kwargs.get("reply_markup")
        assert reply_markup is None


# --------------- Create Post Handler ---------------


def _make_post_mock(post_id: int = 1):
    """Create a mock Post object."""
    post = MagicMock()
    post.id = post_id
    post.status = "pending"
    return post


def _make_graph_result(generated_text="Generated post", error=None):
    result = {"generated_text": generated_text}
    if error:
        result["error"] = error
    return result


class TestCreatePostHandler:
    async def test_create_post_button_sets_fsm_state(self):
        """Pressing 'Создать пост' sets FSM state to waiting_for_input."""
        msg = _make_message("private")
        state = AsyncMock()

        await start_create_post(msg, state)

        state.clear.assert_called_once()
        state.set_state.assert_called_once_with(CreatePost.waiting_for_input)
        msg.answer.assert_called_once()

    @patch("bot.handlers.create_post.build_graph")
    async def test_create_post_success(self, mock_build_graph):
        """Mocked pipeline → post saved with status=pending, preview sent."""
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = _make_graph_result("Great product post")
        mock_build_graph.return_value = mock_graph

        msg = _make_message("private")
        msg.text = "iPhone 15 Pro"
        msg.caption = None
        msg.photo = None
        msg.video = None
        msg.document = None

        state = AsyncMock()
        repo = AsyncMock()
        repo.get_setting.return_value = None
        post = _make_post_mock(post_id=42)
        repo.create_post.return_value = post

        # status_msg returned by first answer call
        status_msg = AsyncMock()
        msg.answer = AsyncMock(side_effect=[status_msg, AsyncMock()])

        await process_create_post(
            msg, state, repo,
            tavily_api_key="fake-key",
            llm_router=AsyncMock(),
            album=None,
        )

        # Post created with correct data
        repo.create_post.assert_called_once()
        call_kwargs = repo.create_post.call_args.kwargs
        assert call_kwargs["original_text"] == "iPhone 15 Pro"
        assert call_kwargs["generated_text"] == "Great product post"

        # FSM cleared
        state.clear.assert_called_once()

        # Preview sent (second answer call)
        assert msg.answer.call_count == 2

    @patch("bot.handlers.create_post.build_graph")
    async def test_create_post_with_media(self, mock_build_graph):
        """Media file_ids are extracted and saved."""
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = _make_graph_result("Post text")
        mock_build_graph.return_value = mock_graph

        msg = _make_message("private")
        msg.text = None
        msg.caption = "Product with photos"
        msg.photo = None
        msg.video = None
        msg.document = None

        # Create album messages with photos
        album_msg1 = MagicMock()
        album_msg1.photo = [MagicMock(file_id="photo_id_1")]
        album_msg1.video = None
        album_msg1.document = None

        album_msg2 = MagicMock()
        album_msg2.photo = [MagicMock(file_id="photo_id_2")]
        album_msg2.video = None
        album_msg2.document = None

        state = AsyncMock()
        repo = AsyncMock()
        repo.get_setting.return_value = None
        repo.create_post.return_value = _make_post_mock()

        status_msg = AsyncMock()
        msg.answer = AsyncMock(side_effect=[status_msg, AsyncMock()])

        await process_create_post(
            msg, state, repo,
            tavily_api_key="fake-key",
            llm_router=AsyncMock(),
            album=[album_msg1, album_msg2],
        )

        call_kwargs = repo.create_post.call_args.kwargs
        media_ids = call_kwargs["media_ids"]
        assert len(media_ids) == 2
        assert "photo:photo_id_1" in media_ids[0]
        assert "photo:photo_id_2" in media_ids[1]

    @patch("bot.handlers.create_post.build_graph")
    async def test_create_post_search_failure(self, mock_build_graph):
        """Search failure → fallback text saved in generated_text."""
        from services.ai.prompts import SEARCH_FALLBACK_TEXT

        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = _make_graph_result(
            SEARCH_FALLBACK_TEXT, error="search_failed"
        )
        mock_build_graph.return_value = mock_graph

        msg = _make_message("private")
        msg.text = "Unknown product"
        msg.caption = None
        msg.photo = None
        msg.video = None
        msg.document = None

        state = AsyncMock()
        repo = AsyncMock()
        repo.get_setting.return_value = None
        repo.create_post.return_value = _make_post_mock()

        status_msg = AsyncMock()
        msg.answer = AsyncMock(side_effect=[status_msg, AsyncMock()])

        await process_create_post(
            msg, state, repo,
            tavily_api_key="fake-key",
            llm_router=AsyncMock(),
            album=None,
        )

        call_kwargs = repo.create_post.call_args.kwargs
        assert call_kwargs["generated_text"] == SEARCH_FALLBACK_TEXT

    @patch("bot.handlers.create_post.build_graph")
    async def test_create_post_shows_inline_buttons(self, mock_build_graph):
        """Preview message includes InlineKeyboardMarkup."""
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = _make_graph_result("Post content")
        mock_build_graph.return_value = mock_graph

        msg = _make_message("private")
        msg.text = "MacBook Pro"
        msg.caption = None
        msg.photo = None
        msg.video = None
        msg.document = None

        state = AsyncMock()
        repo = AsyncMock()
        repo.get_setting.return_value = None
        repo.create_post.return_value = _make_post_mock(post_id=7)

        status_msg = AsyncMock()
        preview_call = AsyncMock()
        msg.answer = AsyncMock(side_effect=[status_msg, preview_call])

        await process_create_post(
            msg, state, repo,
            tavily_api_key="fake-key",
            llm_router=AsyncMock(),
            album=None,
        )

        # Second answer call is the preview
        preview_kwargs = msg.answer.call_args_list[1].kwargs
        reply_markup = preview_kwargs.get("reply_markup")
        assert isinstance(reply_markup, InlineKeyboardMarkup)

    @patch("bot.handlers.create_post.build_graph")
    async def test_group_create_post(self, mock_build_graph):
        """Text message in group → immediate post generation (no FSM)."""
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = _make_graph_result("Group post")
        mock_build_graph.return_value = mock_graph

        msg = _make_message("group")
        msg.text = "Samsung Galaxy S24"
        msg.caption = None
        msg.photo = None
        msg.video = None
        msg.document = None

        repo = AsyncMock()
        repo.get_setting.return_value = None
        repo.create_post.return_value = _make_post_mock(post_id=10)

        status_msg = AsyncMock()
        msg.answer = AsyncMock(side_effect=[status_msg, AsyncMock()])

        await group_create_post(
            msg, repo,
            tavily_api_key="fake-key",
            llm_router=AsyncMock(),
            album=None,
        )

        repo.create_post.assert_called_once()
        call_kwargs = repo.create_post.call_args.kwargs
        assert call_kwargs["original_text"] == "Samsung Galaxy S24"
        assert call_kwargs["generated_text"] == "Group post"
        assert msg.answer.call_count == 2


# --------------- Post Actions Handler ---------------


def _make_callback(post_id: int, action: str, msg_text: str = "Post text"):
    """Create a mock CallbackQuery for post:{id}:{action}."""
    cb = AsyncMock()
    cb.data = f"post:{post_id}:{action}"
    cb.message = AsyncMock()
    cb.message.text = msg_text
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


class TestPostActionsHandler:
    async def test_publish_now_calls_publisher(self):
        """Publish action calls publish_post callable."""
        cb = _make_callback(1, "publish")
        repo = AsyncMock()
        post = _make_post_mock(post_id=1)
        post.status = PostStatus.pending.value
        repo.get_post.return_value = post
        repo.update_post_status.return_value = post

        publish_fn = AsyncMock()
        state = AsyncMock()

        await on_post_action(cb, state, repo, publish_post=publish_fn)

        publish_fn.assert_called_once_with(post)

    async def test_publish_now_updates_status(self):
        """Publish action sets status to published."""
        cb = _make_callback(1, "publish")
        repo = AsyncMock()
        post = _make_post_mock(post_id=1)
        post.status = PostStatus.pending.value
        repo.get_post.return_value = post

        state = AsyncMock()

        await on_post_action(cb, state, repo, publish_post=AsyncMock())

        repo.update_post_status.assert_called_with(1, PostStatus.published)

    async def test_approve_sets_status(self):
        """Approve action sets status to approved."""
        cb = _make_callback(1, "approve")
        repo = AsyncMock()
        post = _make_post_mock(post_id=1)
        post.status = PostStatus.pending.value
        repo.get_post.return_value = post

        state = AsyncMock()

        await on_post_action(cb, state, repo)

        repo.update_post_status.assert_called_with(1, PostStatus.approved)

    async def test_edit_enters_fsm_state(self):
        """Edit action sets FSM to EditPost.waiting_for_text."""
        cb = _make_callback(1, "edit")
        repo = AsyncMock()
        post = _make_post_mock(post_id=1)
        post.status = PostStatus.pending.value
        repo.get_post.return_value = post

        state = AsyncMock()

        await on_post_action(cb, state, repo)

        state.set_state.assert_called_once_with(EditPost.waiting_for_text)
        state.update_data.assert_called_once_with(edit_post_id=1)

    async def test_edit_sets_editing_status(self):
        """Edit action sets post status to editing."""
        cb = _make_callback(1, "edit")
        repo = AsyncMock()
        post = _make_post_mock(post_id=1)
        post.status = PostStatus.pending.value
        repo.get_post.return_value = post

        state = AsyncMock()

        await on_post_action(cb, state, repo)

        repo.update_post_status.assert_called_with(1, PostStatus.editing)

    async def test_edit_submit_new_text(self):
        """Submitting new text in EditPost FSM updates generated_text and sets status=pending."""
        msg = _make_message("private")
        msg.text = "Updated post text"

        state = AsyncMock()
        state.get_data.return_value = {"edit_post_id": 5}

        repo = AsyncMock()

        await on_edit_text(msg, state, repo)

        repo.update_post_text.assert_called_once_with(5, "Updated post text")
        repo.update_post_status.assert_called_once_with(5, PostStatus.pending)
        state.clear.assert_called_once()

        # Preview with inline buttons sent
        preview_kwargs = msg.answer.call_args.kwargs
        assert isinstance(preview_kwargs.get("reply_markup"), InlineKeyboardMarkup)

    async def test_rewrite_calls_llm(self):
        """Rewrite action calls llm_router.generate with the prompt."""
        msg = _make_message("private")
        msg.text = "Make it shorter"

        state = AsyncMock()
        state.get_data.return_value = {"rewrite_post_id": 3}

        repo = AsyncMock()
        post = _make_post_mock(post_id=3)
        post.generated_text = "Original long text"
        repo.get_post.return_value = post

        llm_router = AsyncMock()
        llm_router.generate.return_value = LLMResponse(
            text="Short text", provider_name="test", model="m"
        )

        status_msg = AsyncMock()
        msg.answer = AsyncMock(side_effect=[status_msg, AsyncMock()])

        await on_rewrite_prompt(msg, state, repo, llm_router=llm_router)

        llm_router.generate.assert_called_once()
        call_messages = llm_router.generate.call_args[0][0]
        user_msg = next(m for m in call_messages if m["role"] == "user")
        assert "Make it shorter" in user_msg["content"]

        repo.update_post_text.assert_called_once_with(3, "Short text")
        repo.update_post_status.assert_called_once_with(3, PostStatus.pending)

    async def test_delete_removes_from_db(self):
        """Delete action calls repo.delete_post."""
        cb = _make_callback(1, "delete")
        repo = AsyncMock()
        post = _make_post_mock(post_id=1)
        post.status = PostStatus.pending.value
        repo.get_post.return_value = post

        state = AsyncMock()

        await on_post_action(cb, state, repo)

        repo.delete_post.assert_called_once_with(1)

    async def test_action_on_editing_post_blocked(self):
        """Actions on a post with status=editing are rejected."""
        cb = _make_callback(1, "approve")
        repo = AsyncMock()
        post = _make_post_mock(post_id=1)
        post.status = PostStatus.editing.value
        repo.get_post.return_value = post

        state = AsyncMock()

        await on_post_action(cb, state, repo)

        # Status not changed, callback answered with reject message
        repo.update_post_status.assert_not_called()
        cb.answer.assert_called_once()
        assert "редактируется" in cb.answer.call_args[0][0]


# --------------- Queue Handler ---------------


def _make_approved_post(post_id: int, text: str = "Post text"):
    p = MagicMock()
    p.id = post_id
    p.generated_text = text
    p.original_text = "query"
    return p


class TestQueueHandler:
    async def test_queue_empty(self):
        """Empty queue → 'Очередь пуста'."""
        msg = _make_message("private")
        repo = AsyncMock()
        repo.count_approved_posts.return_value = 0

        await cmd_queue(msg, repo)

        msg.answer.assert_called_once()
        assert "пуста" in msg.answer.call_args[0][0].lower()

    async def test_queue_shows_posts(self):
        """3 approved posts displayed with inline keyboard."""
        msg = _make_message("private")
        repo = AsyncMock()
        repo.count_approved_posts.return_value = 3
        repo.get_approved_posts.return_value = [
            _make_approved_post(1, "First post"),
            _make_approved_post(2, "Second post"),
            _make_approved_post(3, "Third post"),
        ]

        await cmd_queue(msg, repo)

        msg.answer.assert_called_once()
        kwargs = msg.answer.call_args.kwargs
        markup = kwargs.get("reply_markup")
        assert isinstance(markup, InlineKeyboardMarkup)
        # 3 post rows + 1 nav row = 4 rows
        assert len(markup.inline_keyboard) == 4

    async def test_queue_pagination(self):
        """7 posts → page 1 has 5 items, page 2 has 2 items."""
        # Page 1
        msg = _make_message("private")
        repo = AsyncMock()
        repo.count_approved_posts.return_value = 7
        repo.get_approved_posts.return_value = [
            _make_approved_post(i, f"Post {i}") for i in range(1, 6)
        ]

        await cmd_queue(msg, repo)

        markup = msg.answer.call_args.kwargs["reply_markup"]
        # 5 post rows + 1 nav row
        assert len(markup.inline_keyboard) == 6
        # Nav row should have page counter and next button
        nav_row = markup.inline_keyboard[-1]
        assert any("1/2" in btn.text for btn in nav_row)
        assert any("➡️" in btn.text for btn in nav_row)

    async def test_queue_post_detail(self):
        """Clicking a post shows its preview with action buttons."""
        cb = AsyncMock()
        cb.data = "queue:post:5"
        cb.message = AsyncMock()
        cb.message.edit_text = AsyncMock()
        cb.answer = AsyncMock()

        repo = AsyncMock()
        post = _make_approved_post(5, "Detailed post text")
        repo.get_post.return_value = post

        await on_queue_post_detail(cb, repo)

        cb.message.edit_text.assert_called_once()
        call_kwargs = cb.message.edit_text.call_args.kwargs
        assert isinstance(call_kwargs.get("reply_markup"), InlineKeyboardMarkup)

    async def test_queue_page_navigation(self):
        """Page navigation edits the message with new page content."""
        cb = AsyncMock()
        cb.data = "queue:page:2"
        cb.message = AsyncMock()
        cb.message.edit_text = AsyncMock()
        cb.answer = AsyncMock()

        repo = AsyncMock()
        repo.count_approved_posts.return_value = 7
        repo.get_approved_posts.return_value = [
            _make_approved_post(6, "Post 6"),
            _make_approved_post(7, "Post 7"),
        ]

        await on_queue_page(cb, repo)

        repo.get_approved_posts.assert_called_once_with(page=2, per_page=5)
        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called_once()


# --------------- Settings Handler ---------------


class TestSettingsHandler:
    async def test_edit_prompt_text_rejected(self):
        """Text message → rejected, asks for .txt file."""
        msg = _make_message("private")
        msg.text = "Some text"

        await on_prompt_not_a_file(msg)

        msg.answer.assert_called_once()
        assert ".txt" in msg.answer.call_args[0][0]

    async def test_edit_prompt_start_sends_file(self):
        """Starting prompt edit sends current prompt as .txt file."""
        cb = AsyncMock()
        cb.data = "settings:prompt"
        cb.message = AsyncMock()
        cb.answer = AsyncMock()
        repo = AsyncMock()
        repo.get_setting.return_value = "Current prompt"
        state = AsyncMock()

        await on_edit_prompt_start(cb, state, repo)

        cb.message.answer_document.assert_called_once()
        state.set_state.assert_called_once_with(EditPrompt.waiting_for_prompt)

    async def test_edit_prompt_txt_file(self):
        """Sending .txt file → prompt saved to DB immediately."""
        msg = _make_message("private")
        msg.document = MagicMock()
        msg.document.file_name = "prompt.txt"

        bot = AsyncMock()
        file_content = io.BytesIO(b"File prompt content")
        bot.download.return_value = file_content

        state = AsyncMock()
        repo = AsyncMock()

        await on_prompt_document(msg, state, repo, bot)

        repo.set_setting.assert_called_once_with("system_prompt", "File prompt content")
        state.clear.assert_called_once()

    @patch("bot.handlers.settings.reschedule")
    @patch("bot.handlers.settings.CronTrigger")
    async def test_edit_schedule_valid_cron(self, mock_cron_cls, mock_reschedule):
        """Valid cron expression → saved to DB + scheduler updated."""
        mock_cron_cls.from_crontab.return_value = MagicMock()

        msg = _make_message("private")
        msg.text = "0 9 * * *"
        state = AsyncMock()
        repo = AsyncMock()
        scheduler = MagicMock()

        await on_schedule_input(msg, state, repo, scheduler)

        repo.set_setting.assert_called_once_with("cron_schedule", "0 9 * * *")
        mock_reschedule.assert_called_once_with(scheduler, "0 9 * * *")
        state.clear.assert_called_once()

    @patch("bot.handlers.settings.reschedule")
    @patch("bot.handlers.settings.CronTrigger")
    async def test_edit_schedule_invalid_cron(self, mock_cron_cls, mock_reschedule):
        """Invalid cron expression → error message, state not cleared."""
        mock_cron_cls.from_crontab.side_effect = ValueError("bad cron")

        msg = _make_message("private")
        msg.text = "not a cron"
        state = AsyncMock()
        repo = AsyncMock()
        scheduler = MagicMock()

        await on_schedule_input(msg, state, repo, scheduler)

        repo.set_setting.assert_not_called()
        mock_reschedule.assert_not_called()
        state.clear.assert_not_called()
        # Error message sent
        assert msg.answer.call_count == 1
        assert "❌" in msg.answer.call_args[0][0]

    async def test_edit_providers_shows_current_config(self):
        """Starting provider edit sends current JSON config as file."""
        cb = AsyncMock()
        cb.data = "settings:providers"
        cb.message = AsyncMock()
        cb.answer = AsyncMock()

        state = AsyncMock()
        repo = AsyncMock()
        current_config = json.dumps([{"type": "gemini", "api_keys": ["k1"]}])
        repo.get_setting.return_value = current_config

        await on_edit_providers_start(cb, state, repo)

        # Current config sent as file
        cb.message.answer_document.assert_called_once()
        call_args = cb.message.answer_document.call_args
        assert call_args[1].get("caption") == "Текущий конфиг провайдеров" or \
               call_args[0][0].filename == "llm_providers.json"

    async def test_edit_providers_valid_json_file(self):
        """Valid .json file → saved to DB."""
        config = [
            {"type": "gemini", "api_keys": ["k1"], "models": ["flash"]},
            {"type": "openai_compatible", "api_keys": ["sk-1"], "models": ["gpt-4o"]},
        ]

        msg = _make_message("private")
        msg.document = MagicMock()
        msg.document.file_name = "providers.json"

        bot = AsyncMock()
        file_content = io.BytesIO(json.dumps(config).encode("utf-8"))
        bot.download.return_value = file_content

        state = AsyncMock()
        repo = AsyncMock()

        await on_providers_json_file(msg, state, repo, bot)

        repo.set_setting.assert_called_once()
        saved = json.loads(repo.set_setting.call_args[0][1])
        assert len(saved) == 2
        state.clear.assert_called_once()

    async def test_edit_providers_invalid_json_file(self):
        """Invalid JSON → rejection, state not cleared."""
        msg = _make_message("private")
        msg.document = MagicMock()
        msg.document.file_name = "bad.json"

        bot = AsyncMock()
        file_content = io.BytesIO(b"not json at all")
        bot.download.return_value = file_content

        state = AsyncMock()
        repo = AsyncMock()

        await on_providers_json_file(msg, state, repo, bot)

        repo.set_setting.assert_not_called()
        state.clear.assert_not_called()
        assert "❌" in msg.answer.call_args[0][0]

    # ---- Chats management ----

    async def test_chats_list(self):
        """settings:chats → shows list of allowed chats."""
        cb = AsyncMock()
        cb.data = "settings:chats"
        cb.message = AsyncMock()
        cb.answer = AsyncMock()

        state = AsyncMock()
        repo = AsyncMock()
        chat_obj = MagicMock()
        chat_obj.id = 1
        chat_obj.telegram_id = -100123
        chat_obj.username = "mygroup"
        chat_obj.description = "My Group"
        repo.get_all_allowed_chats.return_value = [chat_obj]

        await on_chats_start(cb, state, repo)

        cb.message.answer.assert_called_once()
        # Description shown as label
        call_kwargs = cb.message.answer.call_args
        assert "Разрешённые чаты" in call_kwargs[0][0]
        state.clear.assert_called_once()

    async def test_add_chat_by_username_step1(self):
        """Step 1: @username → resolves, asks for description."""
        msg = _make_message("private")
        msg.text = "@testgroup"
        state = AsyncMock()
        state.get_data.return_value = {}
        repo = AsyncMock()
        repo.is_chat_allowed.return_value = False

        bot = AsyncMock()
        chat_info = MagicMock()
        chat_info.id = -1001234567890
        chat_info.username = "testgroup"
        bot.get_chat.return_value = chat_info

        await on_chat_add_input(msg, state, repo, bot)

        # Saves data to FSM and asks for description
        state.update_data.assert_called_once_with(
            telegram_id=-1001234567890, username="testgroup",
        )
        state.set_state.assert_called_once()
        assert "описание" in msg.answer.call_args[0][0].lower()

    async def test_add_chat_step2_description(self):
        """Step 2: description → saves chat to DB."""
        msg = _make_message("private")
        msg.text = "Рабочая группа"
        state = AsyncMock()
        state.get_data.return_value = {
            "telegram_id": -1001234567890,
            "username": "testgroup",
        }
        repo = AsyncMock()
        repo.add_allowed_chat.return_value = MagicMock()
        repo.get_all_allowed_chats.return_value = []

        await on_chat_add_description(msg, state, repo)

        repo.add_allowed_chat.assert_called_once_with(
            -1001234567890, username="testgroup", description="Рабочая группа",
        )
        state.clear.assert_called_once()

    async def test_add_chat_by_id_step1(self):
        """Step 1: numeric ID → asks for description."""
        msg = _make_message("private")
        msg.text = "-1009876543210"
        state = AsyncMock()
        repo = AsyncMock()
        repo.is_chat_allowed.return_value = False

        bot = AsyncMock()
        bot.get_chat.side_effect = Exception("not found")

        await on_chat_add_input(msg, state, repo, bot)

        state.update_data.assert_called_once()
        assert state.update_data.call_args[1]["telegram_id"] == -1009876543210
        state.set_state.assert_called_once()

    async def test_add_chat_duplicate(self):
        """Adding already existing chat → message, no duplicate."""
        msg = _make_message("private")
        msg.text = "-100123"
        state = AsyncMock()
        repo = AsyncMock()
        repo.is_chat_allowed.return_value = True

        bot = AsyncMock()
        bot.get_chat.side_effect = Exception("not found")

        await on_chat_add_input(msg, state, repo, bot)

        repo.add_allowed_chat.assert_not_called()

    async def test_remove_chat(self):
        """Remove chat via callback → removed from DB."""
        cb = AsyncMock()
        cb.data = "chats:remove:5"
        cb.message = AsyncMock()
        cb.answer = AsyncMock()

        repo = AsyncMock()
        chat_obj = MagicMock()
        chat_obj.telegram_id = -100999
        chat_obj.username = "oldgroup"
        repo.session = AsyncMock()
        repo.session.get.return_value = chat_obj
        repo.get_all_allowed_chats.return_value = []

        await on_chat_remove(cb, repo)

        repo.remove_allowed_chat.assert_called_once_with(-100999)
