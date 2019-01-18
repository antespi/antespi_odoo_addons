# -*- coding: utf-8 -*-

import re
import tweepy
import logging
from odoo import api, fields, models
from .common import crop_text, batch_split

_logger = logging.getLogger(__name__)

# MEDIUM_TEXT_MAX_LENGTH = 80
SHORT_TEXT_MAX_LENGTH = 50
DISPLAY_NAME_MAX_LENGTH = 40
DEFAULT_CRON_SYNC_STATUSES_LIMIT = 50


class TwitterStatus(models.Model):
    _description = 'Twitter status'
    _name = 'twitter.status'

    twitter_id = fields.Char(string="Twitter ID", readonly=True, index=True)
    twitter_url = fields.Char(string="Twitter URL", compute='_compute_url')
    display_name = fields.Char(compute='_compute_display_name', store=True, index=True)

    author_id = fields.Many2one(
        string="Author", comodel_name='twitter.user', readonly=True, index=True, ondelete='cascade')
    created_at = fields.Datetime(string="Created at", readonly=True)
    full_text = fields.Text(string="Full text", readonly=True)
    # medium_text = fields.Char(string="Medium text", compute='_compute_text', store=True, readonly=True)
    short_text = fields.Char(string="Short text", compute='_compute_text', store=True, readonly=True)
    source = fields.Char(string="Source", readonly=True)
    lang = fields.Char(string="Language", readonly=True)
    place = fields.Char(string="Place", readonly=True)
    truncated = fields.Boolean(string="Truncated", readonly=True)

    twitter_error = fields.Text(string="Error", readonly=True)

    # hashtag_ids = fields.Many2many(string="Hashtags", ..., readonly=True)
    # mention_ids = fields.Many2many(string="Mentions", ..., readonly=True)
    # url_ids = fields.Many2many(string="URLs", ..., readonly=True)

    retweet_count = fields.Integer(string="# Retweets", readonly=True)
    favorite_count = fields.Integer(string="# Favorites", readonly=True)

    quoted_status_id = fields.Many2one(
        string="Quote", comodel_name='twitter.status', readonly=True)
    retweeted_status_id = fields.Many2one(
        string="Retweet", comodel_name='twitter.status', readonly=True)
    in_reply_to_status_id = fields.Many2one(
        string="In reply", comodel_name='twitter.status', readonly=True)
    in_reply_to_user_id = fields.Many2one(
        string="In reply to", comodel_name='twitter.user', readonly=True)
    last_update = fields.Datetime(string="Last update", readonly=True)

    _sql_constraints = [
        ('twitter_id_uniq', 'unique(twitter_id)', "[SQL Constraint] Twitter ID must be unique!"),
    ]

    @api.depends('twitter_id', 'author_id.screen_name')
    def _compute_url(self):
        for s in self:
            if s.author_id.screen_name and s.twitter_id:
                s.twitter_url = (
                    "https://www.twitter.com/%s/status/%s" % (s.author_id.screen_name, s.twitter_id))
            else:
                s.twitter_url = False

    @api.depends('full_text')
    def _compute_text(self):
        for s in self:
            s.short_text = crop_text(s.full_text, SHORT_TEXT_MAX_LENGTH)
            # s.medium_text = crop_text(s.full_text, MEDIUM_TEXT_MAX_LENGTH)

    @api.depends('twitter_id', 'author_id.screen_name', 'full_text')
    def _compute_display_name(self):
        for s in self:
            if s.author_id:
                display_name = "@%s: %s" % (s.author_id.screen_name, s.short_text)
                s.display_name = crop_text(display_name, DISPLAY_NAME_MAX_LENGTH)
            else:
                s.display_name = "Fake %s" % (s.twitter_id, )

    @api.multi
    def _sync_status_statuses_lookup(self):
        ta = self.env['twitter.account'].selected_twitter_account()
        batches = batch_split(self, chunk_size=100)
        for b in batches:
            try:
                statuses = ta.tapi_statuses_lookup(b.mapped('twitter_id'))
                for status in statuses:
                    _logger.info("statuses_lookup: %s", status.id_str)
                    self.with_context(twitter_account=ta).create_or_update_from_status(status)
            except tweepy.error.TweepError as e:
                _logger.info("Twitter error: %s", e)
                b.write({'twitter_error': str(e)})

    @api.multi
    def _sync_status_get_status(self):
        ta = self.env['twitter.account'].selected_twitter_account()
        for s in self:
            try:
                _logger.info("get_status: %s", s.twitter_id)
                status = ta.tapi_get_status(s.twitter_id)
                s.with_context(twitter_account=ta).update_from_status(status)
            except tweepy.error.TweepError as e:
                _logger.info("Twitter error: %s", e)
                s.twitter_error = str(e)

    @api.multi
    def sync_status(self):
        if len(self) > 10:
            return self._sync_status_statuses_lookup()
        return self._sync_status_get_status()

    @api.model
    def text_from_status(self, status):
        full_text = False
        if hasattr(status, 'text'):
            full_text = status.text
        if hasattr(status, 'full_text'):
            full_text = status.full_text
        if hasattr(status, 'retweeted_status'):
            retweet = self.text_from_status(status.retweeted_status)
            author = '?'
            if hasattr(status.retweeted_status, 'author'):
                author = status.retweeted_status.author.screen_name
            elif hasattr(status.retweeted_status, 'user'):
                author = status.retweeted_status.user.screen_name
            else:
                match = re.match(r'RT @([^:]+):', full_text)
                if match:
                    author = match.group(1)
            full_text = "RT @%s: %s" % (author, retweet)
        return full_text

    @api.model
    def author_from_status(self, status):
        if hasattr(status, 'author'):
            return self.env['twitter.user'].create_or_update_from_user(status.author)
        if hasattr(status, 'user'):
            return self.env['twitter.user'].create_or_update_from_user(status.user)
        if self.env.context.get('status_author'):
            return self.env.context.get('status_author')
        return False

    @api.model
    def retweet_from_status(self, status):
        if not hasattr(status, 'retweeted_status'):
            return False
        return self.with_context(
            status_author=False).create_or_update_from_status(status.retweeted_status)

    @api.model
    def quote_from_status(self, status):
        if not hasattr(status, 'quoted_status'):
            return False
        return self.with_context(
            status_author=False).create_or_update_from_status(status.quoted_status)

    @api.model
    def replied_status_from_status(self, status):
        if not hasattr(status, 'in_reply_to_status_id_str'):
            return False
        status_id = status.in_reply_to_status_id_str
        if not status_id:
            return False
        return self.search_or_create_fake_status_id(status_id)

    @api.model
    def replied_user_from_status(self, status, discovered_by=False):
        if not hasattr(status, 'in_reply_to_user_id_str'):
            return False
        user_id = status.in_reply_to_user_id_str
        if not user_id:
            return False
        return self.env['twitter.user'].search_or_create_fake_user_id(
            user_id, discovered_by=discovered_by)

    @api.model
    def mapping_from_status(self, status):
        data = {
            'twitter_id': status.id_str,
            'created_at': status.created_at,
            'full_text': self.text_from_status(status),
            'source': status.source,
            'lang': status.lang,
            'place': status.place and status.place or False,
            'retweet_count': status.retweet_count,
            'favorite_count': status.favorite_count,
            'truncated': status.truncated,
        }

        author = self.author_from_status(status)
        if author:
            data['author_id'] = author.id
        retweet = self.retweet_from_status(status)
        if retweet:
            data['retweeted_status_id'] = retweet.id
        quote = self.quote_from_status(status)
        if quote:
            data['quoted_status_id'] = quote.id
        replied_status = self.replied_status_from_status(status)
        if replied_status:
            data['in_reply_to_status_id'] = replied_status.id
        ta = self.env.context.get('twitter_account')
        discovered_by = ta and ta.user_id.screen_name or False
        replied_user = self.replied_user_from_status(status, discovered_by=discovered_by)
        if replied_user:
            data['in_reply_to_user_id'] = replied_user.id
        return data

    @api.multi
    def changed_fields_filter(self, data):
        self.ensure_one()
        res = {}
        if self.author_id and self.last_update:
            common = [
                'retweet_count',
                'favorite_count',
                'truncated',
            ]
            if self.truncated:
                common.append('full_text')
            res = {k: data[k] for k in common if k in data and self[k] != data[k]}
        else:
            res = data
        return res

    @api.model
    def create_fake_prepare(self, status_id):
        return {
            'twitter_id': status_id,
        }

    @api.model
    def search_or_create_fake_status_id(self, status_id):
        if not status_id:
            return self.browse()
        status = self.search_from_status_id(status_id)
        if not status:
            data = self.create_fake_prepare(status_id)
            status = self.create(data)
        return status

    @api.model
    def search_from_status_id(self, status_id):
        return self.search([('twitter_id', '=', status_id)])

    @api.model
    def search_from_status(self, status):
        status_id = status.id_str
        return self.search_from_status_id(status_id)

    @api.model
    def create_from_status(self, status):
        data = self.mapping_from_status(status)
        data['last_update'] = fields.Datetime.now()
        return self.create(data)

    @api.multi
    def update_from_status(self, status):
        self.ensure_one()
        data = self.mapping_from_status(status)
        data = self.changed_fields_filter(data)
        data['last_update'] = fields.Datetime.now()
        return self.write(data)

    @api.model
    def create_or_update_from_status(self, status):
        s = self.search_from_status(status)
        if s:
            s.update_from_status(status)
        else:
            s = self.create_from_status(status)
        return s

    @api.model
    def cron_sync_statuses(self):
        accounts = self.env['twitter.account'].all_twitter_accounts()
        cfg = self.env['ir.config_parameter'].sudo()
        max_statuses_limit = int(cfg.get_param(
            'twitter.cron_sync_statuses_limit', DEFAULT_CRON_SYNC_STATUSES_LIMIT))
        statuses_limit = len(accounts) > 0 and max_statuses_limit / len(accounts) or 0
        for a in accounts:
            cases = [
                ([
                    ('author_id', '=', False),
                    ('twitter_error', '=', False)], 'create_date ASC', 'fake tweets'),
                ([
                    ('author_id', '!=', False),
                    ('twitter_error', '=', False),
                    ('last_update', '=', False)], 'create_date ASC', 'pending tweets'),
                ([
                    ('author_id', '!=', False),
                    ('twitter_error', '=', False),
                    ('truncated', '=', True)], 'create_date ASC', 'truncated tweets'),
            ]
            remaining = statuses_limit
            for domain, order, t in cases:
                statuses = self.search(domain, limit=remaining, order=order)
                _logger.info("cron_sync_statuses: %s %s", len(statuses), t)
                statuses.sync_status()
                remaining -= len(statuses)
                if not remaining > 0:
                    break
