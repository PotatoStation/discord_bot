import os
import time
import asyncio

from typing import Dict, Sequence

import discord
import travitia_talk as tt

from discord.ext import tasks, commands

from potato_bot.bot import Bot
from potato_bot.cog import Cog

try:
    from potato_bot.cogs.accents import AccentConvertable
except ImportError:
    raise Exception("This cog relies on the existance of accents cog")


class Emotion(commands.Converter):
    async def convert(self, ctx, argument: str):
        try:
            return tt.Emotion(argument)
        except ValueError:
            raise commands.BadArgument(
                f"Must be one of {', '.join(e.value for e in tt.Emotion)}"
            )


class SessionSettings:
    __slots__ = (
        "session_id",
        "channel_id",
        "emotion",
        "accents",
        "last_reply",
        "lock",
    )

    def __init__(
        self,
        session_id: int,
        *,
        channel_id: int,
        emotion: tt.Emotion = tt.Emotion.neutral,
        accents: Sequence[AccentConvertable] = [],  # noqa
    ):
        self.session_id = session_id
        self.channel_id = channel_id
        self.emotion = emotion
        self.accents = accents

        self.last_reply = time.time()
        self.lock = asyncio.Lock()


class Chat(Cog):
    """ChatBot commands"""

    MAX_ACCENTS = 10
    SESSION_RATELIMIT = 3
    SESSION_TIMEOUT = 60

    def __init__(self, bot: Bot):
        super().__init__(bot)

        self.chatbot = tt.ChatBot(os.environ["TRAVITIA_API_TOKEN"])
        self.emotion = tt.Emotion.neutral

        self.sessions: Dict[int, SessionSettings] = {}

        self.cleanup_sessions.start()

    def cog_unload(self):
        self.bot.loop.create_task(self.chatbot.close())

        self.cleanup_sessions.stop()

    @commands.command()
    async def emotion(self, ctx, emotion: Emotion = None):
        """Manage chatbot emotion globally"""

        if emotion is None:
            return await ctx.send(f"Current emotion is **{self.emotion.value}**")

        self.emotion = emotion

        await ctx.ok()

    @commands.command(aliases=["cb", "talk"])
    async def ask(self, ctx, *, text: str):
        """Talk to PotatoBot"""

        async with ctx.typing():
            result = await self._query(
                text, SessionSettings(ctx.author.id, channel_id=ctx.channel.id)
            )

            await ctx.send(result)

    @commands.command()
    async def session(self, ctx, emotion: Emotion, *accents: AccentConvertable):
        """Start chat session in channel

        Use  accent list  commamd to get list of accents.
        """

        if ctx.author.id in self.sessions:
            del self.sessions[ctx.author.id]

            await ctx.send("Closed previous session")

        if len(accents) > self.MAX_ACCENTS:
            return await ctx.send(f"Cannot use more than {self.MAX_ACCENTS} at once")

        settings = SessionSettings(
            ctx.author.id,
            channel_id=ctx.channel.id,
            emotion=emotion,
            accents=accents,
        )

        self.sessions[ctx.author.id] = settings

        await ctx.send("Started session. Say `stop` to stop")

    async def _query(self, text: str, settings: SessionSettings) -> str:
        lower_bound = 3
        upper_bound = 60

        if not (lower_bound <= len(text) <= upper_bound):
            result = f"Error: Text lenght must be between **{lower_bound}** and **{upper_bound}**"
        else:
            try:
                response = await self.chatbot.ask(
                    text, id=settings.session_id, emotion=settings.emotion
                )
            except tt.APIError as e:
                result = f"Error: `{e}`"
            else:
                result = response.text

        for accent in settings.accents:
            result = accent.apply(result)

        return result

    @tasks.loop(minutes=5)
    async def cleanup_sessions(self):
        now = time.time()

        expired = []

        for user_id, settings in self.sessions.items():
            if settings.lock.locked():
                continue

            if (now - settings.last_reply) > self.SESSION_TIMEOUT:
                expired.append(user_id)

        for user_id in expired:
            del self.sessions[user_id]

    @Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id not in self.sessions:
            return

        settings = self.sessions[message.author.id]
        if settings.channel_id != message.channel.id:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        if message.content.lower() == "stop":
            del self.sessions[message.author.id]

            return await ctx.send("Closed session")

        if (time.time() - settings.last_reply) < self.SESSION_RATELIMIT:
            return await ctx.reply("You are sending messages too frequently")

        if settings.lock.locked():
            return

        async with settings.lock:
            async with ctx.typing():
                result = await self._query(message.content, settings)

                await ctx.reply(result, accents=[])

            settings.last_reply = time.time()


def setup(bot):
    bot.add_cog(Chat(bot))
