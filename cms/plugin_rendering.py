# -*- coding: utf-8 -*-
from cms.models.placeholdermodel import Placeholder
from cms.plugin_processors import (plugin_meta_context_processor, mark_safe_plugin_processor)
from cms.utils import get_language_from_request
from cms.utils.compat.type_checks import string_types
from cms.utils.conf import get_cms_setting
from cms.utils.django_load import iterload_objects
from cms.utils.placeholder import get_placeholder_conf
from cms.utils.i18n import get_fallback_languages, get_default_language
from django.template import Template, Context
from django.template.defaultfilters import title
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _
from cms.utils.placeholder import get_toolbar_plugin_struct

# these are always called before all other plugin context processors
DEFAULT_PLUGIN_CONTEXT_PROCESSORS = (
    plugin_meta_context_processor,
)

# these are always called after all other plugin processors
DEFAULT_PLUGIN_PROCESSORS = (
    mark_safe_plugin_processor,
)


class PluginContext(Context):
    """
    This subclass of template.Context automatically populates itself using
    the processors defined in CMS_PLUGIN_CONTEXT_PROCESSORS.
    Additional processors can be specified as a list of callables
    using the "processors" keyword argument.
    """

    def __init__(self, dict, instance, placeholder, processors=None, current_app=None):
        super(PluginContext, self).__init__(dict, current_app=current_app)
        if not processors:
            processors = []
        for processor in DEFAULT_PLUGIN_CONTEXT_PROCESSORS:
            self.update(processor(instance, placeholder, self))
        for processor in iterload_objects(get_cms_setting('PLUGIN_CONTEXT_PROCESSORS')):
            self.update(processor(instance, placeholder, self))
        for processor in processors:
            self.update(processor(instance, placeholder, self))


def render_plugin(context, instance, placeholder, template, processors=None, current_app=None):
    """
    Renders a single plugin and applies the post processors to it's rendered
    content.
    """
    if not processors:
        processors = []
    if isinstance(template, string_types):
        content = render_to_string(template, context_instance=context)
    elif isinstance(template, Template):
        content = template.render(context)
    else:
        content = ''
    for processor in iterload_objects(get_cms_setting('PLUGIN_PROCESSORS')):
        content = processor(instance, placeholder, content, context)
    for processor in processors:
        content = processor(instance, placeholder, content, context)
    for processor in DEFAULT_PLUGIN_PROCESSORS:
        content = processor(instance, placeholder, content, context)
    return content


def render_plugins(plugins, context, placeholder, processors=None):
    """
    Renders a collection of plugins with the given context, using the appropriate processors
    for a given placeholder name, and returns a list containing a "rendered content" string
    for each plugin.

    This is the main plugin rendering utility function, use this function rather than
    Plugin.render_plugin().
    """
    out = []
    total = len(plugins)
    for index, plugin in enumerate(plugins):
        plugin._render_meta.total = total
        plugin._render_meta.index = index
        context.push()
        out.append(plugin.render_plugin(context, placeholder, processors=processors))
        context.pop()
    return out


def render_dragables(plugins, slot, request):
    return render_to_string("cms/toolbar/draggable.html", {'plugins': plugins, 'slot': slot, 'request': request})


def render_placeholder(placeholder, context_to_copy, name_fallback="Placeholder", lang=None):
    """
    Renders plugins for a placeholder on the given page using shallow copies of the
    given context, and returns a string containing the rendered output.
    """
    from cms.plugins.utils import get_plugins

    context = context_to_copy
    context.push()
    request = context['request']
    page = placeholder.page if placeholder else None
    if page:
        template = page.template
    else:
        template = None
    # It's kind of duplicate of the similar call in `get_plugins`, but it's required
    # to have a valid language in this function for `get_fallback_languages` to work
    if not lang:
        lang = get_language_from_request(request)
    plugins = [plugin for plugin in get_plugins(request, placeholder, lang=lang)]
    # If no plugin is present in the current placeholder we loop in the fallback languages
    # and get the first available set of plugins
    if (len(plugins) == 0 and placeholder and
            get_placeholder_conf("language_fallback", placeholder.slot, template, False)):
        fallbacks = get_fallback_languages(lang)
        for fallback_language in fallbacks:
            plugins = [plugin for plugin in get_plugins(request, placeholder, fallback_language)]
            if plugins:
                break
    # Add extra context as defined in settings, but do not overwrite existing context variables,
    # since settings are general and database/template are specific
    # TODO this should actually happen as a plugin context processor, but these currently overwrite
    # existing context -- maybe change this order?
    slot = getattr(placeholder, 'slot', None)
    extra_context = {}
    if slot:
        extra_context = get_placeholder_conf("extra_context", slot, template, {})
    for key, value in extra_context.items():
        if not key in context:
            context[key] = value

    content = []

    # Prepend frontedit toolbar output if applicable
    edit = False
    toolbar = getattr(request, 'toolbar', None)

    if (getattr(toolbar, 'edit_mode', False) and
        (not page or page.has_change_permission(request))):
        edit = True
    if edit:
        from cms.middleware.toolbar import toolbar_plugin_processor

        processors = (toolbar_plugin_processor,)
    else:
        processors = None

    content.extend(render_plugins(plugins, context, placeholder, processors))
    toolbar_content = ''
    draggable_content = ''
    if edit:
        toolbar_content = mark_safe(render_placeholder_toolbar(placeholder, context, '', name_fallback=name_fallback))
        draggable_content = mark_safe(render_dragables(plugins, slot, request))
    content = mark_safe("".join(content))

    result = render_to_string("cms/toolbar/placeholder.html",
                              {'plugins': content, "bar": toolbar_content, "draggables": draggable_content,
                              'edit': edit})
    context.pop()
    return result


def render_placeholder_toolbar(placeholder, context, content, name_fallback=None):
    from cms.plugin_pool import plugin_pool

    request = context['request']
    page = placeholder.page if placeholder else None
    if not page:
        page = getattr(request, 'current_page', None)
    if page:
        template = page.template
        if name_fallback and not placeholder:
            placeholder = Placeholder.objects.create(slot=name_fallback)
            page.placeholders.add(placeholder)
            placeholder.page = page
    else:
        template = None
    if placeholder:
        slot = placeholder.slot
    else:
        slot = None
    # Builds the list of dictionaries containing module, name and value for the plugin dropdowns
    installed_plugins = get_toolbar_plugin_struct(plugin_pool.get_all_plugins(slot, page), slot, page)

    name = get_placeholder_conf("name", slot, template, title(slot))
    name = _(name)
    context.push()
    context['installed_plugins'] = installed_plugins
    ## to restrict child-only plugins from draggables..
    context['allowed_plugins'] = [cls.__name__ for cls in plugin_pool.get_all_plugins(slot, page)]
    context['language'] = get_language_from_request(request)
    context['placeholder_label'] = name
    context['placeholder'] = placeholder
    context['page'] = page
    toolbar = render_to_string("cms/toolbar/placeholder_bar.html", context)
    context.pop()
    return toolbar
