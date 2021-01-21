import os, sys, datetime, time, json, re
from xml.sax.saxutils import unescape
from requests_oauthlib import OAuth1Session

USER_TIMELINE_URL = '/statuses/user_timeline'
SHOW_URL = '/statuses/show/:id'

class TweetCollecter(object):
    def __init__(self, CK, CS, AT, AS):
        self.__session = OAuth1Session(CK, CS, AT, AS)

    def __specifyUrlAndParams(self, screen_name):
        """
        リクエストURLとパラメータを返す
        """
        url = 'https://api.twitter.com/1.1/statuses/user_timeline.json?tweet_mode=extended'
        params = { 'screen_name': screen_name, 'count': 200 } # 一度に取得可能な件数は'200'
        return url, params

    def __pickupTweet(self, res_text):
        """
        レスポンスを配列にまとめて返却
        """
        tweets = []
        for tweet in res_text:
            tweets.append(tweet)

        return tweets

    def __getLimitContext(self, res_text, url):
        """
        レスポンスに応じた回数制限を取得 
        """
        remaining = res_text['resources']['statuses'][url]['remaining']
        reset     = res_text['resources']['statuses'][url]['reset']

        return int(remaining), int(reset)

    def __checkLimit(self, limit_check_url):
        """
        回数制限を確認（アクセス可能になるまで待機する）
        """
        unavailable_cnt = 0
        while True:
            url = "https://api.twitter.com/1.1/application/rate_limit_status.json"
            res = self.__session.get(url)

            if res.status_code == 429:
                # 429 : Too Many Requests
                if unavailable_cnt > 10:
                    raise Exception('Twitter API error %d' % res.status_code)

                unavailable_cnt += 1
                print ('Too Many Requests 429(wait 60 seconds)')
                time.sleep(60) 
                continue

            elif res.status_code == 503:
                # 503 : Service Unavailable
                if unavailable_cnt > 10:
                    raise Exception('Twitter API error %d' % res.status_code)

                unavailable_cnt += 1
                print ('Service Unavailable 503')
                self.__waitUntilReset(time.mktime(datetime.datetime.now().timetuple()) + 30)
                continue

            unavailable_cnt = 0

            if res.status_code != 200:
                raise Exception('Twitter API error %d' % res.status_code)

            remaining, reset = self.__getLimitContext(json.loads(res.text), limit_check_url)
            print ('[remaining]', limit_check_url, remaining)
            if remaining == 0:
                self.__waitUntilReset(reset)
            else:
                break

    def __waitUntilReset(self, reset):
        """
        Twitter API が再度使えるようになる時間まで待機
        """
        seconds = reset - time.mktime(datetime.datetime.now().timetuple())
        seconds = max(seconds, 0)
        print ('\n     =====================')
        print ('     == waiting %d sec ==' % seconds)
        print ('     =====================')
        sys.stdout.flush()
        time.sleep(seconds + 10)  # 念のため +10 秒

    def collectTweetFromShow(self, tweet_id):
        """
        プロフィールから単体ツイートを取得
        """
        # 念のため3秒待ってから取得
        time.sleep(3)

        # 回数制限を確認
        self.__checkLimit(SHOW_URL)

        # ツイート取得
        url = 'https://api.twitter.com/1.1/statuses/show.json?tweet_mode=extended&id=' + str(tweet_id)
        res = self.__session.get(url)
        if res.status_code != 200:
            return None

        return json.loads(res.text)

    def collectTweetsFromUserTimeline(self, screen_name, max_count, start_tweet_id, end_tweet_id):
        """
        タイムラインから複数ツイートを取得
        """
        # 回数制限を確認
        self.__checkLimit(USER_TIMELINE_URL)

        # URL、パラメータ
        url, params = self.__specifyUrlAndParams(screen_name)
        params['include_rts'] = str(True).lower()
        if start_tweet_id > 0:
            params['max_id'] = start_tweet_id - 1

        cnt = 0
        unavailableCnt = 0
        while True:
            # タイムライン取得
            res = self.__session.get(url, params = params)
            if res.status_code == 503:
                # 503 : Service Unavailable
                if unavailableCnt > 10:
                    raise Exception('Twitter API error %d' % res.status_code)

                unavailableCnt += 1
                print ('Service Unavailable 503')
                self.__waitUntilReset(time.mktime(datetime.datetime.now().timetuple()) + 30)
                continue

            unavailableCnt = 0

            if res.status_code != 200:
                raise Exception('Twitter API error %d' % res.status_code)

            tweets = self.__pickupTweet(json.loads(res.text))
            if len(tweets) == 0:
                break

            for tweet in tweets:
                if tweet['id'] == end_tweet_id:
                    return
                else:
                    yield tweet

                cnt += 1
                if max_count > 0 and cnt >= max_count:
                    return

            params['max_id'] = tweet['id'] - 1

            # ヘッダ確認 （回数制限）
            if ('X-Rate-Limit-Remaining' in res.headers and 'X-Rate-Limit-Reset' in res.headers):
                if (int(res.headers['X-Rate-Limit-Remaining']) == 0):
                    self.__waitUntilReset(int(res.headers['X-Rate-Limit-Reset']))
                    self.__checkLimit(USER_TIMELINE_URL)
            else:
                print ('not found  -  X-Rate-Limit-Remaining or X-Rate-Limit-Reset')
                self.__checkLimit(USER_TIMELINE_URL)

            print (' go to next loop...(wait 5 seconds)')
            time.sleep(5) 

        print (' done')

def sentence(sentence):
    if sentence is None:
        return ''

    # 特殊文字デコード
    sentence = unescape(sentence)

    # ユーザー名削除
    sentence = re.sub(r'@[0-9a-zA-Z_:]*', "", sentence)

    # ハッシュタグ削除
    sentence = re.sub(r'#.*', "", sentence)
    
    # URL削除
    sentence = re.sub(r'(https?)(:\/\/[-_.!~*\'()a-zA-Z0-9;\/?:\@&=+\$,%#]+)', "", sentence)

    # 改行削除
    sentence = re.sub(r'\n', "", sentence)

    return sentence.strip()

if __name__ == '__main__':
    # Twitter API
    CK = 'Your Consumer Key'
    CS = 'Your Consumer Secret'
    AT = 'Your Access Token'
    AS = 'Your Access Token Secret'

    # 取得するTwitterアカウントの表示名
    screen_name = ''

    # 最大取得件数（負数：全件）
    max_count = -1

    # 取得開始TweetID（負数：最初から）
    start_tweet_id = -1

    # 取得終了TweetID（負数：最後まで）
    end_tweet_id = -1

    # Twitterの会話を取得
    collecter = TweetCollecter(CK, CS, AT, AS)
    cnt = 0
    for reply in collecter.collectTweetsFromUserTimeline(screen_name, max_count, start_tweet_id, end_tweet_id):
        cnt += 1
        tweet = collecter.collectTweetFromShow(reply['in_reply_to_status_id'])
        if tweet is None:
            print ('[' + str(cnt) + ']', '\'tweet\' is None')
            continue
        i = sentence(tweet['full_text'])
        o = sentence(reply['full_text'])
        if i == "" or o == "":
            print('[' + str(cnt) + ']', "error!")
            continue
        print ('[' + str(cnt) + ']', i, ' -> ', o)
        with open("./data.txt", 'a', encoding='utf-8') as f:
            f.write(i + "\n" + o + "\n")