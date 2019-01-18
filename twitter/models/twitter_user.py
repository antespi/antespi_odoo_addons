# -*- coding: utf-8 -*-

import tweepy
from odoo import api, fields, models
from .common import batch_split
import logging
_logger = logging.getLogger(__name__)

PROFILE_SYNC_THRESHOLD = 7
DEFAULT_CRON_SYNC_PROFILES_LIMIT = 50
SYNC_FRIENDSHIPS_FAKE_USERS_LIMIT = 1000


class TwitterUser(models.Model):
    _description = 'Twitter user'
    _name = 'twitter.user'
    _rec_name = 'screen_name'

    twitter_id = fields.Char(string="Twitter ID", readonly=True, index=True)
    twitter_url = fields.Char(string="Twitter URL", compute='_compute_url')
    name = fields.Char(string="Name", readonly=True)
    screen_name = fields.Char(string="Username", readonly=True)
    display_name = fields.Char(compute='_compute_display_name', store=True, index=True)
    description = fields.Text(string="Description", readonly=True, index=True)
    lang = fields.Char(string="Language", readonly=True)
    location = fields.Char(string="Location", readonly=True, index=True)
    created_at = fields.Date(string="Created at", readonly=True)
    statuses_count = fields.Integer(string="# Tweets", readonly=True)
    friends_count = fields.Integer(string="# Friends", readonly=True)
    followers_count = fields.Integer(string="# Followers", readonly=True)
    favourites_count = fields.Integer(string="# Likes", readonly=True)
    listed_count = fields.Integer(string="# Listed", readonly=True)

    protected = fields.Boolean(string="Protected", readonly=True)
    verified = fields.Boolean(string="Verified", readonly=True)
    last_status_date = fields.Datetime(string="Last status", readonly=True)

    discovered_by = fields.Char(string="Discovered by", readonly=True)

    twitter_error = fields.Text(string="Error", readonly=True)

    friendship_ids = fields.One2many(
        string="Friendships", comodel_name='twitter.friendship', inverse_name='friend_id')
    friendship_ids_fo = fields.Integer(string="Friendships following", compute='_compute_friendship', store=True)
    friendship_ids_fb = fields.Integer(string="Friendships following back", compute='_compute_friendship', store=True)
    friendship_ids_total = fields.Integer(string="Friendships total", compute='_compute_friendship', store=True)
    friendship_ids_label = fields.Char(string="Friendship label", compute='_compute_friendship_label')

    followers_ratio = fields.Float(string="Followers ratio", compute='_compute_followers', store=True)
    followers_category = fields.Selection(string="Category", selection=[
        ('newbie', 'Newbie'),
        ('common', 'Common'),
        ('social', 'Social'),
        ('influencer', 'Influencer'),
        ('mainstream', 'Main stream'),
    ], compute='_compute_followers', store=True)

    last_update = fields.Datetime(string="Last update", readonly=True)
    last_followers_date = fields.Datetime(string="Last followers sync", readonly=True)
    last_followers_count = fields.Integer(string="Last # Followers", readonly=True)
    need_followers_discover = fields.Boolean(
        string="Need followers sync", compute='_compute_need_discover', readonly=True, store=True)
    last_friends_date = fields.Datetime(string="Last friends sync", readonly=True)
    last_friends_count = fields.Integer(string="last # Friends", readonly=True)
    need_friends_discover = fields.Boolean(
        string="Need friends sync", compute='_compute_need_discover', readonly=True, store=True)

    _sql_constraints = [
        ('twitter_id_uniq', 'unique(twitter_id)', "[SQL Constraint] Twitter ID must be unique!"),
    ]

    @api.multi
    def twitter_error_reset(self):
        self.write({'twitter_error': False})

    @api.depends('screen_name')
    def _compute_url(self):
        for u in self:
            if u.screen_name:
                u.twitter_url = "https://www.twitter.com/%s" % u.screen_name
            else:
                u.twitter_url = False

    @api.depends('name', 'screen_name')
    def _compute_display_name(self):
        for u in self:
            if u.name and u.screen_name:
                u.display_name = "%s @%s" % (u.name, u.screen_name)
            else:
                u.display_name = "Fake %s by @%s" % (u.twitter_id, u.discovered_by)

    @api.depends('followers_count', 'friends_count')
    def _compute_followers(self):
        for u in self:
            u.followers_ratio = (
                u.friends_count > 0 and
                float(u.followers_count) / float(u.friends_count) or 0)
            if u.followers_count < 100:
                u.followers_category = 'newbie'
            elif u.followers_count < 1000:
                u.followers_category = 'common'
            elif u.followers_count < 10000:
                u.followers_category = 'social'
            elif u.followers_count < 100000:
                u.followers_category = 'influencer'
            else:
                u.followers_category = 'mainstream'

    @api.depends('followers_count', 'friends_count', 'last_followers_count', 'last_friends_count')
    def _compute_need_discover(self):
        for u in self:
            u.need_followers_discover = u.last_followers_count != u.followers_count
            u.need_friends_discover = u.last_friends_count != u.friends_count

    @api.multi
    def sync_reset(self):
        self.write({
            'last_followers_date': False,
            'last_followers_count': 0,
            'last_friends_date': False,
            'last_friends_count': 0,
        })

    @api.multi
    def _sync_profile_lookup_users(self):
        ta = self[0].get_twitter_account()
        batches = batch_split(self, chunk_size=100)
        for b in batches:
            try:
                users = ta.tapi_lookup_users(b.mapped('twitter_id'))
                for user in users:
                    _logger.info("lookup_users: %s", user.id_str)
                    self.with_context(twitter_account=ta).create_or_update_from_user(user)
            except tweepy.error.TweepError as e:
                _logger.info("Twitter error: %s", e)
                b.write({'twitter_error': str(e)})

    @api.multi
    def _sync_profile_get_user(self):
        for u in self:
            try:
                _logger.info("get_user: %s", u.display_name)
                ta = u.get_twitter_account()
                user = ta.tapi_get_user(u.twitter_id)
                u.with_context(twitter_account=ta).update_from_user(user)
            except tweepy.error.TweepError as e:
                _logger.info("Twitter error: %s", e)
                u.twitter_error = str(e)

    @api.multi
    def sync_profile(self):
        if len(self) > 10:
            return self._sync_profile_lookup_users()
        return self._sync_profile_get_user()

    @api.multi
    def get_twitter_account(self):
        ta = self.env['twitter.account']
        if not self:
            return ta.selected_twitter_account()
        self.ensure_one()
        ta = ta.search([
            ('user_id', '=', self.id),
        ], limit=1)
        if not ta and self.discovered_by:
            discover = self.search_from_screen_name(self.discovered_by)
            ta = discover.get_twitter_account()
        return ta or ta.selected_twitter_account()

    @api.multi
    def _discover_from_friendship(self, friendship_type='followers'):
        now = fields.Datetime.now()
        methods = {
            'followers': ('tapi_followers_ids', 'friend_id'),
            'friends': ('tapi_friends_ids', 'follower_id'),
        }
        friendship_type = friendship_type in methods.keys() and friendship_type or 'followers'
        method_name = methods.get(friendship_type)[0]
        for u in self:
            ta = u.get_twitter_account()
            tu = ta.user_id
            if not (ta and tu):
                _logger.warning("User %s has not account or discovered_by", u.display_name)
            method = getattr(ta, method_name, None)
            _logger.info("discover_from_%s: @%s", friendship_type, u.screen_name)
            fc = 0
            n_known = 0
            n_fake = 0
            n_new = 0
            for user_id in method(u.twitter_id):
                fc += 1
                user = self.search_from_user_id(user_id)
                if not user:
                    user = u.search_or_create_fake_user_id(user_id, discovered_by=tu.screen_name)
                    _logger.info("[+] %s @%s", fc, user.twitter_id)
                    n_new += 1
                else:
                    if user.screen_name:
                        _logger.info("[ ] %s @%s", fc, user.screen_name)
                        n_known += 1
                    else:
                        _logger.info("[#] %s @%s", fc, user.twitter_id)
                        n_fake += 1
            if fc > 0:
                _logger.info(
                    "sync_%s: @%s : %s users\n"
                    "- New   : %5s (%6s%%)\n"
                    "- Fake  : %5s (%6s%%)\n"
                    "- Known : %5s (%6s%%)",
                    friendship_type, u.screen_name, fc,
                    n_new, '%.2f' % ((n_new / fc) * 100),
                    n_fake, '%.2f' % ((n_fake / fc) * 100),
                    n_known, '%.2f' % ((n_known / fc) * 100))
            u.write({
                'last_%s_count' % friendship_type: fc,
                'last_%s_date' % friendship_type: now,
            })

    @api.multi
    def discover_followers(self):
        return self._discover_from_friendship(friendship_type='followers')

    @api.multi
    def discover_friends(self):
        return self._discover_from_friendship(friendship_type='friends')

    @api.model
    def create_fake_prepare(self, user_id, discovered_by=False):
        return {
            'twitter_id': user_id,
            'discovered_by': discovered_by,
        }

    @api.model
    def search_or_create_fake_user_id(self, user_id, discovered_by=False):
        if not user_id:
            return self.browse()
        user = self.search_from_user_id(user_id)
        if not user:
            data = self.create_fake_prepare(user_id, discovered_by=discovered_by)
            user = self.create(data)
        return user

    @api.depends('friendship_ids.following', 'friendship_ids.followed_back')
    def _compute_friendship(self):
        for u in self:
            u.friendship_ids_fo = len(u.friendship_ids.filtered('following'))
            u.friendship_ids_fb = len(u.friendship_ids.filtered('followed_back'))
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
        action['domain'] = "[('friend_id', 'in', %s)]" % self.ids
        action['views'] = [(tree_view.id, 'tree'), (form_view.id, 'form')]
        return action

    @api.model
    def status_from_user(self, user, author):
        if not hasattr(user, 'status'):
            return False
        return self.env['twitter.status'].with_context(
            status_author=author).create_or_update_from_status(user.status)

    @api.model
    def mapping_from_user(self, user):
        data = {
            'twitter_id': user.id_str,
            'name': user.name or user.screen_name,
            'screen_name': user.screen_name,
            'description': user.description,
            'lang': user.lang,
            'location': user.location,
            'created_at': fields.Date.to_date(user.created_at),
            'statuses_count': user.statuses_count,
            'friends_count': user.friends_count,
            'followers_count': user.followers_count,
            'favourites_count': user.favourites_count,
            'listed_count': user.listed_count,
            'protected': user.protected,
            'verified': user.verified,
        }
        return data

    @api.multi
    def need_update(self):
        now = fields.Datetime.now()
        self and self.ensure_one()
        delta = self.last_update and (now - self.last_update)
        return (not delta) or delta.days > PROFILE_SYNC_THRESHOLD

    @api.model
    def search_from_screen_name(self, screen_name):
        return self.search([('screen_name', '=', screen_name)])

    @api.model
    def search_from_user_id(self, user_id):
        return self.search([('twitter_id', '=', user_id)])

    @api.model
    def search_from_user(self, user):
        user_id = user.id_str
        return self.search_from_user_id(user_id)

    @api.model
    def create_or_update_from_user(self, user):
        u = self.search_from_user(user)
        if u:
            u.update_from_user(user)
        else:
            u = self.create_from_user(user)
        return u

    @api.model
    def create_from_user(self, user):
        data = self.mapping_from_user(user)
        data['last_update'] = fields.Datetime.now()
        ta = self.env.context.get('twitter_account')
        if ta:
            data['discovered_by'] = ta.user_id.screen_name
        u = self.create(data)
        status = self.status_from_user(user, u)
        if status:
            u.last_status_date = status.created_at
        return u

    @api.multi
    def update_from_user(self, user):
        self.ensure_one()
        data = self.mapping_from_user(user)
        status = self.status_from_user(user, self)
        if status:
            data['last_status_date'] = status.created_at
        data = self.changed_fields_filter(data)
        data['last_update'] = fields.Datetime.now()
        ta = self.env.context.get('twitter_account')
        if not self.discovered_by and ta:
            data['discovered_by'] = ta.user_id.screen_name
        return self.write(data)

    @api.multi
    def changed_fields_filter(self, data):
        self.ensure_one()
        common = {
            'twitter_id',
            'name',
            'screen_name',
            'description',
            'lang',
            'location',
            'favourites_count',
            'followers_count',
            'friends_count',
            'statuses_count',
            'listed_count',
            'protected',
            'verified',
            'created_at',
            'last_status_date',
        }
        res = {k: data[k] for k in common if k in data and self[k] != data[k]}
        return res

    @api.model
    def cron_sync_profiles(self):
        accounts = self.env['twitter.account'].all_twitter_accounts()
        cfg = self.env['ir.config_parameter'].sudo()
        max_profiles_limit = int(cfg.get_param(
            'twitter.cron_sync_profiles_limit', DEFAULT_CRON_SYNC_PROFILES_LIMIT))
        profiles_limit = len(accounts) > 0 and max_profiles_limit / len(accounts) or 0
        for a in accounts:
            cases = [
                ([
                    ('screen_name', '=', False),
                    ('twitter_error', '=', False),
                    ('discovered_by', '=', a.user_id.screen_name)], 'create_date ASC', 'fake users'),
                ([
                    ('screen_name', '!=', False),
                    ('twitter_error', '=', False),
                    ('last_update', '=', False),
                    ('discovered_by', '=', a.user_id.screen_name)], 'create_date ASC', 'pending users'),
                ([
                    ('screen_name', '!=', False),
                    ('twitter_error', '=', False),
                    ('last_status_date', '=', False),
                    ('discovered_by', '=', a.user_id.screen_name)], 'create_date DESC', 'no status users'),
            ]
            remaining = profiles_limit
            for domain, order, t in cases:
                users = self.search(domain, limit=remaining, order=order)
                _logger.info("cron_sync_profiles: %s %s", len(users), t)
                users.sync_profile()
                remaining -= len(users)
                if not remaining > 0:
                    break

    @api.multi
    def action_follow(self):
        # TODO: Get account from user preferences
        pass
