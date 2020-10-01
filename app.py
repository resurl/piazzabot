import os
import discord
import datetime
import asyncio
import regex
import json
import html
from dotenv import load_dotenv
from piazza_api import Piazza
from discord.ext import tasks, commands

load_dotenv()
PIAZZA_EMAIL = os.getenv('EMAIL')
PIAZZA_PASSWORD = os.getenv('PASSWORD')
TOKEN = os.getenv('TOKEN')
bot = commands.Bot('.')
# 747259140908384386 bot-commands channel

class PiazzaUpdater(commands.Cog):
    """Sends daily updates (at 7AM UTC, 12AM PST) to the target_channel from a
    specified Piazza forum. Requires an e-mail and password, but if none are
    provided, then they will be asked for in the console (doesn't work for Heroku deploys).

    Attributes
    ----------
    bot : `commands.Bot` 
        Discord bot client.
    TARGET : `int`
        ID of target channel (where the bot will post)
    CLASS : `str`
        Name of class (ex. CPSC221)
    ID : `int` 
        ID of Piazza forum (usually found at the end of a Piazza's home url)
    EMAIL : `str (optional)`
        Piazza log-in email
    PASSWORD : `str (optional)` 
        Piazza password
    """

    def __init__(self, bot, TARGET, CLASS, ID, EMAIL=None, PASSWORD=None):
        self.bot = bot
        self.p = Piazza()
        self.p.user_login(email=EMAIL, password=PASSWORD)
        self._nid = ID
        self.classname = CLASS
        self.cls = self.p.network(self._nid)
        self.url = f'https://piazza.com/class/{self._nid}?cid='
        self.target_channel = TARGET # bot-commands channel
        self.sendUpdate.start() # this error is ok, was written this way in the docs 

    # testing update function, but only fires on ready
    @tasks.loop(count=1)
    async def updateTest(self):
        chnl = self.bot.get_channel(self.target_channel)
        print('Sending piazza update')
        await chnl.send(self.fetch(10))

    @tasks.loop(hours=24)
    async def sendUpdate(self):
        chnl = self.bot.get_channel(self.target_channel)
        print('Sending piazza update')
        await chnl.send(self.fetch(10))

    @sendUpdate.before_loop
    async def before_sendUpdate(self):
        today = datetime.datetime.utcnow()
        postTime = datetime.datetime(today.year, today.month, today.day, hour=7, minute=00, tzinfo=today.tzinfo)
        timeUntilPost = postTime - today
        if timeUntilPost.total_seconds() > 0: 
            await asyncio.sleep(timeUntilPost.total_seconds())
        await self.bot.wait_until_ready()
   
    @commands.command()
    #@commands.cooldown(1, 5, commands.BucketType.user)
    async def read(self, ctx):
        """
        `!read` __`Post ID`__
        **Usage:** !read [post ID]

        **Examples:**
        `!read 152` returns embed of post #152 from preset Piazza
        """
        postID = ctx.message.content[(len(self.bot.command_prefix) + 5):].strip()
        post=None
        try:
            isinstance(int(postID), int)
            if postID == '1': raise Exception()
            post = self.cls.get_post(postID)
        except:
            return await ctx.send(f'{postID} not a valid Piazza post ID. Please try again.')
        postEmbed=self.fetchPost(post,postID)
        return await ctx.send(embed=postEmbed)
    
    @commands.command()
    @commands.cooldown(1,5,commands.BucketType.user)
    async def pinned(self, ctx):
        posts = self.getPinnedPosts(lim=15) # arbitr. number, pinned posts are always the first to be fetched by api
        response = f'Pinned posts for {self.classname}:\n'
        for post in posts:
            postNum = post['nr']
            postSubject = post['history'][0]['subject']
            response += f'@{postNum}: {postSubject} <{self.url}{postNum}>\n'
        return await ctx.send(response)
     
    def fetchPost(self, post, postID):
        """
        produces Embed object with details for a specific post
        
        Parameters:
            post (str) - JSON string representing a Piazza post
            postID (int) - integer for a valid Piazza post ID 
        """
        postEmbed=discord.Embed(title=post['history'][0]['subject'], 
                            url=f'{self.url}{postID}',
                            description=f'@{post["nr"]}')
        postEmbed.add_field(name='Question' if post['type'] != 'note' else 'Note', 
                            value=self.formatContent(post['history'][0]['content']))
        answers = post['children']
        if answers: # check if answers exist
            answer = answers[0]
            if answer['type'] == 'followup': # if a followup is the most recent contribution
                try: # look for another official answer first
                    if answers[1]['type'] == 'followup': raise Exception()
                    answerHeading = 'Instructor Answer' if answer['type']=='i_answer' else 'Student Answer'
                    answer = postEmbed.add_field(name=answerHeading, 
                                                value=self.formatContent(answers[1]['history'][0]['content']), 
                                                inline=False) 
                except: # if it doesn't exist, just default to the followup
                    postEmbed.add_field(name="Follow-up Post", 
                                        value=self.formatContent(answer['subject']), 
                                        inline=False)
            else: # if it's an actual answer
                answerContent = answer['history'][0]['content']
                answerHeading = 'Instructor Answer' if answer['type']=='i_answer' else 'Student Answer'
                postEmbed.add_field(name=answerHeading, 
                                    value=self.formatContent(answerContent), 
                                    inline=False) 
            if len(answers) > 1: # more discussion exists
                postEmbed.add_field(name=f'{len(answers)-1} more contribution(s) hidden', 
                                    value='Click the title above to access the rest of the post.', 
                                    inline=False)
        else: # no answer exists yet
            postEmbed.add_field(name="Answers", value='No answers yet :(', inline=False)
        postEmbed.set_footer(text=f'tags: {", ".join(post["tags"] if post["tags"] else "None")}')
        return postEmbed

    def formatContent(self, text):
        """gets rid of json-formatted text and markdown tags"""
        result = text

        if len(result) > 1024:
            result = result[:1000]
            result += '...\n\n *(Read more of this post by clicking the post title above!)*'

        tagRegex = regex.compile("<.*?>")
        result = html.unescape(regex.sub(tagRegex,'',result)) 
        
        if len(result) < 1: result += 'An image or video was posted'
        
        return result

    def fetch(self, showLimit):
        """Sorts and formats the day's piazza posts"""
        response = f'**{self.classname}\'s posts for { datetime.date.today() }**\n'
        posts = self.getPostsToday(lim=50)
        instr, qna = [], []

        def fetchTag(piazza_post, content, arr, tagged):
            """Sorts posts by instructor or student and append it to the respective array of posts"""
            for tag in piazza_post['tags']:
                if tag == tagged:
                    arr.append((content, piazza_post['nr']))
        
        def addPostListing(arr, isStudent):
            """Returns a string formatted as:
                Instructor's Notes/Discussion posts: 
                @`postID`: `post title` `url to post` 
                ...
            """
            section = '\nDiscussion posts: \n' if isStudent else 'Instructor\'s Notes:\n'
            for elm in arr:
                section += f'@{elm[1]}: {elm[0]} <{self.url}{elm[1]}>\n'
            if len(arr) < 1: section += 'None for today!\n'
            return section

        # first adds all instructor notes to update, then student notes
        # for student notes, show first 10 and indicate there's more to be seen for today
        for post in posts:
            fetchTag(post, post['history'][0]['subject'], instr, 'instructor-note')

        if len(posts) <= showLimit:
            for p in posts:
                fetchTag(p, p['history'][0]['subject'], qna, 'student')
        else:
            for i in range(showLimit+1):
                fetchTag(posts[i],posts[i]['history'][0]['subject'], qna, 'student')
            response += f'Showing first {showLimit} posts, {len(posts)-showLimit} more on Piazza\n'

        response += addPostListing(instr, False)
        response += addPostListing(qna, True)
        return response
    
    def getPinnedPosts(self, lim=1):
        posts = self.cls.iter_all_posts(limit=lim)
        result = []
        for post in posts:
            if post['bucket_name'] and post['bucket_name'] == 'Pinned':
                result.append(post)
        return result

    def getPostsToday(self, lim=1):
        """gets up to `lim` posts from Piazza's internal API and returns the ones that 
            were made today"""
        if lim > 50:
            lim = 50
        elif lim < 1:
            lim = 1
        posts = self.cls.iter_all_posts(limit=lim)
        date = datetime.date.today() # format yyyy-mm-dd
        result = []
        for post in posts:
            created_at = [int(x) for x in post['created'][:10].split('-')] # [2020,9,19] from 2020-09-19T22:41:52Z might cause an error lol
            created_at = datetime.date(created_at[0],created_at[1],created_at[2])
            if (date - created_at).days <= 1:
                result.append(post)
        return result


@bot.event
async def on_command_error(ctx,error):
    if isinstance(error, commands.CommandOnCooldown): await ctx.send("Command on cooldown, please wait 5 seconds.")

@bot.event
async def on_ready():
    print('bot ready')
    print(f'Bot name: {bot.user.name}')
    print(f'Discord version: {discord.__version__}')
    bot.add_cog(PiazzaUpdater(bot,479512513378123798,"CPSC221","ke1ukp9g4xx6oi",PIAZZA_EMAIL,PIAZZA_PASSWORD))

# testing commands!
@bot.command(aliases=['hi,hello'])
async def hello(ctx):
    await ctx.send(f'hello {ctx.author.mention}')

bot.run(TOKEN)



