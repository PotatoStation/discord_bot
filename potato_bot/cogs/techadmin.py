import io
import asyncio
import textwrap
import traceback

from contextlib import redirect_stdout

import discord

from discord.ext import commands

from potato_bot.bot import Bot
from potato_bot.utils import run_process_shell
from potato_bot.checks import is_techadmin


class TechAdmin(commands.Cog):
    SQL_VALUE_LEN_CAP = 30

    def __init__(self, bot: Bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return await is_techadmin().predicate(ctx)

    @commands.command()
    async def load(self, ctx, module: str):
        """Load extension"""

        self.bot.load_extension(f"potato_bot.cogs.{module}")
        await ctx.ok()

    @commands.command()
    async def unload(self, ctx, module: str):
        """Unload extension"""

        self.bot.unload_extension(f"potato_bot.cogs.{module}")
        await ctx.ok()

    @commands.command()
    async def reload(self, ctx, module: str):
        """Reload extension"""

        self.bot.reload_extension(f"potato_bot.cogs.{module}")
        await ctx.ok()

    @commands.command()
    async def eval(self, ctx, *, program: str):
        """
        Evaluate code inside bot, with async support
        Has conveniece shortcuts like
        - ctx
        - discord

        To get result you can either print or return object.
        """

        if program.startswith("```") and program.endswith("```"):
            # strip codeblock
            program = program[:-3]
            program = "\n".join(program.split("\n")[1:])

        result = await self._eval(ctx, program)
        result = result.replace(self.bot.http.token, "TOKEN_LEAKED")

        await ctx.send(f"```python\n{result[-2000 - 1 + 14:]}```")

    async def _eval(self, ctx, program):
        # copied from https://github.com/Fogapod/KiwiBot/blob/49743118661abecaab86388cb94ff8a99f9011a8/modules/owner/module_eval.py
        # (originally copied from R. Danny bot)
        glob = {
            "self": self,
            "bot": self.bot,
            "ctx": ctx,
            "message": ctx.message,
            "guild": ctx.guild,
            "author": ctx.author,
            "channel": ctx.channel,
            "discord": discord,
        }

        fake_stdout = io.StringIO()

        to_compile = "async def func():\n" + textwrap.indent(program, "  ")

        try:
            exec(to_compile, glob)
        except Exception as e:
            return f"{e.__class__.__name__}: {e}"

        func = glob["func"]

        try:
            with redirect_stdout(fake_stdout):
                returned = await func()
        except asyncio.CancelledError:
            raise
        except Exception:
            return f"{fake_stdout.getvalue()}{traceback.format_exc()}"
        else:
            from_stdout = fake_stdout.getvalue()

            if returned is None:
                if from_stdout:
                    return f"{from_stdout}"

                return "Evaluated"
            else:
                return f"{from_stdout}{returned}"

    @commands.command()
    async def exec(self, ctx, *, arguments: str):
        """Execute shell command"""

        stdout, stderr = await run_process_shell(arguments)

        result = ""
        if stderr:
            result += f"STDERR:\n{stderr}"
        if stdout:
            result += stdout

        result = result.replace(self.bot.http.token, "TOKEN_LEAKED")

        await ctx.send(f"```bash\n{result[-2000 - 1 + 12:]}```")

    @commands.command()
    async def sql(self, ctx, *, program: str):
        """Run SQL command against bot database"""

        async with self.bot.db.cursor() as cur:
            await cur.execute(program)
            result = await cur.fetchall()

        if not result:
            return await ctx.ok()

        columns = result[0].keys()
        col_widths = [len(c) for c in columns]

        for row in result:
            for i, column in enumerate(columns):
                col_widths[i] = min(
                    (
                        max((col_widths[i], len(str(row[column])))),
                        self.SQL_VALUE_LEN_CAP,
                    )
                )

        header = " | ".join(
            f"{column:^{col_widths[i]}}" for i, column in enumerate(columns)
        )
        separator = "-+-".join("-" * width for width in col_widths)

        def sanitize_value(value):
            value = str(value).replace("\n", "\\n")

            if len(value) > self.SQL_VALUE_LEN_CAP:
                value = f"{value[:self.SQL_VALUE_LEN_CAP - 2]}.."

            return value

        paginator = commands.Paginator(prefix=f"```\n{header}\n{separator}")

        for row in result:
            paginator.add_line(
                " | ".join(
                    f"{sanitize_value(value):<{col_widths[i]}}"
                    for i, value in enumerate(row)
                )
            )

        for page in paginator.pages:
            await ctx.send(page)


def setup(bot):
    bot.add_cog(TechAdmin(bot))
