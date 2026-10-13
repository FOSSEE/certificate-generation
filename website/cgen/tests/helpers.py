import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from cgen.models import Certificate, Event


class CgenTestCase(TestCase):
    """Gives each test its own media folder and an organiser with one event."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(
            MEDIA_ROOT=self.media,
            CERTIFICATES_PATH=f'{self.media}/certificates')
        override.enable()
        self.addCleanup(override.disable)

        self.organiser = User.objects.create_user('org', password='pw')
        self.client.force_login(self.organiser)
        now = timezone.now()
        self.event = Event.objects.create(
            name='Workshop', description='A workshop', start_date=now,
            end_date=now, creator=self.organiser)

    def make_certificate(self, template, template_type='svg'):
        certificate = Certificate(
            event=self.event, description='Participation',
            template_type=template_type)
        certificate.template.save(f'template.{template_type}',
                                  ContentFile(template.encode()), save=False)
        certificate.save()
        return certificate
