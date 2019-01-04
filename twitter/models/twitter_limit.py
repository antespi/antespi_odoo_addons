# -*- coding: utf-8 -*-

from odoo import fields, models


class TwitterLimit(models.Model):
    _description = 'Twitter limit'
    _name = 'twitter.limit'
    _rec_name = 'name'

    name = fields.Char(string="Name", readonly=True)
    manual = fields.Boolean(string="Manual")
    resource = fields.Char(string="Resource", readonly=True)
    endpoint = fields.Char(string="Endpoint", readonly=True)
    limit = fields.Integer(string="Limit")
    minutes = fields.Integer(string="Minutes")
