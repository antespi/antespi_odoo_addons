# -*- coding: utf-8 -*-

from odoo import fields, models


class TwitterApp(models.Model):
    _description = 'Twitter app'
    _name = 'twitter.app'
    _rec_name = 'name'

    name = fields.Char(string="Name", required=True)
    consumer_token = fields.Char(string="Consumer token", required=True)
    consumer_secret = fields.Char(string="Consumer secret", required=True)
