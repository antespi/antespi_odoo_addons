# -*- coding: utf-8 -*-

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    twitter_account_id = fields.Many2one(
        string="Twitter Account", comodel_name='twitter.account')
