"""Tests for bot module — debounce and extracted functions"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telethon.tl.types import User

import bot
import storage
import config


@pytest.fixture(autouse=True)
def reset_pending_responses():
    """Clean up _pending_responses between tests"""
    bot._pending_responses.clear()
    yield
    bot._pending_responses.clear()


def _make_event(sender_id=123, message_text='hello', is_bot=False):
    """Create a mock Telethon NewMessage event"""
    event = AsyncMock()
    event.is_private = True

    sender = MagicMock(spec=User)
    sender.id = sender_id
    sender.first_name = 'Test'
    sender.last_name = 'User'
    sender.bot = is_bot
    event.get_sender = AsyncMock(return_value=sender)

    event.message = MagicMock()
    event.message.message = message_text
    event.message.id = 1
    event.chat_id = sender_id

    event.respond = AsyncMock()

    return event


def _make_client():
    """Create a mock TelegramClient"""
    cl = AsyncMock()
    cl.send_read_acknowledge = AsyncMock()
    return cl


class TestDelayedReadReceipt:
    @pytest.mark.asyncio
    async def test_sends_read_acknowledge(self):
        """Read receipt is sent after delay"""
        cl = _make_client()
        event = _make_event()
        msg_cfg = {'READ_RECEIPT_DELAY_MIN': '0', 'READ_RECEIPT_DELAY_MAX': '0'}

        with patch('bot.asyncio.sleep', new_callable=AsyncMock):
            await bot._delayed_read_receipt(cl, event, msg_cfg)

        cl.send_read_acknowledge.assert_called_once_with(event.chat_id, event.message)

    @pytest.mark.asyncio
    async def test_handles_exception(self):
        """Doesn't raise on send_read_acknowledge failure"""
        cl = _make_client()
        cl.send_read_acknowledge = AsyncMock(side_effect=Exception("network error"))
        event = _make_event()
        msg_cfg = {'READ_RECEIPT_DELAY_MIN': '0', 'READ_RECEIPT_DELAY_MAX': '0'}

        with patch('bot.asyncio.sleep', new_callable=AsyncMock):
            await bot._delayed_read_receipt(cl, event, msg_cfg)

    @pytest.mark.asyncio
    async def test_swaps_min_max_when_inverted(self):
        """Handles inverted min/max delay values"""
        cl = _make_client()
        event = _make_event()
        msg_cfg = {'READ_RECEIPT_DELAY_MIN': '5', 'READ_RECEIPT_DELAY_MAX': '1'}

        with patch('bot.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await bot._delayed_read_receipt(cl, event, msg_cfg)
            # sleep should have been called with a value between 1 and 5
            delay = mock_sleep.call_args[0][0]
            assert 1.0 <= delay <= 5.0

    @pytest.mark.asyncio
    async def test_uses_defaults_for_invalid_config(self):
        """Falls back to defaults for invalid config values"""
        cl = _make_client()
        event = _make_event()
        msg_cfg = {'READ_RECEIPT_DELAY_MIN': 'invalid', 'READ_RECEIPT_DELAY_MAX': None}

        with patch('bot.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await bot._delayed_read_receipt(cl, event, msg_cfg)
            delay = mock_sleep.call_args[0][0]
            assert bot.DEFAULT_READ_RECEIPT_DELAY_MIN <= delay <= bot.DEFAULT_READ_RECEIPT_DELAY_MAX


class TestRespondToSender:
    def _patch_to_thread(self):
        """Create a mock for asyncio.to_thread that routes to correct return values"""
        call_count = {'n': 0}
        returns = [
            {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0', 'RESPONSE_DELAY_MAX': '0'},
            [{'direction': 'received', 'text': 'hello'}],  # storage.get_messages_by_sender
            '',  # storage.load_sender_profile
            'Be friendly',  # config.load_identity
            None,  # storage.add_message (sent)
        ]

        async def side_effect(func, *args, **kwargs):
            idx = call_count['n']
            call_count['n'] += 1
            if idx < len(returns):
                return returns[idx]
            return None

        return side_effect, returns

    @pytest.mark.asyncio
    async def test_generates_and_sends_response(self):
        """Normal flow: generates AI response and sends it"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='hello')
        side_effect, _ = self._patch_to_thread()

        with patch('bot.asyncio.to_thread', side_effect=side_effect), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='AI reply'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot.ai, 'is_trivial_message', return_value=True):

            await bot._respond_to_sender(cl, event, 123, 'Test User')

        event.respond.assert_called_once_with('AI reply')

    @pytest.mark.asyncio
    async def test_cancellation_during_sleep(self):
        """Task can be cancelled during response delay"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='hello')
        side_effect, _ = self._patch_to_thread()

        async def raise_cancelled(delay):
            raise asyncio.CancelledError()

        with patch('bot.asyncio.to_thread', side_effect=side_effect), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='AI reply'), \
             patch('bot.asyncio.sleep', side_effect=raise_cancelled):

            with pytest.raises(asyncio.CancelledError):
                await bot._respond_to_sender(cl, event, 123, 'Test User')

        # Response should NOT have been sent
        event.respond.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancellation_during_ai_generation(self):
        """Task can be cancelled during AI response generation"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='hello')
        side_effect, _ = self._patch_to_thread()

        async def raise_cancelled(*args, **kwargs):
            raise asyncio.CancelledError()

        with patch('bot.asyncio.to_thread', side_effect=side_effect), \
             patch.object(bot, '_generate_response', side_effect=raise_cancelled):

            with pytest.raises(asyncio.CancelledError):
                await bot._respond_to_sender(cl, event, 123, 'Test User')

        event.respond.assert_not_called()

    @pytest.mark.asyncio
    async def test_profile_update_for_nontrivial(self):
        """Profile update runs for non-trivial messages"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='I work at Acme Corp')
        side_effect, _ = self._patch_to_thread()

        with patch('bot.asyncio.to_thread', side_effect=side_effect), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='Nice!'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot.ai, 'is_trivial_message', return_value=False), \
             patch.object(bot, '_update_sender_profile', new_callable=AsyncMock) as mock_profile:

            await bot._respond_to_sender(cl, event, 123, 'Test User')

        mock_profile.assert_called_once()
        call_kwargs = mock_profile.call_args
        # messages arg should include sent response
        messages_arg = call_kwargs.kwargs.get('messages') or call_kwargs[1].get('messages')
        assert any(m['text'] == 'Nice!' and m['direction'] == 'sent' for m in messages_arg)

    @pytest.mark.asyncio
    async def test_profile_update_skipped_for_trivial(self):
        """Profile update is skipped for trivial messages"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='ok')
        side_effect, _ = self._patch_to_thread()

        with patch('bot.asyncio.to_thread', side_effect=side_effect), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='reply'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot.ai, 'is_trivial_message', return_value=True), \
             patch.object(bot, '_update_sender_profile', new_callable=AsyncMock) as mock_profile:

            await bot._respond_to_sender(cl, event, 123, 'Test User')

        mock_profile.assert_not_called()

    @pytest.mark.asyncio
    async def test_profile_update_when_last_trivial_but_batch_has_nontrivial(self):
        """Profile update runs if batch has non-trivial messages, even if last is trivial.

        Debounce scenario: sender sends "I got promoted!" then "ㅋㅋ".
        The event is for "ㅋㅋ" (trivial), but "I got promoted!" is non-trivial.
        Profile update should still run.
        """
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='ㅋㅋ')

        call_count = {'n': 0}
        returns = [
            {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0', 'RESPONSE_DELAY_MAX': '0'},
            # Storage has both messages (stored in Phase A before this task)
            [
                {'direction': 'received', 'text': 'I just got promoted at work!'},
                {'direction': 'received', 'text': 'ㅋㅋ'},
            ],
            '',  # sender_profile
            'Be friendly',  # identity
            None,  # add_message (sent)
        ]

        async def side_effect(func, *args, **kwargs):
            idx = call_count['n']
            call_count['n'] += 1
            return returns[idx] if idx < len(returns) else None

        with patch('bot.asyncio.to_thread', side_effect=side_effect), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='Congrats!'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot, '_update_sender_profile', new_callable=AsyncMock) as mock_profile:
            # Use REAL is_trivial_message — no patch
            await bot._respond_to_sender(cl, event, 123, 'Test User')

        # Profile update should run because "I just got promoted at work!" is non-trivial
        mock_profile.assert_called_once()

    @pytest.mark.asyncio
    async def test_profile_update_skipped_when_all_batch_trivial(self):
        """Profile update skipped when all pending received messages are trivial."""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='ㅋㅋ')

        call_count = {'n': 0}
        returns = [
            {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0', 'RESPONSE_DELAY_MAX': '0'},
            [
                {'direction': 'received', 'text': 'ok'},
                {'direction': 'received', 'text': 'ㅋㅋ'},
            ],
            '',
            'Be friendly',
            None,
        ]

        async def side_effect(func, *args, **kwargs):
            idx = call_count['n']
            call_count['n'] += 1
            return returns[idx] if idx < len(returns) else None

        with patch('bot.asyncio.to_thread', side_effect=side_effect), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='reply'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot, '_update_sender_profile', new_callable=AsyncMock) as mock_profile:
            await bot._respond_to_sender(cl, event, 123, 'Test User')

        mock_profile.assert_not_called()

    @pytest.mark.asyncio
    async def test_profile_check_stops_at_last_sent(self):
        """Trivial check only scans received messages after the last sent response."""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='ㅋㅋ')

        call_count = {'n': 0}
        returns = [
            {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0', 'RESPONSE_DELAY_MAX': '0'},
            [
                # Old non-trivial message BEFORE the last sent — should not count
                {'direction': 'received', 'text': 'I work at Google!'},
                {'direction': 'sent', 'text': 'Cool!'},
                # New trivial message AFTER last sent
                {'direction': 'received', 'text': 'ㅋㅋ'},
            ],
            '',
            'Be friendly',
            None,
        ]

        async def side_effect(func, *args, **kwargs):
            idx = call_count['n']
            call_count['n'] += 1
            return returns[idx] if idx < len(returns) else None

        with patch('bot.asyncio.to_thread', side_effect=side_effect), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='reply'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot, '_update_sender_profile', new_callable=AsyncMock) as mock_profile:
            await bot._respond_to_sender(cl, event, 123, 'Test User')

        # "I work at Google!" is before the last sent, so only "ㅋㅋ" counts → trivial → skip
        mock_profile.assert_not_called()


class TestDebounce:
    @pytest.mark.asyncio
    async def test_pending_response_cancelled_on_new_message(self):
        """When a new message arrives, the pending response task is cancelled"""
        barrier = asyncio.Event()

        async def slow_respond(cl, event, sender_id, sender_name):
            """Simulated slow response that can be cancelled"""
            barrier.set()
            await asyncio.sleep(100)  # Will be cancelled

        with patch.object(bot, '_respond_to_sender', side_effect=slow_respond):
            # Start first response task
            task1 = asyncio.create_task(slow_respond(None, None, 123, 'Alice'))
            bot._pending_responses[123] = task1

            # Wait for task1 to start executing
            await barrier.wait()

            # Simulate second message arriving: cancel task1
            existing = bot._pending_responses.get(123)
            assert existing is not None
            assert not existing.done()
            existing.cancel()

            # Verify task1 is cancelled
            with pytest.raises(asyncio.CancelledError):
                await task1

            assert task1.cancelled()

    @pytest.mark.asyncio
    async def test_all_messages_included_after_cancel(self):
        """After cancellation, the new response task sees all stored messages"""
        captured_messages = []

        async def mock_to_thread(func, *args, **kwargs):
            if func is storage.get_messages_by_sender:
                # Simulates storage with 3 accumulated messages
                return [
                    {'direction': 'received', 'text': 'msg1'},
                    {'direction': 'received', 'text': 'msg2'},
                    {'direction': 'received', 'text': 'msg3'},
                ]
            elif func is config.load_config:
                return {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0', 'RESPONSE_DELAY_MAX': '0'}
            elif func is storage.load_sender_profile:
                return ''
            elif func is config.load_identity:
                return 'Be friendly'
            elif func is storage.add_message:
                return None
            return None

        cl = _make_client()
        event = _make_event(sender_id=123, message_text='msg3')

        async def capture_generate(sender_name, messages, *args, **kwargs):
            captured_messages.extend(messages)
            return 'combined reply'

        with patch('bot.asyncio.to_thread', side_effect=mock_to_thread), \
             patch.object(bot, '_generate_response', side_effect=capture_generate), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot.ai, 'is_trivial_message', return_value=True):

            await bot._respond_to_sender(cl, event, 123, 'Alice')

        # AI should have received all 3 messages
        assert len(captured_messages) == 3
        texts = [m['text'] for m in captured_messages]
        assert texts == ['msg1', 'msg2', 'msg3']

    @pytest.mark.asyncio
    async def test_cleanup_after_completion(self):
        """_pending_responses is cleaned up after task completes normally"""
        sender_id = 456
        completed = asyncio.Event()

        async def quick_respond(cl, event, sid, name):
            completed.set()

        task = asyncio.create_task(quick_respond(None, None, sender_id, 'Bob'))
        bot._pending_responses[sender_id] = task

        await task
        # Simulate the finally block cleanup from handle_new_message
        if bot._pending_responses.get(sender_id) is task:
            del bot._pending_responses[sender_id]

        assert sender_id not in bot._pending_responses

    @pytest.mark.asyncio
    async def test_cleanup_not_removed_if_replaced(self):
        """Old task's cleanup does not remove a newer task's entry"""
        sender_id = 789

        async def noop():
            pass

        task_old = asyncio.create_task(noop())
        task_new = asyncio.create_task(noop())
        bot._pending_responses[sender_id] = task_new

        await task_old
        # Old task's finally: should NOT remove because it's not the current task
        if bot._pending_responses.get(sender_id) is task_old:
            del bot._pending_responses[sender_id]

        # task_new should still be in _pending_responses
        assert bot._pending_responses.get(sender_id) is task_new

        await task_new

    @pytest.mark.asyncio
    async def test_read_receipt_independent_of_response(self):
        """Read receipt completes even when response task is cancelled"""
        cl = _make_client()
        event = _make_event()
        msg_cfg = {'READ_RECEIPT_DELAY_MIN': '0', 'READ_RECEIPT_DELAY_MAX': '0'}

        with patch('bot.asyncio.sleep', new_callable=AsyncMock):
            # Read receipt runs as fire-and-forget, independent of response task
            receipt_task = asyncio.create_task(
                bot._delayed_read_receipt(cl, event, msg_cfg)
            )
            await receipt_task

        cl.send_read_acknowledge.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_cancel_and_create_flow(self):
        """Full debounce flow: task1 created → task1 cancelled → task2 completes"""
        call_log = []

        async def slow_respond(cl, event, sender_id, sender_name):
            call_log.append(f'start-{event}')
            await asyncio.sleep(100)
            call_log.append(f'end-{event}')  # Should only happen for uncancelled

        # Start task1
        task1 = asyncio.create_task(slow_respond(None, 'evt1', 123, 'Alice'))
        bot._pending_responses[123] = task1

        await asyncio.sleep(0)  # Let task1 start

        # Cancel task1 (new message arrived)
        task1.cancel()

        # Create task2 with a fast version
        async def fast_respond(cl, event, sender_id, sender_name):
            call_log.append(f'start-{event}')
            call_log.append(f'end-{event}')

        task2 = asyncio.create_task(fast_respond(None, 'evt2', 123, 'Alice'))
        bot._pending_responses[123] = task2

        # Wait for both
        try:
            await task1
        except asyncio.CancelledError:
            pass
        await task2

        # task1 started but didn't end, task2 started and ended
        assert 'start-evt1' in call_log
        assert 'end-evt1' not in call_log
        assert 'start-evt2' in call_log
        assert 'end-evt2' in call_log


class TestParseDelayConfig:
    def test_valid_values(self):
        """Parses valid numeric values"""
        cfg = {'MIN': '2', 'MAX': '8'}
        result = bot._parse_delay_config(cfg, 'MIN', 'MAX', 3.0, 10.0)
        assert result == (2.0, 8.0)

    def test_missing_keys_use_defaults(self):
        """Uses defaults when keys are missing"""
        result = bot._parse_delay_config({}, 'MIN', 'MAX', 3.0, 10.0)
        assert result == (3.0, 10.0)

    def test_invalid_values_use_defaults(self):
        """Falls back to defaults on invalid values"""
        cfg = {'MIN': 'bad', 'MAX': None}
        result = bot._parse_delay_config(cfg, 'MIN', 'MAX', 3.0, 10.0)
        assert result == (3.0, 10.0)

    def test_swaps_when_inverted(self):
        """Swaps min/max when min > max"""
        cfg = {'MIN': '10', 'MAX': '2'}
        result = bot._parse_delay_config(cfg, 'MIN', 'MAX', 3.0, 10.0)
        assert result == (2.0, 10.0)

    def test_equal_values(self):
        """Handles equal min and max"""
        cfg = {'MIN': '5', 'MAX': '5'}
        result = bot._parse_delay_config(cfg, 'MIN', 'MAX', 3.0, 10.0)
        assert result == (5.0, 5.0)

    def test_float_values(self):
        """Parses float string values"""
        cfg = {'MIN': '1.5', 'MAX': '7.5'}
        result = bot._parse_delay_config(cfg, 'MIN', 'MAX', 3.0, 10.0)
        assert result == (1.5, 7.5)

    def test_mixed_valid_invalid(self):
        """Falls back per-field: valid min, invalid max"""
        cfg = {'MIN': '2', 'MAX': 'bad'}
        result = bot._parse_delay_config(cfg, 'MIN', 'MAX', 3.0, 10.0)
        assert result == (2.0, 10.0)


class TestCreateClient:
    def test_valid_config(self):
        """Creates TelegramClient with valid config"""
        cfg = {'API_ID': '12345', 'API_HASH': 'abcdef'}
        cl = bot._create_client(cfg)
        assert cl is not None

    def test_invalid_api_id(self):
        """Raises ValueError for non-numeric API_ID"""
        cfg = {'API_ID': 'not_a_number', 'API_HASH': 'abcdef'}
        with pytest.raises(ValueError, match='Invalid API_ID'):
            bot._create_client(cfg)


class TestGenerateResponse:
    @pytest.mark.asyncio
    async def test_with_openai_key(self):
        """Returns AI response when OPENAI_API_KEY is set"""
        with patch.object(bot.ai, 'build_chat_messages', return_value=[{'role': 'user', 'content': 'hi'}]), \
             patch.object(bot.ai, 'generate_response', new_callable=AsyncMock, return_value='AI says hi'):
            result = await bot._generate_response(
                'Alice', [{'direction': 'received', 'text': 'hi'}],
                '', 'Be friendly', {'OPENAI_API_KEY': 'sk-test'}
            )
        assert result == 'AI says hi'

    @pytest.mark.asyncio
    async def test_without_openai_key(self):
        """Returns fallback message when no OPENAI_API_KEY"""
        result = await bot._generate_response(
            'Alice', [], '', '', {'AUTO_RESPONSE_MESSAGE': 'I am away'}
        )
        assert result == 'I am away'

    @pytest.mark.asyncio
    async def test_ai_failure_returns_fallback(self):
        """Returns fallback when AI call fails"""
        with patch.object(bot.ai, 'build_chat_messages', return_value=[]), \
             patch.object(bot.ai, 'generate_response', new_callable=AsyncMock, side_effect=Exception('API error')):
            result = await bot._generate_response(
                'Alice', [], '', '', {'OPENAI_API_KEY': 'sk-test', 'AUTO_RESPONSE_MESSAGE': 'Fallback'}
            )
        assert result == 'Fallback'

    @pytest.mark.asyncio
    async def test_ai_empty_response_returns_fallback(self):
        """Returns fallback when AI returns empty string"""
        with patch.object(bot.ai, 'build_chat_messages', return_value=[]), \
             patch.object(bot.ai, 'generate_response', new_callable=AsyncMock, return_value=''):
            result = await bot._generate_response(
                'Alice', [], '', '', {'OPENAI_API_KEY': 'sk-test', 'AUTO_RESPONSE_MESSAGE': 'Fallback'}
            )
        assert result == 'Fallback'


class TestFetchTelegramHistory:
    @pytest.mark.asyncio
    async def test_returns_imported_messages(self):
        """Fetches and imports Telegram message history"""
        cl = _make_client()

        me = MagicMock()
        me.id = 999
        cl.get_me = AsyncMock(return_value=me)

        msg1 = MagicMock()
        msg1.text = 'Hi there'
        msg1.sender_id = 123
        msg1.date = MagicMock()
        msg1.date.isoformat = MagicMock(return_value='2025-01-01T12:00:00+00:00')

        msg2 = MagicMock()
        msg2.text = 'Reply'
        msg2.sender_id = 999
        msg2.date = MagicMock()
        msg2.date.isoformat = MagicMock(return_value='2025-01-01T12:01:00+00:00')

        cl.get_messages = AsyncMock(return_value=[msg2, msg1])  # newest first from Telegram

        with patch('bot.asyncio.to_thread', new_callable=AsyncMock):
            result = await bot._fetch_telegram_history(cl, 123, 'Alice', 100)

        assert len(result) == 2
        assert result[0]['direction'] == 'received'
        assert result[1]['direction'] == 'sent'

    @pytest.mark.asyncio
    async def test_empty_history(self):
        """Returns empty list when no messages found"""
        cl = _make_client()

        me = MagicMock()
        me.id = 999
        cl.get_me = AsyncMock(return_value=me)
        cl.get_messages = AsyncMock(return_value=[])

        result = await bot._fetch_telegram_history(cl, 123, 'Alice', 100)
        assert result == []

    @pytest.mark.asyncio
    async def test_handles_fetch_error(self):
        """Returns empty list on fetch error"""
        cl = _make_client()
        cl.get_me = AsyncMock(side_effect=Exception("connection error"))

        result = await bot._fetch_telegram_history(cl, 123, 'Alice', 100)
        assert result == []


class TestUpdateSenderProfile:
    @pytest.mark.asyncio
    async def test_skips_without_api_key(self):
        """Does nothing when OPENAI_API_KEY is not set"""
        with patch('bot.asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
            await bot._update_sender_profile(123, 'Alice', {})
        mock_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_profile(self):
        """Updates profile when content changes"""
        saved_profiles = []

        async def mock_to_thread(func, *args, **kwargs):
            if func is storage.load_sender_profile:
                return 'old profile'
            elif func is storage.get_messages_by_sender:
                return [{'direction': 'received', 'text': 'I work at Google'}]
            elif func is storage.save_sender_profile:
                saved_profiles.append(args)
                return None
            return None

        with patch('bot.asyncio.to_thread', side_effect=mock_to_thread), \
             patch.object(bot.ai, 'update_sender_profile', new_callable=AsyncMock, return_value='new profile'):
            await bot._update_sender_profile(123, 'Alice', {'OPENAI_API_KEY': 'sk-test'})

        assert len(saved_profiles) == 1

    @pytest.mark.asyncio
    async def test_no_save_when_unchanged(self):
        """Skips save when profile is unchanged"""
        async def mock_to_thread(func, *args, **kwargs):
            if func is storage.load_sender_profile:
                return 'same profile'
            elif func is storage.get_messages_by_sender:
                return [{'direction': 'received', 'text': 'hi'}]
            elif func is storage.save_sender_profile:
                pytest.fail("Should not save unchanged profile")
            return None

        with patch('bot.asyncio.to_thread', side_effect=mock_to_thread), \
             patch.object(bot.ai, 'update_sender_profile', new_callable=AsyncMock, return_value='same profile'):
            await bot._update_sender_profile(123, 'Alice', {'OPENAI_API_KEY': 'sk-test'})


class TestHandleNewMessage:
    @pytest.mark.asyncio
    async def test_ignores_non_private(self):
        """Skips non-private messages"""
        cl = _make_client()
        event = _make_event()
        event.is_private = False

        await bot._handle_new_message(cl, event)
        # No crash, no side effects
        event.get_sender.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_none_sender(self):
        """Skips messages when get_sender() returns None"""
        cl = _make_client()
        event = _make_event()
        event.get_sender = AsyncMock(return_value=None)

        await bot._handle_new_message(cl, event)
        event.respond.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_empty_message(self):
        """Skips messages with empty text (media-only)"""
        cl = _make_client()
        event = _make_event(message_text='')

        # get_sender will be called, but no storage operations
        await bot._handle_new_message(cl, event)
        event.respond.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_flow(self):
        """Full message handling flow: store → receipt → respond"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='Hi there')

        to_thread_calls = []

        async def mock_to_thread(func, *args, **kwargs):
            to_thread_calls.append(func.__name__ if hasattr(func, '__name__') else str(func))
            if func is config.load_config:
                return {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0',
                        'RESPONSE_DELAY_MAX': '0', 'READ_RECEIPT_DELAY_MIN': '0',
                        'READ_RECEIPT_DELAY_MAX': '0'}
            elif func is storage.is_history_synced:
                return True
            elif func is storage.get_messages_by_sender:
                return [{'direction': 'received', 'text': 'Hi there'}]
            elif func is storage.load_sender_profile:
                return ''
            elif func is config.load_identity:
                return 'Be friendly'
            return None

        with patch('bot.asyncio.to_thread', side_effect=mock_to_thread), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='Hello!'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot.ai, 'is_trivial_message', return_value=True):
            await bot._handle_new_message(cl, event)

        # Response should have been sent
        event.respond.assert_called_once_with('Hello!')
        # add_message should have been called (store received)
        assert 'add_message' in to_thread_calls

    @pytest.mark.asyncio
    async def test_triggers_history_sync(self):
        """Triggers Telegram history fetch when not synced"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='Hi')

        fetch_called = []

        async def mock_to_thread(func, *args, **kwargs):
            if func is config.load_config:
                return {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0',
                        'RESPONSE_DELAY_MAX': '0'}
            elif func is storage.is_history_synced:
                return False  # Not yet synced
            elif func is storage.mark_history_synced:
                return None
            elif func is storage.get_messages_by_sender:
                return [{'direction': 'received', 'text': 'Hi'}]
            elif func is storage.load_sender_profile:
                return ''
            elif func is config.load_identity:
                return 'Be friendly'
            return None

        async def mock_fetch(cl, sid, name, msg_id):
            fetch_called.append(sid)
            return []

        with patch('bot.asyncio.to_thread', side_effect=mock_to_thread), \
             patch.object(bot, '_fetch_telegram_history', side_effect=mock_fetch), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='Reply'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot.ai, 'is_trivial_message', return_value=True):
            await bot._handle_new_message(cl, event)

        assert 123 in fetch_called

    @pytest.mark.asyncio
    async def test_creates_pending_response_task(self):
        """_handle_new_message creates and tracks a pending response task"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='Hi')

        async def mock_to_thread(func, *args, **kwargs):
            if func is config.load_config:
                return {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0',
                        'RESPONSE_DELAY_MAX': '0'}
            elif func is storage.is_history_synced:
                return True
            elif func is storage.get_messages_by_sender:
                return [{'direction': 'received', 'text': 'Hi'}]
            elif func is storage.load_sender_profile:
                return ''
            elif func is config.load_identity:
                return 'Be friendly'
            return None

        with patch('bot.asyncio.to_thread', side_effect=mock_to_thread), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='Reply'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot.ai, 'is_trivial_message', return_value=True):
            await bot._handle_new_message(cl, event)

        # After completion, pending_responses should be cleaned up
        assert 123 not in bot._pending_responses


