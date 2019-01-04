# -*- coding: utf-8 -*-

import tweepy
from odoo import api, fields, models
import logging
_logger = logging.getLogger(__name__)

FOLLOW_SYNC_THRESHOLD = 7
DEFAULT_CRON_SYNC_FOLLOWS_LIMIT = 10


class TwitterFollow(models.Model):
    _description = 'Twitter follow'
    _name = 'twitter.follow'

    display_name = fields.Char(compute='_compute_display_name', store=True, index=True)
    follower_twitter_id = fields.Char(string="Follower ID", readonly=True, index=True)
    follower_id = fields.Many2one(
        string="Follower", comodel_name='twitter.user', readonly=True, index=True, ondelete='cascade')
    friend_twitter_id = fields.Char(string="Friend ID", readonly=True, index=True)
    friend_id = fields.Many2one(
        string="Friend", comodel_name='twitter.user', readonly=True, index=True, ondelete='cascade')
    can_dm = fields.Boolean(string="Can DM", readonly=True)
    following = fields.Boolean(string="Following", readonly=True)
    followed_by = fields.Boolean(string="Followed back", readonly=True)
    live_following = fields.Boolean(string="Live following", readonly=True)
    marked_spam = fields.Boolean(string="Marked spam", readonly=True)
    muting = fields.Boolean(string="Muting", readonly=True)
    notifications_enabled = fields.Boolean(string="Notifications", readonly=True)
    want_retweets = fields.Boolean(string="Retweets enabled", readonly=True)
    last_update = fields.Datetime(string="Last update", readonly=True)
    block_unfollow = fields.Boolean(string="Block unfollow")
    block_follow = fields.Boolean(string="Block follow")

    target_id = fields.Many2one(
        string="Target", comodel_name='twitter.user', compute='_compute_target', store=True, index=True)
    target_name = fields.Char(string="Target name", related='target_id.name', store=True, readonly=True)
    target_screen_name = fields.Char(string="Target username", related='target_id.screen_name', store=True, readonly=True)
    target_url = fields.Char(string="Target URL", related='target_id.twitter_url', readonly=True)
    target_description = fields.Text(
        string="Target description", related='target_id.description', store=True, readonly=True, index=True)
    target_lang = fields.Char(string="Target language", related='target_id.lang', store=True, readonly=True)
    target_location = fields.Char(
        string="Target location", related='target_id.location', store=True, readonly=True, index=True)
    target_statuses_count = fields.Integer(
        string="Target # Tweets", related='target_id.statuses_count', store=True, readonly=True)
    target_friends_count = fields.Integer(
        string="Target # Friends", related='target_id.friends_count', store=True, readonly=True)
    target_followers_count = fields.Integer(
        string="Target # Followers", related='target_id.followers_count', store=True, readonly=True)
    target_followers_ratio = fields.Float(
        string="Target followers ratio", related='target_id.followers_ratio', store=True, readonly=True)
    target_followers_category = fields.Selection(string="Target category", selection=[
        ('newbie', 'Newbie'),
        ('common', 'Common'),
        ('social', 'Social'),
        ('influencer', 'Influencer'),
        ('mainstream', 'Main stream'),
    ], related='target_id.followers_category', store=True)

    _sql_constraints = [
        ('friendship_uniq',
         'unique(follower_twitter_id, friend_twitter_id)',
         "[SQL Constraint] Follower ID and Friend ID must be unique!"),
    ]

    @api.depends('follower_id', 'friend_id')
    def _compute_target(self):
        ta = self.env['twitter.account']
        for f in self:
            follower = ta.search([('user_id', '=', f.follower_id.id)], limit=1)
            friend = ta.search([('user_id', '=', f.friend_id.id)], limit=1)
            if follower and not friend:
                f.target_id = f.friend_id.id
            elif friend and not follower:
                f.target_id = f.follower_id.id

    @api.depends('follower_id.display_name', 'friend_id.display_name')
    def _compute_display_name(self):
        for f in self:
            f.display_name = "%s > %s" % (f.follower_id.display_name, f.friend_id.display_name)

    @api.multi
    def get_twitter_account(self):
        ta = self.env['twitter.account']
        for follow in self:
            ta = (
                self.follower_id.get_twitter_account() or
                self.friend_id.get_twitter_account())
            if ta:
                break
        if not ta:
            ta = ta.any_twitter_account()
        return ta

    @api.multi
    def sync_follow(self):
        for follow in self:
            try:
                ta = follow.get_twitter_account()
                _logger.info("sync_follow: %s", follow.display_name)
                if follow.follower_id.twitter_id and follow.friend_id.twitter_id:
                    fo, fr = ta.tapi_show_friendship(
                        follow.follower_id.twitter_id, follow.friend_id.twitter_id)
                    follow.update_from_friendship(fo, fr)
            except tweepy.error.TweepError as e:
                _logger.info("Twitter error: %s", e)
                follow.unlink()

    @api.model
    def cron_sync_follows(self):
        accounts = self.env['twitter.account'].all_twitter_accounts()
        cfg = self.env['ir.config_parameter'].sudo()
        max_follows_limit = int(cfg.get_param(
            'twitter.cron_sync_follows_limit', DEFAULT_CRON_SYNC_FOLLOWS_LIMIT))
        follows_limit = len(accounts) > 0 and max_follows_limit / len(accounts) or 0
        for a in accounts:
            tu = a.user_id
            cases = [
                ([
                    ('friend_id', '=', tu.id),
                    ('follower_id.screen_name', '=', False)], 'create_date ASC', 'fake followers'),
                ([
                    ('follower_id', '=', tu.id),
                    ('friend_id.screen_name', '=', False)], 'create_date ASC', 'fake friends'),
                ([
                    ('friend_id', '=', tu.id),
                    ('last_update', '=', False)], 'create_date ASC', 'unknown followers'),
                ([
                    ('follower_id', '=', tu.id),
                    ('last_update', '=', False)], 'create_date ASC', 'unknown friends'),
                ([('friend_id', '=', tu.id)], 'last_update ASC', 'refresh followers'),
                ([('follower_id', '=', tu.id)], 'last_update ASC', 'refresh friends'),
            ]
            remaining = follows_limit
            for domain, order, t in cases:
                follows = self.search(domain, limit=remaining, order=order)
                _logger.info("cron_sync_follows: %s %s", len(follows), t)
                follows.sync_follow()
                remaining -= len(follows)
                if not remaining > 0:
                    break

    @api.model
    def mapping_fake(self, follower, friend, following=None):
        data = {
            'follower_twitter_id': follower.twitter_id,
            'follower_id': follower.id,
            'friend_twitter_id': friend.twitter_id,
            'friend_id': friend.id,
        }
        if following is not None:
            data['following'] = following
        return data

    @api.model
    def create_or_update_fake(self, follower, friend, following=None):
        follow = self.search_from_twitter_users(follower, friend)
        if not follow:
            data = self.mapping_fake(follower, friend, following=following)
            follow = self.create(data)
        elif following is not None:
            follow.write({'following': following})
        return follow

    @api.model
    def mapping_from_friendship(self, follower, follower_id, friend, friend_id):
        return {
            'follower_twitter_id': follower.id_str,
            'follower_id': follower_id.id,
            'friend_twitter_id': friend.id_str,
            'friend_id': friend_id.id,
            'can_dm': follower.can_dm,
            'followed_by': follower.followed_by,
            'following': follower.following,
            'live_following': follower.live_following,
            'marked_spam': follower.marked_spam,
            'muting': follower.muting,
            'notifications_enabled': follower.notifications_enabled,
            'want_retweets': follower.want_retweets,
        }

    @api.multi
    def need_update(self):
        now = fields.Datetime.now()
        self and self.ensure_one()
        if len(self) == 1 and not (self.follower_id.screen_name and self.friend_id.screen_name):
            return False
        delta = self.last_update and (now - self.last_update)
        return (not delta) or delta.days > FOLLOW_SYNC_THRESHOLD

    @api.model
    def search_from_twitter_users(self, follower, friend):
        return self.search([
            ('follower_id', '=', follower.id),
            ('friend_id', '=', friend.id),
        ])

    @api.model
    def search_from_friendship(self, follower, friend):
        return self.search([
            ('follower_twitter_id', '=', follower.id_str),
            ('friend_twitter_id', '=', friend.id_str),
        ])

    @api.model
    def _create_or_update_from_friendship(self, follower, follower_id, friend, friend_id):
        twitter_follow = self.search_from_friendship(follower, friend)
        if twitter_follow:
            twitter_follow._update_from_friendship(follower, follower_id, friend, friend_id)
        else:
            twitter_follow = self._create_from_friendship(follower, follower_id, friend, friend_id)
        return twitter_follow

    @api.model
    def create_or_update_from_friendship(self, follower, friend):
        twitter_follow = self.search_from_friendship(follower, friend)
        if twitter_follow:
            twitter_follow.update_from_friendship(follower, friend)
        else:
            twitter_follow = self.create_from_friendship(follower, friend)
        return twitter_follow

    @api.model
    def twitter_users_from_friendship(self, follower, friend):
        twitter_account = self.env['twitter.account'].any_twitter_account()
        twitter_user = twitter_account.user_id
        follower_id = twitter_user.search([
            ('twitter_id', '=', follower.id_str),
        ])
        if not follower_id:
            follower_id = twitter_user.create_fake_user_id(
                follower.id_str, discovered_by=twitter_user.screen_name)
        friend_id = twitter_user.search([
            ('twitter_id', '=', friend.id_str),
        ])
        if not friend_id:
            friend_id = twitter_user.create_from_user(
                friend.id_str, discovered_by=twitter_user.screen_name)
        return follower_id, friend_id

    @api.model
    def _create_from_friendship(self, follower, follower_id, friend, friend_id):
        data = self.mapping_from_friendship(follower, follower_id, friend, friend_id)
        data['last_update'] = fields.Datetime.now()
        return self.create(data)

    @api.model
    def create_from_friendship(self, follower, friend):
        follower_id, friend_id = self.twitter_users_from_friendship(follower, friend)
        return self._create_from_friendship(follower, follower_id, friend, friend_id)

    @api.multi
    def _update_from_friendship(self, follower, follower_id, friend, friend_id):
        self.ensure_one()
        data = self.mapping_from_friendship(follower, self.follower_id, friend, self.friend_id)
        data = self.changed_fields_filter(data)
        data['last_update'] = fields.Datetime.now()
        return self.write(data)

    @api.multi
    def update_from_friendship(self, follower, friend):
        self.ensure_one()
        follower_id, friend_id = self.twitter_users_from_friendship(follower, friend)
        return self._update_from_friendship(follower, follower_id, friend, friend_id)

    @api.multi
    def changed_fields_filter(self, data):
        self.ensure_one()
        common = {
            'follower_twitter_id',
            'friend_twitter_id',
            'can_dm',
            'following',
            'followed_by',
            'live_following',
            'marked_spam',
            'muting',
            'notifications_enabled',
            'want_retweets',
        }
        res = {k: data[k] for k in common if k in data and self[k] != data[k]}
        if self.follower_id.id != data.get('follower_id', False):
            res['follower_id'] = data.get('follower_id', False)
        if self.friend_id.id != data.get('friend_id', False):
            res['friend_id'] = data.get('friend_id', False)
        return res
