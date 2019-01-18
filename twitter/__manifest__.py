# -*- coding: utf-8 -*-

{
    'name': 'Twitter',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Twitter accounts management',
    'description': "",
    'website': 'https://twitter.com/antespi',
    'depends': [
        'base',
    ],
    'data': [
        'security/res_groups.xml',
        'security/ir.model.access.csv',

        'views/menus.xml',
        'views/twitter_account_views.xml',
        'views/twitter_app_views.xml',
        'views/twitter_limit_views.xml',
        'views/twitter_user_views.xml',
        'views/twitter_friendship_views.xml',
        'views/twitter_status_views.xml',
        'views/res_users_views.xml',

        'data/ir_cron.xml',
        'data/ir_config_parameter.xml',
        'data/twitter_limit.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
