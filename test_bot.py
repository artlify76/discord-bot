import discord
from discord.ext import commands
import json

with open('config.json') as f:
    config = json.load(f)

DISCORD_TOKEN = config['discord_token']

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot ready: {bot.user}')
    await bot.tree.sync()
    print(f'Synced commands')

@bot.tree.command(name='ping', description='Ping!')
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('Pong!')

bot.run(DISCORD_TOKEN)
