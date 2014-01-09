import uuid
from cms.utils.compat.dj import python_2_unicode_compatible
from cms.utils.copy_plugins import copy_plugins_to

from django.db import models
from django.utils.translation import ugettext_lazy as _

from cms.models.fields import PlaceholderField
from cms.models.pluginmodel import CMSPlugin



def stack_slotname(instance):
    """
    Returns a string to be used as the slot
    for the stack's content placeholder field.
    """
    return instance.code


@python_2_unicode_compatible
class Stack(models.Model):
    CREATION_BY_TEMPLATE = 'template'
    CREATION_BY_CODE = 'code'
    CREATION_METHODS = (
        (CREATION_BY_TEMPLATE, _('by template')),
        (CREATION_BY_TEMPLATE, _('by code')),
    )
    name = models.CharField(
        verbose_name=_(u'stack name'), max_length=255, blank=True, default='',
        help_text=_(u'Descriptive name to identify this stack. Not displayed to users.'))
    code = models.CharField(
        verbose_name=_(u'stack code'), max_length=255, unique=True, blank=True,
        help_text=_(u'To render the stack in templates.'))
    draft = PlaceholderField(stack_slotname, verbose_name=_(u'stack content'), related_name='stacks_draft')
    public = PlaceholderField(stack_slotname, editable=False, related_name='stacks_public')
    dirty = models.BooleanField(default=False, editable=False)
    creation_method = models.CharField(
        verbose_name=_('creation_method'), choices=CREATION_METHODS,
        default=CREATION_BY_CODE, max_length=20, blank=True,
    )

    class Meta:
        verbose_name = _(u'stack')
        verbose_name_plural = _(u'stacks')

    def __str__(self):
        return self.name

    def clean(self):
        # TODO: check for clashes if the random code is already taken
        if not self.code:
            self.code = u'stack-%s' % uuid.uuid4()

    def publish(self, request, force=False):
        if force or self.has_publish_permission(request):
            CMSPlugin.objects.filter(placeholder=self.public).delete()
            plugins = self.draft.get_plugins_list()
            copy_plugins_to(plugins, self.public)
            self.dirty = False
            self.save()
            return True
        return False

    def has_change_permission(self, request):
        if request.user.is_superuser:
            return True
        opts = self._meta
        return request.user.has_perm(opts.app_label + '.' + "change")

    def has_publish_permission(self, request):
        if request.user.is_superuser:
            return True
        opts = self._meta
        return request.user.has_perm(opts.app_label + '.' + "change") and \
               self.has_generic_permission(request, "publish")


@python_2_unicode_compatible
class StackLink(CMSPlugin):
    stack = models.ForeignKey(Stack, verbose_name=_(u'stack'), related_name='linked_plugins')

    def __str__(self):
        return self.stack.name
