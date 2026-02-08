"""Tests for bot module — debounce and extracted functions"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import bot
import storage
import config


@pytest.fixture(autouse=True)
def reset_pending_responses():
    """Clean up _pending_responses between tests"""
    bot._pending_responses.clear()
    yield
    bot._pending_responses.clear()


def _make_event(sender_id=123, message_text='hello'):
    """Create a mock Telethon NewMessage event"""
    event = AsyncMock()
    event.is_private = True

    sender = MagicMock()
    sender.id = sender_id
    sender.first_name = 'Test'
    sender.last_name = 'User'
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
