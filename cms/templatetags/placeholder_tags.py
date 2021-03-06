# -*- coding: utf-8 -*-
from classytags.arguments import Argument
from classytags.core import Tag, Options
from django import template

register = template.Library()


class RenderPlaceholder(Tag):
    name = 'render_placeholder'
    options = Options(
        Argument('placeholder'),
        Argument('width', default=None, required=False),
        'language',
        Argument('language', default=None, required=False),
    )

    def render_tag(self, context, placeholder, width, language=None):
        raise DeprecationWarning('render_placeholder is now located in cms_tags. Please do not load placeholder_tags anymore')
register.tag(RenderPlaceholder)