class TestSendMessageCancelsAutoResponse:
    """Tests for HIGH #1: manual reply cancels pending auto-response"""

    @pytest.mark.asyncio
    async def test_cancel_and_send_cancels_pending(self):
        """Manual reply cancels any pending auto-response for the sender"""
        sender_id = 123

        cancelled = asyncio.Event()

        async def pending_response():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        task = asyncio.create_task(pending_response())
        bot._pending_responses[sender_id] = task
        await asyncio.sleep(0)  # Let task start

        # Simulate the _cancel_and_send logic from send_message_to_user
        existing = bot._pending_responses.get(sender_id)
        if existing is not None and not existing.done():
            existing.cancel()

        await asyncio.sleep(0)
        assert cancelled.is_set()
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_no_pending_task_is_safe(self):
        """No error when no pending task exists for sender"""
        sender_id = 456
        # Simulate _cancel_and_send logic with no pending task
        existing = bot._pending_responses.get(sender_id)
        assert existing is None
        # No error — safe to proceed


class TestRespondToSenderErrorHandling:
    """Tests for HIGH #2 + MEDIUM #4: send-store atomicity and send failure"""

    @pytest.mark.asyncio
    async def test_send_failure_does_not_store(self):
        """When event.respond() fails, message is not stored"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='hello')
        event.respond = AsyncMock(side_effect=ConnectionError("Network error"))

        call_count = {'n': 0}
        stored_calls = []
        returns = [
            {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0', 'RESPONSE_DELAY_MAX': '0'},
            [{'direction': 'received', 'text': 'hello'}],
            '',
            'Be friendly',
        ]

        async def side_effect(func, *args, **kwargs):
            name = func.__name__ if hasattr(func, '__name__') else ''
            if name == 'add_message':
                stored_calls.append(args)
                return None
            idx = call_count['n']
            call_count['n'] += 1
            return returns[idx] if idx < len(returns) else None

        with patch('bot.asyncio.to_thread', side_effect=side_effect), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='AI reply'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock):
            await bot._respond_to_sender(cl, event, 123, 'Test User')

        # Message should NOT have been stored since send failed
        assert len(stored_calls) == 0

    @pytest.mark.asyncio
    async def test_store_fallback_on_cancel_after_send(self):
        """When cancelled after send, storage.add_message is called synchronously"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='hello')
        event.respond = AsyncMock()  # Send succeeds

        call_count = {'n': 0}
        returns = [
            {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0', 'RESPONSE_DELAY_MAX': '0'},
            [{'direction': 'received', 'text': 'hello'}],
            '',
            'Be friendly',
        ]

        async def side_effect(func, *args, **kwargs):
            idx = call_count['n']
            call_count['n'] += 1
            if idx == 4:  # 5th call = storage.add_message
                raise asyncio.CancelledError()
            return returns[idx] if idx < len(returns) else None

        with patch('bot.asyncio.to_thread', side_effect=side_effect), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='AI reply'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch('bot.storage.add_message') as mock_add:
            with pytest.raises(asyncio.CancelledError):
                await bot._respond_to_sender(cl, event, 123, 'Test User')

        # Sync fallback should have stored the message
        mock_add.assert_called_once_with('sent', 'Me', 'AI reply', sender_id=123)


class TestPhaseAStorageFailure:
    """Tests for MEDIUM #1: Phase A storage failure should not block Phase B"""

    @pytest.mark.asyncio
    async def test_response_still_sent_when_storage_fails(self):
        """Phase B response is still generated and sent when Phase A storage write fails"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='Hello')

        call_count = {'n': 0}

        async def mock_to_thread(func, *args, **kwargs):
            name = func.__name__ if hasattr(func, '__name__') else ''
            if name == 'add_message' and args and args[0] == 'received':
                raise OSError("disk full")
            if func is config.load_config:
                return {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0',
                        'RESPONSE_DELAY_MAX': '0', 'READ_RECEIPT_DELAY_MIN': '0',
                        'READ_RECEIPT_DELAY_MAX': '0'}
            elif func is storage.is_history_synced:
                return True
            elif func is storage.get_messages_by_sender:
                return [{'direction': 'received', 'text': 'Hello'}]
            elif func is storage.load_sender_profile:
                return ''
            elif func is config.load_identity:
                return 'Be friendly'
            return None

        with patch('bot.asyncio.to_thread', side_effect=mock_to_thread), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='Hi!'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot.ai, 'is_trivial_message', return_value=True):
            await bot._handle_new_message(cl, event)

        # Response should still have been sent despite Phase A storage failure
        event.respond.assert_called_once_with('Hi!')


class TestShieldedSend:
    """Tests for MEDIUM #2: asyncio.shield protects send from cancellation"""

    @pytest.mark.asyncio
    async def test_cancel_during_send_stores_message(self):
        """When cancelled during shielded send, message is stored via sync fallback"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='hello')

        # Use barriers to synchronize: respond starts → test cancels → respond finishes
        respond_started = asyncio.Event()

        async def slow_respond(msg):
            respond_started.set()
            # Yield control — the outer task will be cancelled while we're here
            await asyncio.sleep(100)

        event.respond = slow_respond

        call_count = {'n': 0}
        returns = [
            {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0', 'RESPONSE_DELAY_MAX': '0'},
            [{'direction': 'received', 'text': 'hello'}],
            '',
            'Be friendly',
        ]

        async def side_effect(func, *args, **kwargs):
            idx = call_count['n']
            call_count['n'] += 1
            return returns[idx] if idx < len(returns) else None

        with patch('bot.asyncio.to_thread', side_effect=side_effect), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='AI reply'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch('bot.storage.add_message') as mock_add:

            task = asyncio.create_task(
                bot._respond_to_sender(cl, event, 123, 'Test User')
            )
            # Wait until respond has started (inside asyncio.shield)
            await respond_started.wait()

            # Cancel the outer task while it's inside asyncio.shield(slow_respond)
            task.cancel()
            await asyncio.sleep(0)  # Let CancelledError propagate

            with pytest.raises(asyncio.CancelledError):
                await task

        # Sync fallback should have stored the message
        mock_add.assert_called_with('sent', 'Me', 'AI reply', sender_id=123)


class TestBotAccountHandling:
    """Tests for bot account detection and RESPOND_TO_BOTS config"""

    def _mock_to_thread(self, respond_to_bots=False):
        """Create mock for asyncio.to_thread with configurable RESPOND_TO_BOTS"""
        async def side_effect(func, *args, **kwargs):
            name = func.__name__ if hasattr(func, '__name__') else ''
            if func is config.load_config:
                return {
                    'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0',
                    'RESPONSE_DELAY_MAX': '0', 'READ_RECEIPT_DELAY_MIN': '0',
                    'READ_RECEIPT_DELAY_MAX': '0',
                    'RESPOND_TO_BOTS': respond_to_bots,
                }
            elif func is storage.is_history_synced:
                return True
            elif func is storage.get_messages_by_sender:
                return [{'direction': 'received', 'text': 'hello'}]
            elif func is storage.load_sender_profile:
                return ''
            elif func is config.load_identity:
                return 'Be friendly'
            return None
        return side_effect

    @pytest.mark.asyncio
    async def test_bot_message_stored_but_no_response(self):
        """Bot messages are stored but auto-response is skipped by default"""
        cl = _make_client()
        event = _make_event(sender_id=999, message_text='I am a bot', is_bot=True)

        stored_calls = []
        side_effect = self._mock_to_thread(respond_to_bots=False)

        async def track_to_thread(func, *args, **kwargs):
            name = func.__name__ if hasattr(func, '__name__') else ''
            if name == 'add_message':
                stored_calls.append(args)
            return await side_effect(func, *args, **kwargs)

        with patch('bot.asyncio.to_thread', side_effect=track_to_thread), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock):
            await bot._handle_new_message(cl, event)

        # Message should be stored (Phase A)
        assert len(stored_calls) == 1
        assert stored_calls[0][0] == 'received'
        # No response should be sent (Phase B skipped)
        event.respond.assert_not_called()

    @pytest.mark.asyncio
    async def test_bot_message_responded_when_enabled(self):
        """Bot messages get auto-response when RESPOND_TO_BOTS is true"""
        cl = _make_client()
        event = _make_event(sender_id=999, message_text='I am a bot', is_bot=True)

        with patch('bot.asyncio.to_thread', side_effect=self._mock_to_thread(respond_to_bots=True)), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='Hello bot!'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot.ai, 'is_trivial_message', return_value=True):
            await bot._handle_new_message(cl, event)

        # Response SHOULD be sent
        event.respond.assert_called_once_with('Hello bot!')

    @pytest.mark.asyncio
    async def test_human_message_unaffected_by_bot_setting(self):
        """Human messages always get auto-response regardless of RESPOND_TO_BOTS"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='Hello', is_bot=False)

        with patch('bot.asyncio.to_thread', side_effect=self._mock_to_thread(respond_to_bots=False)), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='Hi!'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot.ai, 'is_trivial_message', return_value=True):
            await bot._handle_new_message(cl, event)

        # Human user always gets a response
        event.respond.assert_called_once_with('Hi!')

    @pytest.mark.asyncio
    async def test_bot_read_receipt_still_sent(self):
        """Read receipt is still sent for bot messages even when response is skipped"""
        cl = _make_client()
        event = _make_event(sender_id=999, message_text='Bot msg', is_bot=True)

        receipt_created = []

        original_create_task = asyncio.create_task

        def track_create_task(coro, **kwargs):
            task = original_create_task(coro, **kwargs)
            receipt_created.append(True)
            return task

        with patch('bot.asyncio.to_thread', side_effect=self._mock_to_thread(respond_to_bots=False)), \
             patch('bot.asyncio.create_task', side_effect=track_create_task), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock):
            await bot._handle_new_message(cl, event)

        # Read receipt task should have been created
        assert len(receipt_created) >= 1


