import hashlib
import io
import shutil
import zipfile
from unittest import mock, skipUnless

from django.urls import reverse

from cgen import generator
from cgen.models import CertificateManager, Participant
from cgen.tests import templates
from cgen.tests.helpers import CgenTestCase
from cgen.tests.test_parallel_generation import qr_matches

tools = all(shutil.which(t) for t in ('rsvg-convert', 'pdfimages'))


def verify_url(key):
    return f'https://example.com/certificate/verify/{key}/'


class SerialKeyTests(CgenTestCase):

    def setUp(self):
        super().setUp()
        self.certificate = self.make_certificate(templates.SVG)

    def add(self, email, name):
        return Participant.objects.create(certificate=self.certificate,
                                          email=email, details={'name': name})

    def key_for(self, participant):
        return generator._certificate_manager(participant).serial_key_short

    def test_first_key_for_an_email_is_unchanged_from_before(self):
        old_formula = hashlib.sha1(
            f'a@x.com{self.certificate.id}'.encode()).hexdigest()[:4]
        self.assertEqual(self.key_for(self.add('a@x.com', 'A')), old_formula)

    def test_same_email_gets_different_keys(self):
        first, second = self.add('a@x.com', 'A'), self.add('a@x.com', 'B')
        self.assertNotEqual(self.key_for(first), self.key_for(second))

    def test_key_never_changes_once_issued(self):
        participant = self.add('a@x.com', 'A')
        CertificateManager.objects.create(participant=participant,
                                          serial_key_long='old',
                                          serial_key_short='old1')
        self.assertEqual(self.key_for(participant), 'old1')
        participant.email = 'changed@x.com'
        participant.save()
        self.assertEqual(self.key_for(participant), 'old1')

    def test_edit_keeps_serial_key(self):
        participant = self.add('a@x.com', 'A')
        key = self.key_for(participant)
        self.client.post(reverse('edit_participant', args=[participant.id]),
                         {'email': 'a@x.com', 'details': '{"name": "Fixed"}'})
        self.assertEqual(self.key_for(participant), key)
        self.assertEqual(CertificateManager.objects.count(), 1)


@skipUnless(tools, 'rsvg-convert and pdfimages needed')
class DownloadTests(CgenTestCase):

    def setUp(self):
        super().setUp()
        self.certificate = self.make_certificate(templates.SVG)
        for email, name in [('a@x.com', 'Ram'), ('a@x.com', 'Ram'),
                            ('b@x.com', 'Sita')]:
            Participant.objects.create(certificate=self.certificate, email=email,
                                       details={'name': name, 'institute': 'I'})
        self.url = reverse('certificate_download', args=[self.certificate.id])

    def keys(self, email):
        return [generator._certificate_manager(p).serial_key_short
                for p in Participant.objects.filter(email=email).order_by('id')]

    def test_single_certificate_is_a_pdf(self):
        response = self.client.post(self.url, {'email': 'B@X.com '})
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_several_certificates_come_as_a_zip(self):
        response = self.client.post(self.url, {'email': 'a@x.com'})
        self.assertEqual(response['Content-Type'], 'application/zip')
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        self.assertEqual(archive.namelist(), ['ram.pdf', 'ram-2.pdf'])

        keys = self.keys('a@x.com')
        for name, key in zip(archive.namelist(), keys):
            path = self.media + '/x.pdf'
            with open(path, 'wb') as f:
                f.write(archive.read(name))
            self.assertTrue(qr_matches(path, verify_url(key)), name)

    def test_unknown_email(self):
        response = self.client.post(self.url, {'email': 'nobody@x.com'})
        self.assertEqual(response.context['notregistered'], 1)

    def test_failed_generation_shows_message(self):
        with mock.patch.object(generator, 'generate', return_value=(None, False)):
            response = self.client.post(self.url, {'email': 'a@x.com'})
        self.assertContains(response, 'could not be created')

    def test_bulk_zip_names(self):
        response = self.client.get(
            reverse('bulk_download_certificates', args=[self.certificate.id]))
        names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
        self.assertEqual(names, ['a@x.com-1.pdf', 'a@x.com-2.pdf', 'b@x.com.pdf'])

    def test_test_generation_by_participant(self):
        second = Participant.objects.filter(email='a@x.com').order_by('id')[1]
        response = self.client.post(
            reverse('test_certificate_generation', args=[self.certificate.id]),
            {'participant': second.id})
        self.assertEqual(response['Content-Type'], 'application/pdf')
        path = self.media + '/t.pdf'
        with open(path, 'wb') as f:
            f.write(response.content)
        self.assertTrue(qr_matches(path, verify_url(self.keys('a@x.com')[1])))

    def test_organiser_list_has_one_row_per_email(self):
        response = self.client.get(
            reverse('certificate_download_all', args=[self.certificate.id]))
        self.assertEqual([e for e, _ in response.context['details']],
                         ['a@x.com', 'b@x.com'])
