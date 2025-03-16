import os
import discord
import pytube
import asyncio
import random
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from collections import deque

load_dotenv()
TOKEN = os.getenv('TOKEN')

SONG_QUEUES = {}
GUILD_ID = 1168043245863960676
DJ_ROLE_IDS = {}
VOTE_SKIPS = {}

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='?', intents=intents)

@bot.event
async def on_ready():
    test_guild = discord.Object(id=GUILD_ID)

    try:
        await bot.tree.sync()
        print("Global commands synced.")

        await bot.tree.sync(guild=test_guild)
        print("Guild commands synced.")

        await asyncio.sleep(1)

    except Exception as e:
        print(f"Error syncing commands: {e}")

    print(f'{bot.user} is now jamming to some beats! 🎵')

@bot.tree.command(name="skip", description="Skips the current playing song")
async def skip(interaction: discord.Interaction):
    dj_role_id = DJ_ROLE_IDS.get(interaction.guild.id)
    if not dj_role_id or not await is_dj(interaction.user, interaction, dj_role_id):
        await interaction.response.send_message("You need the DJ role to use this command.")
        return

    if interaction.guild.voice_client and (
            interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Skipped the current song.")
    else:
        await interaction.response.send_message("Not playing anything to skip.")

# ... (pause, resume, stop, shuffle, remove, volume, dj_config, is_dj commands remain the same)

@bot.tree.command(name="play", description="Play a song or add it to the queue.")
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()

    voice_channel = interaction.user.voice.channel

    if voice_channel is None:
        await interaction.followup.send("You must be in a voice channel.")
        return

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)

    try:
        if "youtube.com" in song_query or "youtu.be" in song_query:
            yt = pytube.YouTube(song_query)
        else:
            search_results = pytube.Search(song_query).results
            if not search_results:
                await interaction.followup.send("No results found.")
                return
            yt = search_results[0]  # Take the first result

        audio_stream = yt.streams.filter(only_audio=True).first()
        audio_url = audio_stream.url
        title = yt.title

        guild_id = str(interaction.guild_id)
        if SONG_QUEUES.get(guild_id) is None:
            SONG_QUEUES[guild_id] = deque()

        SONG_QUEUES[guild_id].append((audio_url, title))

        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.followup.send(f"Added to queue: **{title}**")
        else:
            await interaction.followup.send(f"Now playing: **{title}**")
            await play_next_song(voice_client, guild_id, interaction.channel)

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}")

async def play_next_song(voice_client, guild_id, channel):
    if SONG_QUEUES[guild_id]:
        audio_url, title = SONG_QUEUES[guild_id].popleft()

        ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn -c:a libopus -b:a 96k",
        }

        source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options)

        def after_play(error):
            if error:
                print(f"Error playing {title}: {error}")
            asyncio.run_coroutine_threadsafe(play_next_song(voice_client, guild_id, channel), bot.loop)

        voice_client.play(source, after=after_play)
        await channel.send(f"Now playing: **{title}**")
    else:
        await voice_client.disconnect()
        SONG_QUEUES[guild_id] = deque()


@bot.tree.command(name="pause", description="Pause the currently playing song.", guild=test_guild)
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        return await interaction.response.send_message("I'm not in a voice channel.")

    if not voice_client.is_playing():
        return await interaction.response.send_message("Nothing is currently playing.")

    voice_client.pause()
    await interaction.response.send_message("Playback paused!")

@bot.tree.command(name="resume", description="Resume the currently paused song.", guild=test_guild)
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        return await interaction.response.send_message("I'm not in a voice channel.")

    if not voice_client.is_paused():
        return await interaction.response.send_message("I’m not paused right now.")

    voice_client.resume()
    await interaction.response.send_message("Playback resumed!")

@bot.tree.command(name="stop", description="Stop playback and clear the queue.", guild=test_guild)
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_connected():
        return await interaction.response.send_message("I'm not connected to any voice channel.")

    # Clear the guild's queue
    guild_id_str = str(interaction.guild_id)
    if guild_id_str in SONG_QUEUES:
        SONG_QUEUES[guild_id_str].clear()

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    await voice_client.disconnect()

    await interaction.response.send_message("Stopped playback and disconnected!")

