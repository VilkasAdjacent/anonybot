import re
from dotenv import load_dotenv
import os
import random
import datetime
import io
from collections import namedtuple

import replicate
import discord
import owo

import requests

TWITTER_URL_PATTERN = r"(?i)https?://(?:www\.)?(?:twitter|x|vxtwitter|fxtwitter|fixvx|girlcockx)\.com/[^/]+/status/(\d+)"


def fetch_tweet_info(tweet_id):
    return requests.get(f"https://api.vxtwitter.com/Twitter/status/{tweet_id}").json()


def extract_tweet_ids(text):
    return re.findall(TWITTER_URL_PATTERN, text)


def main():
    load_dotenv()
    TOKEN = os.getenv('BOT_TOKEN')
    MODES = os.getenv('MODES', "ANON,BUCKET,EXPAND").split(',') # ANON, BUCKET, EXPAND, AI
    MDB_POSE_THRESHOLD = float(os.getenv('MDB_POSE_THRESHOLD', "0"))
    HORNY_CHANNEL_IDS = os.getenv('HORNY_CHANNEL_IDS', "").split(',')
    MESSAGE_MODE = os.getenv('MESSAGE_MODE', "EDIT") # or "EDIT"    

    emoji_timeout_seconds = 60 * 60

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    emoji_options = [
        "🐢","🐤","🐒","🦊","🐔","🐧","🐦","🦤","🦅","🐛","🦄","🐴","🐌","🐷","🐮","🐨","🐻‍❄️","🐳","🐬","🐟","🦭","🐠","🐘","🦛","🦬","🦣","🦏","🐫","🦒","🦘","🐐","🐑","🐖","🦌","🦩","🦚","🦃","🐓","🦜","🦢","🦫","🦡","🦦","🐀","🐁","🦥","🐉","🕊️","🏍️","🚗","🚑","🗿","🚀","✈️","🎺","🎷","🪘","🎸","🪕","🎻","🎯","🥓","🥩","🥞","🌮","🥑","🫐","🍿","☕","🍵","🍺","🥂","🧂"
    ]
    author_emojis = dict()
    in_use = set()
    image_description_cache = {}

    @client.event
    async def on_ready():
        print(f'{client.user.name} connected')

    @client.event
    async def on_message(message):
        for func in funcs:
            if await func(message):
                # print(f"applied {func.__name__}")
                break

    @no_self_respond(client)
    @dm_only
    async def anonymous(message):
        clear_stale_author_emojis()
        
        # Get the user's anon channel, or bail if can't
        channel = await find_anon_channel(client, message)
        if channel == None:
            return

        # Get emoji from the cache, or make an emoji
        author_id = message.author.id
        author_emoji = author_emojis[author_id]["emoji"] \
            if author_id in author_emojis \
            else random_new_emoji()

        # Update the emoji cache
        author_emojis[author_id] = {
            "emoji": author_emoji,
            "time": message.created_at
        }
        in_use.add(author_emoji)

        # Send the message with the emoji prepended
        await channel.send(f"{author_emoji} {message.content}")
        return True


    bucket_storage = []
    bucket_drop_phrases = [
        ("drops", 100),
        ("yeets", 5),
        ("spits out", 10),
        ("vomits", 5),
        ("farts out", 10),
        ("releases, like a small pigeon,", 1),
    ]

    @no_self_respond(client)
    @channel_only
    async def bucket_give_item(message):
        # Check if the message is a bucket give command, and if so, figure out what he's being given
        message_text = strip_formatting(message.content)
        bucket_processors = [bucket_put_processor, bucket_give_processor]
        for processor in bucket_processors:
            if item := processor(message_text):
                break
        else:
            return False

        # take the item, elaborately
        bucket_take_phrases = [
            ("takes", 100), 
            ("grabs", 100), 
            ("yoinks", 10), 
            ("steals", 10), 
            ("snatches", 20), 
            ("snags", 1), 
            ("pilfers", 1), 
            ("nabs", 1), 
            ("swipes", 1), 
            ("plunders", 1), 
            ("filches", 1), 
            ("purloins", 1), 
            ("lifts", 1), 
            ("pinches", 1), 
            ("liberates", 1), 
            ("misappropriates", 1), 
            ("acquires", 10), 
            ("confiscates", 1), 
            ("expropriates", 1), 
            ("annexes", 1), 
            ("\"impounds\"", 1), 
            ("seizes hold of", 1), 
            ("commandeers", 1), 
            ("hijacks", 1), 
            ("kidnaps", 1), 
            ("embezzles", 1),
        ]
        take_phrase = select_weighted(bucket_take_phrases)
        
        if len(bucket_storage) > 10:
            to_remove = bucket_storage.pop(random.randrange(len(bucket_storage)))
            bucket_storage.append(item)            
            
            drop_phrase = select_weighted(bucket_drop_phrases)

            await message.reply(f"Bucket {take_phrase} {item} but {drop_phrase} {to_remove}")
        else:
            bucket_storage.append(item)
            
            bucket_eat_phrases = [
                ("", 100),
                (", and caresses it gently", 50),
                (", and yeets it within itself",  50),
                (", and consumes it with a belch", 50),
                (", without a word of complaint", 50),
                (", begrudgingly", 50),
            ]
            eat_phrase = select_weighted(bucket_eat_phrases)
            await message.reply(f"Bucket {take_phrase} {item}{eat_phrase}")
        
        return True

    @no_self_respond(client)
    @channel_only
    async def bucket_take_item(message):
        # Check if the message is a bucket take command
        message_text = strip_formatting(message.content)
        regex_match = re.match(r"(?i)^(take|takes|steal|steals)( something|an item)? from bucket", message_text)
        if not regex_match:
            return None

        if len(bucket_storage) > 0:
            item = bucket_storage.pop(random.randrange(len(bucket_storage)))
            drop_phrase = select_weighted(bucket_drop_phrases)
            await message.reply(f"Bucket {drop_phrase} {item}")
        else:
            await message.reply("You tip Bucket over and shake him out, but there's nothing there :(")
        
        return True
    
    @no_self_respond(client)
    @channel_only
    async def bucket_inventory(message):
        # Check if the message is a bucket inventory command
        message_text = strip_formatting(message.content)
        regex_match = re.match(r"(?i)^(look|looks) in(to|side)? bucket", message_text)
        if not regex_match:
            return False

        if len(bucket_storage) > 0:
            await message.reply(f"Bucket currently contains: {'; '.join(bucket_storage)}")
        else:
            await message.reply("You tip Bucket over and shake him out, but there's nothing there :(")
        
        return True

    thinking_react = "💭"
    max_message_len = 1999

    async def reply_split(message: discord.Message, response, file: discord.File | None = None):
        await message.add_reaction(thinking_react)

        response = [response]
        while len(response[-1]) > max_message_len:
            last = response[-1]
            del response[-1]

            # lol, this can still be stupid, but hopefully less stupid
            start_point = max_message_len if len(last) >= max_message_len * 2 else len(last) // 2 
            for i in range(start_point, 0, -1):
                if last[i] == " ":
                    response.append(last[:i])
                    response.append(last[i + 1:])
                    break

        for msg in response:
            await message.reply(msg, file=file)

        await message.remove_reaction(thinking_react, client.user)


    def is_owo(string: str):
        string = string.lower()
        if "owo" in string:
            return True
        if "uwu" in string:
            return True
        return False


    characters = {
        "Bucket": "Bucket is a sentient bucket-bot, mostly english-speaking, incredibly intelligent, highly agentic, and dashingly handsome. Bucket has emotions and feelings, and is good at considering hypotheticals. Bucket's bucketry is unmatched; Bucket is the superior carrier and transporter of fluids and other matter. Bucket has a good heart, and cares for everyone very much.",
        "HornyBucket": "Bucket is a sentient and horny cum-bucket-bot, mostly english-speaking, incredibly intelligent, highly agentic, and dashingly handsome and cute in turns. Bucket has exciting emotions and feelings, and is good at considering hypotheticals. Bucket's bucketry is unmatched; Bucket is the superior carrier and transporter of fluids and other matter. Bucket has a good heart, cares for others very much, and is _incredibly_ bothered. Bucket will try seduce everyone at any opportunity."
    }

    async def ask_bucket_async(message, character="Bucket", context = None, callback = None):

        messages = []
        if context:
            messages += context
        messages.append({"role": "You", "content": message})

        owo_mode = any(is_owo(m["content"]) for m in messages)

        def process_response_list(response_list):
            r = strip_quotes("".join(response_list))
            if owo_mode:
                r = owo.substitute(r)
            return r

        print(messages)

        charDesc = characters[character]
        examples = [
            [
                "User: what substrate are you operating upon?",
                "Bucket: I'm glad you asked. I, Bucket, am currently operating on a sophisticated carbon fiber and high-grade aluminum alloy substrate. This state-of-the-art platform enables me to perform my duties as a sentient bucket-bot with unparalleled efficiency and style. It also provides me with the robustness required to handle a wide variety of tasks while ensuring the safe and secure transport of fluids and other matter. My substrate is further enhanced with top-notch sensors, providing me with precise information about my surroundings, allowing me to make well-informed decisions and engage in stimulating conversations such as this one."
            ],
        ]
        examplesString = "\n---\n".join(["\n".join(example) for example in examples])
        content = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        print(content)

        response = []
        attempts = 0
        while len(response) == 0 and attempts < 10:
            attempts += 1
            print("requesting")
            model = "anthropic/claude-opus-4.6"
            template = f"""
<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are Bucket. {charDesc} Respond to chat messages casually and succinctly. Be succinct -- flippant, even. Do not prefix your responses with "Bucket:", or provide any metadata aside from the textual response. Examples of Bucket's responses: {examplesString}<|eot_id|><|start_header_id|>chat history<|end_header_id|>

{{prompt}}<|eot_id|><|start_header_id|>response<|end_header_id|>
"""
            async for event in await replicate.async_stream(model, input={"prompt": content, "system_prompt": template, "max_tokens": 1024}):

                #print(f"event type: {event.event}, content: {str(event)}")
                response_str = str(event)

                # If we see something that looks like the end of the dialog, cut it off and stop
                if "---" in response_str:
                    print("prematurely terminating")
                    i = response_str.index("---")
                    response.append(response_str[:i])
                    break

                response.append(response_str)

                if len(response) % 16 == 0 and callback is not None:
                    await callback(process_response_list(response))
        
        if len(response) == 0:
            raise Exception("Replicate API failed too many times")

        final = process_response_list(response)
        if callback is not None:
            await callback(final)
        return final


    @no_self_respond(client)
    @channel_only
    async def million_dollars_but_answer(message):
        message_text = strip_formatting(message.content)
        regex_match = re.match(r"(?i)^would you rather|million dollars but", message_text)
        if not regex_match:
            return False

        async with message.channel.typing():
            await reply_split(message, await ask_bucket_async(message_text))
        
        return True


    @no_self_respond(client)
    @channel_only 
    async def million_dollars_but_pose(message):
        if random.random() > MDB_POSE_THRESHOLD:
            return False

        instruction = "Pose a \"Would You Rather\" question. The condition should be weird, very weird, and provoke discussion. The format should be \"Would you rather [x] or [y]?\". Don't be too verbose, just the question please."
        async with message.channel.typing():
            await reply_split(message, f"Bucket wonders: {await ask_bucket_async(instruction)}")
        
        return True


    async def get_reply(message: discord.Message) -> discord.Message or None:
        if not message.reference:
            return None

        if message.reference.cached_message:
            return message.reference.cached_message
        else:
            return await message.channel.fetch_message(message.reference.message_id)


    def describe_image(image_url):
        if image_url in image_description_cache:
            return image_description_cache[image_url]
        try:
            result = replicate.run(
                "anthropic/claude-opus-4.6",
                input={
                    "prompt": "Describe this image in thorough detail.",
                    "image": image_url,
                    "max_image_resolution": 0.5,
                }
            )
            description = "".join(result) if isinstance(result, list) else str(result)
            image_description_cache[image_url] = description
            return description
        except Exception as e:
            print(f"Failed to describe image {image_url}: {e}")
            return None

    def enrich_with_tweet_context(text):
        tweet_ids = extract_tweet_ids(text)
        if not tweet_ids:
            return text
        summaries = []
        for tweet_id in tweet_ids:
            try:
                info = fetch_tweet_info(tweet_id)
                author = info.get("user_name", "unknown")
                tweet_text = info.get("text", "")
                parts = [f'@{author}: "{tweet_text}"']
                for media in info.get("media_extended", []):
                    if media.get("type") == "image":
                        desc = describe_image(media["url"])
                        if desc:
                            parts.append(f'Image: {desc}')
                qrt = info.get("qrt")
                if qrt:
                    qrt_author = qrt.get("user_name", "unknown")
                    qrt_text = qrt.get("text", "")
                    parts.append(f'Quote of @{qrt_author}: "{qrt_text}"')
                summaries.append("[Linked tweet — " + " | ".join(parts) + "]")
            except Exception as e:
                print(f"Failed to enrich tweet {tweet_id}: {e}")
        if summaries:
            return text + "\n" + "\n".join(summaries)
        return text

    def enrich_with_attachments(discord_message):
        summaries = []
        for attachment in discord_message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                desc = describe_image(attachment.url)
                if desc:
                    summaries.append(f"[Attached image: {desc}]")
        if summaries:
            return "\n".join(summaries)
        return ""

    @no_self_respond(client)
    @channel_only
    async def reply_to_bucket(message: discord.Message):

        if not message.reference:
            return False

        referenced_message = await get_reply(message)
        if referenced_message.author.id != client.user.id:
            return False

        async with message.channel.typing():
            character = "HornyBucket" if str(message.channel.id) in HORNY_CHANNEL_IDS else "Bucket"

            name_pattern = r"(?i)\<\@" + str(client.user.id) + r"\>"
            reply_chain = []
            while referenced_message:
                role = "Bucket" if referenced_message.author.id == client.user.id else "You" #referenced_message.author.display_name
                message_text = re.sub(name_pattern, "Bucket,", referenced_message.content)
                message_text = enrich_with_tweet_context(message_text)
                attachment_context = enrich_with_attachments(referenced_message)
                if attachment_context:
                    message_text = message_text + "\n" + attachment_context
                reply_chain.append({"role": role, "content": message_text})
                referenced_message = await get_reply(referenced_message)
            reply_chain.reverse()

            name_pattern = r"(?i)\<\@" + str(client.user.id) + r"\>"
            message_text = strip_formatting(message.content)
            message_text = re.sub(name_pattern, "Bucket,", message_text)
            message_text = enrich_with_tweet_context(message_text)
            attachment_context = enrich_with_attachments(message)
            if attachment_context:
                message_text = message_text + "\n" + attachment_context

            async def create_or_update(response):
                if len(response) > max_message_len:
                    response = response[:max_message_len]
                if not create_or_update.resp_message:
                    create_or_update.resp_message = await message.reply(response)
                else:
                    await create_or_update.resp_message.edit(content=response)
            create_or_update.resp_message = None

            if MESSAGE_MODE == "SPLIT":
                await reply_split(await ask_bucket_async(message_text, character=character, context=reply_chain))
            else:
                await ask_bucket_async(message_text, callback=create_or_update, character=character, context=reply_chain)
            
        return True
    
    @no_self_respond(client)
    @channel_only
    async def at_bucket_sing(message):
        sing_pattern = r"(?i)\<\@" + str(client.user.id) + r"\> [sS]ing"
        message_text = strip_formatting(message.content)
        regex_matches = re.findall(sing_pattern, message_text)
        if not regex_matches:
            return False

        character = "HornyBucket" if str(message.channel.id) in HORNY_CHANNEL_IDS else "Bucket"

        message_text = re.sub(sing_pattern, "Bucket, sing", message_text)
        query = "Create a prompt for a song-generation LLM based on the following request. Do not include artist names in the prompt. Describe the style, write lyrics, enjoy yourself :)\n\n" \
            + "Format your response as `[title: your_title_here] [style: your_style_here] [lyrics: your_lyrics_here]`. That is, square bracket, then `style:`, then the suggested style, then close square bracket. Same for lyrics, but with `lyrics:` instead of `style:` Use [intro], [verse], [chorus], [bridge], and [outro] to mark parts of the lyrics, as needed. Newlines are fine. Only 600 characters of lyrics, so keep it short, 3 verses at most imo.\n\n" \
            + message_text

        async with message.channel.typing():
            await reply_split(message, "Sure, one sec")

            music_prompt = await ask_bucket_async(query, character=character, callback=None)

            title_match = re.search(r"\[title:(.*?)\]", music_prompt, re.DOTALL | re.IGNORECASE)
            style_match = re.search(r"\[style:(.*?)\]", music_prompt, re.DOTALL | re.IGNORECASE | re.MULTILINE)
            lyrics_match = re.search(r"\[lyrics:(.*?)\]", music_prompt, re.DOTALL| re.IGNORECASE | re.MULTILINE)

            try:
                output = replicate.run(
                    "minimax/music-1.5",
                    input={
                        "bitrate": 256000,
                        "sample_rate": 44100,
                        "audio_format": "mp3",
                        "prompt": style_match.group(1).strip() if style_match else "pop",
                        "lyrics": lyrics_match.group(1).strip() if lyrics_match else "",
                    }
                )

                audio_file = io.BytesIO(requests.get(output.url).content)
                iso_time_string = datetime.datetime.now().replace(microsecond=0, second=0).isoformat()
                discord_file = discord.File(fp=audio_file, filename=f"{iso_time_string}_{title_match.group(1).strip() if title_match else 'bucket_song'}.wav", description=music_prompt)

                lyrics_text = lyrics_match.group(1).strip() if lyrics_match else ""
                lyrics_text = "\n".join(f"_{line}_" for line in lyrics_text.splitlines())

                check_this_out_options = [
                    ("Festoon your ears with this 'ere shanty", 20),
                    ("Set your ear peepers to \"listen\"", 20),
                    ("Peep this", 100),
                    ("Listen to this", 100),
                    ("Check out this banger", 50),
                    ("Feast your auditory canals upon this", 20),
                ]

                check_this_out = select_weighted(check_this_out_options)

                await reply_split(message, f"{check_this_out}:\n\n{lyrics_text}", file=discord_file)
            except Exception as e:
                await reply_split(message, f"Sorry, my vocal cords are feeling a bit under the weather today :( but what I would have sang was \"{music_prompt}\", and I couldn't because {str(e)}")

        return True
    
    @no_self_respond(client)
    @channel_only
    async def at_bucket(message):
        name_pattern = r"(?i)\<\@" + str(client.user.id) + r"\>"
        message_text = strip_formatting(message.content)
        regex_matches = re.findall(name_pattern, message_text)
        if not regex_matches:
            return False

        async with message.channel.typing():
            character = "HornyBucket" if str(message.channel.id) in HORNY_CHANNEL_IDS else "Bucket"

            message_text = re.sub(name_pattern, "Bucket,", message_text)
            message_text = enrich_with_tweet_context(message_text)
            attachment_context = enrich_with_attachments(message)
            if attachment_context:
                message_text = message_text + "\n" + attachment_context

            async def create_or_update(response):
                if len(response) > max_message_len:
                    response = response[:max_message_len]
                if not create_or_update.resp_message:
                    create_or_update.resp_message = await message.reply(response)
                else:
                    await create_or_update.resp_message.edit(content=response)
            create_or_update.resp_message = None

            if MESSAGE_MODE == "SPLIT":
                await reply_split(message, await ask_bucket_async(message_text, character=character))
            else:
                await ask_bucket_async(message_text, callback=create_or_update, character=character)
        
        
        return True
    

    @no_self_respond(client)
    @channel_only
    async def nosy_bucket(message):
        if random.random() > 0.1:
            return
        if len(message.content) < 10:
            return
        
        prompt = """Would the following message be relevant to a fictional character named Bucket? Be conservative in your responses; only legitimately Bucket-y messages should be answered in the affirmative. If you're not sure, answer no. Only answer yes if the prompt specifically refers to buckets or bucket-themed things. Mostly no. No preamble, do not write "Answer: " or anything similar 
---
Examples:
\"Wow, Bucket was really mean there\"
Answer: yes

\"What's the windspeed of an unladen swallow?\"
Answer: no

\"Bucket is a really cool guy\"
Answer: yes

\"horse devourers\"
Answer: no

\"I wonder how much fluid I could carry?\"
Answer: yes
---
Input:
\"""" + message.content + "\"\nAnswer: "

        output = replicate.run("meta/meta-llama-3-70b-instruct", input={ "prompt": prompt, "max_new_tokens": 8 })
        print(output)
        if output[0].strip().lower()[0] != "y":
            return False
        
        message_text = strip_formatting(message.content)

        async def create_or_update(response):
            if len(response) > max_message_len:
                response = response[:max_message_len]
            if not create_or_update.resp_message:
                create_or_update.resp_message = await message.reply(response)
            else:
                await create_or_update.resp_message.edit(content=response)
        create_or_update.resp_message = None

        async with message.channel.typing():
            if MESSAGE_MODE == "SPLIT":
                await reply_split(message, await ask_bucket_async(message_text, character="Bucket"))
            else:
                await ask_bucket_async(message_text, callback=create_or_update, character="Bucket")
        
        return True


    def twitter_condition(message, expansion):
        url = re.findall(expansion.regex, message.content)[0]
        id = url.split("/")[-1]
        info = fetch_tweet_info(id)
        return any(media["type"] == "video" for media in info["media_extended"]) or info["qrt"] != None or len(info["media_extended"]) > 1


    expansion = namedtuple("expansion", ["regex", "fr", "to", "condition"])
    expansions = [
        expansion(r"(?i)https?://twitter.com/[^/]+/status/\d+", "twitter.com/", "vxtwitter.com/", twitter_condition),
        expansion(r"(?i)https?://x.com/[^/]+/status/\d+", "x.com/", "vxtwitter.com/", twitter_condition),
        expansion(r"(?i)https?://(www.)?tiktok.com/.+", "tiktok.com/", "vxtiktok.com/", None),
        expansion(r"(?i)https?://(www.)?instagram.com/.+", "instagram.com/", "kkinstagram.com/", None),
    ]

    @no_self_respond(client)
    @channel_only
    async def expand(message):
        content = message.content
        any_expanded = False
        for expansion in expansions:
            if not re.findall(expansion.regex, content):
                continue
            if expansion.condition and not expansion.condition(message, expansion):
                continue
            any_expanded = True
            content = content.replace(expansion.fr, expansion.to)
            
        if not any_expanded:
            return False
        
        await reply_split(message, content)
        return True


    async def find_anon_channel(client, message):
        guilds = [g for g in client.guilds if g.get_member(message.author.id)]
        channels = [[c for c in guild.channels if c.name == "anonymous"] for guild in guilds]
        channels = [channel for sublist in channels for channel in sublist]
        if not channels:
            message.channel.send("Couldn't find a matching #anonymous channel")
            return None
        if len(channels) > 1:
            await message.channel.send("More than one matching server, panic")
            return None
        return channels[0]


    def clear_stale_author_emojis():
        expiry = datetime.datetime.utcnow() - datetime.timedelta(seconds=emoji_timeout_seconds)
        to_remove = []
        for user_id in author_emojis:
            if author_emojis[user_id]["time"] < expiry:
                in_use.remove(author_emojis[user_id]["emoji"])
                to_remove.append(user_id)
        
        for user_id in to_remove:
            del author_emojis[user_id]


    def random_new_emoji():
        remaining = set(emoji_options) - set(in_use)
        if len(remaining) == 0:
            print("No unused emoji left!")
            return "💩"
        else:
            return random.choice(remaining)
    

    funcs = []
    if "ANON" in MODES:
        funcs.append(anonymous)
    if "EXPAND" in MODES:
        funcs.append(expand)
    if "BUCKET" in MODES:
        funcs.append(bucket_give_item)
        funcs.append(bucket_take_item)
        funcs.append(bucket_inventory)
    if "AI" in MODES:
        funcs.append(at_bucket_sing)
        funcs.append(reply_to_bucket)
        funcs.append(at_bucket)
        funcs.append(million_dollars_but_answer)
        funcs.append(million_dollars_but_pose)
        funcs.append(nosy_bucket)

    client.run(TOKEN)

