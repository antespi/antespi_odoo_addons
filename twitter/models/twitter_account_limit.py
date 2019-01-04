# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from odoo import api, fields, models


class TwitterAccountLimit(models.Model):
    _description = 'Twitter account limit'
    _name = 'twitter.account.limit'
    _rec_name = 'name'

    account_id = fields.Many2one(
        string="Twitter account", comodel_name='twitter.account', readonly=True, index=True, ondelete='cascade')
    limit_id = fields.Many2one(
        string="Twitter limit", comodel_name='twitter.limit', readonly=True, index=True, ondelete='cascade')
    name = fields.Char(string="Name", related='limit_id.name', store=True, readonly=True)
    manual = fields.Boolean(string="Manual", related='limit_id.manual', store=True, readonly=True)
    minutes = fields.Integer(string="Minutes", related='limit_id.minutes', store=True, readonly=True)

    limit = fields.Integer(string="Limit", readonly=True)
    remaining = fields.Integer(string="Remaining", readonly=True)
    reset = fields.Datetime(string="Reset", readonly=True)
    ratio = fields.Float(string="Ratio", compute='_compute_ratio', store=True, readonly=True)

    @api.depends('remaining', 'limit_id.limit')
    def _compute_ratio(self):
        for l in self:
            l.ratio = 100 * (l.limit > 0 and (l.remaining / l.limit) or 0.)

    @api.multi
    def update_from_limits(self, limits):
        resources = limits.get('resources', {}) or {}
        for al in self:
            resource = resources.get(al.limit_id.resource, {}) or {}
            endpoint = resource.get(al.limit_id.endpoint, {}) or {}
            if endpoint:
                reset = endpoint.get('reset', False) or False
                # safe_write?
                al.write({
                    'limit': endpoint.get('limit', 0) or 0,
                    'remaining': endpoint.get('remaining', 0) or 0,
                    'reset': reset and datetime.fromtimestamp(reset) or False,
                })

    @api.multi
    def reset_manual(self):
        for al in self:
            if not al.manual:
                continue
            now = fields.Datetime.now()
            if (not al.reset) or (now > al.reset) or (al.remaining == al.limit):
                # safe_write
                al.write({
                    'reset': now + timedelta(minutes=al.minutes),
                    'remaining': al.limit,
                })

    @api.model
    def search_limit(self, account_id, limit):
        return self.env['twitter.account.limit'].search([
            ('account_id', '=', account_id.id),
            ('name', '=', limit)
        ], limit=1)

    @api.multi
    def update_from_method(self, method):
        self.ensure_one()
        data = {}
        if method._remaining_calls:
            data['remaining'] = method._remaining_calls
        if method._reset_time:
            data['reset'] = datetime.fromtimestamp(method._reset_time)
        if data:
            # safe_write
            self.write(data)