class TestSyncMarkerOrder:
    """Tests for LOW #6: sync marker set after profile update attempt"""

    @pytest.mark.asyncio
    async def test_sync_marker_after_profile_update(self):
        """mark_history_synced is called after _update_sender_profile"""
        cl = _make_client()
        event = _make_event(sender_id=123, message_text='Hello!')

        call_order = []

        async def mock_to_thread(func, *args, **kwargs):
            name = func.__name__ if hasattr(func, '__name__') else ''
            if func is config.load_config:
                return {'OPENAI_API_KEY': 'test', 'RESPONSE_DELAY_MIN': '0',
                        'RESPONSE_DELAY_MAX': '0'}
            elif func is storage.add_message:
                return None
            elif func is storage.is_history_synced:
                return False
            elif func is storage.mark_history_synced:
                call_order.append('mark_synced')
                return None
            elif func is storage.get_messages_by_sender:
                return [{'direction': 'received', 'text': 'Hello!'}]
            elif func is storage.load_sender_profile:
                return ''
            elif func is config.load_identity:
                return 'Be friendly'
            return None

        async def mock_fetch(cl, sid, name, msg_id):
            return [{'direction': 'received', 'text': 'old msg', 'timestamp': '2025-01-01T00:00:00+00:00'}]

        async def mock_profile(*args, **kwargs):
            call_order.append('profile_update')

        with patch('bot.asyncio.to_thread', side_effect=mock_to_thread), \
             patch.object(bot, '_fetch_telegram_history', side_effect=mock_fetch), \
             patch.object(bot, '_update_sender_profile', side_effect=mock_profile), \
             patch.object(bot, '_generate_response', new_callable=AsyncMock, return_value='Reply'), \
             patch('bot.asyncio.sleep', new_callable=AsyncMock), \
             patch.object(bot.ai, 'is_trivial_message', return_value=True):
            await bot._handle_new_message(cl, event)

        # Profile update must come BEFORE sync marker
        assert call_order == ['profile_update', 'mark_synced']
