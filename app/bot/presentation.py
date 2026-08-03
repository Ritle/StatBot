"""Shared HTML presentation helpers for Telegram handlers."""

from html import escape

from app.services.status import ChannelStatus


def format_status(status: ChannelStatus) -> str:
    """Format diagnostics without exposing configuration secrets."""
    channel = status.channel
    last_event = status.last_event_at.isoformat() if status.last_event_at else "событий ещё нет"
    warnings = list(status.permissions.problems)
    if not channel.is_active:
        warnings.append("сбор событий для канала выключен")
    if status.active_season is None:
        warnings.append("нет активного периода рейтинга")
    lines = [
        "<b>Статус канала</b>",
        f"Канал: {escape(channel.title)} (<code>{channel.telegram_channel_id}</code>)",
        f"Обсуждения: {escape(status.discussion_title)} "
        f"(<code>{channel.discussion_chat_id}</code>)",
        f"Права бота в канале: {'есть' if status.permissions.channel_ok else 'нет'}",
        "Права бота в discussion group: "
        f"{'есть' if status.permissions.discussion_ok else 'нет'}",
        "Права администратора: "
        f"{'подтверждены' if status.administrator_ok else 'нет'}",
        f"Активный период: {escape(status.active_season.name) if status.active_season else 'нет'}",
        f"Пользователей: {status.user_count}",
        f"Публикаций: {status.post_count}",
        f"Комментариев: {status.comment_count}",
        f"Активных реакций: {status.reaction_count}",
        f"Последнее событие: {escape(last_event)}",
    ]
    if warnings:
        lines.append("\n<b>Предупреждения:</b>")
        lines.extend(f"• {escape(item)}" for item in warnings)
    return "\n".join(lines)
