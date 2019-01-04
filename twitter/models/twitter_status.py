# -*- coding: utf-8 -*-

from odoo import api, fields, models


class TwitterStatus(models.Model):
    _description = 'Twitter status'
    _name = 'twitter.status'

    twitter_id = fields.Char(string="Twitter ID", readonly=True)
    display_name = fields.Char(compute='_compute_display_name', store=True, index=True)

    author_id = fields.Many2one(
        string="Author", comodel_name='twitter.user', readonly=True)
    created_at = fields.Date(string="Created at", readonly=True)
    full_text = fields.Text(string="Full text", readonly=True)
    source = fields.Char(string="Source", readonly=True)
    lang = fields.Char(string="Language", readonly=True)
    place = fields.Char(string="Place", readonly=True)

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

    _sql_constraints = [
        ('twitter_id_uniq', 'unique(twitter_id)', "[SQL Constraint] Twitter ID must be unique!"),
    ]

    @api.depends('author_id.screen_name', 'full_text')
    def _compute_display_name(self):
        for s in self:
            s.display_name = "@%s: %s" % (s.author_id.screen_name, s.full_text)

    @api.model
    def mapping_from_status(self, status):
        pass

    @api.model
    def create_from_status(self, status):
        pass

    @api.multi
    def update_from_status(self, status):
        self.ensure_one()
        pass

    @api.model
    def create_or_update_from_status(self, status):
        pass
