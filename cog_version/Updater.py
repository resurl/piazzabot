import discord
import datetime
import regex
import datetime
import asyncio
import html
from piazza_api import Piazza
from discord.ext import tasks, commands

class PiazzaUpdater(commands.Cog):
    def __init__(self, bot, EMAIL, PASSWORD, TARGET, NAME, ID):
        self.bot = bot
        self.p = Piazza()
        self.p.user_login(email=EMAIL, password=PASSWORD)
        self.name = NAME
        self._nid = ID
        self.cls = self.p.network(self._nid)
        self.url = f'https://piazza.com/class/{self._nid}?cid='
        self.target_channel = TARGET # bot-commands channel
        self.sendUpdate.start()

    @tasks.loop(count=1)
    async def updateTest(self):
        chnl = self.bot.get_channel(self.target_channel)
        print('sending piazza update')
        await chnl.send(self.fetch())

    @tasks.loop(hours=24)
    async def sendUpdate(self):
        chnl = self.bot.get_channel(self.target_channel)
        print('Sending piazza update')
        await chnl.send(self.fetch())

    @sendUpdate.before_loop
    async def before_sendUpdate(self):
        today = datetime.datetime.utcnow()
        postTime = datetime.datetime(today.year, today.month, today.day, hour=21, minute=00, tzinfo=today.tzinfo)
        timeUntilPost = postTime - today
        if timeUntilPost.total_seconds() > 0: 
            await asyncio.sleep(timeUntilPost.total_seconds())
        await self.bot.wait_until_ready()

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def read(self, ctx):
        postID = ctx.message.content[(len(self.bot.command_prefix) + 5):].strip()
        try:
            isinstance(int(postID), int)
            if postID == '1': raise Exception()
            post = self.cls.get_post(postID)
        except:
            return await ctx.send(f'{postID} not a valid Piazza post ID. Please try again.')
        return await ctx.send(embed=self.producePost(post,postID))
    
    # produces embed with post details  
    def producePost(self, post, postID):
        postEmbed=discord.Embed(title=post['history'][0]['subject'], 
                            url=f'{self.url}{postID}',
                            description=f'@{post["nr"]}')
        postEmbed.add_field(name='Question' if post['type']!='note' else 'Note', value=self.formatContent(post['history'][0]['content']))
        answers = post['children']
        if answers: # check if answers exist
            answer = answers[0]
            if answer['type'] == 'followup':
                # want to show actual answers first so try to find one if you can
                try:
                    answerHeading = 'Instructor Answer' if answer['type']=='i_answer' else 'Student Answer'
                    answer = postEmbed.add_field(name=answerHeading, 
                                                value=self.formatContent(answers[1]['history'][0]['content']), 
                                                inline=False) 
                except:
                    postEmbed.add_field(name="Follow-up Post", value=self.formatContent(answer['subject']), inline=False)
            else:
                answerContent = answer['history'][0]['content']
                answerHeading = 'Instructor Answer' if answer['type']=='i_answer' else 'Student Answer'
                postEmbed.add_field(name=answerHeading, value=self.formatContent(answerContent), inline=False) 
            
            if len(answers) > 1:
                postEmbed.add_field(name=f'{len(answers)-1} more contribution(s) hidden', 
                                    value='Click the title above to access the rest of the post.', 
                                    inline=False)
        else:
            postEmbed.add_field(name="Answers", value='No answers yet :(', inline=False)
        postEmbed.set_footer(text=f'tags: {", ".join(post["tags"] if post["tags"] else "None")}')
        return postEmbed 

    def formatContent(self, text):
        result = text
        tagRegex = regex.compile("<.*?>")
        result = html.unescape(regex.sub(tagRegex,'',result)) 
        return result

    def fetch(self):
        response = f'**{self.name}\'s posts for { datetime.date.today() }**\n'
        posts = self.getPostsToday(lim=50)
        instr, qna = [], []

        def fetchTags(piazza_post, content):
            for tag in piazza_post['tags']:
                if tag == 'instructor-note':
                    instr.append((content, post['nr']))
                elif tag == 'student':
                    qna.append((content, post['nr']))
        
        def addPostListing(arr, isStudent):
            # arr of posts, isStudent (bool)
            section = 'Instructor\'s Notes:\n' if isStudent else '\nDiscussion posts: \n'
            for elm in arr:
                section += f'@{elm[1]}: {elm[0]} <{self.url}{elm[1]}>\n'
            return section

        # want to show first 20 posts, everything else we'll say exists but don't show 
        if len(posts) <= 20:
            for post in posts:
                fetchTags(post, post['history'][0]['subject'])
        else: 
            for i in range(21):
                fetchTags(posts[i],posts[i]['history'][0]['subject'])
            response += f'Fetched {20} posts, {len(posts)-20} more on Piazza'

        response += addPostListing(instr, False)
        response += addPostListing(qna, True)
        return response

    def getPostsToday(self, lim=1):
        if lim > 50:
            lim = 50
        posts = self.cls.iter_all_posts(limit=lim)
        date = datetime.date.today() # format yyyy-mm-dd
        result = []
        for post in posts:
            created_at = [int(x) for x in post['created'][:10].split('-')] # [2020,9,19] from 2020-09-19T22:41:52Z might cause an error lol
            created_at = datetime.date(created_at[0],created_at[1],created_at[2])
            if (date - created_at).days <= 1:
                result.append(post)
        return result