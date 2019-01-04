# -*- coding: utf-8 -*-

import tweepy
from odoo import http
from odoo.http import request, Response
import logging
_logger = logging.getLogger(__name__)


class oauth(http.Controller):

    @http.route('/twitter/oauth/callback', auth='public', type='http', csrf=False)
    def oauth_callback(self, **args):
        env = request.env
        _logger.info("request: %s", dir(request))
        _logger.info("args: %s", args)
        oauth_token = args.get('oauth_token')
        oauth_verifier = args.get('oauth_verifier')
        if not oauth_token:
            return "OAuth token not found in callback URL"
        if not oauth_verifier:
            return "OAuth verifier not found in callback URL"
        twitter_account = env['twitter.account'].search([
            ('oauth_token', '=', oauth_token)
        ])
        if not twitter_account:
            return "Twitter account not found for this OAuth token"
        auth = tweepy.OAuthHandler(
            twitter_account.twitter_app_id.consumer_token,
            twitter_account.twitter_app_id.consumer_secret,
            twitter_account.oauth_callback())
        auth.request_token = {
            'oauth_token': twitter_account.oauth_token,
            'oauth_token_secret': twitter_account.oauth_secret,
        }
        access_token, access_secret = auth.get_access_token(oauth_verifier)
        api = tweepy.API(auth)
        user = api.me()
        twitter_user = env['twitter.user'].create_or_update_from_user(user)
        twitter_user.write({
            'discovered_by': twitter_user.screen_name,
        })
        twitter_account.write({
            'user_id': twitter_user.id,
            'access_token': access_token,
            'access_secret': access_secret,
        })
        redirect_url = '/web#id=%s&model=twitter.account&view_type=form' % twitter_account.id
        response = Response(
            'Twitter User linked to Twitter account successfully. '
            '<a href="%s">Return to Twitter account</a>' % redirect_url,
            headers={'Location': redirect_url}, status=301)
        return response
