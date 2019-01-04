# -*- coding: utf-8 -*-

import tweepy
from odoo import api, fields, models
import logging
_logger = logging.getLogger(__name__)

FRIENDSHIP_SYNC_THRESHOLD = 7
DEFAULT_CRON_SYNC_FRIENDSHIP_LIMIT = 10


class TwitterFriendship(models.Model):
    _description = 'Twitter friendship'
    _name = 'twitter.friendship'

    display_name = fields.Char(compute='_compute_display_name', store=True, index=True)
    account_id = fields.Many2one(
        string="Account", comodel_name='twitter.account', readonly=True, index=True, ondelete='cascade')
    user_id = fields.Many2one(
        string="User", comodel_name='twitter.user', related='account_id.user_id', index=True, store=True)
    friend_id = fields.Many2one(
        string="Friend", comodel_name='twitter.user', index=True, ondelete='cascade')
    friend_name = fields.Char(
        string="Friend name", related='friend_id.name', store=True, readonly=True)
    friend_screen_name = fields.Char(
        string="Friend username", related='friend_id.screen_name', store=True, readonly=True)
    friend_url = fields.Char(
        string="Friend URL", related='friend_id.twitter_url', readonly=True)
    friend_description = fields.Text(
        string="Friend description", related='friend_id.description', store=True, readonly=True, index=True)
    friend_lang = fields.Char(
        string="Friend language", related='friend_id.lang', store=True, readonly=True)
    friend_location = fields.Char(
        string="Friend location", related='friend_id.location', store=True, readonly=True, index=True)
    friend_statuses_count = fields.Integer(
        string="Friend # Tweets", related='friend_id.statuses_count', store=True, readonly=True)
    friend_friends_count = fields.Integer(
        string="Friend # Friends", related='friend_id.friends_count', store=True, readonly=True)
    friend_followers_count = fields.Integer(
        string="Friend # Followers", related='friend_id.followers_count', store=True, readonly=True)
    friend_followers_ratio = fields.Float(
        string="Friend followers ratio", related='friend_id.followers_ratio', store=True, readonly=True)
    friend_followers_category = fields.Selection(string="Friend category", selection=[
        ('newbie', 'Newbie'),
        ('common', 'Common'),
        ('social', 'Social'),
        ('influencer', 'Influencer'),
        ('mainstream', 'Main stream'),
    ], related='friend_id.followers_category', store=True)

    following = fields.Boolean(string="Following", readonly=True)
    followed_back = fields.Boolean(string="Followed back", readonly=True)

    following_start = fields.Datetime(string="Following start", readonly=True)
    following_end = fields.Datetime(string="Following end", readonly=True)
    followed_back_start = fields.Datetime(string="Followed back start", readonly=True)
    followed_back_end = fields.Datetime(string="Followed back end", readonly=True)
    last_update = fields.Datetime(string="Last update", readonly=True)

    block_unfollow = fields.Boolean(string="Block unfollow")
    block_follow = fields.Boolean(string="Block follow")

    _sql_constraints = [
        ('friendship_uniq',
         'unique(account_id, friend_id)',
         "[SQL Constraint] Account and Friend must be unique!"),
    ]

    # @api.model
    # def create(self, vals):
    #     _logger.info("create: vals = %s", pformat(vals))
    #     return super(TwitterFriendship, self).create(vals)

    # @api.multi
    # def write(self, vals):
    #     _logger.info("write: vals = %s", pformat(vals))
    #     return super(TwitterFriendship, self).write(vals)

    @api.depends('account_id.display_name', 'friend_id.display_name')
    def _compute_display_name(self):
        for f in self:
            f.display_name = "%s : %s" % (f.account_id.user_id.display_name, f.friend_id.display_name)

    @api.multi
    def mapping_from_friendship(self, follower, friend):
        self.ensure_one()
        data = {
            'account_id': self.account_id.id,
            'friend_id': self.friend_id.id,
            'following': follower.following,
            'followed_back': friend.following,
        }
        if follower.following:
            data['following_end'] = False
            if not (self.following_start and self.following):
                data['following_start'] = fields.Datetime.now()
        elif not (self.following_end or not self.following):
            data['following_end'] = fields.Datetime.now()
        if friend.following:
            data['followed_back_end'] = False
            if not (self.followed_back_start and self.followed_back):
                data['followed_back_start'] = fields.Datetime.now()
        elif not (self.followed_back_end or not self.followed_back):
            data['followed_back_end'] = fields.Datetime.now()
        return data

    @api.multi
    def changed_fields_filter(self, data):
        self.ensure_one()
        common = {
            'following',
            'followed_back',
            'following_start',
            'following_end',
            'followed_back_start',
            'followed_back_end',
        }
        res = {k: data[k] for k in common if k in data and self[k] != data[k]}
        account_id = data.get('account_id', False)
        friend_id = data.get('friend_id', False)
        if account_id and self.account_id.id != account_id:
            res['account_id'] = account_id
        if friend_id and self.friend_id.id != friend_id:
            res['friend_id'] = friend_id
        return res

    @api.multi
    def update_from_friendship(self, follower, friend):
        self.ensure_one()
        data = self.mapping_from_friendship(follower, friend)
        data = self.changed_fields_filter(data)
        data['last_update'] = fields.Datetime.now()
        return self.write(data)

    @api.model
    def create_from_friendship(self, follower, friend):
        account = self.env['twitter.account']
        user = self.env['twitter.user']
        account = account.search_from_user_id(follower.id_str)
        if not account:
            raise Exception("Account not found for [%s] @%s", follower.id_str, follower.screen_name)
        user = user.search_from_user_id(friend.id_str)
        if not user:
            user = user.create_fake_user_id(friend.id_str, discovered_by=account.user_id.screen_name)
        f = self.create({
            'account_id': account.id,
            'friend_id': user.id,
        })
        f.update_from_friendship(follower, friend)
        return f

    @api.model
    def search_from_friendship(self, follower, friend):
        return self.search([
            ('account_id.user_id.twitter_id', '=', follower.id_str),
            ('friend_id.twitter_id', '=', friend.id_str),
        ])

    @api.model
    def create_or_update_from_friendship(self, follower, friend):
        f = self.search_from_friendship(follower, friend)
        if f:
            f.update_from_friendship(follower, friend)
        else:
            f = self.create_from_friendship(follower, friend)
        return f

    @api.model
    def search_from_friend(self, account_id, friend_id):
        return self.search([
            ('account_id', '=', account_id.id),
            ('friend_id', '=', friend_id.id),
        ])

    @api.multi
    def mapping_from_following(self, friendship_field):
        self.ensure_one()
        data = {
            friendship_field: True,
        }
        start_field = '%s_start' % friendship_field
        end_field = '%s_end' % friendship_field
        data[end_field] = False
        if not (self[start_field] and self[friendship_field]):
            data[start_field] = fields.Datetime.now()
        return data

    @api.multi
    def update_from_following(self, friendship_field):
        self.ensure_one()
        data = self.mapping_from_following(friendship_field)
        data = self.changed_fields_filter(data)
        data['last_update'] = fields.Datetime.now()
        return self.write(data)

    @api.model
    def create_from_following(self, account_id, friend_id, friendship_field):
        f = self.create({
            'account_id': account_id.id,
            'friend_id': friend_id.id,
        })
        f.update_from_following(friendship_field)
        return f

    @api.model
    def create_or_update_from_following(self, account_id, friend_id, friendship_field):
        f = self.search_from_friend(account_id, friend_id)
        if f:
            f.update_from_following(friendship_field)
        else:
            f = self.create_from_following(account_id, friend_id, friendship_field)
        return f

    @api.multi
    def sync_friendship(self):
        for f in self:
            try:
                if f.user_id.twitter_id and f.friend_id.twitter_id:
                    _logger.info("sync_friendship: %s", f.display_name)
                    fo, fr = f.account_id.tapi_show_friendship(
                        f.user_id.twitter_id, f.friend_id.twitter_id)
                    f.update_from_friendship(fo, fr)
            except tweepy.error.TweepError as e:
                _logger.info("Twitter error: %s", e)
                f.unlink()

    @api.model
    def cron_sync_friendships(self):
        accounts = self.env['twitter.account'].all_twitter_accounts()
        cfg = self.env['ir.config_parameter'].sudo()
        max_fs_limit = int(cfg.get_param(
            'twitter.cron_sync_friendships_limit', DEFAULT_CRON_SYNC_FRIENDSHIP_LIMIT))
        fs_limit = len(accounts) > 0 and max_fs_limit / len(accounts) or 0
        for a in accounts:
            cases = [
                ([
                    ('account_id', '=', a.id),
                    ('last_update', '=', False)],
                 'create_date ASC', 'pending friendships'),
                # AEA: Not needed, we can calculate from account followers and friends ids list
                # ([('account_id', '=', a.id)],
                #  'last_update ASC', 'refresh friendships'),
            ]
            remaining = fs_limit
            for domain, order, t in cases:
                fs = self.search(domain, limit=remaining, order=order)
                _logger.info("cron_sync_friendships: %s %s", len(fs), t)
                fs.sync_friendship()
                remaining -= len(fs)
                if not remaining > 0:
                    break