@bot.tree.command(name="now_playing", description="Shows the currently playing song.")
async def now_playing(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    if voice_client and voice_client.is_playing():
        current_song = voice_client.source
        if hasattr(current_song, 'title'):
            await interaction.response.send_message(f"Now playing: **{current_song.title}**")
        else:
            await interaction.response.send_message("Now playing: Unknown Title")
    else:
        await interaction.response.send_message("Not playing anything right now.")

@bot.tree.command(name="volume", description="Sets the volume of the player.")
@app_commands.describe(volume="Volume percentage (0-100)")
async def volume(interaction: discord.Interaction, volume: int):
    if not await is_dj(interaction.user, interaction):
        await interaction.response.send_message("You need the DJ role to use this command.")
        return

    if volume < 0 or volume > 100:
        await interaction.response.send_message("Volume must be between 0 and 100.")
        return

    voice_client = interaction.guild.voice_client
    if voice_client is None:
        await interaction.response.send_message("Not connected to a voice channel.")
        return

    voice_client.source.volume = volume / 100
    await interaction.response.send_message(f"Volume set to {volume}%")

@bot.tree.command(name="search", description="Searches for a song on YouTube.")
@app_commands.describe(song_query="Search query")
async def search(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()

    try:
        search_results = pytube.Search(song_query).results
        if not search_results:
            await interaction.followup.send("No results found.")
            return

        search_results_list =
        for i, result in enumerate(search_results[:5]):  # Show top 5 results
            search_results_list.append(f"{i + 1}. {result.title}")

        embed = discord.Embed(
            title="Search Results",
            description="\n".join(search_results_list),
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}")

@bot.tree.command(name="playlist", description="Play a YouTube playlist.")
@app_commands.describe(playlist_url="YouTube playlist URL")
async def playlist(interaction: discord.Interaction, playlist_url: str):
    await interaction.response.defer()

    voice_channel = interaction.user.voice.channel

    if voice_channel is None:
        await interaction.followup.send("You must be in a voice channel.")
        return

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)

    try:
        playlist = pytube.Playlist(playlist_url)
        video_count = len(playlist.video_urls)

        if video_count == 0:
            await interaction.followup.send("Playlist is empty or invalid.")
            return

        added_count = 0
        guild_id = str(interaction.guild_id)
        if SONG_QUEUES.get(guild_id) is None:
            SONG_QUEUES[guild_id] = deque()

        for video_url in playlist.video_urls:
            try:
                yt = pytube.YouTube(video_url)
                audio_stream = yt.streams.filter(only_audio=True).first()
                audio_url = audio_stream.url
                title = yt.title
                SONG_QUEUES[guild_id].append((audio_url, title))
                added_count += 1
            except Exception as video_error:
                print(f"Error adding video from playlist: {video_error}")
                continue  # Skip to the next video

        await interaction.followup.send(f"Added {added_count} of {video_count} videos from the playlist to the queue.")

        if not voice_client.is_playing() and not voice_client.is_paused():
            await play_next_song(voice_client, guild_id, interaction.channel)

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}")


@bot.tree.command(name="voteskip", description="Vote to skip the current song.")
async def voteskip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("Nothing is playing right now.")
        return

    guild_id = interaction.guild.id
    user_id = interaction.user.id
    voice_channel = interaction.user.voice.channel

    if not voice_channel:
        await interaction.response.send_message("You must be in a voice channel to vote.")
        return

    if guild_id not in VOTE_SKIPS:
        VOTE_SKIPS[guild_id] = {"votes": set(), "channel": voice_channel}

    if VOTE_SKIPS[guild_id]["channel"] != voice_channel:
        await interaction.response.send_message("You must be in the same voice channel as the bot to vote.")
        return

    VOTE_SKIPS[guild_id]["votes"].add(user_id)
    total_users = len(voice_channel.members) - 1  # Subtract the bot itself
    required_votes = total_users // 2 + 1  # Majority vote

    current_votes = len(VOTE_SKIPS[guild_id]["votes"])

    await interaction.response.send_message(f"Vote added. {current_votes}/{required_votes} votes to skip.")

    if current_votes >= required_votes:
        voice_client.stop()
        await interaction.channel.send("Vote skip successful.")
        del VOTE_SKIPS[guild_id]  # Reset vote data

bot.run(TOKEN)