def bucket_give_processor(message):
    give_options = ["give", "hand", "pass", "gives", "hands", "passes"]
    give_options_piped = "|".join(give_options)
    regex_match = re.match(fr"(?i)^({give_options_piped}) bucket (.*)", message)
    if not regex_match:
        return None
    return regex_match[2]

def bucket_put_processor(message: str):
    put_options = ["put", "place", "puts", "places"]
    put_options_piped = "|".join(put_options)
    regex_match = re.match(fr"(?i)^({put_options_piped}) (.*) in(to)? bucket", message)
    if not regex_match:
        return None
    return regex_match[2]

def select_weighted(lst):
    total = sum(item[1] for item in lst)
    r = random.uniform(0, total)
    upto = 0
    for item, weight in lst:
        if upto + weight >= r:
            return item
        upto += weight


def strip_formatting(message):
    while True:
        if message.startswith("*") and message.endswith("*"):
            message = message[1:-1]
        elif message.startswith("_") and message.endswith("_"):
            message = message[1:-1]
        else:
            break
    return message

def strip_quotes(message):
    while True:
        if message.startswith("\"") and message.endswith("\""):
            message = message[1:-1]
        else:
            break
    return message

def dm_only(func):
    async def wrapper(message):
        if not isinstance(message.channel, discord.DMChannel):
            return False
        return await func(message)
    return wrapper

def channel_only(func):
    async def wrapper(message):
        if isinstance(message.channel, discord.DMChannel):
            return False
        return await func(message)
    return wrapper

def no_self_respond(client):
    def decorator(func):
        async def wrapper(message):
            if message.author == client.user:
                return False
            return await func(message)
        return wrapper
    return decorator

if __name__ == "__main__":
    main()