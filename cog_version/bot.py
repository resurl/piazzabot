import os
import discord
from Updater import PiazzaUpdater
from dotenv import load_dotenv
from discord.ext import commands

"""
example bot that uses Piazza Updater as a Cog 
"""
load_dotenv()
TOKEN = os.getenv('TOKEN')
PIAZZA_USER = os.getenv('PIAZZA_USER')
PIAZZA_PW = os.getenv('PIAZZA_PW')
bot = commands.Bot('!')

@bot.event
async def on_ready(ctx):
    print(f'Starting bot: {bot.user.name}')
    print(f'Discord Version: {discord.__version__}')
    bot.add_cog(PiazzaUpdater(bot, PIAZZA_USER, PIAZZA_PW, 479512513378123798, "CPSC221", "ke1ukp9g4xx6oi"))

@bot.command(aliases=['hi', 'hey', 'hello'])
async def hello(ctx):
    await ctx.send(f'Hi {ctx.message.author}!')

@bot.event
async def on_command_error(ctx, error):
     """
     (optional) 
     use for custom error handling in chat
     Piazza Updater raises command.CommandOnCooldown errors 
     if messages are sent too quickly.
     """
     if isinstance(error, commands.CommandOnCooldown):
        ctx.send('Message sent too quickly! Please wait 5 seconds.')
    

bot.run(TOKEN)