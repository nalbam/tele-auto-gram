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


class TestIsTrivialMessage:
    def test_none(self):
        """None is trivial"""
        import ai
        assert ai.is_trivial_message(None) is True

    def test_empty_string(self):
        """Empty string is trivial"""
        import ai
        assert ai.is_trivial_message('') is True

    def test_short_text(self):
        """Text shorter than 3 chars is trivial"""
        import ai
        assert ai.is_trivial_message('hi') is True
        assert ai.is_trivial_message('ㅋ') is True

    def test_trivial_words(self):
        """Known trivial words are detected"""
        import ai
        assert ai.is_trivial_message('ok') is True
        assert ai.is_trivial_message('ㅋㅋㅋ') is True
        assert ai.is_trivial_message('haha') is True
        assert ai.is_trivial_message('넵') is True

    def test_trivial_words_case_insensitive(self):
        """Trivial word check is case-insensitive"""
        import ai
        assert ai.is_trivial_message('OK') is True
        assert ai.is_trivial_message('Okay') is True

    def test_emoji_only(self):
        """Emoji-only messages are trivial"""
        import ai
        assert ai.is_trivial_message('\U0001F600') is True
        assert ai.is_trivial_message('\U0001F44D\U0001F44D') is True

    def test_substantive_korean(self):
        """Korean substantive messages are not trivial"""
        import ai
        assert ai.is_trivial_message('오늘 회의 몇 시에 해요?') is False

    def test_substantive_english(self):
        """English substantive messages are not trivial"""
        import ai
        assert ai.is_trivial_message('Can we meet tomorrow at 3pm?') is False

    def test_whitespace_only(self):
        """Whitespace-only is trivial"""
        import ai
        assert ai.is_trivial_message('   ') is True


class TestBuildChatMessages:
    def test_empty_messages(self):
        """Returns only system message for empty input"""
        import ai
        result = ai.build_chat_messages([], 'Be friendly', 'Alice')
        assert len(result) == 1
        assert result[0]['role'] == 'system'
        assert 'Be friendly' in result[0]['content']
        assert 'first contact' in result[0]['content']

    def test_direction_mapping(self):
        """Maps received→user, sent→assistant"""
        import ai
        messages = [
            {'direction': 'received', 'text': 'hello'},
            {'direction': 'sent', 'text': 'hi there'},
        ]
        result = ai.build_chat_messages(messages, 'system', 'Alice')
        assert result[1] == {'role': 'user', 'content': 'hello'}
        assert result[2] == {'role': 'assistant', 'content': 'hi there'}

    def test_consecutive_merge(self):
        """Merges consecutive same-role messages"""
        import ai
        messages = [
            {'direction': 'received', 'text': 'hello'},
            {'direction': 'received', 'text': 'are you there?'},
            {'direction': 'sent', 'text': 'yes'},
        ]
        result = ai.build_chat_messages(messages, 'system', 'Alice')
        # system + merged user + assistant = 3
        assert len(result) == 3
        assert result[1]['content'] == 'hello\nare you there?'
        assert result[1]['role'] == 'user'

    def test_skips_none_text(self):
        """Skips messages with None text"""
        import ai
        messages = [
            {'direction': 'received', 'text': None},
            {'direction': 'received', 'text': 'hello'},
        ]
        result = ai.build_chat_messages(messages, 'system', 'Alice')
        assert len(result) == 2
        assert result[1]['content'] == 'hello'

    def test_includes_profile(self):
        """Includes sender profile in system message"""
        import ai
        result = ai.build_chat_messages([], 'Be friendly', 'Alice',
                                        sender_profile='- Prefers Korean')
        system_msg = result[0]['content']
        assert 'Be friendly' in system_msg
        assert 'Profile: Alice' in system_msg
        assert 'Prefers Korean' in system_msg

    def test_default_system_prompt(self):
        """Uses default system prompt when none provided"""
        import ai
        result = ai.build_chat_messages([], '', 'Alice')
        assert ai.DEFAULT_SYSTEM_PROMPT in result[0]['content']
        assert 'first contact' in result[0]['content']

    def test_limit(self):
        """Respects message limit"""
        import ai
        messages = [{'direction': 'received', 'text': f'msg{i}'} for i in range(30)]
        result = ai.build_chat_messages(messages, 'system', 'Alice', limit=5)
        # system + up to 5 user messages (all same role → merged into 1)
        assert len(result) == 2
        # Should contain only last 5 messages
        assert 'msg25' in result[1]['content']
        assert 'msg29' in result[1]['content']
        assert 'msg24' not in result[1]['content']


class TestGenerateResponse:
    @pytest.mark.asyncio
    async def test_no_api_key(self):
        """Returns None when no API key"""
        import ai
        result = await ai.generate_response(
            [{'role': 'system', 'content': 'test'}], api_key=''
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

        chat_messages = [
            {'role': 'system', 'content': 'Be friendly'},
            {'role': 'user', 'content': 'hello'},
        ]

        with patch.object(ai, '_get_client', return_value=mock_client):
            result = await ai.generate_response(
                chat_messages, api_key='test-key'
            )
        assert result == 'AI response'

    @pytest.mark.asyncio
    async def test_passes_chat_messages(self):
        """Passes pre-built chat messages directly to API"""
        import ai
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_completion('response')
        )

        chat_messages = [
            {'role': 'system', 'content': 'Be friendly'},
            {'role': 'user', 'content': 'hello'},
            {'role': 'assistant', 'content': 'hi'},
            {'role': 'user', 'content': 'how are you?'},
        ]

        with patch.object(ai, '_get_client', return_value=mock_client):
            await ai.generate_response(chat_messages, api_key='test-key')

        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs['messages'] == chat_messages

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
                [{'role': 'system', 'content': 'test'}], api_key='test-key'
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
