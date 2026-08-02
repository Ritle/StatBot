"""Thin Telegram handlers for publication and comment ingestion."""

from aiogram import Router
from aiogram.types import Message, MessageReactionUpdated, Update

from app.database.session import Database
from app.services.activity import ActivityService
from app.services.reactions import ReactionIngestService

router = Router(name=__name__)


@router.channel_post()
async def handle_channel_post(message: Message, database: Database) -> None:
    async with database.session() as session, session.begin():
        await ActivityService(session).ingest_channel_post(message)


@router.message()
async def handle_discussion_message(message: Message, database: Database) -> None:
    async with database.session() as session, session.begin():
        await ActivityService(session).ingest_discussion_message(message)


@router.message_reaction()
async def handle_message_reaction(
    event: MessageReactionUpdated,
    event_update: Update,
    database: Database,
) -> None:
    async with database.session() as session, session.begin():
        await ReactionIngestService(session).ingest(event, event_update.update_id)
