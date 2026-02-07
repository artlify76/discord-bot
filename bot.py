import discord
from discord.ext import commands
from discord import app_commands
import docker
import os
import time
import sqlite3
import json
from datetime import datetime
from pathlib import Path

with open('config.json') as f:
    config = json.load(f)

DISCORD_TOKEN = config['discord_token']
COMMAND_PREFIX = config['command_prefix']
IMAGE_NAME = config['image_name']
CPU_LIMIT = config['cpu_limit']
MEMORY_LIMIT = config['memory_limit']
ADMIN_IDS = config['admin_ids']
GUILD_ID = config.get('guild_id')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

client = None
try:
    client = docker.from_env()
except Exception as e:
    try:
        client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
    except:
        try:
            client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
        except:
            print(f"Warning: Docker not available - container commands will fail")

DB_PATH = Path('containers.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_containers
                 (user_id TEXT PRIMARY KEY, 
                  container_id TEXT, 
                  container_name TEXT,
                  created_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS blacklist
                 (user_id TEXT PRIMARY KEY,
                  reason TEXT,
                  blacklisted_at TIMESTAMP)''')
    conn.commit()
    conn.close()

def get_user_container(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT container_id FROM user_containers WHERE user_id = ?', (str(user_id),))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def save_container(user_id, container_id, container_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO user_containers (user_id, container_id, container_name, created_at) VALUES (?, ?, ?, ?)',
              (str(user_id), container_id, container_name, datetime.now()))
    conn.commit()
    conn.close()

def delete_container_record(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM user_containers WHERE user_id = ?', (str(user_id),))
    conn.commit()
    conn.close()

def is_blacklisted(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT user_id FROM blacklist WHERE user_id = ?', (str(user_id),))
    result = c.fetchone()
    conn.close()
    return result is not None

def add_blacklist(user_id, reason=''):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO blacklist (user_id, reason, blacklisted_at) VALUES (?, ?, ?)',
              (str(user_id), reason, datetime.now()))
    conn.commit()
    conn.close()

def remove_blacklist(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM blacklist WHERE user_id = ?', (str(user_id),))
    conn.commit()
    conn.close()

def load_containers():
    user_containers = {}
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT user_id, container_id FROM user_containers')
    for row in c.fetchall():
        try:
            container = client.containers.get(row[1])
            user_containers[row[0]] = row[1]
        except docker.errors.NotFound:
            delete_container_record(row[0])
    conn.close()
    return user_containers

user_containers = {}

@bot.event
async def on_ready():
    global user_containers
    init_db()
    user_containers = load_containers()
    await bot.tree.sync()
    print(f'{bot.user} has connected to Discord!')
    print(f'Loaded {len(user_containers)} containers from database')
    print(f'Synced {len(bot.tree.get_commands())} slash commands')

@bot.event
async def on_member_remove(member):
    user_id = str(member.id)
    
    if user_id not in user_containers:
        return
    
    try:
        container = client.containers.get(user_containers[user_id])
        container.stop()
        container.remove()
        
        del user_containers[user_id]
        delete_container_record(user_id)
        
        print(f'Deleted container for user {member.name} ({user_id}) who left the server')
    except docker.errors.NotFound:
        del user_containers[user_id]
        delete_container_record(user_id)
    except Exception as e:
        print(f'Error deleting container for {member.name}: {str(e)}')

def is_admin(user_id):
    return int(user_id) in ADMIN_IDS

def strip_ansi(text):
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def get_container_urls(container):
    try:
        logs = container.logs(stdout=True, stderr=True).decode('utf-8')
        tmate_url = None
        sshx_url = None
        
        for line in logs.split('\n'):
            line = line.strip()
            if line.startswith('ssh ') and '@' in line:
                tmate_url = strip_ansi(line)
            elif 'https://sshx.io/s/' in line:
                sshx_url = strip_ansi(line)
        
        return tmate_url, sshx_url
    except Exception as e:
        print(f"Error extracting URLs: {e}")
        return None, None

@bot.tree.command(name='create', description='Create a new container', guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
@app_commands.checks.cooldown(1, 10)
async def create_container(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    
    if interaction.guild is None:
        await interaction.followup.send('Commands must be used in a server, not in DMs.')
        return
    
    user_id = str(interaction.user.id)
    
    if is_blacklisted(user_id):
        await interaction.followup.send(f'{interaction.user.mention}, you are blacklisted from using this service.')
        return
    
    if user_id in user_containers:
        await interaction.followup.send(f'{interaction.user.mention}, you already have a container running. Use `/delete` to remove it first.')
        return
    
    try:
        container = client.containers.run(
            IMAGE_NAME,
            detach=True,
            name=f'discord-bot-{user_id}-{int(datetime.now().timestamp())}',
            cpu_quota=int(CPU_LIMIT * 100000),
            cpu_period=100000,
            mem_limit=MEMORY_LIMIT,
            stdin_open=True,
            tty=True,
        )
        
        time.sleep(6)
        tmate_url, sshx_url = get_container_urls(container)
        
        user_containers[user_id] = container.id
        save_container(user_id, container.id, container.name)
        
        embed = discord.Embed(
            title='Container Created',
            description=f'Container ID: `{container.id[:12]}`',
            color=discord.Color.green()
        )
        embed.add_field(name='Name', value=container.name, inline=False)
        embed.add_field(name='CPU Limit', value='2 cores', inline=True)
        embed.add_field(name='Memory Limit', value='4 GB', inline=True)
        
        if tmate_url:
            embed.add_field(name='Tmate SSH', value=f'`{tmate_url}`', inline=False)
        if sshx_url:
            embed.add_field(name='SSHX URL', value=f'`{sshx_url}`', inline=False)
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f'{interaction.user.mention}, failed to create container: {str(e)}')

@bot.tree.command(name='start', description='Temporarily disabled')
async def start_container(interaction: discord.Interaction):
    await interaction.response.send_message(f'{interaction.user.mention}, the `/start` command has been temporarily disabled.')

@bot.tree.command(name='stop', description='Temporarily disabled')
async def stop_container(interaction: discord.Interaction):
    await interaction.response.send_message(f'{interaction.user.mention}, the `/stop` command has been temporarily disabled.')

@bot.tree.command(name='delete', description='Delete your container')
async def delete_container(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    user_id = str(interaction.user.id)
    
    if user_id not in user_containers:
        await interaction.followup.send(f'{interaction.user.mention}, you don\'t have a container.')
        return
    
    try:
        container = client.containers.get(user_containers[user_id])
        container.stop()
        container.remove()
        
        del user_containers[user_id]
        delete_container_record(user_id)
        
        await interaction.followup.send(f'{interaction.user.mention}, your container has been deleted.')
        
    except docker.errors.NotFound:
        del user_containers[user_id]
        delete_container_record(user_id)
        await interaction.followup.send(f'{interaction.user.mention}, your container no longer exists.')
    except Exception as e:
        await interaction.followup.send(f'{interaction.user.mention}, failed to delete container: {str(e)}')

@bot.tree.command(name='status', description='Check your container status')
async def status_container(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    user_id = str(interaction.user.id)
    
    if user_id not in user_containers:
        await interaction.followup.send(f'{interaction.user.mention}, you don\'t have a container.')
        return
    
    try:
        container = client.containers.get(user_containers[user_id])
        
        embed = discord.Embed(
            title='Container Status',
            description=f'Container: `{container.id[:12]}`',
            color=discord.Color.blue()
        )
        embed.add_field(name='Name', value=container.name, inline=False)
        embed.add_field(name='Status', value=container.status, inline=True)
        embed.add_field(name='CPU Limit', value='0.5 cores', inline=True)
        embed.add_field(name='Memory Limit', value='1 GB', inline=True)
        
        await interaction.followup.send(embed=embed)
        
    except docker.errors.NotFound:
        del user_containers[user_id]
        await interaction.followup.send(f'{interaction.user.mention}, your container no longer exists.')
    except Exception as e:
        await interaction.followup.send(f'{interaction.user.mention}, failed to get container status: {str(e)}')

@bot.tree.command(name='help', description='Show available commands')
async def help_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    is_user_admin = is_admin(user_id)
    
    embed = discord.Embed(
        title='Bot Commands',
        description='Available commands for this bot',
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name='User Commands',
        value='`/create` - Create a new container\n'
              '`/delete` - Delete your container\n'
              '`/status` - Check your container status\n'
              '`/help` - Show this help menu',
        inline=False
    )
    
    embed.add_field(
        name='Temporarily Disabled',
        value='`/start` - Temporarily disabled\n'
              '`/stop` - Temporarily disabled',
        inline=False
    )
    
    if is_user_admin:
        embed.add_field(
            name='Admin Commands',
            value='`/blacklist @user [reason]` - Blacklist a user\n'
                  '`/unblacklist @user` - Unblacklist a user',
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='blacklist', description='[ADMIN] Blacklist a user')
@app_commands.describe(user='The user to blacklist', reason='Reason for blacklist')
async def blacklist_user(interaction: discord.Interaction, user: discord.User, reason: str = ''):
    await interaction.response.defer(thinking=True)
    user_id = str(interaction.user.id)
    
    if not is_admin(user_id):
        await interaction.followup.send(f'{interaction.user.mention}, you do not have permission to use this command.')
        return
    
    try:
        target_id = str(user.id)
        add_blacklist(target_id, reason)
        
        if target_id in user_containers:
            container = client.containers.get(user_containers[target_id])
            container.stop()
            container.remove()
            del user_containers[target_id]
            delete_container_record(target_id)
        
        await interaction.followup.send(f'{user.mention} has been blacklisted.{f" Reason: {reason}" if reason else ""}')
    except Exception as e:
        await interaction.followup.send(f'Error blacklisting user: {str(e)}')

@bot.tree.command(name='unblacklist', description='[ADMIN] Unblacklist a user')
@app_commands.describe(user='The user to unblacklist')
async def unblacklist_user(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(thinking=True)
    user_id = str(interaction.user.id)
    
    if not is_admin(user_id):
        await interaction.followup.send(f'{interaction.user.mention}, you do not have permission to use this command.')
        return
    
    try:
        target_id = str(user.id)
        remove_blacklist(target_id)
        await interaction.followup.send(f'{user.mention} has been unblacklisted.')
    except Exception as e:
        await interaction.followup.send(f'Error unblacklisting user: {str(e)}')

if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print('Error: DISCORD_TOKEN not set')
    else:
        bot.run(DISCORD_TOKEN)
