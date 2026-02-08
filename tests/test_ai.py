"""Tests for ai module"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def reset_ai_singleton(monkeypatch):
    """Reset AI module singleton state between tests"""
    import ai
    monkeypatch.setattr('ai._client', None)
    monkeypatch.setattr('ai._client_api_key', None)


def _mock_completion(content='test response'):
    """Create a mock OpenAI completion response"""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


class TestSummarizeConversation:
    @pytest.mark.asyncio
    async def test_empty_messages(self):
        """Returns empty string for empty messages"""
        import ai
        result = await ai.summarize_conversation([], 'Alice')
        assert result == ''

    @pytest.mark.asyncio
    async def test_no_api_key(self):
        """Returns empty string when no API key"""
        import ai
        messages = [{'direction': 'received', 'text': 'hello'}]
        result = await ai.summarize_conversation(messages, 'Alice', api_key='')
        assert result == ''

    @pytest.mark.asyncio
    async def test_success(self):
        """Returns summary from OpenAI"""
        import ai
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_completion('Summary of conversation')
        )

        with patch.object(ai, '_get_client', return_value=mock_client):
            messages = [
                {'direction': 'received', 'text': 'hello'},
                {'direction': 'sent', 'text': 'hi there'}
            ]
            result = await ai.summarize_conversation(
                messages, 'Alice', api_key='test-key'
            )
        assert result == 'Summary of conversation'

    @pytest.mark.asyncio
    async def test_error_returns_empty(self):
        """Returns empty string on API error"""
        import ai
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception('API Error')
        )

        with patch.object(ai, '_get_client', return_value=mock_client):
            result = await ai.summarize_conversation(
                [{'direction': 'received', 'text': 'hi'}], 'Alice', api_key='test-key'
            )
        assert result == ''


class TestGenerateResponse:
    @pytest.mark.asyncio
    async def test_no_api_key(self):
        """Returns None when no API key"""
        import ai
        result = await ai.generate_response(
            'system', 'summary', 'Alice', 'hello', api_key=''
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_success(self):
        """Returns generated response"""
        import ai
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_completion('AI response')
        )

        with patch.object(ai, '_get_client', return_value=mock_client):
            result = await ai.generate_response(
                'Be friendly', 'summary', 'Alice', 'hello',
                api_key='test-key'
            )
        assert result == 'AI response'

    @pytest.mark.asyncio
    async def test_with_profile(self):
        """Includes sender profile in system message"""
        import ai
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_completion('profiled response')
        )

        with patch.object(ai, '_get_client', return_value=mock_client):
            result = await ai.generate_response(
                'Be friendly', 'summary', 'Alice', 'hello',
                sender_profile='- Prefers Korean',
                api_key='test-key'
            )
        assert result == 'profiled response'

        # Verify profile was included in system message
        call_args = mock_client.chat.completions.create.call_args
        system_msg = call_args.kwargs['messages'][0]['content']
        assert 'Profile: Alice' in system_msg
        assert 'Prefers Korean' in system_msg

    @pytest.mark.asyncio
    async def test_fallback_system_prompt(self):
        """Uses default system prompt when none provided"""
        import ai
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_completion('default response')
        )

        with patch.object(ai, '_get_client', return_value=mock_client):
            result = await ai.generate_response(
                '', '', 'Alice', 'hello', api_key='test-key'
            )

        call_args = mock_client.chat.completions.create.call_args
        system_msg = call_args.kwargs['messages'][0]['content']
        assert system_msg == ai.DEFAULT_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_error_returns_none(self):
        """Returns None on API error"""
        import ai
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception('API Error')
        )

        with patch.object(ai, '_get_client', return_value=mock_client):
            result = await ai.generate_response(
                'system', 'summary', 'Alice', 'hello', api_key='test-key'
            )
        assert result is None


class TestUpdateSenderProfile:
    @pytest.mark.asyncio
    async def test_empty_messages(self):
        """Returns current profile for empty messages"""
        import ai
        result = await ai.update_sender_profile('existing', [], 'Alice')
        assert result == 'existing'

    @pytest.mark.asyncio
    async def test_no_api_key(self):
        """Returns current profile when no API key"""
        import ai
        messages = [{'direction': 'received', 'text': 'hello'}]
        result = await ai.update_sender_profile(
            'existing', messages, 'Alice', api_key=''
        )
        assert result == 'existing'

    @pytest.mark.asyncio
    async def test_success(self):
        """Returns updated profile from OpenAI"""
        import ai
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_completion('- Works at Acme\n- Prefers English')
        )

        with patch.object(ai, '_get_client', return_value=mock_client):
            result = await ai.update_sender_profile(
                '', [{'direction': 'received', 'text': 'I work at Acme'}],
                'Alice', api_key='test-key'
            )
        assert 'Acme' in result

    @pytest.mark.asyncio
    async def test_error_returns_current(self):
        """Returns current profile on API error"""
        import ai
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception('API Error')
        )

        with patch.object(ai, '_get_client', return_value=mock_client):
            result = await ai.update_sender_profile(
                'keep this',
                [{'direction': 'received', 'text': 'hi'}],
                'Alice', api_key='test-key'
            )
        assert result == 'keep this'

    @pytest.mark.asyncio
    async def test_limits_recent_messages(self):
        """Only uses last PROFILE_RECENT_MESSAGES_LIMIT messages"""
        import ai
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_completion('profile')
        )

        messages = [{'direction': 'received', 'text': f'msg{i}'} for i in range(20)]

        with patch.object(ai, '_get_client', return_value=mock_client):
            await ai.update_sender_profile(
                '', messages, 'Alice', api_key='test-key'
            )

        call_args = mock_client.chat.completions.create.call_args
        system_content = call_args.kwargs['messages'][0]['content']
        # Should only include last 10 messages
        assert 'msg10' in system_content
        assert 'msg19' in system_content
        assert 'msg0' not in system_content


class TestSingleton:
    def test_client_reuse(self):
        """_get_client reuses client for same API key"""
        import ai
        with patch('ai.AsyncOpenAI') as mock_cls:
            mock_cls.return_value = MagicMock()
            c1 = ai._get_client('key1')
            c2 = ai._get_client('key1')
            assert c1 is c2
            assert mock_cls.call_count == 1

    def test_client_recreate_on_key_change(self):
        """_get_client creates new client when API key changes"""
        import ai
        with patch('ai.AsyncOpenAI') as mock_cls:
            mock_cls.return_value = MagicMock()
            c1 = ai._get_client('key1')
            mock_cls.return_value = MagicMock()
            c2 = ai._get_client('key2')
            assert c1 is not c2
            assert mock_cls.call_count == 2
