import datetime
import regex
import html
from piazza_api import Piazza

class PiazzaHandler():
    """Handles requests to a specific Piazza network. Requires an e-mail and password, but if none are
    provided, then they will be asked for in the console (doesn't work for Heroku deploys).

    Attributes
    ----------
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
    def __init__(self, TARGET, CLASSNAME, id, EMAIL, PASSWORD):
        self.target = TARGET
        self.classname = CLASSNAME
        self._nid = id
        self.url = f'https://piazza.com/class/{self._nid}?cid='
        self.p = Piazza()
        self.p.user_login(email=EMAIL, password=PASSWORD)
        self.network = self.p.network(self._nid) 
        self.target_channel = TARGET

    @property
    def piazza_url(self):
        return self.url
    
    @property
    def course_name(self):
        return self.classname

    @property
    def piazza_id(self):
        return self._nid

    def fetch_post_instance(self, postID):
        """
        returns a post object corresponding to a specific Piazza network's post ID

        Parameters
        ----------
        postID : `int`
            requested post ID
        """
        try:
            isinstance(int(postID),int)
            if postID == '1': raise Exception()
            post = self.network.get_post(postID)
            return post
        except:
            return None
    
    def find_recent_notes(self, lim=10):
        posts = self.fetch_posts_today(lim=lim)
        response = []
        for post in posts:
            if post['tags'][0] == 'instructor-note' or post['bucket_name'] == 'Pinned':
                response.append(post)
        return response

    def fetch_pinned(self, lim=10):
        posts = self.network.iter_all_posts(limit=lim)
        response = []
        for post in posts: 
            if post['bucket_name'] and post['bucket_name'] == 'Pinned':
                response.append(post)
        return response

    def fetch_post(self, postID):
        """
        Parameters
        ----------
        postID : `int`
            requested post ID
        """
        post = self.fetch_post_instance(postID)
        postType = 'Note' if post['type'] == 'note' else 'Question'
        response = {
            'title': post['history'][0]['subject'],
            'id': f'@{postID}',
            'url': f'{self.url}{postID}',
            'post_type': postType,
            'post_body': self.clean_response(self.get_body(post)),
            'more_answers': False
        }

        answers = post['children']
        answerHeading, answerBody = "", ""
        if answers:
            answer = answers[0]
            
            if answer['type'] == 'followup':
                try:
                    if answers[1]['type'] == 'followup': raise Exception()
                    answerHeading = 'Instructor Answer' if answer['type'] == 'i_answer' else 'Student Answer'
                    answerBody = self.get_body(answers[1])
                except:
                    answerHeading = 'Follow-up Post'
                    answerBody = answer['subject']
            else:
                answerHeading = 'Instructor Answer' if answer['type'] == 'i_answer' else 'Student Answer'
                answerBody = self.get_body(answer)
            
            if len(answers) > 1:
                response.update({'more_answers':True})
        else:
            answerHeading = 'Answers'
            answerBody = 'No answers yet :('
                    
        response.update({'ans_type' : answerHeading})
        response.update({'ans_body' : answerBody})
        response.update({'tags' : ", ".join(post['tags'] if post['tags'] else 'None')})
        return response

    def fetch_posts_today(self, lim=10):
        if lim > 50: lim = 50
        elif lim < 1: lim = 1
        posts = self.network.iter_all_posts(limit=lim)
        date = datetime.date.today()
        result = []
        for post in posts:
            created_at = [int(x) for x in post['created'][:10].split('-')] # [2020,9,19] from 2020-09-19T22:41:52Z
            created_at = datetime.date(created_at[0],created_at[1],created_at[2])
            if (date - created_at).days <= 1:
                result.append(post)
        return result
        

    @staticmethod
    def clean_response(res):
        if len(res) > 1024:
            res = res[:1000]
            res += '...\n\n *(Read more)*'

        tagRegex = regex.compile("<.*?>")
        res = html.unescape(regex.sub(tagRegex, '', res))

        if len(res) < 1: res += 'An image or video was posted in response.'

        return res

    @staticmethod
    def get_body(res):
        try:
            body = res['history'][0]['content']
            if not body: raise Exception()
            return body
        except:
            print(f'ERROR: Passed invalid object into get_body:\n{res}')
        

    