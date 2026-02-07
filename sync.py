import discord
from discord.ext import commands
from discord import app_commands
import json

with open('config.json') as f:
    config = json.load(f)

DISCORD_TOKEN = config['discord_token']
COMMAND_PREFIX = config['command_prefix']

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

@app_commands.command(name='create', description='Create a new container')
async def create_container(interaction: discord.Interaction):
    pass

@app_commands.command(name='delete', description='Delete your container')
async def delete_container(interaction: discord.Interaction):
    pass

@app_commands.command(name='status', description='Check your container status')
async def status_container(interaction: discord.Interaction):
    pass

@app_commands.command(name='help', description='Show available commands')
async def help_command(interaction: discord.Interaction):
    pass

@app_commands.command(name='start', description='Temporarily disabled')
async def start_container(interaction: discord.Interaction):
    pass

@app_commands.command(name='stop', description='Temporarily disabled')
async def stop_container(interaction: discord.Interaction):
    pass

@app_commands.command(name='blacklist', description='[ADMIN] Blacklist a user')
async def blacklist_user(interaction: discord.Interaction, user: discord.User):
    pass

@app_commands.command(name='unblacklist', description='[ADMIN] Unblacklist a user')
async def unblacklist_user(interaction: discord.Interaction, user: discord.User):
    pass

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.tree.sync()
    print(f'Synced {len(bot.tree.get_commands())} slash commands')
    await bot.close()

bot.tree.add_command(create_container)
bot.tree.add_command(delete_container)
bot.tree.add_command(status_container)
bot.tree.add_command(help_command)
bot.tree.add_command(start_container)
bot.tree.add_command(stop_container)
bot.tree.add_command(blacklist_user)
bot.tree.add_command(unblacklist_user)

bot.run(DISCORD_TOKEN)
