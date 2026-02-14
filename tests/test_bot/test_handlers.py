import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot.handlers.start import cmd_start
from bot.handlers.create_post import start_create_post, process_create_post
from bot.states.fsm import CreatePost


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
        # No reply_markup kwarg or it's not a ReplyKeyboardMarkup
        reply_markup = kwargs.kwargs.get("reply_markup") or kwargs[1].get("reply_markup") if kwargs[1] else None
        assert reply_markup is None or not isinstance(reply_markup, ReplyKeyboardMarkup)


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
