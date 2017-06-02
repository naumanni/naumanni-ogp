# -*- coding: utf-8 -*-
from naumanni.plugin import Plugin


class OGPPlugin(Plugin):
    def on_filter_accounts(self, objects, entities):
        print('OGPPlugin:on_filter_accounts', objects)
        return objects

    def on_filter_statuses(self, objects, entities):
        print('OGPPlugin:on_filter_statuses', objects)
        return objects
