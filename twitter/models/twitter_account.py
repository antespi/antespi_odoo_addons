# -*- coding: utf-8 -*-

import tweepy
import time
# import psycopg2
import random
# from datetime import datetime, timedelta
from datetime import timedelta
from odoo import api, fields, models
from .common import twitter_client

import logging
_logger = logging.getLogger(__name__)

ACCOUNT_LIMIT_THRESHOLD = 10  # 30%
DEFAULT_WAITING_FOR_LIMIT = 15  # 15 seconds
DEFAULT_RETRIES_FOR_LIMIT = 6  # 6 * 15 seconds = 1:30 minutes
ACCOUNT_LIMITS_SYNC_THRESHOLD = 60  # 60 seconds
ACCOUNT_FRIENDSHIPS_SYNC_THRESHOLD = 3600  # 1 hour seconds
SAFE_WRITE_NAX_RETRIES = 5
MAX_FRIENDSHIP_IDS = 2  # 2 pages of 5000 friends/followers (10k)


class TwitterAccount(models.Model):
    _description = 'Twitter account'
    _name = 'twitter.account'

    _tapi = None
    twitter_app_id = fields.Many2one(
        string="Twitter App", comodel_name='twitter.app', required=True)
    user_id = fields.Many2one(
        string="Twitter user", comodel_name='twitter.user', readonly=True, ondelete='cascade')
    display_name = fields.Char(compute='_compute_display_name', store=True, index=True)
    oauth_token = fields.Char(string="OAuth token", readony=True)
    oauth_secret = fields.Char(string="OAuth secret", readony=True)
    access_token = fields.Char(string="Access token", readony=True)
    access_secret = fields.Char(string="Access secret", readony=True)
    last_limit_update = fields.Datetime(string="Last limit sync", readonly=True)
    last_friendship_update = fields.Datetime(string="Last friendship sync", readonly=True)

    # Temporal
    next_follow = fields.Datetime(string="Next follow")

    # twitter_follow.sync_follow: tapi.show_friendship --> /friendships/show.json
    # friendships_show_limit = fields.Integer(string="Friendships show limit", readonly=True)
    # friendships_show_remaining = fields.Integer(string="Friendships show remining", readonly=True)
    # friendships_show_reset = fields.Datetime(string="Friendships show reset", readonly=True)
    # friendships_show_ratio = fields.Float(string="Friendships show ratio", compute='_compute_limits')

    # twitter_user._sync_friendship: tapi.followers_ids --> /followers/ids.json
    # followers_ids_limit = fields.Integer(string="Followers ids limit", readonly=True)
    # followers_ids_remaining = fields.Integer(string="Followers ids remining", readonly=True)
    # followers_ids_reset = fields.Datetime(string="Followers ids reset", readonly=True)
    # followers_ids_ratio = fields.Float(string="Followers ids ratio", compute='_compute_limits')

    # twitter_user._sync_friendship: tapi.friends_ids --> /friends/ids.json
    # friends_ids_limit = fields.Integer(string="Friends ids limit", readonly=True)
    # friends_ids_remaining = fields.Integer(string="Friends ids remining", readonly=True)
    # friends_ids_reset = fields.Datetime(string="Friends ids reset", readonly=True)
    # friends_ids_ratio = fields.Float(string="Friends ids ratio", compute='_compute_limits')

    # twitter_user.create_or_update_from_user_id: tapi.get_user --> /users/show.json
    # twitter_user.sync_profile: tapi.get_user --> /users/show.json
    # users_show_limit = fields.Integer(string="Users show limit", readonly=True)
    # users_show_remaining = fields.Integer(string="Users show remining", readonly=True)
    # users_show_reset = fields.Datetime(string="Users show reset", readonly=True)
    # users_show_ratio = fields.Float(string="Users show ratio", compute='_compute_limits')

    # tapi.create_friendship --> /friendships/create.json
    # friendships_create_limit = fields.Integer(string="Friendships create limit", readonly=True, default=1000)
    # friendships_create_remaining = fields.Integer(string="Friendships create remining", readonly=True)
    # friendships_create_reset = fields.Datetime(string="Friendships create reset", readonly=True)
    # friendships_create_ratio = fields.Float(string="Friendships create ratio", compute='_compute_limits')

    # tapi.destroy_friendship --> /friendships/destroy.json
    # friendships_destroy_limit = fields.Integer(string="Friendships destroy limit", readonly=True, default=15)
    # friendships_destroy_remaining = fields.Integer(string="Friendships destroy remining", readonly=True)
    # friendships_destroy_reset = fields.Datetime(string="Friendships destroy reset", readonly=True)
    # friendships_destroy_ratio = fields.Float(string="Friendships destroy ratio", compute='_compute_limits')

    # @api.multi
    # def set_method_limit(self, limit, method):
    #     self.ensure_one()
    #     remaining = '%s_remaining' % limit
    #     reset = '%s_reset' % limit
    #     data = {}
    #     if method._remaining_calls:
    #         data[remaining] = method._remaining_calls
    #     if method._reset_time:
    #         data[reset] = datetime.fromtimestamp(method._reset_time)
    #     if data:
    #         self.write(data)

    # @api.multi
    # def set_manual_limit(self, limit, days=0, hours=0, minutes=0):
    #     self.ensure_one()
    #     now = fields.Datetime.now()
    #     total = '%s_limit' % limit
    #     remaining = '%s_remaining' % limit
    #     reset = '%s_reset' % limit
    #     if (not self[reset]) or (now > self[reset]) or (self[remaining] == self[total]):
    #         self.write({
    #             reset: now + timedelta(days=days, hours=hours, minutes=minutes),
    #             remaining: self[total],
    #         })

    friendship_ids = fields.One2many(
        string="Friendships", comodel_name='twitter.friendship', inverse_name='account_id')
    friendship_ids_fo = fields.Integer(string="Friendships following", compute='_compute_friendship', store=True)
    friendship_ids_fb = fields.Integer(string="Friendships following back", compute='_compute_friendship', store=True)
    friendship_ids_total = fields.Integer(string="Friendships total", compute='_compute_friendship', store=True)
    friendship_ids_label = fields.Char(string="Friendship label", compute='_compute_friendship_label')

    @api.depends('friendship_ids.following', 'friendship_ids.followed_back')
    def _compute_friendship(self):
        for u in self:
            following = u.friendship_ids.filtered('following')
            u.friendship_ids_fo = len(following)
            u.friendship_ids_fb = len(following.filtered('followed_back'))
            u.friendship_ids_total = len(u.friendship_ids)

    @api.depends('friendship_ids_total', 'friendship_ids_fo', 'friendship_ids_fb')
    def _compute_friendship_label(self):
        for u in self:
            u.friendship_ids_label = (
                "%s/%s/%s" % (u.friendship_ids_total, u.friendship_ids_fo, u.friendship_ids_fb))

    @api.multi
    def action_view_friendships(self):
        action = self.env.ref('twitter.twitter_friendship_action').read()[0]
        form_view = self.env.ref('twitter.twitter_friendship_view_form', False)
        tree_view = self.env.ref('twitter.twitter_account_friendships_view_tree', False)
        action['name'] = "Friendships"
        action['context'] = "{}"
        # action['context'] = "{'search_default_following': True}"
        action['domain'] = "[('account_id', 'in', %s)]" % self.ids
        action['views'] = [(tree_view.id, 'tree'), (form_view.id, 'form')]
        return action

    @api.multi
    def _sync_friendships(self, friendship_type='followers'):
        methods = {
            'followers': ('tapi_followers_ids', 'followed_back'),
            'friends': ('tapi_friends_ids', 'following'),
        }
        friendship_type = friendship_type in methods.keys() and friendship_type or 'followers'
        method_name = methods.get(friendship_type)[0]
        friendship_field = methods.get(friendship_type)[1]
        for a in self:
            u = a.user_id
            if not u:
                _logger.warning("Account %s is not linked to any user", a.display_name)
            method = getattr(a, method_name, None)
            current = self.env['twitter.friendship'].search([
                ('account_id', '=', a.id),
                (friendship_field, '=', True),
            ])
            _logger.info("sync_%s: @%s", friendship_type, u.screen_name)
            cc = len(current)
            fc = 0
            n_known = 0
            n_fake = 0
            n_new = 0
            for friend_id in method(u.twitter_id):
                fc += 1
                friend = u.search_from_user_id(friend_id)
                if not friend:
                    friend = u.create_fake_user_id(friend_id, discovered_by=u.screen_name)
                    _logger.info("[+] %s @%s", fc, friend.twitter_id)
                    n_new += 1
                else:
                    if friend.screen_name:
                        _logger.info("[ ] %s @%s", fc, friend.screen_name)
                        n_known += 1
                    else:
                        _logger.info("[#] %s @%s", fc, friend.twitter_id)
                        n_fake += 1
                friendship = current.create_or_update_from_following(a, friend, friendship_field)
                current -= friendship
            if fc > 0:
                _logger.info(
                    "sync_%s: @%s : %s users\n"
                    "- New   : %5s (%6s%%)\n"
                    "- Fake  : %5s (%6s%%)\n"
                    "- Known : %5s (%6s%%)\n"
                    "- Churn : %5s (%6s%%)",
                    friendship_type, u.screen_name, fc,
                    n_new, '%.2f' % ((n_new / fc) * 100),
                    n_fake, '%.2f' % ((n_fake / fc) * 100),
                    n_known, '%.2f' % ((n_known / fc) * 100),
                    len(current), '%.2f' % (cc > 0 and ((len(current) / cc) * 100) or 0))
            current.write({
                friendship_field: False,
                'last_update': False,
            })
            u.write({
                'last_%s_count' % friendship_type: fc,
                'last_%s_date' % friendship_type: fields.Datetime.now(),
            })
        return True

    @api.multi
    def sync_friendships(self):
        self._sync_friendships(friendship_type='followers')
        self._sync_friendships(friendship_type='friends')
        self.last_friendship_update = fields.Datetime.now()
        return True

    @api.multi
    def sync_followers(self):
        return self._sync_friendships(friendship_type='followers')

    @api.multi
    def sync_friends(self):
        return self._sync_friendships(friendship_type='friends')

    @api.multi
    def wait_for_more_limit(self, limit, timeout=DEFAULT_WAITING_FOR_LIMIT, manual=False):
        self.ensure_one()
        al = self.env['twitter.account.limit'].search_limit(self, limit)
        if not al:
            raise Exception("Twitter rate limit %s not found" % limit)
        retry = 0
        al.reset_manual()
        while al.ratio < ACCOUNT_LIMIT_THRESHOLD:
            retry += 1
            if retry > DEFAULT_RETRIES_FOR_LIMIT:
                raise Exception("Twitter rate limit %s exhausted" % limit)
            _logger.info(
                "wait_for_more_limit(%s/%s): %s (%s < %s)",
                retry, DEFAULT_RETRIES_FOR_LIMIT, limit, al.ratio, ACCOUNT_LIMIT_THRESHOLD)
            time.sleep(timeout)
            if self.need_limits_update():
                self.sync_limits()
            al.reset_manual()
        if al.manual or manual:
            # safe_write
            al.remaining -= 1
        return al

    @api.multi
    def _tapi_friendship_ids(self, twitter_id, friendship_type, limit=MAX_FRIENDSHIP_IDS, test=False):
        self.ensure_one()
        tapi = self.twitter_client()
        method = getattr(tapi, friendship_type, None)

        def wrapper(*args, **kargs):
            self.wait_for_more_limit(friendship_type, manual=True)
            return method(*args, **kargs)

        wrapper.pagination_mode = 'cursor'
        for page in tweepy.Cursor(wrapper, user_id=twitter_id).pages(limit=limit):
            for item in page:
                # For long process, avoid rollback and memory limit
                if not test:
                    self.env.cr.commit()
                    self.env.clear()
                yield item

    @api.multi
    def tapi_followers_ids(self, twitter_id, limit=MAX_FRIENDSHIP_IDS, test=False):
        return self._tapi_friendship_ids(twitter_id, 'followers_ids', limit=limit, test=test)

    @api.multi
    def tapi_friends_ids(self, twitter_id, limit=MAX_FRIENDSHIP_IDS, test=False):
        return self._tapi_friendship_ids(twitter_id, 'friends_ids', limit=limit, test=test)

    @api.multi
    def tapi_get_user(self, twitter_id):
        self.ensure_one()
        tapi = self.twitter_client()
        al = self.wait_for_more_limit('users_show')
        method = tapi.get_user(user_id=twitter_id, create=True)
        user = method.execute()
        al.update_from_method(method)
        return user

    @api.multi
    def tapi_show_friendship(self, follower_id, friend_id):
        self.ensure_one()
        tapi = self.twitter_client()
        al = self.wait_for_more_limit('friendships_show')
        method = tapi.show_friendship(source_id=follower_id, target_id=friend_id, create=True)
        fo, fr = method.execute()
        al.update_from_method(method)
        return fo, fr

    @api.multi
    def tapi_create_friendship(self, twitter_id, notifications=False):
        self.ensure_one()
        tapi = self.twitter_client()
        self.wait_for_more_limit('friendships_create')
        user = tapi.create_friendship(user_id=twitter_id, follow=notifications)
        self.env['twitter.user'].create_or_update_from_user(user)
        return user

    @api.multi
    def tapi_destroy_friendship(self, twitter_id, notifications=False):
        self.ensure_one()
        tapi = self.twitter_client()
        self.wait_for_more_limit('friendships_destroy')
        user = tapi.destroy_friendship(user_id=twitter_id)
        self.env['twitter.user'].create_or_update_from_user(user)
        return user

    @api.depends('twitter_app_id.name', 'user_id.screen_name')
    def _compute_display_name(self):
        for a in self:
            if a.user_id:
                a.display_name = "@%s via %s" % (
                    a.user_id.screen_name, a.twitter_app_id.name)
            else:
                a.display_name = "Link pending via %s" % (a.twitter_app_id.name, )

    @api.model
    def all_twitter_accounts(self):
        return self.search([
            ('user_id', '!=', False),
            ('access_token', '!=', False),
            ('access_secret', '!=', False),
        ])

    @api.model
    def any_twitter_account(self):
        return self.search([
            ('user_id', '!=', False),
            ('access_token', '!=', False),
            ('access_secret', '!=', False),
        ], limit=1)

    @api.model
    def any_twitter_client(self, twitter_account=None):
        if not twitter_account:
            any_account = self.any_twitter_account()
        else:
            any_account = twitter_account[0]
        return any_account.twitter_client()

    # @api.depends()
    # def _compute_limits(self):
    #     for a in self:
    #         a.friendships_show_ratio = 100 * (
    #             a.friendships_show_limit > 0 and
    #             (a.friendships_show_remaining / a.friendships_show_limit) or 0.)
    #         a.friendships_create_ratio = 100 * (
    #             a.friendships_create_limit > 0 and
    #             (a.friendships_create_remaining / a.friendships_create_limit) or 0.)
    #         a.friendships_destroy_ratio = 100 * (
    #             a.friendships_destroy_limit > 0 and
    #             (a.friendships_destroy_remaining / a.friendships_destroy_limit) or 0.)
    #         a.followers_ids_ratio = 100 * (
    #             a.followers_ids_limit > 0 and
    #             (a.followers_ids_remaining / a.followers_ids_limit) or 0.)
    #         a.friends_ids_ratio = 100 * (
    #             a.friends_ids_limit > 0 and
    #             (a.friends_ids_remaining / a.friends_ids_limit) or 0.)
    #         a.users_show_ratio = 100 * (
    #             a.users_show_limit > 0 and
    #             (a.users_show_remaining / a.users_show_limit) or 0.)

    # @api.model
    # def mapping_limits(self, limits):
    #     r = limits['resources']
    #     return {
    #         'friendships_show_limit': r['friendships']['/friendships/show']['limit'],
    #         'friendships_show_remaining': r['friendships']['/friendships/show']['remaining'],
    #         'friendships_show_reset': datetime.fromtimestamp(r['friendships']['/friendships/show']['reset']),
    #         'followers_ids_limit': r['followers']['/followers/ids']['limit'],
    #         'followers_ids_remaining': r['followers']['/followers/ids']['remaining'],
    #         'followers_ids_reset': datetime.fromtimestamp(r['followers']['/followers/ids']['reset']),
    #         'friends_ids_limit': r['friends']['/friends/ids']['limit'],
    #         'friends_ids_remaining': r['friends']['/friends/ids']['remaining'],
    #         'friends_ids_reset': datetime.fromtimestamp(r['friends']['/friends/ids']['reset']),
    #         'users_show_limit': r['users']['/users/show/:id']['limit'],
    #         'users_show_remaining': r['users']['/users/show/:id']['remaining'],
    #         'users_show_reset': datetime.fromtimestamp(r['users']['/users/show/:id']['reset']),
    #     }

    # @api.multi
    # def safe_write(self, data):
    #     ok = False
    #     retry = 0
    #     while not ok and retry < SAFE_WRITE_NAX_RETRIES:
    #         retry += 1
    #         try:
    #             ok = self.write(data)
    #         except psycopg2.extensions.TransactionRollbackError:
    #             _logger.info("safe_write: Rollback exception, retry... (%s/%s)", retry, SAFE_WRITE_NAX_RETRIES)
    #             self.env.cr.rollback()
    #             pass
    #     return ok

    @api.multi
    def need_friendship_update(self):
        now = fields.Datetime.now()
        self and self.ensure_one()
        delta = self.last_friendship_update and (now - self.last_friendship_update)
        return (not delta) or delta.seconds > ACCOUNT_FRIENDSHIPS_SYNC_THRESHOLD

    @api.multi
    def need_limits_update(self):
        now = fields.Datetime.now()
        self and self.ensure_one()
        delta = self.last_limit_update and (now - self.last_limit_update)
        return (not delta) or delta.seconds > ACCOUNT_LIMITS_SYNC_THRESHOLD

    @api.model
    def cron_sync_limits(self):
        accounts = self.all_twitter_accounts()
        accounts.sync_limits()

    @api.multi
    def sync_limits(self):
        for a in self:
            tapi = a.twitter_client()
            _logger.info("twitter_account::sync_limits: %s", a.display_name)
            limits = tapi.rate_limit_status()
            self.env['twitter.account.limit'].search([
                ('account_id', '=', a.id),
                ('manual', '=', False),
            ]).update_from_limits(limits)
            # data = self.mapping_limits(limits)
            a.last_limit_update = fields.Datetime.now()
            # a.safe_write(data)

    @api.model
    def search_from_user_id(self, user_id):
        return self.search([
            ('user_id.twitter_id', '=', user_id),
        ], limit=1)

    @api.model
    def cron_accounts(self, test=False):
        accounts = self.all_twitter_accounts()
        for a in accounts:
            a.user_id.sync_profile()
            if a.need_limits_update():
                a.sync_limits()
            if a.need_friendship_update():
                a.sync_friendships()
            a.action_next_follow()
        not test and self.env.cr.commit()
        self.env['twitter.user'].cron_sync_profiles()
        not test and self.env.cr.commit()
        self.env['twitter.friendship'].cron_sync_friendships()
        not test and self.env.cr.commit()
        # self.env['twitter.follow'].cron_sync_follows()
        # not test and self.env.cr.commit()
        # self.env['twitter.user'].cron_sync_friendships()
        # not test and self.env.cr.commit()

    @api.multi
    def action_next_follow(self):
        now = fields.Datetime.now()
        for a in self:
            _logger.info(
                "action_next_follow: @%s : %s",
                a.user_id.screen_name, fields.Datetime.to_string(a.next_follow))
            if a.next_follow and now > a.next_follow:
                users = self.env['twitter.user'].search([
                    ('friendship_ids_total', '=', 0),
                    ('followers_category', 'in', ('social', 'common', 'newbie')),
                    ('followers_ratio', '<', 0.4),
                    ('lang', '=', 'es'),
                    '|', ('description', 'ilike', 'femini'),
                    ('display_name', 'ilike', 'femini'),
                ])
                if users:
                    user = random.choice(users)
                    _logger.info(
                        "action_next_follow: From %s users, Follow @%s",
                        len(users), user.screen_name)
                    a.tapi_create_friendship(user.twitter_id)
                    self.env['twitter.friendship'].create({
                        'account_id': a.id,
                        'friend_id': user.id,
                        'following': True,
                    })
                else:
                    _logger.info("action_next_follow: No users found")
                minutes = random.choice([5, 7, 11])
                next_time = now + timedelta(minutes=minutes)
                if next_time.hour < 8:
                    next_time += timedelta(hours=8)
                a.next_follow = next_time

    @api.multi
    def twitter_client(self):
        self.ensure_one()
        if not (self.access_token and self.access_secret):
            return False
        return twitter_client(
            self.twitter_app_id.consumer_token,
            self.twitter_app_id.consumer_secret,
            self.access_token,
            self.access_secret,
        )

    @api.model
    def oauth_callback(self):
        return (
            self.env['ir.config_parameter'].sudo().get_param('web.base.url') +
            '/twitter/oauth/callback')

    @api.multi
    def action_view_limits(self):
        action = self.env.ref('twitter.twitter_account_limits_action').read()[0]
        action['domain'] = "[('account_id', 'in', %s)]" % self.ids
        return action

    @api.multi
    def create_account_limits(self):
        limits = self.env['twitter.limit'].search([])
        m_al = self.env['twitter.account.limit']
        for a in self:
            for l in limits:
                al = m_al.search([
                    ('account_id', '=', a.id),
                    ('limit_id', '=', l.id),
                ])
                if not al:
                    m_al.create({
                        'account_id': a.id,
                        'limit_id': l.id,
                        'limit': l.limit,
                        'remaining': l.limit,
                    })

    def oauth_link(self):
        self.ensure_one()
        auth = tweepy.OAuthHandler(
            self.twitter_app_id.consumer_token,
            self.twitter_app_id.consumer_secret,
            self.oauth_callback())
        url = auth.get_authorization_url()
        self.oauth_token = auth.request_token.get('oauth_token')
        self.oauth_secret = auth.request_token.get('oauth_token_secret')
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }

    def oauth_unlink(self):
        self.ensure_one()
        self.write({
            'user_id': False,
            'oauth_token': False,
            'access_token': False,
            'access_secret': False,
        })
